# The Reverse-Engineering Story

A technical case study of how ForzaTech's text and font subsystems were cracked. This document is narrative, not specification — for the formal specs, see `docs/`.

## Starting state

Forza Horizon 6 shipped on Steam in May 2026. The game ships with 24 official languages. None of them are Arabic. None are Thai. None are Ukrainian. The publisher has no announced plans to add any.

The game install contains, among many other things:

```
media/Stripped/StringTables/
    EN.zip                  ~2.9 MB
    JP.zip
    BR.zip
    ... (24 languages total)

media/UI/Fonts.zip          ~16.6 MB
media/UI.zip                ~2.5 MB
```

The `*.zip` files are standard PKZIP archives — every entry begins with the `50 4B 03 04` signature. They open in any zip viewer. Inside `EN.zip` are 287 files with `.str` extensions, none of which are a recognized format. Inside `Fonts.zip` are 85 files with `.vfont` and `.vfont0` extensions, also unrecognized. `UI.zip` contains XAML files in plain text that look like WPF UI definitions.

A search for prior reverse-engineering work returned a 2022 Nexus Mods community thread requesting tools to modify ForzaTech fonts. No public tools existed. No specs. No prior work to build on.

## Step 1: The `.str` format

The smallest `.str` file is 215 bytes. Opening it in a hex viewer:

```
00000000: 00 08 43 61 6c 65 6e 64  61 72 00 00 00 00 00 00  ..Calendar......
00000010: 00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  ................
...
00000080: 8c 00 00 00 8c 00 00 00  c4 00 00 00 38 00 00 00  ............8...
00000090: 24 00 00 00 04 00 00 00  ...
```

A magic `00 08`. A string `Calendar` (the table name). A wide zero-padded region. Then at offset `0x80`, three little-endian `u32`s: `0x8C, 0x8C, 0xC4`. Then more structure.

The pattern repeated across all 287 files: magic, name, padding to `0x80`, three `u32`s. The first two were constants (`0x8C`). The third varied per file. A pattern like that is almost always an offset.

Hypothesis: header at `0x00..0x8C`, two sections starting at `0x8C` and the third-`u32` offset. The structure of each section: more `u32`s, then 8-byte entries, then a blob of null-terminated strings.

Within a day of probing, the format yielded. Each section had a 12-byte header (`section_size`, `blob_size`, `entry_count`), an entry array of `(u32 hash, u32 blob_offset)` pairs, and a UTF-8 blob.

The proof of correctness was byte-identical roundtrip: parse a file into Python data structures, write it back out, compare bytes. The parser had to be exactly right or the comparison would fail. Across all 287 files of `EN.zip`, all 287 of `JP.zip`, all 287 of every language ZIP — the roundtrip passed for every single file.

The format was solved. Now translation could happen.

## Step 2: The first failure — tofu

Inject Arabic strings into a few of the `.str` files. Repack into a new `EN.zip`. Copy to the game install. Launch.

Result: every Arabic character renders as an empty rectangle. The `.notdef` glyph. The engine accepted the UTF-8, decoded it correctly (the box count matched the character count), and tried to render each codepoint — but the font atlas had no Arabic glyphs.

This was expected. None of the 24 shipping languages need Arabic codepoints, so the fonts don't have them. The font atlas would need to be extended.

The 16 MB `Fonts.zip` was about to become the project's main obstacle.

## Step 3: The `.vfont` format — first attempt

`Horizon_A.vfont` is 168 KB. The first 16 bytes are the ASCII string `Horizon_A` zero-padded. Then a long zero-padded region. Then at offset `0x80`, `0x02000000` (`= 0x00000002` little-endian). Then more structure.

The first attempt at decoding identified some header fields but got the glyph record structure wrong. The hypothesis at the time: each glyph record was 36 bytes containing `(codepoint, w, h, ...)` where `w` and `h` were bounding-box dimensions.

A glyph relabeling experiment seemed to confirm this: relabel some Latin codepoints to Arabic codepoints in the records, repack, install. In-game, Latin letter shapes appeared at Arabic codepoint positions. The codepoint lookup worked.

