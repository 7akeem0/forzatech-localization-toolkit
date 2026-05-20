"""
ForzaTech .str codec.

The .str file is ForzaTech's custom string table. Each language ZIP
(EN.zip, JP.zip, BR.zip, ...) contains 287 of these files.

File layout:
    0x00..0x02  magic 00 08
    0x02..0x80  null-terminated table name + zero padding
    0x80..0x84  constant 0x0000008C
    0x84..0x88  values section offset (= 0x8C)
    0x88..0x8C  keys section offset (= 0x8C + values_section_size)
    0x8C..      VALUES section
    ...         KEYS section

Each section (VALUES, KEYS):
    +0x00  u32  section_size  = 12 + 8*entry_count + blob_size
    +0x04  u32  blob_size
    +0x08  u32  entry_count
    +0x0C  8*N  entries (hash:u32, offset_into_blob:u32)
    +...   var  null-terminated UTF-8 string blob

Strings are linked between sections by `hash`. For index i,
values[i].hash == keys[i].hash; the engine looks up the value
for a given key by hashing the key string.

Byte-identical roundtrip is guaranteed if entries are preserved
in their original order with their original hash values.
"""

from __future__ import annotations
import struct
from dataclasses import dataclass


@dataclass
class Entry:
    hash: int
    string: str


@dataclass
class StrTable:
    name: str             # table name from offset 0x02
    keys: list[Entry]     # KEYS section
    values: list[Entry]   # VALUES section, parallel to keys


def parse(data: bytes) -> StrTable:
    """Parse a .str file into a StrTable."""
    if data[:2] != b'\x00\x08':
        raise ValueError("not a ForzaTech .str file (bad magic)")

    name_end = data.index(b'\x00', 2)
    name = data[2:name_end].decode('ascii')

    magic_field, values_off, keys_off = struct.unpack_from('<III', data, 0x80)
    if magic_field != 0x8C or values_off != 0x8C:
        raise ValueError(f"unexpected header: magic={magic_field:#x} values_off={values_off:#x}")

    def _read_section(off: int) -> list[Entry]:
        _, blob_size, count = struct.unpack_from('<III', data, off)
        entries_off = off + 12
        blob_off = entries_off + 8 * count
        out = []
        for i in range(count):
            h, s_off = struct.unpack_from('<II', data, entries_off + i * 8)
            end = data.index(b'\x00', blob_off + s_off)
            out.append(Entry(h, data[blob_off + s_off:end].decode('utf-8')))
        return out

    values = _read_section(values_off)
    keys = _read_section(keys_off)
    return StrTable(name, keys, values)


def build(table: StrTable) -> bytes:
    """Serialize a StrTable back to bytes."""
    out = bytearray(0x8C)
    out[0:2] = b'\x00\x08'
    name_bytes = table.name.encode('ascii') + b'\x00'
    out[2:2 + len(name_bytes)] = name_bytes

    def _build_section(entries: list[Entry]) -> bytes:
        blob = bytearray()
        offsets = []
        for e in entries:
            offsets.append(len(blob))
            blob += e.string.encode('utf-8') + b'\x00'
        entry_table = bytearray()
        for e, off in zip(entries, offsets):
            entry_table += struct.pack('<II', e.hash, off)
        section_size = 12 + len(entry_table) + len(blob)
        header = struct.pack('<III', section_size, len(blob), len(entries))
        return header + bytes(entry_table) + bytes(blob)

    values_section = _build_section(table.values)
    keys_section = _build_section(table.keys)

    keys_off = 0x8C + len(values_section)
    struct.pack_into('<III', out, 0x80, 0x8C, 0x8C, keys_off)

    return bytes(out) + values_section + keys_section


def roundtrip_ok(data: bytes) -> bool:
    """True if parse() then build() reproduces the original bytes exactly."""
    return build(parse(data)) == data


if __name__ == '__main__':
    import sys
    if len(sys.argv) != 2:
        print("Usage: python str_codec.py <file.str>", file=sys.stderr)
        sys.exit(1)
    with open(sys.argv[1], 'rb') as f:
        data = f.read()
    t = parse(data)
    print(f"Table: {t.name}")
    print(f"Entries: {len(t.values)}")
    print(f"Roundtrip OK: {roundtrip_ok(data)}")
    for k, v in list(zip(t.keys, t.values))[:5]:
        print(f"  {k.string!r:50s} = {v.string!r}")
