# Rendering RTL Scripts in an LTR Engine

ForzaTech has no Bidirectional or shaping support. It renders text strictly left-to-right in codepoint order. For RTL scripts (Arabic, Hebrew, Persian, Urdu, Syriac), the strings must be preprocessed offline so that the codepoints already appear in the order the engine will draw them.

This document is the general approach. Script-specific details (e.g. Arabic Presentation Forms B vs. Hebrew without joining) require per-script tuning.

## The two transformations

To take logical-order RTL text and render it correctly through an LTR engine, two transformations are required:

1. **Script shaping** — for scripts with contextual letterforms (Arabic, Syriac), replace each base letter with its appropriate connected form (initial / medial / final / isolated) based on its neighbors. The Unicode Presentation Forms blocks (`U+FB50..U+FDFF` Arabic A, `U+FE70..U+FEFF` Arabic B, `U+FB1D..U+FB4F` Hebrew) contain pre-shaped variants for direct substitution. For Hebrew, this step is essentially a no-op since Hebrew has no contextual shaping.

2. **Visual reordering** — reverse the codepoint sequence so the visually-rightmost (logically-first) character is at the start of the string. The LTR engine draws codepoint 0 leftmost, codepoint N-1 rightmost; visual-order = reversed logical-order.

In Python:

```python
import arabic_reshaper

def prep_arabic(s: str) -> str:
    # Step 1: shape — convert base Arabic to Presentation Forms B
    shaped = arabic_reshaper.reshape(s)
    # Step 2: reverse — for the LTR engine to draw rightmost-first
    return shaped[::-1]
```

For Hebrew:

```python
def prep_hebrew(s: str) -> str:
    return s[::-1]   # no shaping needed; just reverse
```

## Why `arabic_reshaper` is needed

`arabic_reshaper.reshape("متابعة")` converts the input from base Arabic codepoints (`U+0645 U+062A U+0627 U+0628 U+0639 U+0629`) into Presentation Forms B (`U+FEE3 U+FE98 U+FE8E U+FE91 U+FECC U+FE94`). The font only contains presentation-form glyphs; without reshape, each base codepoint either renders as its isolated form (looking disconnected) or falls through to the `.notdef` box.

This works because the font generation pipeline targets the PFB range (`U+FE70..U+FEFF` ≈ 140 codepoints covering all four forms of every Arabic letter), not the base Arabic range. See [`build_font_from_ttf.py`](../tools/build_font_from_ttf.py) and the example in `examples/03_build_custom_font.py`.

## Bidi for mixed-direction content

For strings containing both RTL text and LTR fragments (e.g. Latin proper names, numbers, English car names embedded in Arabic dialogue), pure-reverse-after-reshape is wrong — the LTR fragments will appear reversed inside the Arabic context.

The Unicode Bidirectional Algorithm (UAX #9) handles this correctly. The `python-bidi` library implements it:

```python
import arabic_reshaper
from bidi.algorithm import get_display

def prep_arabic_mixed(s: str) -> str:
    shaped = arabic_reshaper.reshape(s)
    return get_display(shaped)
```

`get_display` does both the resolution of bidi levels and the reversal in one step. Use this approach for any string that may contain Latin runs, numbers, or markup tags.

## Multi-line text

If `prep()` runs over a string containing `\n`, the global reversal swaps line order along with character order. Result: paragraphs read bottom-to-top.

Fix: split on `\n` first, prep each line independently, rejoin with `\n` (no further reversal):

```python
def prep_multiline(s: str) -> str:
    lines = s.split('\n')
    return '\n'.join(prep_arabic_mixed(line) for line in lines)
```

## Word wrapping

Single-line `.str` content that the engine word-wraps onto multiple visual lines exhibits the same bottom-to-top problem: the reversed string, when wrapped, places the logically-first words on the lowest visual line.

Fix: soft-wrap the *logical* string before reshape, then prep each pre-wrapped line:

```python
def soft_wrap(s: str, width: int) -> list[str]:
    if len(s) <= width: return [s]
    words = s.split(' ')
    lines, cur = [], ''
    for w in words:
        cand = w if not cur else cur + ' ' + w
        if len(cand) <= width or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines

def prep_with_wrap(s: str, width: int) -> str:
    lines = []
    for chunk in s.split('\n'):
        for line in soft_wrap(chunk, width):
            lines.append(prep_arabic_mixed(line))
    return '\n'.join(lines)
```

The `width` value depends on the target UI panel — narrow tooltips need `~22`, wide dialogue panels can use `~50`. Choosing one global value sacrifices either dialogue spaciousness or tooltip fit; an injection script can per-string-type widths if the source data carries that classification.

## Atomic placeholders

Markup like `[BOLD:name]`, `{0}`, `[HIGHLIGHT:text]` must remain intact through wrap and reshape. A wrap algorithm that splits on spaces can break `[BOLD:Two Words]` across lines.

The standard trick is to mask spaces inside placeholders with a non-breaking space before wrapping, then restore them:

```python
import re

PLACEHOLDER_RE = re.compile(r'(\{[^}]+\}|\[[^\]]+\]|<[^>]+>|\\[nrt]|%[sdfox])')
NBSP = '\u00a0'

def soft_wrap_atomic(s: str, width: int) -> list[str]:
    masked = PLACEHOLDER_RE.sub(lambda m: m.group(0).replace(' ', NBSP), s)
    # ... existing soft_wrap logic on masked ...
    # restore NBSPs to spaces inside each output line
```

For markup containing translatable text (e.g. `[BOLD:Mei]`), the content inside the tag should be reshaped and reversed along with surrounding text, but the tag delimiters themselves must remain Latin:

```python
WRAPPER_CONTENT_RE = re.compile(r'^(\[[A-Za-z_]+:)(.*)(\])$')

def reshape_wrapper(s: str) -> str:
    m = WRAPPER_CONTENT_RE.match(s)
    if not m or not has_rtl(m.group(2)):
        return s
    inner = get_display(arabic_reshaper.reshape(m.group(2)))
    return m.group(1) + inner + m.group(3)
```

## Engine layout still assumes LTR

Even after the text is correctly reversed and rendered visually right-to-left, the surrounding UI containers still flow LTR by default. Speaker boxes, panel anchors, and DockPanel directions in the XAML may need editing to match the RTL reading direction.

See [`ui_zip_repack.md`](ui_zip_repack.md) for the technique to modify Scene XAML files; the common edit for a dialogue panel is changing `DockPanel.Dock="Left"` to `"Right"` on the speaker-name `StackPanel`.

## Verifying the result in-game

A common failure mode is "everything looks right offline, but in-game some words read backwards." The cause is usually a mix of preprocessed and unprocessed strings in the same `.str`, or a string that the engine wraps differently than the offline soft-wrap assumed.

A useful diagnostic: extract `EN.zip` after injection and scan for any string still containing base Arabic codepoints (`U+0600..U+06FF`). After a correct prep pass, there should be zero such strings — everything should be in the PFB range or in the Latin range.

```python
import re
BASE_ARABIC = re.compile(r'[\u0600-\u06FF]')
# ... iterate every injected string and assert BASE_ARABIC.search(s) is None
```
