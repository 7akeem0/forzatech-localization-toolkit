# The Latin LSB Convention

ForzaTech's text layout assumes that **every glyph mesh has a Latin-style left-side-bearing**: the leftmost vertex of the polygon should sit roughly `UPM × 0.5` font units to the right of the glyph origin.

Latin glyphs from any standard TTF naturally have this property. Glyphs from other scripts often do not. If you generate Arabic, Thai, or similar glyphs directly from a TTF and inject them, **the leftmost glyph on each rendered line will be clipped on its left half** — the text container's clip rectangle assumes the Latin LSB and cuts through any glyph that violates it.

This document explains the cause and the fix.

## Symptom

A multi-line block of text. Each line individually renders correctly except for the visual-leftmost glyph on each line, which is missing its left half — as if a vertical scissor cut through the letter at its midline. Affected glyphs are typically those whose mesh `min_x` is at or near 0.

The clip is deterministic and reproducible: the same glyph in the same position always clips the same way. It is not a rendering bug, not a font-data bug, not an alignment issue. It is the text container computing its width or clip-rect based on an assumed LSB that the glyph violates.

## Diagnostic measurement

Open any working font (e.g. the original `Horizon_A.vfont` shipping with the game) and dump the per-glyph `min_x` after decoding the vertex stream:

```python
from tools.vfont_codec import load_font

vf, v0, blobs = load_font('Horizon_A.vfont', 'Horizon_A.vfont0')
import struct
for rec, blob in zip(vf.records, blobs):
    # Each vertex is 4 x float16 = 8 bytes; we want field 0 (X).
    import numpy as np
    verts = np.frombuffer(blob.vert_bytes, dtype=np.float16).reshape(-1, 4)
    print(f"U+{rec.cp:04X}  min_x={verts[:,0].min():.4f}")
```

For Latin glyphs in `Horizon_A` you will see `min_x ≈ +0.51` consistently. For Arabic / non-Latin glyphs generated naively from a TTF, `min_x ≈ +0.06` or even lower. The gap between these values is what the clip rect is reserving for "Latin LSB space" — and any glyph that doesn't reserve that space overflows the clip on the left.

## The fix

Before normalizing vertex coordinates by `÷ UPM`, shift all vertex X coordinates by `+ UPM × 0.6` font units. After shift and normalization, `min_x` lands near `+0.5` matching Latin convention.

```python
SHIFT_FU = face.units_per_EM * 0.6
all_verts = [(x + SHIFT_FU, y) for (x, y) in all_verts]
# ... then normalize and pack as before
```

The exact factor `0.6` was chosen as roughly `0.51 - 0.06 ≈ 0.45`, rounded up for safety margin. Empirically, `0.6` eliminates the clip on first install. Values below `0.5` leave residual clipping; values above `0.65` over-compensate and produce a visible empty gap on the right of each line.

## What also needs the shift

When the shift is applied to a glyph's interior mesh, three other things must shift consistently:

1. **Baseline-extension rectangles** (for joining scripts like Arabic) — must use the *shifted* `min_x` and `max_x` as their bounds, so the extension connects correctly to the next letter.
2. **Advance width** `f1` in the glyph record — must include the shift: `advance = (face.glyph.advance.x + SHIFT_FU) / UPM`.
3. **Mesh-extension calibration** (e.g. how far an Arabic init-form's left bridge reaches) — extension width tuned for the unshifted geometry will be wrong after the shift. For Arabic at shift=`UPM*0.6`, extension=`UPM*0.25` is the empirical sweet spot. For shift=0, extension=`UPM*0.32` was the previous sweet spot.

## Why the engine assumes this

Unverified — most likely the engine's text-line measurement uses `sum(advances) - first_glyph_LSB + last_glyph_RSB`, a common typesetting convention. The clip rectangle is then sized to the measured width, expecting the first glyph's actual ink to extend left by exactly the LSB amount it reserved. Glyphs from scripts where ink starts at the origin (no reserved LSB) extend their ink past the left clip edge.

A more thorough investigation would require shader / layout-engine decompilation. For practical purposes the fix is simple and universal.

## Applicability beyond Arabic

This convention applies to **any** script that generates glyphs without a Latin-style LSB:

- **Thai** — ink starts near the origin, needs the shift.
- **Devanagari** — ink starts near the origin, needs the shift.
- **Korean Hangul** — typically has Latin-style LSB in standard fonts, may not need the shift; test with the diagnostic above.
- **Chinese / Japanese** — typically has Latin-style LSB, may not need the shift.
- **Cyrillic** — Latin-style LSB present, does not need the shift.

The diagnostic is the source of truth: dump `min_x` of your generated glyphs, compare to `min_x` of Latin glyphs in the same font slot. If yours is significantly smaller (e.g. `0.06` vs `0.51`), apply the shift.

## Reference implementation

See [`tools/build_font_from_ttf.py`](../tools/build_font_from_ttf.py) — the `shift_funits` argument in `generate_glyph()`.
