"""
Example 02: Re-inject modified JSON files back into a language ZIP.

This is the second half of the round-trip. After you (or your team)
have edited the JSON files produced by example 01, this script
rebuilds the .str files and packs them into a new ZIP.

The output ZIP is structured identically to the input — same filenames,
same compression mode — so it can replace the original directly in the
game install.

Usage:
    python 02_modify_one_string.py ./json_dir /path/to/template_EN.zip output_EN.zip

Arguments:
    json_dir       directory containing the edited JSON files
    template       the original game ZIP (used to preserve any non-.str entries)
    output         path to write the modified ZIP

Hooks for script-specific preprocessing (Arabic shaping, etc.) can be
added in the `preprocess()` function below. By default it returns the
value unchanged — appropriate for LTR scripts that don't need shaping.
"""

from __future__ import annotations
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tools'))
from str_codec import Entry, StrTable, parse, build  # noqa: E402


def preprocess(value: str) -> str:
    """
    Hook for script-specific text preprocessing.

    For LTR scripts (Cyrillic, Latin extensions, Greek): return value as-is.

    For RTL scripts (Arabic, Hebrew, Persian, Urdu):
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(value))

    For complex LTR scripts with marks (Thai, Devanagari): may need
    Unicode normalization (NFC) but no reversal.
    """
    return value


def rebuild_str_file(original: bytes, edits: dict[int, str]) -> bytes:
    """Parse a .str file, apply hash->new_value edits, return new bytes."""
    table = parse(original)
    new_values = []
    for v in table.values:
        if v.hash in edits:
            new_values.append(Entry(v.hash, preprocess(edits[v.hash])))
        else:
            new_values.append(v)
    new_table = StrTable(name=table.name, keys=table.keys, values=new_values)
    return build(new_table)


def main() -> None:
    if len(sys.argv) != 4:
        print("Usage: python 02_modify_one_string.py <json_dir> <template.zip> <output.zip>",
              file=sys.stderr)
        sys.exit(1)

    json_dir = Path(sys.argv[1])
    template = Path(sys.argv[2])
    output = Path(sys.argv[3])

    # Load all edits into memory: {stem -> {hash -> new_value}}
    all_edits: dict[str, dict[int, str]] = {}
    for jf in json_dir.glob('*.json'):
        with open(jf, encoding='utf-8') as f:
            entries = json.load(f)
        all_edits[jf.stem] = {int(e['hash']): e['value'] for e in entries}

    total_replaced = 0
    total_files = 0

    with zipfile.ZipFile(template, 'r') as zin, \
         zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info)
            if info.filename.endswith('.str'):
                stem = Path(info.filename).stem
                edits = all_edits.get(stem, {})
                if edits:
                    data = rebuild_str_file(data, edits)
                    total_replaced += len(edits)
                    total_files += 1
            zout.writestr(info, data)

    print(f"Replaced {total_replaced} strings across {total_files} files.")
    print(f"Output: {output}")


if __name__ == '__main__':
    main()
