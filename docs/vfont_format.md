# `.vfont` Format

The `.vfont` file describes a single font face's metadata, metrics, and glyph slot table. It is paired with a `.vfont0` (described in [`vfont0_format.md`](vfont0_format.md)) that holds the actual mesh data.

This format was previously undocumented publicly. The layout below was reverse-engineered with byte-identical roundtrip verified on 20 of 20 shipping fonts.

## File layout

| Offset | Size | Field |
|---|---|---|
| `0x00` | `0x80` | `header_a` — font name (ASCII, null-padded) + reserved padding |
| `0x80` | 2 | `declared_count` (u16) — number of 36-byte slots |
| `0x82` | `0x5E` | `header_b` — font metrics (opaque) |
| `0xE0` + `i*36` | 36 | Glyph record `i`, sorted by codepoint |
| `end_of_records` | var | Trailer (kerning data + optional footer) |

Some fonts (e.g. `Horizon_C_tf`, `DG2_LCD-BOLD`) include a 24-byte "footer slot" that counts toward `declared_count` but is not a glyph record. A correct parser walks slots from `0xE0` and stops when one of:

- The next 36-byte slot does not start with `0xFFFFFFFF`.
- The `pad` field at `+0x04` is non-zero.
- The `codepoint` field at `+0x0C` exceeds `0x10FFFF` (max Unicode).
- Fewer than 36 bytes remain in the file.

## Glyph record (36 bytes)

| Offset | Size | Field | Notes |
|---|---|---|---|
| `+0x00` | 4 | `0xFFFFFFFF` | Start sentinel |
| `+0x04` | 4 | `0x00000000` | Padding |
| `+0x08` | 4 | `tag` (u32) | Font fingerprint constant (see below) |
| `+0x0C` | 4 | `codepoint` (u32 LE) | Unicode codepoint |
| `+0x10` | 4 | `f1` (f32) | Glyph advance width (em units after `÷ UPM`) |
| `+0x14` | 4 | `f2` (f32) | Max Y of mesh (ascent) |
| `+0x18` | 4 | `f3` (f32) | Min Y of mesh (descent) |
| `+0x1C` | 2 | `w` (u16) | **Vertex count** (not bbox width) |
| `+0x1E` | 2 | `h` (u16) | **Index count** (not bbox height) |
| `+0x20` | 4 | `atlas_off` (u32 LE) | Byte offset into the paired `.vfont0` |

**Note on `w` and `h`:** It is tempting to read these as bounding-box dimensions because of their names, but they are vertex/index counts. The engine reads exactly `w * 8 + h * 2` bytes of mesh data from the blob at `atlas_off`. Misinterpretation produces garbage glyphs that span into neighboring blobs.

## Record ordering and the `0xFFFD` sentinel

**Records are sorted ascending by codepoint.** The engine binary-searches the table. When inserting new records, the combined list must be re-sorted before writing.

The last record in every font has `codepoint = 0xFFFD` (Unicode replacement character) with `w = 40, h = 72`. This is the `.notdef` fallback drawn when a requested codepoint has no record. **It must remain the last record.** Sorting by codepoint ascending places it last automatically since `0xFFFD` is greater than every script codepoint up to and including Arabic Presentation Forms-B (`0xFEFC`).

If `0xFFFD` is shifted out of the last position (e.g. by appending records without sorting), the engine's lookup logic fails and the game crashes on load.

## Font fingerprint tag

The 4-byte `tag` at `+0x08` is constant per font:

| Font | Tag (little-endian as written in file) |
|---|---|
| `Horizon_A` / `B` / `C` / `D` | `0x06010000` |
| `Horizon_C_tf` | `0x5A010000` |
| `Horizon_D_tf` | `0xE0010000` |
| `Horizon_RU_A` | `0xD3010000` |
| `Horizon_KO` | `0xED010000` |
| `DG2_LCD-BOLD` | `0x00010000` |

New records inserted into a font should reuse the tag from existing records in the same font. The exact semantics of this field are not yet known, but preservation across modification works reliably.

## Trailer / kerning section

After all records, the file contains a variable-size trailer of `12 * N` bytes (plus an optional 24-byte footer). The structure resembles a kerning table:

```
[u32 codepoint_A]
[u32 codepoint_B]
[f32 kerning_offset]
```

For `Horizon_A` this trailer is 159,948 bytes = 13,329 entries. New glyphs do not require new kerning entries — the engine uses zero kerning for unknown pairs without issue. **Preserve the trailer as opaque bytes** when modifying.

## Per-glyph metric semantics

For each record:
- `f1` — advance width in em units (i.e. font-units divided by `units_per_EM`).
- `f2` — maximum Y coordinate of the mesh.
- `f3` — minimum Y coordinate of the mesh.

When generating new glyphs from a TTF, compute these from the FreeType outline directly. Do not attempt to "tune" `f1` to tighten letter spacing — experimental modifications produced worse rendering, not better. The engine uses `f1` for cursor advancement; mismatched values cause visible positioning errors.

## Reference implementation

See [`tools/vfont_codec.py`](../tools/vfont_codec.py) for parser, writer, and roundtrip test.
