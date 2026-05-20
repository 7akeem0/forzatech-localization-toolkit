# `.str` Binary Format

The `.str` file is ForzaTech's custom string table. Each language ZIP (`EN.zip`, `JP.zip`, `BR.zip`, ...) contains 287 of these files. The format is fully deterministic, and byte-identical roundtrip has been verified on every shipping file (287 files × 24 languages = 6,888 files).

## File-level layout

| Offset | Size | Field |
|---|---|---|
| `0x00` | 2 | Magic `00 08` |
| `0x02` | var | Table name (null-terminated ASCII, e.g. `Main`) |
| ... | | Zero-padding to `0x80` |
| `0x80` | 4 | `magic_field` — constant `0x0000008C` |
| `0x84` | 4 | `values_section_offset` — constant `0x0000008C` |
| `0x88` | 4 | `keys_section_offset` = `0x8C + values_section_size` |
| `0x8C` | – | VALUES section starts here |

The table name at offset `0x02` is the human-readable identifier of the string table (`Main`, `Calendar`, `Dialogue`, etc.). It is null-terminated, but the field is zero-padded out to offset `0x80`. Names range from 4 to ~30 bytes; the padding fills the rest.

## Section layout

Both VALUES and KEYS share the same structure:

| Offset within section | Size | Field |
|---|---|---|
| `+0x00` | 4 | `section_size` = `12 + 8*entry_count + blob_size` |
| `+0x04` | 4 | `blob_size` (bytes of string data) |
| `+0x08` | 4 | `entry_count` |
| `+0x0C` | `8*N` | Entry array — each entry is `(u32 hash, u32 offset_into_blob)` |
| `+0x0C + 8N` | – | Blob — concatenated null-terminated UTF-8 strings |

## Key↔value linking by hash

The VALUES and KEYS sections both contain `entry_count` records. For index `i`, `values.entries[i].hash == keys.entries[i].hash`. The engine looks up a string by:

1. Computing the hash of the key string (an FNV-like algorithm; the exact polynomial is not required for modification — see "Modification rule" below).
2. Searching the KEYS section's entry array for a matching hash.
3. Reading the VALUES section's entry at the same index.

## Modification rule

For localization purposes, only the VALUES section needs modification. The KEYS section can be copied verbatim from the original file. As long as the entries in VALUES preserve their original order and original hash values, the engine will look them up correctly with any new string content.

Algorithm to modify:

1. Parse VALUES and KEYS as described above.
2. Build a `hash → value_string` dictionary.
3. Apply translations: `dict[hash] = new_string`.
4. Re-emit VALUES blob: walk the original entry array in order, append `new_string + \0` for each hash, recording the new offset.
5. Rebuild the VALUES section header with the new `blob_size`.
6. Copy the KEYS section verbatim.
7. Recompute `keys_offset = 0x8C + values_section_size`.
8. Write the new header with the updated `keys_offset` at `0x88`.

UTF-8 is the native encoding. Multi-byte sequences for any script are accepted by the engine without configuration.

## Maximum string length

Not formally tested, but observed shipping strings range up to ~2,000 bytes (long dialogue lines). Empty strings are present and valid. Strings containing newlines (`0x0A`) render as multi-line text in the UI.

## Special markup

A subset of strings contains markup tags that the engine interprets at render time:

- `{0}`, `{1}` — positional substitution placeholders.
- `[BOLD:...]`, `[HIGHLIGHT:...]`, `[KING:...]` — styled inline runs.
- `[CREDITS]`, `[GAMERTAG]`, `[PLAYERICON]` — opaque widgets (no content to translate).
- `\n` — line break.

Markup must be preserved exactly. Any text content inside `[TAG:...]` wrappers should be treated as part of the string (translated and shaped along with surrounding text), then re-wrapped in the same tag.

## Reference implementation

See [`tools/str_codec.py`](../tools/str_codec.py).
