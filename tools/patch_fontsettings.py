"""
Rewrite font fallback chains in fontsettings.xml.

Inside Fonts.zip, fontsettings.xml defines per-locale font sets with
fallback chains. By default, the bold/condensed weights (Horizon_B, _C,
_D) fall back to Cyrillic variants (Horizon_RU_A, _C, _D). For any
locale whose primary font was extended with new glyphs (typically
Horizon_A), strings rendered through a bold or condensed style will
look up the missing codepoints in fonts that do not have them,
producing tofu (□) instead of the new script.

This tool rewrites the fallback attribute of selected font names to
point at a target font, so that all weights resolve through the font
where the new glyphs live.

Default behavior is the documented fix: redirect Horizon_B, _C, _D to
fall back to Horizon_A. The --sources and --target flags let you adapt
this for any extended font.

Usage:
    # Extract fontsettings.xml from Fonts.zip first, e.g. with unzip
    python patch_fontsettings.py fontsettings.xml fontsettings.new.xml

    # Or pick a different target
    python patch_fontsettings.py fontsettings.xml fontsettings.new.xml \\
        --target Horizon_RU_A --sources Horizon_RU_C Horizon_RU_D

Then put fontsettings.new.xml back into Fonts.zip in place of the original
(standard zip tools are fine — Fonts.zip does not use the custom 0x1123
extra field; only UI.zip does).
"""

from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path


DEFAULT_SOURCES = ('Horizon_B', 'Horizon_C', 'Horizon_D')
DEFAULT_TARGET = 'Horizon_A'


def patch(xml_text: str, sources: list[str], target: str) -> tuple[str, int]:
    """Rewrite the `fallback` attribute on every <FontName name="X"/> where
    X is in `sources`, pointing it at `target`. Attribute order is tolerated.
    Returns the new XML and the number of substitutions made."""
    src_set = set(sources)
    count = 0
    elem_re = re.compile(r'<FontName\s+([^/>]+?)/?>', re.DOTALL)
    fb_re = re.compile(r'(\bfallback\s*=\s*")[^"]*(")')
    name_re = re.compile(r'\bname\s*=\s*"([^"]+)"')

    def _repl(m: re.Match) -> str:
        nonlocal count
        attrs = m.group(1)
        name_m = name_re.search(attrs)
        if not name_m or name_m.group(1) not in src_set:
            return m.group(0)
        new_attrs, n = fb_re.subn(
            lambda mm: mm.group(1) + target + mm.group(2),
            attrs,
            count=1,
        )
        if n > 0:
            count += n
            return m.group(0).replace(attrs, new_attrs, 1)
        return m.group(0)

    return elem_re.sub(_repl, xml_text), count


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument('input', help='Path to fontsettings.xml')
    ap.add_argument('output', help='Path to write the modified fontsettings.xml')
    ap.add_argument('--target', default=DEFAULT_TARGET,
                    help=f'Font name to redirect fallbacks to (default: {DEFAULT_TARGET})')
    ap.add_argument('--sources', nargs='+', default=list(DEFAULT_SOURCES),
                    metavar='FONT',
                    help=f'Font names whose fallback should be rewritten '
                         f'(default: {" ".join(DEFAULT_SOURCES)})')
    args = ap.parse_args()

    inp = Path(args.input)
    if not inp.is_file():
        print(f"error: {inp} not found", file=sys.stderr)
        sys.exit(1)

    text = inp.read_text(encoding='utf-8')
    new_text, count = patch(text, args.sources, args.target)
    Path(args.output).write_text(new_text, encoding='utf-8')

    print(f"Rewrote {count} fallback reference(s) to point at '{args.target}'.")
    if count == 0:
        print("Warning: no substitutions were made. Verify that the source "
              "font names exist in this fontsettings.xml.", file=sys.stderr)


if __name__ == '__main__':
    main()
