# Building the Arabic_Hesham Forza Horizon 6 Installer

This folder contains the full source of the one-click installer EXE
(`Arabic_Hesham_Forza_H6.exe`) distributed on Nexus Mods.

## What the installer does

It is a small Tkinter GUI that copies four Arabic-localized game archives
into the user's Forza Horizon 6 installation. Nothing else. No network
access, no registry writes beyond reading the Steam install path, no
persistence, no telemetry.

| Source file      | Role                                                                 |
|------------------|----------------------------------------------------------------------|
| `gui.py`         | Tkinter front-end. Contract: `find_game()` / `PROGRESS_CB` / `main()`. |
| `apply.py`       | FH6 install method. Locates the game (Steam + Xbox Game Pass), decrypts the bundled archives in memory, and writes them to `media\...`. |
| `loc_crypto.py`  | Stdlib-only obfuscation (SHA-256 keystream + nonce + MAC) used to avoid shipping the raw `.zip` files loose. Not a security boundary. |

The four payloads it installs (replacing the vanilla files):

| Destination (relative to game root)              | Content                |
|--------------------------------------------------|------------------------|
| `media\UI\Fonts.zip`                             | Arabic font (Noto Naskh) |
| `media\UI.zip`                                   | RTL UI layout fix      |
| `media\Stripped\StringTables\EN.zip`             | Arabic string tables   |
| `media\Stripped\StringTables\GB.zip`             | Arabic string tables   |

## Prerequisites

- Windows, Python 3.12
- Packages:

```
pip install pyinstaller pyarmor arabic-reshaper python-bidi
```

## Build steps

The build is two stages: (1) encrypt the localized archives into `data\*.enc`,
(2) obfuscate the three Python files and pack everything into one EXE.

### 1. Prepare the payload tree

Place the four localized archives in a `media\` tree next to the source,
mirroring the game layout:

```
<root>\media\UI\Fonts.zip
<root>\media\UI.zip
<root>\media\Stripped\StringTables\EN.zip
<root>\media\Stripped\StringTables\GB.zip
```

### 2. Encrypt the payloads

```
python apply.py build "<root>"
```

This produces `data\Fonts.enc`, `data\UI.enc`, `data\EN.enc`.

### 3. Build the EXE

```
pyarmor gen --pack ".\Arabic_Hesham_Forza_H6.spec" -r gui.py apply.py loc_crypto.py
```

Output: `dist\Arabic_Hesham_Forza_H6.exe`.

> The `.spec` is a standard PyInstaller spec (windowed, one-file, custom icon).
> PyArmor wraps it via `--pack` to obfuscate the three source modules. The
> obfuscation is only to discourage casual tampering with the installer; the
> full, unobfuscated source is exactly what you see in this folder.

## Notes for reviewers

- The bundled `data\*.enc` are just the four game `.zip` archives above,
  XOR'd against a SHA-256 keystream (see `loc_crypto.encrypt`). The key is
  derived in `apply.py` `_key()`. You can decrypt and inspect them with the
  same functions.
- `apply.py` only ever writes to the four destinations listed above, inside
  a validated Forza Horizon 6 install. It does not touch any other file.