But the experiment was misleading. The records *were* 36 bytes — that part was right. But `w` and `h` were not bbox dimensions. That misinterpretation would cost a session of work later, when the first real Arabic glyphs were injected and rendered as fragmented seagull-shaped triangles spilling across button widths.

## Step 4: The `.vfont0` mystery

`Horizon_A.vfont0` is 340 KB. The first 12 bytes look like a small header: `(0x1F, 0x28, 0x48)` = `(31, 40, 72)`. The 31 matched a count field in the `.vfont`. The 40 and 72 matched a separate field that looked like cell dimensions.

So the file was a 31-cell atlas, 40 × 72 pixels per cell? At 1 byte per pixel that's 31 × 40 × 72 = 89,280 bytes. The file is 340 KB. Not even close.

A few hypotheses tried and discarded: raw L8 grayscale at various dimensions, BC4 compressed atlas at 4 bpp, BC3, BC7. All produced noise, not glyphs. Sizes didn't align to any uniform mosaic.

The breakthrough was noticing that the `atlas_off` field in each glyph record varied by exactly the right amount to be a per-glyph variable-size blob offset, not a uniform atlas coordinate. Subtracting consecutive `atlas_off` values gave per-glyph sizes ranging from 80 bytes to 2 KB. That made no sense for a bitmap atlas.

Then the first 12 bytes of each blob were extracted and dumped: every blob started with what looked like `(codepoint, w, h)` matching the corresponding `.vfont` record. The blobs were per-glyph, not per-atlas-cell.

The remaining bytes after that 12-byte header: not pixels. They were too sparse — most glyphs had hundreds, not thousands, of bytes of payload. And there were no atlas coordinates to be found anywhere.

Looking at half-floats: each pair of bytes interpreted as `float16` produced values in the range `[-2, +2]`. Plotting these as 2D points... they formed glyph shapes. Recognizable digit outlines.

The blobs were **triangulated mesh data**, not bitmap. Each glyph was stored as a polygon mesh: a list of vertices and a list of triangle indices. The pixel shader identifiers visible in the executable confirmed the technique: `AVUI_PS_SDFFont` and `AVUI_PS_MSDFFont` are GPU font rendering pipelines in the Loop-Blinn / Slug family.

## Step 5: Generating new glyphs

With the format understood, the pipeline became clear:

```
TTF outline → contour subdivision → polygon tessellation →
vertex/index mesh → encode as float16x4 + u16 → blob bytes
```

The first injection of real Arabic glyphs from `Noto Kufi Arabic.ttf` rendered in-game. The shapes were recognizably Arabic letters. They had the correct vertical orientation. They were at the correct baseline.

But they were drawn in **left-to-right order** — the engine treats codepoints sequentially regardless of script. For Arabic, this meant the visual order was reversed: a reader sees `م ت ا ب ع ة` left-to-right instead of `متابعة` right-to-left.

The fix was offline preprocessing: reshape the base Arabic into Presentation Forms B (substituting connected variants based on neighbor context), then reverse the entire string. The engine then drew the reversed string LTR, which visually rendered as correct RTL.

Arabic letters appeared. But they were **isolated forms**, not connected. The dots above and below dotted letters (ب ت ث ج خ ن ي) were missing.

## Step 6: Dots, marks, and topology

`mapbox-earcut`, the Python polygon tessellation library, treats every contour after the first as a hole — regardless of winding order. Arabic letters with dots are stored in the TTF as multiple separate contours: the letter body plus one or more dot circles. earcut was subtracting the dots from the body.

The standard TTF tessellation approach is topology-aware contour classification:

1. For each contour `A`, compute its centroid.
2. Test whether `A`'s centroid is inside polygon `B` for every other contour `B`.
3. `depth[A]` = number of contours containing `A`.
4. Even depth → outer polygon (draw filled).
5. Odd depth → hole (subtract from parent).
6. Group each outer with its direct child holes; tessellate each group separately; merge all resulting triangles.

