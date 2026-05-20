# Silent Integrity Checks

Some files in the game's media tree are validated by the engine at load time beyond the standard zip CRC. Modifying them — **even with a byte-identical recompress and correct CRC** — causes the game to silently reject the change. Symptoms range from a missing UI element to a launch crash.

This document catalogues the files known to be checked and the files known to be safe to modify. The validation mechanism itself has not been fully reverse-engineered; suspected sources are `media/zipmanifest.xml` (encrypted, ~1.5 MB) and possibly an internal in-binary hash table.

## Known silent checks (DO NOT modify)

### `media/Stripped/StringTables/EN.zip` → `InGame.str`

Tested behavior: even a no-op recompress of `InGame.str` (zopfli with verified-identical decompressed output and correct CRC32) causes specific UI lookups to silently fail. Specifically, the speaker-name lookup `InGame.IDS_Subtitles_SpeakerCharacterName` returns empty. The game itself continues to run.

**Implication:** other strings in `InGame.str` may have hashed integrity bound to the file itself, not just the deflate stream. Avoid modifying `InGame.str` entirely. To change a format string referenced from this table, modify the consuming XAML instead (replace `{local:Loc Key}` references with literal strings in the relevant Scene).

This check appears to be **scoped to `InGame.str`**. Other `.str` files (`Calendar.str`, `Dialogue.str`, `GameStrings.str`, ...) within `EN.zip` modify cleanly — the entire localization mod is built on modifying 273 of them. The boundary is per-`.str`, not per-zip.

### `media/UI.zip` → `Resources/Anthem/Global_TextStyles.xaml`

Tested behavior: any modification crashes the game during startup, before the main menu appears. Confirmed with both content edits and byte-identical recompress with correct CRC.

The same UI.zip can be modified freely in `Scenes/Anthem/*.xaml` files — those route through a different code path that does not validate.

**Implication:** style definitions are likely bound to a content hash referenced from compiled code or from `zipmanifest.xml`. Style changes must be achieved by overriding the style downstream (inline attributes in a Scene that uses the style), not by editing the style definition.

## Known safe modifications

| File pattern | Notes |
|---|---|
| `media/Stripped/StringTables/*.zip` → `*.str` (except `InGame.str`) | All 286 other `.str` files modify cleanly. UTF-8 string content of any length up to ~2 KB tested. |
| `media/UI/Fonts.zip` → `*.vfont` / `*.vfont0` | Font files modify cleanly. Adding records (with sort + 0xFFFD-last) works without validation. |
| `media/UI/Fonts.zip` → `fontsettings.xml` | Locale and fallback-chain edits modify cleanly. |
| `media/UI.zip` → `Scenes/Anthem/*.xaml` | Scene XAML can be modified to change layout, alignment, colors, dock direction. Slot-preserving repack required. |
| `media/UI.zip` → `Scenes/*/*.xaml` | All non-`Resources` scene files appear modifiable. |

## Unknown / not yet tested

- `media/UI.zip` → `Resources/*` except `Global_TextStyles.xaml` — untested. May or may not be checked. Test with a length-preserving no-op patch before relying on a real modification.
- `media/zipmanifest.xml` — encrypted, ~1.5 MB. First 4 bytes `D6 9F 4E 72` do not match standard zlib/lz4/zip magic. Likely the source of the silent checks; reverse-engineering its format would unlock `InGame.str` and `Global_TextStyles.xaml` modifications.
- `media/ziphashseeds.xml` — plaintext, 225 bytes. References only `tracks/hendrix/bin/` and `tracks/brio/bin/`. Not relevant to UI/text.

## Diagnostic technique

To determine whether a file you want to modify is silently checked:

1. Make a length-preserving no-op patch: recompress the file with zopfli at maximum iterations, verify the decompressed bytes match the original exactly.
2. Patch CRC32 and CompressedSize in the LFH and CD as described in [`ui_zip_repack.md`](ui_zip_repack.md).
3. Launch the game.
4. If the game crashes or the UI element backed by this file misbehaves, the file is silently checked. Revert and find another approach.

This test isolates "engine validates the file" from "the modification is wrong" — by ensuring the modification is a true no-op, any failure must be at the validation layer.

A useful confirmation: change a single byte in a XAML comment of a `Scenes/Anthem/*.xaml` file. If the game launches and the UI works, the slot-preserving technique is correct. If it doesn't, the technique itself has a bug. This test should pass — it's been verified on at least one file per session.
