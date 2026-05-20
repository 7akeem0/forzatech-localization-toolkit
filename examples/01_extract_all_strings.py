"""
Example 01: Extract all strings from a language ZIP into JSON.

This is the starting point for any localization. You give it a path to
one of the game's language archives (EN.zip, BR.zip, JP.zip, ...) and
it dumps every string from every .str file into a directory of JSON
files, one per .str.

JSON format per file:
    [
        {"hash": 0xABCD1234, "key": "IDS_HZ6_VO_...", "value": "Hello world"},
        ...
    ]

Usage:
    python 01_extract_all_strings.py /path/to/EN.zip ./output_json

Output:
    ./output_json/Main.json
    ./output_json/Calendar.json
    ./output_json/Dialogue.json
    ... (287 files for FH6)
"""

from __future__ import annotations
import json
import sys
import zipfile
from pathlib import Path

# Make tools/ importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tools'))
from str_codec import parse  # noqa: E402


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python 01_extract_all_strings.py <input.zip> <output_dir>",
              file=sys.stderr)
        sys.exit(1)

    src_zip = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    total_files = 0
    total_strings = 0

    with zipfile.ZipFile(src_zip, 'r') as zf:
        for info in zf.infolist():
            if not info.filename.endswith('.str'):
                continue
            with zf.open(info) as f:
                data = f.read()
            table = parse(data)

            entries = []
            for k, v in zip(table.keys, table.values):
                entries.append({
                    'hash': k.hash,
                    'key': k.string,
                    'value': v.string,
                })

            out_path = out_dir / (Path(info.filename).stem + '.json')
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(entries, f, ensure_ascii=False, indent=2)

            total_files += 1
            total_strings += len(entries)
            print(f"  {info.filename:40s}  {len(entries):6d} strings")

    print(f"\nExtracted {total_strings} strings across {total_files} files "
          f"into {out_dir}")


if __name__ == '__main__':
    main()
