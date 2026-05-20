# Game Install Layout

This document maps every file the toolkit reads from or writes to inside the game install.

## Default Steam install path

```
<SteamLibrary>/steamapps/common/ForzaHorizon6/
```

Where `<SteamLibrary>` is typically `C:/Program Files (x86)/Steam` or another drive configured in Steam.

## Files this toolkit interacts with

```
<game>/media/
├── UI/
│   ├── Fonts.zip                     ← extend with new glyphs (step 7 of quick start)
│   └── Fonts.zip.original            ← your backup
│
├── UI.zip                            ← modify only if changing UI layout (e.g. RTL panels)
├── UI.zip.original                   ← your backup
│
├── zipmanifest.xml                   ← do not touch (encrypted; suspected integrity source)
├── ziphashseeds.xml                  ← do not touch
│
└── Stripped/StringTables/
    ├── EN.zip                        ← inject translated strings here
    ├── EN.zip.original               ← your backup
    ├── GB.zip                        ← must mirror EN.zip after injection
    ├── GB.zip.original               ← your backup
    ├── BR.zip, JP.zip, ...           ← other locales (do not modify unless localizing those)
    └── *.zip.original                ← your backups
```

## What's inside each zip

### `Fonts.zip` (~16.6 MB)

Contains 85 entries:

| Pattern | Purpose |
|---|---|
| `Horizon_A.vfont` + `Horizon_A.vfont0` | Main regular weight (Latin baseline) |
| `Horizon_B.vfont` + `.vfont0` | Bold weight |
| `Horizon_C.vfont` + `.vfont0` | Condensed weight |
| `Horizon_D.vfont` + `.vfont0` | Alt condensed weight |
| `Horizon_A_tf.vfont` etc. | Small "title font" variants |
| `Horizon_RU_A/C/D` | Cyrillic variants |
| `Horizon_KO`, `Horizon_JP`, `Horizon_CHS`, `Horizon_CHT` | CJK fonts (multiple atlas pages each) |
| `DG1_*` through `DG5_*` | Dashboard gauge fonts (in-car displays) |
| `fontsettings.xml` | Per-locale font sets and fallback chains |

The default modification target is `Horizon_A`. After patching the fallback chain (step 6), every weight resolves through `Horizon_A`, so extending one font covers the entire UI.

`Fonts.zip` does **not** use the custom `0x1123` extra field. Standard zip tools (PowerShell `Compress-Archive`, Python `zipfile`, `7z`, command-line `zip`) all work.

### `UI.zip` (~2.5 MB)

Contains ~454 entries: 385 XAML files + 69 XML files. UI scene definitions, styles, resource dictionaries.

**Uses the custom `0x1123` extra field with 4 KB-aligned data offsets.** Standard zip tools strip the extras and crash the game. See [`ui_zip_repack.md`](ui_zip_repack.md) for the slot-preserving repack technique. Reference implementation in [`tools/ui_zip_patcher.py`](../tools/ui_zip_patcher.py).

Typical reasons to modify:

- Mirror panel layout for RTL scripts (change `DockPanel.Dock="Left"` to `"Right"` on speaker name boxes, etc.).
- Adjust text wrap behavior or panel widths for scripts that wrap differently.

Files in `Scenes/` modify cleanly. Files in `Resources/` are silently integrity-checked — see [`silent_integrity_checks.md`](silent_integrity_checks.md).

### `Stripped/StringTables/EN.zip` (~2.9 MB)

Contains 287 entries, each a `.str` binary file. See [`str_format.md`](str_format.md).

**Caveat:** one entry, `InGame.str`, has a silent integrity check separate from the normal CRC. Modifying it causes specific UI lookups to silently fail. The other 286 entries modify cleanly. See [`silent_integrity_checks.md`](silent_integrity_checks.md).

## Locale-to-zip mapping

The engine selects a zip based on the user's game language setting:

| Setting | Reads |
|---|---|
| en-US | `EN.zip` |
| en-GB | `GB.zip` |
| pt-BR | `BR.zip` |
| de-DE | `DE.zip` |
| ... | ... (24 locales total) |

`EN.zip` and `GB.zip` are byte-identical in the shipping game. After modification, you **must mirror** them — copy your modified `EN.zip` to `GB.zip` after every rebuild. Players whose Steam language is English (US) read `EN.zip`; players on English (UK) read `GB.zip`. Both should see your translation.

To target a non-English locale instead (e.g. replace Portuguese-Brazil with your translation), modify `BR.zip` instead of `EN.zip` and instruct your users to set their game language to Portuguese (Brazil). This is sometimes preferable because users who legitimately want English remain unaffected.

## Backup discipline

Before the first modification, copy every file you might touch to a `.original` sibling **in place**, in the game install directory. This makes restoration a one-line file copy regardless of what goes wrong.

```bash
GAME=/path/to/SteamLibrary/steamapps/common/ForzaHorizon6/media

cp "$GAME/UI/Fonts.zip"                       "$GAME/UI/Fonts.zip.original"
cp "$GAME/UI.zip"                             "$GAME/UI.zip.original"
cp "$GAME/Stripped/StringTables/EN.zip"       "$GAME/Stripped/StringTables/EN.zip.original"
cp "$GAME/Stripped/StringTables/GB.zip"       "$GAME/Stripped/StringTables/GB.zip.original"
```

Verify the backups exist before modifying anything:

```bash
ls -la "$GAME/UI/"*.original "$GAME/"*.original "$GAME/Stripped/StringTables/"*.original
```

## Restoring from backup

```bash
GAME=/path/to/SteamLibrary/steamapps/common/ForzaHorizon6/media
cp "$GAME/UI/Fonts.zip.original"                 "$GAME/UI/Fonts.zip"
cp "$GAME/UI.zip.original"                       "$GAME/UI.zip"
cp "$GAME/Stripped/StringTables/EN.zip.original" "$GAME/Stripped/StringTables/EN.zip"
cp "$GAME/Stripped/StringTables/GB.zip.original" "$GAME/Stripped/StringTables/GB.zip"
```

## Steam "Verify Integrity of Game Files"

Will overwrite every modified file with the original from Steam's content servers. If your players run Verify Integrity (often suggested by Steam Support for any unrelated issue), they will lose your localization until they re-install it. Document this clearly in your distribution.

The Verify operation does not delete `.original` backup siblings — those persist because Steam doesn't know about them.

## Game updates

When the publisher patches the game, modified files in this layout are often overwritten or invalidated. After every game update:

1. Steam pulls fresh `Fonts.zip`, `UI.zip`, `EN.zip`, `GB.zip` from servers.
2. Re-run the toolkit against the new originals to regenerate your modified versions.
3. Diff against your previous build to identify new strings (added by the patch) that need translation.
4. Reinstall.

The toolkit handles this naturally — every script reads from a source file path, so pointing it at the post-patch originals produces a post-patch localization.
