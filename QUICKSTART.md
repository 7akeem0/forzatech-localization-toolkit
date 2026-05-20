# Quick Start

This walkthrough takes you from a fresh clone of this repository to a localized game install in 8 steps. It is intentionally generic — every step references your *script category* rather than a specific language.

## 0. Identify your script category

Pick the row that matches your target script. The choices propagate through later steps.

| Category | Examples | What you do differently |
|---|---|---|
| **A — LTR alphabetic** | Cyrillic, extended Latin, Greek, Vietnamese | Standard pipeline. Disable the LSB shift. No text reshaping. |
| **B — LTR complex** | Thai, Devanagari, Lao, Khmer, Burmese, Sinhala | Standard pipeline. Apply the LSB shift. No reshaping. Word-wrap by character count, not by space. |
| **C — RTL with joining** | Arabic, Persian, Urdu, Syriac | Generate Presentation Forms glyphs. Apply LSB shift and mesh extension. Preprocess strings: shape → reverse. |
| **D — RTL without joining** | Hebrew | Standard pipeline on base block. Apply LSB shift. Preprocess strings: reverse only. |

If your script is not listed, pick the row whose characteristics match: does the script connect adjacent letters (Arabic-like) or not (Latin-like)? Does it have above-and-below marks (Thai-like, Devanagari-like)? Read direction?

## 1. Set up the environment

```bash
python -m pip install -r requirements.txt
```

You will also need:

- A working copy of the game installed via Steam.
- A TrueType font (`.ttf`) covering your script's Unicode block. Open-license families: Noto Sans for most scripts, Noto Naskh / Noto Kufi for Arabic, Noto Sans Thai for Thai, etc.
- ~250 MB of free disk space for extracted game files during work.

## 2. Make backups before touching anything

The game install has three files we will be modifying. Make `.original` copies in place **before** the first run. If anything goes wrong, you can restore from these.

```
<game>/media/UI/Fonts.zip
<game>/media/UI.zip
<game>/media/Stripped/StringTables/EN.zip
<game>/media/Stripped/StringTables/GB.zip
```

See [`docs/install.md`](docs/install.md) for the full directory map and backup procedure.

## 3. Extract the original game files

You need three things from the game install:

1. **`fontsettings.xml`** and one font pair (`Horizon_A.vfont`, `Horizon_A.vfont0`) from inside `Fonts.zip`. Extract them with any zip tool.
2. **`EN.zip`** (the source string archive). Copy as-is — do not extract.
3. The path to `UI.zip` if you plan to modify UI layout (e.g. mirror panels for RTL).

Place these in a working folder of your choice.

## 4. Extract all strings to JSON for translation

```bash
python examples/01_extract_all_strings.py /path/to/EN.zip ./strings_json
```

This produces ~287 JSON files, one per string table. Each entry has `hash`, `key`, and `value`. Edit the `value` fields with your translations; **do not modify `hash` or `key`** — those identify each string to the engine.

Translation methodology is outside the scope of this toolkit. Use whatever workflow suits your team — human translators, professional services, machine translation, or a combination. Hand off the JSON files, get them back translated, continue here.

## 5. Generate font glyphs

Different categories need different invocations. Substitute `--range LO HI` arguments for the Unicode blocks your script uses.

**Category A (Cyrillic, extended Latin, Greek, ...):**

The font may already cover your script (`Horizon_RU_A.vfont` covers Cyrillic). Check first by extracting it and listing its codepoints:

```bash
python tools/vfont_codec.py Horizon_RU_A.vfont Horizon_RU_A.vfont0
```

If a few codepoints are missing (e.g. script-specific letters not in the base font), generate them on top of `Horizon_A` with the shift disabled:

```bash
python tools/build_font_from_ttf.py YourFont.ttf Horizon_A.new.vfont Horizon_A.new.vfont0 \
    --base Horizon_A.vfont --base0 Horizon_A.vfont0 \
    --range 0x0400 0x04FF \
    --shift-fraction 0
```

**Category B (Thai, Devanagari, Lao, ...):**

Generate the full base block. Keep the shift enabled:

```bash
python tools/build_font_from_ttf.py YourFont.ttf Horizon_A.new.vfont Horizon_A.new.vfont0 \
    --base Horizon_A.vfont --base0 Horizon_A.vfont0 \
    --range 0x0E00 0x0E7F
```

**Category C (Arabic, Persian, Urdu, ...):**

Generate both the base block and Presentation Forms B, with mesh extension enabled:

```bash
python tools/build_font_from_ttf.py YourFont.ttf Horizon_A.new.vfont Horizon_A.new.vfont0 \
    --base Horizon_A.vfont --base0 Horizon_A.vfont0 \
    --range 0x0600 0x06FF \
    --range 0xFE70 0xFEFF \
    --joining --ext 250
```

**Category D (Hebrew, ...):**

Generate the base block. Shift enabled, no mesh extension (no joining):

```bash
python tools/build_font_from_ttf.py YourFont.ttf Horizon_A.new.vfont Horizon_A.new.vfont0 \
    --base Horizon_A.vfont --base0 Horizon_A.vfont0 \
    --range 0x0590 0x05FF
```

The output is a `.vfont` and a `.vfont0` you will pack back into `Fonts.zip` in step 7.

## 6. Patch the font fallback chain

By default, `Horizon_B`, `Horizon_C`, and `Horizon_D` (bold and condensed weights) fall back to Cyrillic fonts that do not contain your new glyphs. Any string rendered through a bold or condensed style will display as tofu.

Extract `fontsettings.xml` from the original `Fonts.zip`, then run:

```bash
python tools/patch_fontsettings.py fontsettings.xml fontsettings.new.xml
```

