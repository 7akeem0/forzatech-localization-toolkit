"""
ForzaTech UI.zip patcher.

UI.zip is a standard PKZIP archive with a custom local-file-header extra
field (ID 0x1123, 4 bytes) carrying a 4 KB-aligned data offset. The
engine memory-maps UI.zip and reads each entry's compressed data
directly from its pre-computed offset. If those offsets shift, the
game crashes on load.

The Local File Header extra is variable-length zero padding sized to
push the start of compressed data onto the next 4 KB boundary. The
Central Directory extra is exactly 4 bytes: a u32 equal to that
4 KB-aligned data offset.

Naive repack with stock zip tools strips the extra fields and rebuilds
offsets — the resulting archive will not load. The technique below
preserves all offsets by patching one entry in place:

  1. Compress the new content with zopfli (or zlib level 9) until the
     output fits within the original CompressedSize "slot".
  2. Patch CRC32 and CompressedSize in both the LFH and the CD entry.
  3. Overwrite the compressed payload starting at the original data
     offset.
  4. Zero-pad from (data_offset + new_csize) to (data_offset + old_csize)
     so the next entry's LFH stays exactly where it was.
  5. File size is unchanged. All 0x1123 values are unchanged.

If the new content cannot fit in the slot even with zopfli at maximum
iterations, the patch is rejected — there is no safe way to extend an
entry without shifting the rest of the archive.

Tested on all 454 entries of FH6 UI.zip. The technique applies to any
ForzaTech-engine PKZIP using the 0x1123 extra.
"""

from __future__ import annotations
import struct
import zlib
from dataclasses import dataclass

try:
    import zopfli
    _ZOPFLI = True
except ImportError:
    _ZOPFLI = False


EOCD_SIG = b'PK\x05\x06'
CD_SIG = b'PK\x01\x02'
LFH_SIG = b'PK\x03\x04'
PG_EXTRA_ID = 0x1123


@dataclass
class CDEntry:
    name: str
    cd_off: int           # offset of CD entry in the zip
    lfh_off: int          # offset of local file header
    data_off: int         # offset of compressed data (= LFH end + name + extra)
    crc32: int
    csize: int
    usize: int
    name_len: int
    extra_len_cd: int
    extra_len_lfh: int


def _find_eocd(data: bytes) -> int:
    # EOCD has a variable-length comment at the end. Scan backwards.
    for i in range(len(data) - 22, max(0, len(data) - 65557 - 22), -1):
        if data[i:i + 4] == EOCD_SIG:
            return i
    raise ValueError("EOCD not found")


def read_directory(data: bytes) -> list[CDEntry]:
    """Read every CD entry and resolve the local header + data offset for each."""
    eocd = _find_eocd(data)
    cd_count = struct.unpack_from('<H', data, eocd + 10)[0]
    cd_off = struct.unpack_from('<I', data, eocd + 16)[0]

    entries: list[CDEntry] = []
    off = cd_off
    for _ in range(cd_count):
        if data[off:off + 4] != CD_SIG:
            raise ValueError(f"bad CD signature at {off:#x}")
        crc32 = struct.unpack_from('<I', data, off + 16)[0]
        csize = struct.unpack_from('<I', data, off + 20)[0]
        usize = struct.unpack_from('<I', data, off + 24)[0]
        name_len = struct.unpack_from('<H', data, off + 28)[0]
        extra_len = struct.unpack_from('<H', data, off + 30)[0]
        comment_len = struct.unpack_from('<H', data, off + 32)[0]
        lfh_off = struct.unpack_from('<I', data, off + 42)[0]
        name = data[off + 46:off + 46 + name_len].decode('utf-8', errors='replace')

        # Resolve data offset from the LFH itself
        lfh_name_len = struct.unpack_from('<H', data, lfh_off + 26)[0]
        lfh_extra_len = struct.unpack_from('<H', data, lfh_off + 28)[0]
        data_off = lfh_off + 30 + lfh_name_len + lfh_extra_len

        entries.append(CDEntry(
            name=name, cd_off=off, lfh_off=lfh_off, data_off=data_off,
            crc32=crc32, csize=csize, usize=usize,
            name_len=name_len, extra_len_cd=extra_len, extra_len_lfh=lfh_extra_len,
        ))
        off += 46 + name_len + extra_len + comment_len
    return entries


def find_entry(entries: list[CDEntry], name: str) -> CDEntry:
    for e in entries:
        if e.name == name:
            return e
    raise KeyError(name)


def _raw_deflate(content: bytes, prefer_zopfli: bool = True) -> bytes:
    """Compress to raw DEFLATE (no zlib wrapper)."""
    if prefer_zopfli and _ZOPFLI:
        # Strip 2-byte zlib header + 4-byte adler32 trailer
        zlib_stream = zopfli.zlib.compress(content, numiterations=15)
        return zlib_stream[2:-4]
    # zlib level 9 with raw deflate (negative wbits)
    co = zlib.compressobj(9, zlib.DEFLATED, -15)
    return co.compress(content) + co.flush()


def patch_entry(data: bytes, entry_name: str, new_content: bytes,
                prefer_zopfli: bool = True) -> bytes:
    """
    Replace the content of one entry in place. Returns the new zip bytes.

    Raises ValueError if the new content does not fit in the original slot.
    """
    entries = read_directory(data)
    e = find_entry(entries, entry_name)

    deflated = _raw_deflate(new_content, prefer_zopfli=prefer_zopfli)
    if len(deflated) > e.csize:
        raise ValueError(
            f"new compressed size {len(deflated)} > original slot {e.csize} "
            f"for {entry_name}. Cannot patch in place.")

    new_crc = zlib.crc32(new_content) & 0xFFFFFFFF
    out = bytearray(data)

    # Patch LFH: CRC at +14, CompressedSize at +18, UncompressedSize at +22
    struct.pack_into('<III', out, e.lfh_off + 14, new_crc, len(deflated), len(new_content))

    # Patch CD: CRC at +16, CompressedSize at +20, UncompressedSize at +24
    struct.pack_into('<III', out, e.cd_off + 16, new_crc, len(deflated), len(new_content))

    # Overwrite payload
    out[e.data_off:e.data_off + len(deflated)] = deflated

    # Zero-pad to original slot end so next entry's LFH stays in place
    pad_start = e.data_off + len(deflated)
    pad_end = e.data_off + e.csize
    for i in range(pad_start, pad_end):
        out[i] = 0

    return bytes(out)


def read_entry(data: bytes, entry_name: str) -> bytes:
    """Decompress and return one entry's content."""
    entries = read_directory(data)
    e = find_entry(entries, entry_name)
    compressed = data[e.data_off:e.data_off + e.csize]
    return zlib.decompress(compressed, -15)


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python ui_zip_patcher.py <UI.zip> [entry_name]", file=sys.stderr)
        sys.exit(1)
    with open(sys.argv[1], 'rb') as f:
        data = f.read()
    entries = read_directory(data)
    print(f"Entries: {len(entries)}")
    if len(sys.argv) == 3:
        e = find_entry(entries, sys.argv[2])
        print(f"Name:      {e.name}")
        print(f"LFH off:   0x{e.lfh_off:08x}")
        print(f"Data off:  0x{e.data_off:08x}  (aligned: {e.data_off % 0x1000 == 0})")
        print(f"CSize:     {e.csize}")
        print(f"USize:     {e.usize}")
        print(f"CRC32:     0x{e.crc32:08x}")
    else:
        for e in entries[:5]:
            print(f"  {e.name}  off=0x{e.data_off:08x}  csize={e.csize}")
        print(f"  ... and {len(entries) - 5} more")
