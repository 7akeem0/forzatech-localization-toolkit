"""
Example 03: Build a custom .vfont + .vfont0 from a TrueType font.

This is the highest-level wrapper around tools/build_font_from_ttf.py.
It demonstrates the three common cases:

    1. LTR alphabet (Cyrillic, Latin extensions, Greek):
       just specify the codepoint range.

    2. Complex LTR (Thai, Devanagari):
       same as LTR alphabet — the topology-aware tessellation in
       build_font_from_ttf.py handles marks and holes automatically.

    3. RTL with joining (Arabic, Syriac):
       target the Presentation Forms B range (U+FE70..U+FEFF) and
       pass --joining + --ext to enable baseline mesh extension that
       bridges between connected letters.

The script does NOT replace any glyphs the base font already has —
it adds new records and overwrites only the codepoints you request.
The existing Latin glyphs in Horizon_A.vfont remain untouched, so
the game's English UI continues to render correctly.

Usage examples:

    # Cyrillic (Ukrainian, Russian, Bulgarian, ...):
    python 03_build_custom_font.py NotoSans.ttf Horizon_A.new.vfont Horizon_A.new.vfont0 \\
        --base Horizon_A.vfont --base0 Horizon_A.vfont0 \\
        --range 0x0400 0x04FF

    # Thai:
    python 03_build_custom_font.py NotoSansThai.ttf Horizon_A.new.vfont Horizon_A.new.vfont0 \\
        --base Horizon_A.vfont --base0 Horizon_A.vfont0 \\
        --range 0x0E00 0x0E7F

    # Arabic (covering Presentation Forms B + base):
    python 03_build_custom_font.py NotoNaskhArabic.ttf Horizon_A.new.vfont Horizon_A.new.vfont0 \\
        --base Horizon_A.vfont --base0 Horizon_A.vfont0 \\
        --range 0x0600 0x06FF --range 0xFE70 0xFEFF \\
        --joining --ext 250

After running, pack the new .vfont and .vfont0 into Fonts.zip in place
of the originals. See README quick start for full installation.
"""

# This example is a documentation wrapper; the real work happens in
# tools/build_font_from_ttf.py. Re-export its main() so you can invoke
# either script interchangeably.

from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tools'))
from build_font_from_ttf import main  # noqa: E402


if __name__ == '__main__':
    main()
