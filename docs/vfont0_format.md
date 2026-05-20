# `.vfont0` Format

The `.vfont0` file is the mesh atlas paired with a `.vfont`. Each glyph is stored as a triangulated polygon mesh — not as a bitmap or SDF texture. The engine renders glyphs by drawing the mesh through a custom pixel shader.

This format was previously undocumented publicly. The layout below was reverse-engineered with byte-identical roundtrip verified on 19 of 20 shipping fonts (one outlier, `DG3_Moire-Bold`, has an unrelated misalignment that affects no UI text).

## File layout

| Offset | Size | Field |
|---|---|---|
| `0x000` | 4 | `page_count` (u32) — 1 for single-page fonts, higher for CJK |
| `0x004` | 4 | `cell_w` (u32) — typically `0x28` = 40 |
| `0x008` | 4 | `cell_h` (u32) — typically `0x48` = 72 |
| `0x00C` | 464 | Fixed prelude (template / atlas metadata, opaque) |
| `0x1DC..end` | var | Concatenated glyph blobs, in `atlas_off` order |

The 464-byte prelude is the same length across every font tested, regardless of glyph count or page count. Its contents differ per font but are opaque from a modification perspective — preserve it verbatim when rewriting.

## Per-glyph blob

| Offset | Size | Field |
|---|---|---|
| `+0x00` | 4 | `codepoint` (u32) — MUST match the record's `codepoint` |
| `+0x04` | 4 | `w` (u32) — MUST match the record's `w` (vertex count) |
| `+0x08` | 4 | `h` (u32) — MUST match the record's `h` (index count) |
| `+0x0C` | `w * 8` | Vertex array — 4 × `float16` per vertex: X, Y, U, V |
| `+0x0C + 8w` | `h * 2` | Index array — `u16` per index (triangle list) |

Total blob size = `12 + 8w + 2h` bytes.

There are no count fields inside the blob beyond the header — the counts come from the corresponding `.vfont` record. The engine reads exactly `w` vertices and `h` indices from the blob's body. Off-by-one in either count will read garbage data spanning into the next blob.

**Per-blob header validation:** The engine compares `cp`, `w`, `h` in the blob against the record. Mismatch causes the blob to be silently skipped (no glyph rendered). When modifying a glyph, both the record and the blob header must be updated consistently.

## Vertex format

Each vertex is 4 × `float16` = 8 bytes:

| Field | Meaning |
|---|---|
| X | Position X (em units, signed; left-to-right increases) |
| Y | Position Y (em units, signed; `+Y` is **up** — apex of letters at highest Y) |
| U | Curve coverage parameter 1 |
| V | Curve coverage parameter 2 |

The origin (`X = 0, Y = 0`) is at the glyph's baseline-left. Typical Latin glyph Y range is `[-0.03, +0.74]` (descender to apex).

**`+Y = up` is verified empirically.** Negating Y in generated glyphs produces visibly upside-down letters in-game.

## V channel and the Loop-Blinn hypothesis

The pixel shader identifiers visible in the executable (`AVUI_PS_SDFFont`, `AVUI_PS_MSDFFont`) suggest analytic Bezier coverage rendering in the Loop-Blinn / Slug family. Empirical patterns in original Latin glyphs:

| Triangle UV pattern | Count in glyph 'I' | Interpretation |
|---|---|---|
| `((0, 1), (0, 1), (0, 1))` | 2 | Solid fill interior |
| `((0, ±0.04), (0, ±0.04), (0, ∓0.04))` | 4 | Anti-aliasing rim along long edges |

For curved glyphs like 'O', additional triangles carry larger `(U, V)` magnitudes such as `(±2.5, ±15)`, suggestive of quadratic Bezier coverage encoding.

**However**, attempting to encode new glyphs with non-trivial `(U, V)` values causes engine crashes. Multiple sessions tried this; all crashed identically. The shader appears to accept only `V = 1.0` as a valid input. Whether the original Latin glyphs' non-trivial UVs are used by the shader, or are decorative legacy, is not yet known.

**Practical rule:** for any new glyph, set `U = 0.0, V = 1.0` on every vertex. This produces solid-fill polygons with no edge antialiasing beyond what the engine's rasterizer applies natively. Curves will look slightly polygonal at large sizes but are perfectly readable at UI text sizes.

## Index format

`u16` triangle list. Index `i` references the `i`-th vertex of the same blob. Vertices and indices are both 0-based. Standard triangle winding (CCW for solid fill); engines that backface-cull may need the opposite winding, but FH6 renders both windings.

## Coordinate normalization

When generating glyphs from a TTF, divide all font-unit coordinates by the source font's `units_per_EM` before packing as `float16`. Typical UPM is 1000 (Noto family) or 2048 (other open fonts); the divisor is the source font's own value, not a fixed constant.

`float16` has limited precision. For UPM=2048, the smallest representable position step in normalized coords is ~`6e-5`, which is sub-pixel at any realistic text size — quantization is invisible.

## Reference implementation

See [`tools/vfont_codec.py`](../tools/vfont_codec.py) for blob read/write, and [`tools/build_font_from_ttf.py`](../tools/build_font_from_ttf.py) for the full TTF-to-blob pipeline.
