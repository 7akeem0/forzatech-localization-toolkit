"""
Build a ForzaTech-compatible .vfont + .vfont0 from a TrueType font.

Pipeline per glyph:
    1. Load outline from TTF via freetype-py (no scaling, font units).
    2. Decompose contours, subdividing each quadratic Bezier into N
       line segments (default 8).
    3. Classify contours topologically: even nesting depth = polygon,
       odd depth = hole. Group each outer with its direct child holes.
       This is required for scripts with diacritical marks above/below
       a base (Arabic dots, Thai tone marks, accented Latin) and for
       any glyph with internal holes (O, A, D, ...).
    4. Tessellate each (outer + holes) group separately with earcut.
    5. Shift all vertices +UPM*0.6 funits along X to match the engine's
       Latin-style LSB assumption. See docs/latin_lsb_convention.md.
    6. For connecting scripts (e.g. Arabic Presentation Forms B):
       optionally append baseline-extension rectangles to bridge between
       glyphs. See `extend_for_joining`.
    7. Normalize to em units (divide by UPM), pack as float16 XYUV.
       V is always 1.0 (solid fill marker).
    8. Emit u16 triangle index list.
    9. Write a 36-byte record into the .vfont, append the blob to
       .vfont0, sort records by codepoint with U+FFFD last.

Usage:
    python build_font_from_ttf.py source.ttf out.vfont out.vfont0 \
        --base Horizon_A.vfont --base0 Horizon_A.vfont0 \
        --range 0x0E00 0x0E7F          # Thai
        --range 0xFE70 0xFEFF          # Arabic PFB-B
        --range 0x0400 0x04FF          # Cyrillic
"""

from __future__ import annotations
import argparse
import struct
import sys
import unicodedata
from pathlib import Path

import freetype
import mapbox_earcut as earcut
import numpy as np

# We import sibling modules. Add tools/ to sys.path when run as a script.
sys.path.insert(0, str(Path(__file__).parent))
from vfont_codec import (  # noqa: E402
    GlyphBlob, GlyphRecord, VFont, VFont0,
    parse_vfont, parse_vfont0, build_vfont, build_vfont0,
)


SEG_PER_CURVE = 8                # Bezier subdivisions
SHIFT_FU_FRACTION = 0.6          # vertex shift along X (multiplied by UPM)


# ---------- contour extraction ----------

def _quadratic_subdivide(p0, p1, p2, n=SEG_PER_CURVE):
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1.0 - t
        x = u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0]
        y = u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]
        out.append((x, y))
    return out


def _outline_to_contours(outline) -> list[list[tuple[float, float]]]:
    """Walk a FreeType outline, returning a list of closed contours
    (each is a list of (x, y) points in font units)."""
    points = [(p.x, p.y) for p in outline.points]
    tags = outline.tags
    contours_idx = outline.contours

    result: list[list[tuple[float, float]]] = []
    start = 0
    for end in contours_idx:
        pts = points[start:end + 1]
        tg = tags[start:end + 1]
        # Walk this contour, expanding off-curve points into quadratic segments.
        contour: list[tuple[float, float]] = []
        n = len(pts)
        i = 0
        # Find a starting on-curve point
        while i < n and not (tg[i] & 1):
            i += 1
        if i == n:
            # all off-curve — synthesize a starting point
            i = 0
            mid = ((pts[0][0] + pts[-1][0]) / 2, (pts[0][1] + pts[-1][1]) / 2)
            pts = [mid] + pts
            tg = [1] + list(tg)
            n += 1
        rotated_pts = pts[i:] + pts[:i]
        rotated_tg = list(tg[i:]) + list(tg[:i])
        contour.append(rotated_pts[0])
        j = 1
        while j < n:
            if rotated_tg[j] & 1:
                contour.append(rotated_pts[j])
                j += 1
            else:
                # off-curve control; consume one or more
                p0 = contour[-1]
                ctrl = rotated_pts[j]
                if j + 1 < n and (rotated_tg[j + 1] & 1):
                    p2 = rotated_pts[j + 1]
                    j += 2
                else:
                    next_ctrl = rotated_pts[(j + 1) % n]
                    p2 = ((ctrl[0] + next_ctrl[0]) / 2,
                          (ctrl[1] + next_ctrl[1]) / 2)
                    j += 1
                segs = _quadratic_subdivide(p0, ctrl, p2)
                contour.extend(segs[1:])
        result.append(contour)
        start = end + 1
    return result


# ---------- topology classification (polygon vs hole) ----------