This rewrites the fallback chain so that all weights resolve through `Horizon_A` (where you injected your new glyphs). See the tool's `--help` for advanced cases.

## 7. Repack `Fonts.zip`

Replace three files inside the original `Fonts.zip`:

- `Horizon_A.vfont` → your new version
- `Horizon_A.vfont0` → your new version
- `fontsettings.xml` → your patched version

`Fonts.zip` does **not** use the custom `0x1123` extra field that `UI.zip` does. Standard zip tools work fine:

```bash
cp Fonts.original.zip Fonts.new.zip
zip -j Fonts.new.zip Horizon_A.new.vfont Horizon_A.new.vfont0 fontsettings.new.xml
```

Rename inside the zip if needed (the entries should be plain `Horizon_A.vfont`, `Horizon_A.vfont0`, `fontsettings.xml` — no path prefix).

## 8. Inject translated strings

The injection script needs a small hook for script-specific text preprocessing. Open [`examples/02_modify_one_string.py`](examples/02_modify_one_string.py) and edit the `preprocess()` function:

| Category | What `preprocess()` should do |
|---|---|
| A — LTR alphabetic | `return value` (no change) |
| B — LTR complex | `return value` (no change) — but mind word-wrap behavior; see note below |
| C — RTL joining | `from arabic_reshaper import reshape; from bidi.algorithm import get_display; return get_display(reshape(value))` |
| D — RTL no-joining | `return value[::-1]` |

For category C/D you also typically want multi-line and soft-wrap handling. See [`docs/rtl_in_ltr_engines.md`](docs/rtl_in_ltr_engines.md) for the complete recipe.

For category B, the engine wraps text at spaces. Scripts without inter-word spaces (Thai, Khmer, Lao, ...) may render entire paragraphs as a single long line that overflows the panel. Pragmatic workarounds: insert a zero-width space (U+200B) at syllable boundaries during translation, or pre-wrap at a fixed character count by inserting `\n` directly.

Then run:

```bash
python examples/02_modify_one_string.py ./strings_json /path/to/EN.zip ./EN.new.zip
```

## 9. Install

Copy your modified files into the game install, **after** ensuring backups exist:

```bash
GAME=/path/to/SteamLibrary/steamapps/common/ForzaHorizon6

# Fonts
cp Fonts.new.zip                 "$GAME/media/UI/Fonts.zip"

# Strings — both EN.zip and GB.zip must be the same file
cp EN.new.zip                    "$GAME/media/Stripped/StringTables/EN.zip"
cp EN.new.zip                    "$GAME/media/Stripped/StringTables/GB.zip"
```

The engine reads `EN.zip` for the `en-US` locale and `GB.zip` for `en-GB`. Players on either setting must see the same translated content, so mirror the file.

## 10. Test in-game

Launch the game. Walk through:

1. Main menu (verifies basic text rendering and UI labels).
2. Settings → Language (set to whichever locale you targeted).
3. A short race or scripted scene (verifies dialogue and dynamic text).
4. The pause menu (a good place to see various font weights at once).

Common issues and where to look:

| Symptom | Likely cause | Reference |
|---|---|---|
| Tofu boxes (□) where text should be | Codepoint missing from font OR fallback chain wrong | [`docs/vfont_format.md`](docs/vfont_format.md), [`tools/patch_fontsettings.py`](tools/patch_fontsettings.py) |
| Text reads backwards | Preprocessing not applied OR multi-line wrap reverses line order | [`docs/rtl_in_ltr_engines.md`](docs/rtl_in_ltr_engines.md) |
| Last letter of each line clipped | Missing LSB shift on generated glyphs | [`docs/latin_lsb_convention.md`](docs/latin_lsb_convention.md) |
| Disconnected letters (RTL) | Mesh extension disabled OR insufficient | step 5 (`--ext` value) |
| Game crashes on launch | `UI.zip` modified without slot-preserving repack OR modified a silently-checked file | [`docs/ui_zip_repack.md`](docs/ui_zip_repack.md), [`docs/silent_integrity_checks.md`](docs/silent_integrity_checks.md) |
| Game launches but some specific UI element behaves wrong | Likely a silently-checked file (e.g. `InGame.str`) | [`docs/silent_integrity_checks.md`](docs/silent_integrity_checks.md) |

## 11. Iterate

Localization is iterative. Plan for several install-test-fix cycles. Backup your `EN.new.zip` and `Fonts.new.zip` after each successful test so you can roll back individual changes.

## What's intentionally not covered

This toolkit handles the engineering side of localization: file formats, fonts, text rendering, install layout. The following are out of scope:

- **Translation production.** Use your preferred methodology — human, machine, or hybrid. Output JSON files in the format example 01 produces; pipe them into example 02 when done.
- **Glossary and terminology consistency.** A function of your translation workflow, not the engine.
- **Online play impact.** Modifying client localization files does not affect server logic, but Steam's "Verify Integrity of Game Files" will revert all changes — plan accordingly.
- **Console builds.** Steam PC only.

## Next steps

- Skim [`STORY.md`](STORY.md) for the reverse-engineering background and why each design decision was made.
- Read [`docs/install.md`](docs/install.md) for the complete file layout.
- Read the document for your script category in depth before producing the final build:
  - **A/B/D**: [`docs/latin_lsb_convention.md`](docs/latin_lsb_convention.md)
  - **C**: [`docs/rtl_in_ltr_engines.md`](docs/rtl_in_ltr_engines.md) + the LSB doc above.
- Read [`docs/silent_integrity_checks.md`](docs/silent_integrity_checks.md) to know which files **not** to touch.
