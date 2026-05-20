# ForzaTech Localization Toolkit

> أول هندسة عكسية علنية لنظام النصوص والخطوط في محرك **ForzaTech**، المحرك الخاص بسلسلة Forza Horizon (4/5/6) و Forza Motorsport. هذي الأدوات تخليك تستخرج وتعدّل وتعيد بناء بيانات اللوكلايزيشن لأي لعبة مبنية على المحرك.

---

## وش هذا المشروع

ForzaTech هو المحرك اللي تستخدمه Playground Games و Turn 10 Studios في سلسلة Forza. لين الآن، ما في توثيق علني لطريقة تخزين اللعبة لنصوصها (`.str`)، أو خطوطها (`.vfont` / `.vfont0`)، أو كيف أرشيف الـUI (`UI.zip`) يحافظ على الـmemory-mapped alignment بعد التعديل.

هذا المستودع يوثّق التنسيقات الثنائية ويوفّر أدوات Python لقراءتها وكتابتها، مع تحقّق roundtrip بايت-باي-بايت على ملفات اللعبة الأصلية.

التطبيق المرجعي لهذا الشغل: [أول مود تعريب كامل للعبة Forza Horizon 6](https://www.nexusmods.com/forzahorizon6/mods/65)، منشور على Nexus Mods. المود نفسه خارج نطاق هذا المستودع — اللي موثّق هنا هو الشغل الهندسي اللي خلّى المود ممكن.

---

## وش تم فكّه

| النظام الفرعي | الحالة | التحقّق |
|---|---|---|
| تنسيق `.str` الثنائي (جدول النصوص) | موثّق بالكامل | roundtrip بايت-باي-بايت على ٢٨٧ ملف × ٢٤ لغة |
| `.vfont` (metrics + slot table) | موثّق بالكامل | roundtrip بايت-باي-بايت على ٢٠/٢٠ خط |
| `.vfont0` (mesh blobs: vertex + index) | موثّق بالكامل | roundtrip بايت-باي-بايت على ١٩/٢٠ خط |
| `UI.zip` custom `0x1123` extra field | موثّق | دلالة الحقل مؤكّدة على ٤٥٤ entry |
| Slot-preserving PKZIP repack | موثّق + أداة | ضرورية لأي تعديل على UI بدون كسر الـmemory-mapped offsets |
| Silent integrity checks (فهرس) | موثّق | قائمة الملفات اللي ما تنفع تتعدّل حتى مع CRC صحيح |
| Latin-LSB glyph convention | موثّق | افتراض المحرك اللي يأثّر على كل الـscripts غير اللاتينية |

---

## البدء السريع

```bash
git clone https://github.com/<user>/forzatech-localization-toolkit
cd forzatech-localization-toolkit
pip install -r requirements.txt
```

استخراج كل النصوص من ملف لغة:

```bash
python examples/01_extract_all_strings.py /path/to/EN.zip ./output_json
```

إعادة بناء جدول نصوص معدّل:

```bash
python examples/02_modify_one_string.py ./output_json /path/to/EN.zip
```

بناء خط مخصّص من TTF:

```bash
python examples/03_build_custom_font.py NotoSans.ttf Horizon_Custom.vfont
```

شوف `examples/` للأمثلة القابلة للتشغيل، و `docs/` للمواصفات الكاملة.

---

## التوثيق

| الملف | الموضوع |
|---|---|
| [`docs/str_format.md`](docs/str_format.md) | تنسيق `.str` الثنائي (header، sections، hash-linked key↔value) |
| [`docs/vfont_format.md`](docs/vfont_format.md) | `.vfont`: slot table، glyph records، kerning trailer، font fingerprint tags |
| [`docs/vfont0_format.md`](docs/vfont0_format.md) | `.vfont0`: atlas prelude، per-glyph blob، vertex/index encoding |
| [`docs/ui_zip_repack.md`](docs/ui_zip_repack.md) | `0x1123` extra field، 4 KB alignment، slot-preserving repack algorithm |
| [`docs/silent_integrity_checks.md`](docs/silent_integrity_checks.md) | الملفات اللي المحرك يتحقّق منها بطرق غير CRC؛ وش ينفع وش ما ينفع |
| [`docs/latin_lsb_convention.md`](docs/latin_lsb_convention.md) | افتراض المحرك حول glyph origin؛ vertex shift المطلوب للـscripts غير اللاتينية |
| [`docs/rtl_in_ltr_engines.md`](docs/rtl_in_ltr_engines.md) | منهج عام لعرض الـscripts اليمين-لليسار في محرك يسار-لليمين |
| [`STORY.md`](STORY.md) | سرد لرحلة الهندسة العكسية |

---

## الأدوات

| الأداة | الوظيفة |
|---|---|
| `tools/str_codec.py` | قراءة وكتابة ملفات `.str`. roundtrip متحقّق منه. |
| `tools/vfont_codec.py` | قراءة وكتابة ملفات `.vfont` و `.vfont0`. roundtrip متحقّق منه. |
| `tools/ui_zip_patcher.py` | Slot-preserving patcher لـ`UI.zip`. يحافظ على كل الـ4 KB-aligned data offsets. |
| `tools/build_font_from_ttf.py` | يبني `.vfont` + `.vfont0` من خط TrueType. يتعامل مع أي نطاق codepoints. |

---

## ليش هذا المشروع موجود

سلسلة Forza تشحن بـ٢٤ لغة رسمية. مجتمعات لغوية كثيرة (تايلندي، أوكراني، فيتنامي، عبري، هندي، فارسي، وغيرها) ما عندها دعم رسمي. قبل هذا المستودع، التعريب الفاني كان محجوز خلف ثلاث مشاكل ما تم حلّها:

١. تنسيق `.str` كان مغلق. النصوص ما تنفع تتستخرج أو تترجع.
٢. تنسيقا `.vfont` / `.vfont0` كانا مغلقين. ما ينفع تضاف glyphs جديدة.
٣. `UI.zip` يستخدم custom `0x1123` extra field، لو ما تحفظ صح، اللعبة تنهار عند الإقلاع.

الثلاثة موثّقين ومحلولين هنا. أي مترجم فاني الحين يقدر ينتج تعريب كامل لأي لعبة Forza بلغته.

---

## التوافق

متحقّق منه على **Forza Horizon 6** (إصدار مايو ٢٠٢٦، Steam build). التنسيقات ظلّت ثابتة عبر إصدارات ForzaTech، ومتوقّع تشتغل على **Forza Horizon 4** و **Forza Horizon 5** و **Forza Motorsport (2023)** بتعديلات بسيطة. الـoffsets المحدّدة والـfont sets تختلف من لعبة للثانية؛ التنسيق نفسه ما يتغيّر.

---

## التوافق مع الـAnti-Cheat

ألعاب ForzaTech متّصلة بالإنترنت، والشركة المطوّرة تمنع تعديل ملفات اللعبة في شروط الخدمة. الأدوات في هذا المستودع ما تلمس إلا أصول اللوكلايزيشن في الجهة العميلة، بدون أي تأثير على اللعبية، **لكن استخدام أي تعديل أثناء الاتصال بالخدمات الأونلاين يكون على مسؤولية المستخدم**. اللعب الأوفلاين Single-player هو الوضع الوحيد المدعوم لأي ناتج من هذي الأدوات.

---

## الفضل

الهندسة العكسية، التوثيق، والأدوات: **Hesham**.

مود التعريب على Nexus (التطبيق المرجعي اللي أثبت هذا الشغل من البداية للنهاية) منشور تحت نفس المؤلف.

---

## الترخيص

- **الكود** (`tools/`, `examples/`): رخصة MIT. شوف [`LICENSE`](LICENSE).
- **التوثيق** (`docs/`, `README.md`, `STORY.md`): Creative Commons Attribution 4.0 (CC-BY-4.0).

---

## English

First public reverse-engineering of the text and font subsystems in **ForzaTech**, the proprietary game engine behind Forza Horizon 4/5/6 and Forza Motorsport. This toolkit lets you extract, modify, and repack the localization data of any game built on this engine.

### What this is

ForzaTech is the engine Playground Games and Turn 10 Studios use for the Forza franchise. Until now, no public documentation existed for how the engine stores its text strings (`.str`), its fonts (`.vfont` / `.vfont0`), or how its UI archives (`UI.zip`) preserve memory-mapped alignment after modification.

This repository documents the binary formats and provides Python tools to read and write them, with byte-identical roundtrip verified against shipping game files.

Companion to this work: the [first complete Arabic localization mod for Forza Horizon 6](https://www.nexusmods.com/forzahorizon6/mods/65), shipped on Nexus Mods as a reference implementation. The mod itself is outside the scope of this repository; what is documented here is the underlying engine work that made it possible.

### What was reverse-engineered

| Subsystem | Status | Verification |
|---|---|---|
| `.str` string table binary format | Fully documented | Byte-identical roundtrip across 287 files × 24 languages |
| `.vfont` font metrics + slot table | Fully documented | Byte-identical roundtrip on 20/20 tested fonts |
| `.vfont0` mesh blob format | Fully documented | Byte-identical roundtrip on 19/20 tested fonts |
| `UI.zip` custom `0x1123` extra field | Documented | Semantics confirmed across 454 entries |
| Slot-preserving PKZIP repack technique | Documented + tool | Required to modify UI without breaking memory-mapped offsets |
| Silent integrity checks (catalog) | Documented | List of files that cannot be modified even with correct CRC |
| Latin-LSB glyph convention | Documented | Engine assumption affecting all non-Latin scripts |

### Why this exists

The Forza franchise ships with 24 official text locales. Many language communities (Thai, Ukrainian, Vietnamese, Hebrew, Hindi, Persian, and others) have no first-party support. Before this toolkit, fan localization was blocked by three unsolved problems: the `.str` format was opaque, the `.vfont` / `.vfont0` formats were opaque, and `UI.zip` used a custom `0x1123` extra field that caused crashes if not preserved correctly. All three are documented and solved here.

### Anti-cheat compatibility

ForzaTech games are online-capable and the publisher prohibits modification of game files in their terms of service. The tools in this repository touch only client-side localization assets, with no gameplay effect, but **using any modification while connected to online services is at the user's own risk**. Single-player offline use is the only supported mode.

### Credits

Reverse engineering, documentation, and tools: **Hesham**. The Arabic localization mod on Nexus (the reference implementation) is shipped under the same author.

### License

- **Code** (`tools/`, `examples/`): MIT License.
- **Documentation** (`docs/`, `README.md`, `STORY.md`): Creative Commons Attribution 4.0 (CC-BY-4.0).
