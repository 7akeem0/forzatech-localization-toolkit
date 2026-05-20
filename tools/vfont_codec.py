"""
ForzaTech .vfont and .vfont0 codec.

A font is a pair:
    Horizon_A.vfont   - header + glyph slot table + trailer (kerning)
    Horizon_A.vfont0  - atlas prelude + per-glyph mesh blobs

.vfont layout:
    0x00..0x80   header_a   (font name + reserved padding) opaque
    0x80         u16        declared_count (number of 36-byte slots)
    0x82..0xE0   header_b   (font metrics) opaque
    0xE0..       N x 36     glyph records, packed, sorted by codepoint
    end-of-records..        trailer (kerning data) opaque

A glyph record is 36 bytes:
    +0x00  u32   0xFFFFFFFF              start sentinel
    +0x04  u32   0x00000000              padding
    +0x08  u32   tag                     constant per font (fingerprint)
    +0x0C  u32   codepoint (LE)
    +0x10  f32   f1   glyph advance (em units, scaled by 1/UPM)
    +0x14  f32   f2   ymax (mesh ascent)
    +0x18  f32   f3   ymin (mesh descent)
    +0x1C  u16   w    VERTEX COUNT     (NOT bbox width)
    +0x1E  u16   h    INDEX COUNT      (NOT bbox height)
    +0x20  u32   atlas_off              byte offset into .vfont0

ENGINE RULE: cp=0xFFFD is the .notdef fallback glyph. It MUST be the
last record in the slot table. Since records are sorted by codepoint
ascending and 0xFFFD is greater than every meaningful codepoint up to
PFB-B, sorting the combined record list before serialization is enough.

.vfont0 layout:
    0x000        u32        page_count
    0x004        u32        cell_w    (typically 0x28 = 40)
    0x008        u32        cell_h    (typically 0x48 = 72)
    0x00C..0x1DC 464 bytes  fixed prelude, opaque (preserve verbatim)
    0x1DC..end   variable   concatenated glyph blobs (in atlas_off order)

Per-glyph blob:
    +0x00       u32         codepoint (MUST match record's cp)
    +0x04       u32         w (MUST match record's w == vertex count)
    +0x08       u32         h (MUST match record's h == index count)
    +0x0C       w*8 bytes   vertex array — 4 x float16 per vertex (X, Y, U, V)
    +0x0C+8*w   h*2 bytes   index array — u16 per index (triangle list)

ENGINE RULE: V channel must be 1.0 for solid fill. Other values were
attempted on the hypothesis that V encodes Loop-Blinn-style edge AA;
this caused crashes. Use V=1.0 universally.

ENGINE RULE: For non-Latin scripts, the engine assumes glyph meshes
follow a Latin-style LSB convention where min_x of vertex positions
is roughly UPM/2 to the right of origin. Glyphs with min_x near 0
will be clipped on the leftmost edge of any rendered line. The
solution is to shift all vertex X coordinates by +UPM*0.6 funits
before normalization. See docs/latin_lsb_convention.md.
"""

from __future__ import annotations
import struct
from dataclasses import dataclass, field


# ---------- .vfont ----------

@dataclass
class GlyphRecord:
    cp: int                  # codepoint
    pad: int = 0
    tag: int = 0             # font fingerprint constant
    f1: float = 0.0          # advance
    f2: float = 0.0          # ymax
    f3: float = 0.0          # ymin
    w: int = 0               # vertex count
    h: int = 0               # index count
    atlas_off: int = 0       # offset into .vfont0


@dataclass
class VFont:
    header_a: bytes          # 0x00..0x80 opaque
    declared_count: int      # u16 at 0x80
    header_a_tail: bytes     # 0x82..0xE0 opaque (note: includes 2 bytes after declared_count)
    records: list[GlyphRecord] = field(default_factory=list)
    trailer: bytes = b''     # kerning + footer opaque


def parse_vfont(data: bytes) -> VFont:
    header_a = bytes(data[0x00:0x80])
    declared_count = struct.unpack_from('<H', data, 0x80)[0]
    header_a_tail = bytes(data[0x82:0xE0])

    records: list[GlyphRecord] = []
    off = 0xE0
    while off + 36 <= len(data):
        sentinel, pad, tag, cp, f1, f2, f3, w, h, atlas_off = struct.unpack_from(
            '<IIIIfffHHI', data, off
        )
        if sentinel != 0xFFFFFFFF or pad != 0 or cp > 0x10FFFF:
            break
        records.append(GlyphRecord(cp=cp, pad=pad, tag=tag,
                                   f1=f1, f2=f2, f3=f3,
                                   w=w, h=h, atlas_off=atlas_off))
        off += 36
        if len(records) >= declared_count:
            break

    trailer = bytes(data[off:])
    return VFont(header_a=header_a, declared_count=declared_count,
                 header_a_tail=header_a_tail, records=records, trailer=trailer)


