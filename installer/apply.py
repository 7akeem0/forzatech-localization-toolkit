# -*- coding: utf-8 -*-
# ============================================================
#  apply.py  --  Forza Horizon 6 injection engine
#  Contract: find_game / PROGRESS_CB / main
#  Steam + Xbox Game Pass detection (hardened).
# ============================================================
import os, sys, re, hashlib, string
import loc_crypto

GAME_DIRNAME = "ForzaHorizon6"          # Steam folder
GAME_TITLE   = "Forza Horizon 6"        # human / Game Pass folder

TARGETS = {
    "Fonts.enc": [r"media\UI\Fonts.zip"],
    "UI.enc":    [r"media\UI.zip"],
    "EN.enc":    [r"media\Stripped\StringTables\EN.zip",
                  r"media\Stripped\StringTables\GB.zip"],
}

_SENTINEL = os.path.join("media", "UI", "Fonts.zip")
PROGRESS_CB = None


def _key():
    parts = [b"f6a1", b"3d72", b"b09e", b"8c4f"]
    return hashlib.sha256(b"".join(parts) + b"FH6-Hesham-salt").digest()


def resource_path(rel):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def _report(name, pct):
    if PROGRESS_CB:
        PROGRESS_CB(name, pct)


def _valid(game):
    return bool(game) and os.path.isfile(os.path.join(game, _SENTINEL))


# ---------------------- steam ----------------------
def _steam_root():
    try:
        import winreg
    except ImportError:
        return None
    for hive, sub, val in (
        (winreg.HKEY_CURRENT_USER,  r"Software\Valve\Steam",             "SteamPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam",             "InstallPath"),
    ):
        try:
            k = winreg.OpenKey(hive, sub)
            p, _ = winreg.QueryValueEx(k, val)
            winreg.CloseKey(k)
            if p and os.path.isdir(p):
                return p
        except OSError:
            pass
    return None


def _library_paths(steam):
    libs = [steam]
    try:
        txt = open(os.path.join(steam, "steamapps", "libraryfolders.vdf"),
                   encoding="utf-8", errors="ignore").read()
        for m in re.finditer(r'"path"\s*"([^"]+)"', txt):
            libs.append(m.group(1).replace("\\\\", "\\"))
    except OSError:
        pass
    return libs


def _drives():
    return [c + ":\\" for c in string.ascii_uppercase if os.path.isdir(c + ":\\")]


# ---------------------- xbox / game pass ----------------------
def _xbox_candidates():
    out = []
    for dr in _drives():
        for base in ("XboxGames", "Xbox", "Games"):
            root = os.path.join(dr, base)
            if not os.path.isdir(root):
                continue
            try:
                names = os.listdir(root)
            except OSError:
                continue
            for name in names:
                out.append(os.path.join(root, name, "Content"))
                out.append(os.path.join(root, name))
    return out


# ---------------------- last-resort deep scan ----------------------
_SKIP = {"windows", "$recycle.bin", "system volume information", "appdata",
         "programdata", "perflogs", "recovery", "msocache", "onedrive",
         "windows.old", "intel", "amd", "nvidia", "drivers", "temp", "tmp",
         "node_modules", ".git", "boot", "config.msi", "$windows.~ws",
         "$windows.~bt", "documents and settings"}


def _deep_scan(roots, max_depth=5):
    for r0 in roots:
        if not os.path.isdir(r0):
            continue
        try:
            for cur, dirs, files in os.walk(r0):
                if os.path.basename(cur).lower() == "ui" \
                   and "Fonts.zip" in files \
                   and os.path.basename(os.path.dirname(cur)).lower() == "media":
                    cand = os.path.dirname(os.path.dirname(cur))
                    if _valid(cand):
                        return cand
                rel = os.path.relpath(cur, r0)
                depth = 0 if rel == "." else rel.count(os.sep) + 1
                dirs[:] = [d for d in dirs if d.lower() not in _SKIP]
                if depth >= max_depth:
                    dirs[:] = []
        except OSError:
            continue
    return None


# ---------------------- find_game ----------------------
def find_game():
    cands, seen = [], set()
    def add(p):
        if p and p not in seen:
            seen.add(p); cands.append(p)

    steam = _steam_root()
    if steam:
        for lib in _library_paths(steam):
            add(os.path.join(lib, "steamapps", "common", GAME_DIRNAME))
    for dr in _drives():
        add(os.path.join(dr, "SteamLibrary", "steamapps", "common", GAME_DIRNAME))
        add(os.path.join(dr, "Program Files (x86)", "Steam", "steamapps", "common", GAME_DIRNAME))
        add(os.path.join(dr, "Program Files", "Steam", "steamapps", "common", GAME_DIRNAME))
    for c in _xbox_candidates():
        add(c)
    for dr in _drives():
        for base in ("XboxGames", "Xbox", "Games"):
            add(os.path.join(dr, base, GAME_TITLE, "Content"))
            add(os.path.join(dr, base, GAME_TITLE))
        add(os.path.join(dr, GAME_TITLE, "Content"))
        add(os.path.join(dr, GAME_TITLE))

    for c in cands:
        if _valid(c):
            return c

    scan_roots = []
    for dr in _drives():
        for base in ("XboxGames", "Xbox", "Games"):
            bp = os.path.join(dr, base)
            if os.path.isdir(bp):
                scan_roots.append(bp)
    return _deep_scan(scan_roots)


# ---------------------- main (install) ----------------------
def main(game_path=None):
    game = game_path or find_game()
    if not game:
        raise RuntimeError(
            "لم يتم العثور على Forza Horizon 6 تلقائياً. تأكد أن اللعبة مثبّتة "
            "(Steam أو Xbox Game Pass)، أو اختر مجلد اللعبة يدوياً.")
    if not _valid(game):
        raise RuntimeError(
            "المجلد المحدد ليس تثبيت Forza Horizon 6 صالح (ملف media\\UI\\Fonts.zip "
            "غير موجود). إذا كانت اللعبة تحت التحديث الآن، انتظر حتى ينتهي ثم أعد المحاولة.")

    KEY = _key()
    items = list(TARGETS.items())
    total = sum(len(dests) for _, dests in items)
    done = 0
    changed = False
    _report("بدء التثبيت", 1)

    for enc_name, dests in items:
        blob = loc_crypto.decrypt(
            open(resource_path(os.path.join("data", enc_name)), "rb").read(), KEY)
        new_md5 = hashlib.md5(blob).hexdigest()
        for rel in dests:
            target = os.path.join(game, rel)
            try:
                cur = hashlib.md5(open(target, "rb").read()).hexdigest()
            except OSError:
                cur = None
            if cur != new_md5:
                with open(target, "wb") as f:
                    f.write(blob)
                changed = True
            done += 1
            _report(os.path.basename(rel), int(done * 99 / total))

    _report("اكتمل", 100)
    return "ok" if changed else "already"


# ---------------------- build ----------------------
def build(mod_root=None):
    mod_root = mod_root or os.path.dirname(os.path.abspath(__file__))
    KEY = _key()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(out, exist_ok=True)
    for enc_name, dests in TARGETS.items():
        src = os.path.join(mod_root, dests[0])
        if not os.path.isfile(src):
            raise SystemExit("missing source: " + src)
        loc_crypto.encrypt_file(src, os.path.join(out, enc_name), KEY)
        print("encrypted  " + dests[0] + "  ->  data\\" + enc_name)
    print("done. bundle data\\*.enc with PyInstaller. never ship the raw .zip files.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "build":
        build(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        print('Run:  python apply.py build  "C:\\Users\\Hesham\\Desktop\\forza\\Arabic Hesham Forza H6"')
