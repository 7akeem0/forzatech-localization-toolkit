# `UI.zip` Custom Extra Field and Slot-Preserving Repack

`UI.zip` is a standard PKZIP archive containing the game's XAML UI definitions (~454 entries: 385 XAML + 69 XML for FH6). However, every Local File Header carries a custom extra field with ID `0x1123` and a parallel 4-byte extra in the Central Directory. These extras encode a memory-mapping hint that the engine relies on at load time.

**Naive repack with stock zip tools strips the extras and crashes the game at startup.** This document describes the layout of the custom extras and the technique for modifying an entry without breaking the archive.

## The `0x1123` extra

### Central Directory extra (4 bytes, fixed)

Each CD entry's extra is exactly 4 bytes:

```
23 11 04 00 <data_offset:u32>
```

`<data_offset>` is the absolute offset in the zip where this entry's compressed data starts, **4 KB-aligned**.

### Local File Header extra (variable length, zero-padded)

Each LFH's extra is variable length — pure zero bytes, sized so that:

```
data_offset = lfh_offset + 30 + name_length + lfh_extra_length
```

resolves to a 4 KB-aligned address.

### Verification

For all 454 entries of FH6 UI.zip:
- `cd_data_offset & 0xFFF == 0` — every data offset is 4 KB-aligned.
- `cd_data_offset == lfh_offset + 30 + name_length + lfh_extra_length` — the CD value matches the actual LFH-computed offset.

The 4 KB alignment matches typical OS memory-page size. The engine likely `mmap()`s the entire `UI.zip` and accesses each entry's compressed data directly from its pre-computed offset, bypassing the central directory entirely after the initial read.

**This is a layout hint, not a checksum.** Modifying CRC32, CompressedSize, or even the deflate stream itself does not trigger any validation — but **shifting the data offset of any entry will crash the game**, because the engine's pre-computed mmap addresses no longer match.

## Why standard zip tools break

- **PowerShell `Compress-Archive`** and `[ZipFile]::CreateFromDirectory`: strip all extra fields. Result: every data offset shifts, game crashes.
- **Python `zipfile.writestr(ZipInfo, ...)`**: `ZipInfo.extra` only sets the CD extra, not the LFH extra. Original LFH extras are 1000+ bytes of zero padding; the rewritten ones end up at 0. Result: data offsets shift, game crashes.
- **`7z a -tzip`** and similar: same problem, extras are not preserved by default.

## The slot-preserving repack technique

The key insight: as long as each entry's compressed data stays at the same 4 KB-aligned offset, the engine is happy. We can modify the content of one entry without moving any other entry by:

1. **Compress** new content into the original `CompressedSize` slot.
2. **Patch** CRC32 and CompressedSize in both the LFH and the CD entry.
3. **Overwrite** the deflate payload starting at the original data offset.
4. **Zero-pad** the remainder of the original slot so the next entry's LFH stays exactly where it was.
5. File size is unchanged. All `0x1123` values are unchanged.

### Detailed algorithm

```python
def patch_entry(zip_bytes, entry_name, new_content):
    # 1. Locate the entry's CD record and resolve LFH + data offset
    cd_entry = find_cd_entry(zip_bytes, entry_name)
    lfh_off = cd_entry.lfh_offset
    name_len = u16_at(zip_bytes, lfh_off + 26)
    extra_len = u16_at(zip_bytes, lfh_off + 28)
    data_off = lfh_off + 30 + name_len + extra_len
    orig_csize = cd_entry.compressed_size

    # 2. Compress new content with zopfli (max iterations)
    deflated = zopfli_deflate(new_content)
    if len(deflated) > orig_csize:
        raise ValueError("new content does not fit in original slot")

    new_crc = crc32(new_content)

    # 3. Patch LFH header
    u32_at(zip_bytes, lfh_off + 14, new_crc)
    u32_at(zip_bytes, lfh_off + 18, len(deflated))
    u32_at(zip_bytes, lfh_off + 22, len(new_content))

    # 4. Patch CD entry
    u32_at(zip_bytes, cd_entry.cd_off + 16, new_crc)
    u32_at(zip_bytes, cd_entry.cd_off + 20, len(deflated))
    u32_at(zip_bytes, cd_entry.cd_off + 24, len(new_content))

    # 5. Overwrite payload + zero-pad
    zip_bytes[data_off:data_off + len(deflated)] = deflated
    zip_bytes[data_off + len(deflated):data_off + orig_csize] = bytes(orig_csize - len(deflated))

    return zip_bytes
```

CRC values are little-endian. A typo in CRC byte order produces an apparently valid zip that crashes silently on access — verify by reading back through `zipfile.ZipFile` before installing.

## Why zopfli matters

zopfli is a deflate implementation that produces zlib/gzip-compatible output but with ~4–8% better compression ratio than `zlib.compressobj(level=9)`. For most XAML edits, this extra headroom is the difference between fitting in the original slot and not. At `numiterations=15`, zopfli adds ~100 ms per entry — negligible for one-off patches.

```python
import zopfli
zlib_stream = zopfli.zlib.compress(content, numiterations=15)
deflate_raw = zlib_stream[2:-4]   # strip 2-byte header + 4-byte adler32
```

## When the slot is too small

About 1–2% of XAMLs in FH6 UI.zip are already compressed near-optimally — even zopfli at `numiterations=500` cannot shrink the new content into the original slot. For these, the only options are:

- Make the modification smaller (use shorter attribute values, remove whitespace).
- Edit a different file that achieves the same UX goal.
- Skip that modification.

There is no safe way to extend a single entry. Doing so requires shifting every subsequent entry's data offset, which the engine pre-computed at boot and now expects to find at the old addresses.

## Applicability

This format is shared across ForzaTech-engine games (verified on FH6; expected to apply to FH4, FH5, FM 2023). The exact `0x1123` value and the 4 KB alignment constant may differ across engine versions; verify on the target binary before assuming.

## Reference implementation

See [`tools/ui_zip_patcher.py`](../tools/ui_zip_patcher.py).