After this fix, 60% of generated glyphs had multiple polygon groups. Dots rendered. Letters with internal holes (the medial-`ja` curl, the final-`waw` bowl) rendered with their interiors preserved.

## Step 7: The connection problem

Generated Arabic glyphs rendered correctly individually but with visible hairline gaps between connected letters. The natural overlap between consecutive Presentation Forms glyphs is ~20 font units (≈0.6 px at typical UI text size). This is enough for SDF blending in a proper Arabic shaper but not enough for plain polygon fill with anti-aliased polygon edges.

A failed experiment: tighten the per-glyph advance width `f1`. Result: rendering became worse, not better. The `f1` field appears to influence more than just cursor advancement; modifying it from FreeType's reported value breaks something else. The field's full semantics remain unknown.

The working approach was **mesh extension**: for each joining-form glyph (initial / medial / final), append a baseline rectangle that extends 250 font units past the natural geometry into the adjacent letter's space. The rectangle is a separate quad (4 vertices, 2 triangles) added to the glyph's mesh.

Direction depends on form:
- Initial form — extends *left* (toward the next letter, visually after reversal).
- Medial form — extends both *left* and *right*.
- Final form — extends *right*.
- Isolated form — no extension.

Form detection uses `unicodedata.name(cp)` — the Unicode standard's glyph names contain literal substrings `INITIAL FORM`, `MEDIAL FORM`, `FINAL FORM`, `ISOLATED FORM` for every PFB-B codepoint.

The connection problem was solved. Letters bridged correctly without visible seams.

## Step 8: The font that wasn't enough

With Arabic glyphs working in `Horizon_A.vfont`, most strings rendered. But many strings still showed tofu. The pattern: the *first time* a string appeared, it rendered correctly. The same string later, in a different UI element, sometimes rendered as boxes.

The investigation took most of a session. The cause was font weights.

The game uses four font weights: `Horizon_A` (regular), `Horizon_B` (bold), `Horizon_C` and `D` (condensed). The XAML styles route different UI elements to different weights. We had only extended `Horizon_A`. Strings rendered through styles that requested `Horizon_B/C/D` were looking up Arabic codepoints in fonts that didn't have them.

In a sane fallback chain, `Horizon_B` would fall through to `Horizon_A` for missing codepoints. The actual chain in `fontsettings.xml`:

```xml
<FontName name="Horizon_B" fallback="Horizon_RU_A" />
```

The fallback for the bold weight was `Horizon_RU_A` — the Russian Cyrillic font. Which also has no Arabic. Which had no further fallback. The engine ran out of fallbacks and rendered the `.notdef` box.

Fix: rewrite the fallback chains so `Horizon_B`, `Horizon_C`, `Horizon_D` all fall back to `Horizon_A` (where the Arabic glyphs were). Done in five locale blocks of `fontsettings.xml`.

## Step 9: The `UI.zip` crash

After fixing the font fallback chain, the visual layout was still wrong. Arabic dialogue text rendered correctly, but the *speaker name box* — the small label on the side of dialogue subtitles — sat on the left side of the screen instead of the right. For RTL, it should be on the right.

The fix was a one-character XAML change: in `Scenes/Anthem/A_NotificationLayer.xaml`, change `DockPanel.Dock="Left"` to `Dock="Right"` on a single `StackPanel`.

Editing the XAML, repacking `UI.zip`, copying to the game install, launching:

**The game crashed before reaching the main menu.**

Reverting to the original `UI.zip`: game runs. Re-applying the patch: game crashes. The crash was tied to *any* modification of `UI.zip`, even a byte-identical recompress.

`UI.zip` opens as a standard PKZIP. Every entry has the right signatures. The central directory parses cleanly. But there's an oddity: every Local File Header has an extra field of variable size — pure zero bytes, sometimes 1000+ bytes per entry. The Central Directory has a 4-byte extra with ID `0x1123` carrying what looked like an offset value.