def build_vfont(vf: VFont) -> bytes:
    out = bytearray(vf.header_a)
    out += struct.pack('<H', len(vf.records))
    out += vf.header_a_tail
    for r in vf.records:
        out += struct.pack('<IIIIfffHHI',
                           0xFFFFFFFF, r.pad, r.tag, r.cp,
                           r.f1, r.f2, r.f3, r.w, r.h, r.atlas_off)
    out += vf.trailer
    return bytes(out)


# ---------- .vfont0 ----------

@dataclass
class GlyphBlob:
    cp: int
    w: int        # vertex count
    h: int        # index count
    vert_bytes: bytes   # length = w * 8
    idx_bytes: bytes    # length = h * 2

    @property
    def size(self) -> int:
        return 12 + self.w * 8 + self.h * 2


@dataclass
class VFont0:
    page_count: int
    cell_w: int
    cell_h: int
    prelude: bytes      # the 464-byte opaque chunk after the first 12 bytes
    blobs_raw: bytes    # raw concatenated blobs as found in the file


def parse_vfont0(data: bytes) -> VFont0:
    page_count, cell_w, cell_h = struct.unpack_from('<III', data, 0)
    prelude = bytes(data[0x0C:0x1DC])
    blobs_raw = bytes(data[0x1DC:])
    return VFont0(page_count=page_count, cell_w=cell_w, cell_h=cell_h,
                  prelude=prelude, blobs_raw=blobs_raw)


def read_blob(v0: VFont0, atlas_off: int, expect_w: int, expect_h: int) -> GlyphBlob:
    """Read a single glyph blob at atlas_off (absolute offset into .vfont0)."""
    # atlas_off is given as the offset within the entire file. blobs_raw
    # starts at 0x1DC, so subtract.
    rel = atlas_off - 0x1DC
    cp, w, h = struct.unpack_from('<III', v0.blobs_raw, rel)
    if w != expect_w or h != expect_h:
        raise ValueError(f"blob/record mismatch at {atlas_off:#x}: "
                         f"blob(w={w},h={h}) record(w={expect_w},h={expect_h})")
    vert_off = rel + 12
    idx_off = vert_off + w * 8
    return GlyphBlob(cp=cp, w=w, h=h,
                     vert_bytes=v0.blobs_raw[vert_off:vert_off + w * 8],
                     idx_bytes=v0.blobs_raw[idx_off:idx_off + h * 2])


def pack_blob(b: GlyphBlob) -> bytes:
    """Serialize one glyph blob."""
    return struct.pack('<III', b.cp, b.w, b.h) + b.vert_bytes + b.idx_bytes


def build_vfont0(v0_prelude_src: VFont0, ordered_blobs: list[GlyphBlob]) -> tuple[bytes, list[int]]:
    """
    Build a new .vfont0 by concatenating glyph blobs in their final atlas order.

    Returns the .vfont0 bytes and a parallel list of absolute atlas_off values
    that should be written into each glyph's .vfont record.
    """
    out = bytearray()
    out += struct.pack('<III', v0_prelude_src.page_count,
                       v0_prelude_src.cell_w, v0_prelude_src.cell_h)
    out += v0_prelude_src.prelude
    atlas_offs: list[int] = []
    for b in ordered_blobs:
        atlas_offs.append(len(out))
        out += pack_blob(b)
    return bytes(out), atlas_offs


# ---------- Convenience: load a complete font ----------

def load_font(vfont_path: str, vfont0_path: str) -> tuple[VFont, VFont0, list[GlyphBlob]]:
    """Load and parse both files; return parallel list of blobs in record order."""
    with open(vfont_path, 'rb') as f:
        vf = parse_vfont(f.read())
    with open(vfont0_path, 'rb') as f:
        v0 = parse_vfont0(f.read())
    blobs = [read_blob(v0, r.atlas_off, r.w, r.h) for r in vf.records]
    return vf, v0, blobs


if __name__ == '__main__':
    import sys
    if len(sys.argv) != 3:
        print("Usage: python vfont_codec.py <font.vfont> <font.vfont0>", file=sys.stderr)
        sys.exit(1)
    vf, v0, blobs = load_font(sys.argv[1], sys.argv[2])
    print(f"Records:         {len(vf.records)} (declared: {vf.declared_count})")
    print(f"Atlas page_count: {v0.page_count}")
    print(f"Cell:            {v0.cell_w} x {v0.cell_h}")
    print(f"Codepoint range: U+{vf.records[0].cp:04X}..U+{vf.records[-1].cp:04X}")
    print(f"Trailer size:    {len(vf.trailer)} bytes")
    if vf.records[-1].cp != 0xFFFD:
        print("WARNING: last record is not the U+FFFD .notdef sentinel.")