def _point_in_polygon(pt, poly) -> bool:
    x, y = pt
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and \
           (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _centroid(poly):
    n = len(poly)
    sx = sum(p[0] for p in poly) / n
    sy = sum(p[1] for p in poly) / n
    return (sx, sy)


def _classify(contours: list[list[tuple[float, float]]]):
    """Return (groups, depths) where each group is (outer_idx, [hole_idx, ...])."""
    n = len(contours)
    cents = [_centroid(c) for c in contours]
    depths = [0] * n
    for i in range(n):
        for j in range(n):
            if i != j and _point_in_polygon(cents[i], contours[j]):
                depths[i] += 1
    groups = []
    for i in range(n):
        if depths[i] % 2 == 0:
            # outer
            holes = [j for j in range(n) if depths[j] == depths[i] + 1
                     and _point_in_polygon(cents[j], contours[i])]
            groups.append((i, holes))
    return groups


# ---------- mesh extension for connecting scripts ----------

def _extension_rects(contours, side_left: bool, side_right: bool,
                     ext_funits: float, strip_y_lo: float, strip_y_hi: float):
    """Generate baseline-strip extension rectangles for a joining glyph.
    Returns a list of extra triangles as (verts, indices) where verts is a
    list of (x, y) and indices is a flat triangle list."""
    all_pts = [p for c in contours for p in c]
    if not all_pts:
        return [], []
    xs = [p[0] for p in all_pts]
    xmin, xmax = min(xs), max(xs)
    rects = []
    if side_left:
        rects.append((xmin - ext_funits, xmin, strip_y_lo, strip_y_hi))
    if side_right:
        rects.append((xmax, xmax + ext_funits, strip_y_lo, strip_y_hi))
    verts = []
    idx = []
    for (x0, x1, y0, y1) in rects:
        i = len(verts)
        verts += [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        idx += [i, i + 1, i + 2, i, i + 2, i + 3]
    return verts, idx


def _is_joining_form(cp: int) -> tuple[bool, bool]:
    """For an Arabic Presentation Forms B codepoint, return (needs_right, needs_left).
    Returns (False, False) for non-joining scripts."""
    try:
        name = unicodedata.name(cp)
    except ValueError:
        return False, False
    # Arabic forms: 'ARABIC LETTER X INITIAL FORM' / 'MEDIAL' / 'FINAL' / 'ISOLATED'
    if 'INITIAL FORM' in name:
        return False, True   # extends left (toward following letter in visual LTR after reverse)
    if 'MEDIAL FORM' in name:
        return True, True
    if 'FINAL FORM' in name:
        return True, False
    return False, False


# ---------- per-glyph generation ----------

def _f16_bytes(value: float) -> bytes:
    return np.array([value], dtype=np.float16).tobytes()


def generate_glyph(face: freetype.Face, cp: int, tag: int,
                   shift_funits: float = 0.0,
                   ext_funits: float = 0.0,
                   strip_y_lo: float = -40, strip_y_hi: float = 200,
                   joining: bool = False) -> tuple[GlyphRecord, GlyphBlob] | None:
    """Generate one (record, blob) pair from a TTF glyph. Returns None if the
    codepoint has no glyph in the face or its outline is empty."""
    gi = face.get_char_index(cp)
    if gi == 0:
        return None
    face.load_glyph(gi, freetype.FT_LOAD_NO_SCALE | freetype.FT_LOAD_NO_HINTING)
    outline = face.glyph.outline
    if outline.n_points == 0:
        return None

    contours = _outline_to_contours(outline)
    if not contours:
        return None

    groups = _classify(contours)

    # Tessellate each group with earcut, accumulating into a single mesh.
    all_verts: list[tuple[float, float]] = []
    all_idx: list[int] = []
    for outer_idx, hole_idxs in groups:
        rings = [contours[outer_idx]] + [contours[h] for h in hole_idxs]
        flat = np.array([p for ring in rings for p in ring], dtype=np.float32)
        if len(flat) < 3:
            continue
        ring_ends = np.cumsum([len(r) for r in rings]).astype(np.uint32)
        idx = earcut.triangulate_float32(flat, ring_ends)
        base = len(all_verts)
        all_verts.extend([(float(x), float(y)) for x, y in flat])
        all_idx.extend(int(i) + base for i in idx)

    # Optional baseline extension for joining scripts
    if joining and ext_funits > 0:
        needs_right, needs_left = _is_joining_form(cp)
        if needs_left or needs_right:
            ext_verts, ext_idx = _extension_rects(contours,
                                                  side_left=needs_left,
                                                  side_right=needs_right,
                                                  ext_funits=ext_funits,
                                                  strip_y_lo=strip_y_lo,
                                                  strip_y_hi=strip_y_hi)
            base = len(all_verts)
            all_verts.extend(ext_verts)
            all_idx.extend(i + base for i in ext_idx)

    if not all_verts or not all_idx:
        return None

    # Shift X to match Latin LSB convention
    if shift_funits:
        all_verts = [(x + shift_funits, y) for (x, y) in all_verts]

    # Normalize and pack
    upm = face.units_per_EM
    inv = 1.0 / upm
    advance = face.glyph.advance.x * inv
    if shift_funits:
        advance += shift_funits * inv

    ys = [v[1] * inv for v in all_verts]
    ymax = max(ys)
    ymin = min(ys)

    vert_bytes = bytearray()
    for x, y in all_verts:
        nx = x * inv
        ny = y * inv
        vert_bytes += _f16_bytes(nx)
        vert_bytes += _f16_bytes(ny)
        vert_bytes += _f16_bytes(0.0)   # U
        vert_bytes += _f16_bytes(1.0)   # V = 1.0 → solid fill

    idx_bytes = bytearray()
    for i in all_idx:
        idx_bytes += struct.pack('<H', i)

    record = GlyphRecord(cp=cp, pad=0, tag=tag,
                         f1=float(advance), f2=float(ymax), f3=float(ymin),
                         w=len(all_verts), h=len(all_idx),
                         atlas_off=0)  # filled later
    blob = GlyphBlob(cp=cp, w=len(all_verts), h=len(all_idx),
                     vert_bytes=bytes(vert_bytes), idx_bytes=bytes(idx_bytes))
    return record, blob


# ---------- top-level driver ----------

def inject(base_vfont_path: str, base_vfont0_path: str,
           ttf_path: str, codepoints: list[int],
           out_vfont_path: str, out_vfont0_path: str,
           joining: bool = False,
           ext_funits: float = 0.0) -> None:
    """Inject new glyphs from a TTF into a copy of an existing font pair.

    Existing records are preserved unchanged. New records replace any
    existing records with the same codepoint.
    """
    with open(base_vfont_path, 'rb') as f:
        vf = parse_vfont(f.read())
    with open(base_vfont0_path, 'rb') as f:
        v0 = parse_vfont0(f.read())

    face = freetype.Face(ttf_path)
    upm = face.units_per_EM
    tag = vf.records[0].tag if vf.records else 0
    shift = upm * SHIFT_FU_FRACTION

    existing = {r.cp: r for r in vf.records}

    # Read every existing blob into memory (for re-emit later).
    from vfont_codec import read_blob
    blobs_by_cp: dict[int, GlyphBlob] = {}
    for r in vf.records:
        blobs_by_cp[r.cp] = read_blob(v0, r.atlas_off, r.w, r.h)

    # Generate new glyphs and overwrite any matching cp
    generated = 0
    for cp in codepoints:
        result = generate_glyph(face, cp, tag,
                                shift_funits=shift,
                                ext_funits=ext_funits, joining=joining)
        if result is None:
            continue
        rec, blob = result
        existing[cp] = rec
        blobs_by_cp[cp] = blob
        generated += 1

    # Sort by codepoint. The U+FFFD .notdef must end up last; this
    # happens automatically when codepoints stay below 0x10FFFF.
    sorted_recs = sorted(existing.values(), key=lambda r: r.cp)

    # Reassemble the atlas in the same order as records.
    ordered_blobs = [blobs_by_cp[r.cp] for r in sorted_recs]
    new_v0_bytes, atlas_offs = build_vfont0(v0, ordered_blobs)

    # Patch each record's atlas_off to point at its new position.
    for r, ao in zip(sorted_recs, atlas_offs):
        r.atlas_off = ao

    vf.records = sorted_recs
    vf.declared_count = len(sorted_recs)

    with open(out_vfont_path, 'wb') as f:
        f.write(build_vfont(vf))
    with open(out_vfont0_path, 'wb') as f:
        f.write(new_v0_bytes)

    print(f"Generated {generated} glyphs, total {len(sorted_recs)} records.")
    print(f"Last record cp: U+{sorted_recs[-1].cp:04X} (should be FFFD)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('ttf')
    ap.add_argument('out_vfont')
    ap.add_argument('out_vfont0')
    ap.add_argument('--base', required=True, help='Path to base .vfont')
    ap.add_argument('--base0', required=True, help='Path to base .vfont0')
    ap.add_argument('--range', nargs=2, action='append', metavar=('LO', 'HI'),
                    help='Codepoint range to inject (inclusive). Can be repeated.')
    ap.add_argument('--joining', action='store_true',
                    help='Enable baseline mesh extension for joining scripts (Arabic).')
    ap.add_argument('--ext', type=float, default=250.0,
                    help='Extension width in font units (default: 250).')
    args = ap.parse_args()

    if not args.range:
        ap.error('At least one --range is required.')

    codepoints: list[int] = []
    for lo, hi in args.range:
        codepoints.extend(range(int(lo, 0), int(hi, 0) + 1))

    inject(args.base, args.base0, args.ttf, codepoints,
           args.out_vfont, args.out_vfont0,
           joining=args.joining, ext_funits=args.ext if args.joining else 0.0)


if __name__ == '__main__':
    main()