The hypothesis that cost time: the `0x1123` extra was a checksum or hash. The engine validated it. Modifying any entry recomputed the offset somehow, which broke validation.

The hypothesis was wrong. The truth came from dumping every entry's actual data offset (the byte position in the zip where compressed data starts):

```
AnthemApp.xaml:                 data_off = 0x00001000 (4096)
A_NotificationLayer.xaml:       data_off = 0x00169000
... and so on for all 454 entries
```

Every data offset is **4 KB-aligned**. The `0x1123` extra in the CD encodes that exact aligned offset. The variable-length zero padding in the LFH is sized to push the start of compressed data to the next 4 KB boundary.

4 KB is a typical OS page size. The engine memory-maps `UI.zip` and reads each entry's compressed data directly from its pre-computed offset, bypassing the central directory entirely after the initial parse.

`0x1123` is not a checksum. It's a layout hint for `mmap()`.

The crash happens because standard zip repackers don't preserve the LFH zero padding. Without it, data offsets shift by hundreds or thousands of bytes. The engine's pre-computed addresses still point at the old locations, which now contain random bytes from the next entry's deflate stream. Crash.

## Step 10: Slot-preserving repack

The fix: don't repack. Patch.

For one modified entry:

1. Compress the new content with zopfli (which produces ~5% smaller output than zlib at maximum level).
2. Verify the new compressed size fits in the original `CompressedSize` slot.
3. Patch CRC32 and CompressedSize in both the LFH and CD entry.
4. Overwrite the deflate payload starting at the original data offset.
5. Zero-pad from end-of-new-deflate to end-of-original-slot.

File size: unchanged. Every entry's data offset: unchanged. Every `0x1123` value: unchanged. The engine's mmap addresses still resolve correctly.

The technique works. The DockPanel patch installed, the speaker box moved to the right, the game launched.

## Step 11: The clip

The Arabic localization shipped. It worked. Most things rendered correctly. But there was a long-standing visual bug that nobody could pin down for several sessions: the leftmost letter of certain badges and labels rendered with its left half vertically cut off. The cut was clean — a straight vertical edge. As if a scissor had cut through the glyph at its midline.

The bug existed from the very first install. It pre-dated every font change, every alignment fix, every mesh-extension calibration. It happened in `Horizon_A` (Naskh), then again after the swap to Kufi, then again after every mesh tweak. Every hypothesis missed.

Five hypotheses were tested and disproven:
- LSB padding on individual form types — broke other words.
- Italic skew transform — removing it didn't help.
- `MaxWidth` tuning on the badge — didn't help.
- `FlowDirection` LTR on the badge — didn't help.
- Stripping the layout transform on the affected scene — didn't help.

The breakthrough was a per-glyph mesh dump. Latin glyphs were measured to have `min_x ≈ +0.51` in normalized em coordinates. Generated Arabic glyphs had `min_x ≈ +0.065`. The engine's text-line clip rect was assuming a Latin-style left-side bearing — that every glyph reserves about half an em of space on its left side for ink overshoot. Glyphs that violate this convention have their leftmost ink extending past the clip rect's left edge. The clip cuts through them.

The fix: shift every generated glyph's vertex X coordinates by `+UPM × 0.6` font units before normalization. After shift, `min_x ≈ +0.5`, matching Latin convention. The clip stops cutting.

This is the [Latin LSB convention](docs/latin_lsb_convention.md). It applies to any script generated with naive geometry: Arabic, Thai, Devanagari, etc. Latin and Cyrillic from standard TTFs come pre-shifted; other scripts do not.

## What's documented now

All of the above is captured in `docs/` as formal specifications. The pipeline as it stands today produces a working, polished localization for any script the source TTF can cover. The remaining unknowns — the V-channel shader semantics, the `f1` advance-field semantics, the `zipmanifest.xml` integrity check — affect quality polish, not feasibility.

The `.str`, `.vfont`, `.vfont0`, and `UI.zip` formats are solved. ForzaTech is no longer opaque.
