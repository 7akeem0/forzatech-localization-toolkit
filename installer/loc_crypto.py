# -*- coding: utf-8 -*-
# ============================================================
#  Localization Data Crypto
#  build-time: encrypt_file()  -> encrypt data files before packaging
#  runtime:    load_json()     -> decrypt in memory inside apply.py
#  Stdlib only. No external dependencies.
#  Scheme: SHA-256 keystream (CTR-like) + per-file random nonce + MAC.
# ============================================================
import os, json, hashlib

MAGIC = b"HLOC1"

def _keystream(seed, n):
    # Deterministic keystream from seed via SHA-256 counter mode.
    out = bytearray(); c = 0
    while len(out) < n:
        out += hashlib.sha256(seed + c.to_bytes(8, "little")).digest()
        c += 1
    return bytes(out[:n])

def _xor(a, b):
    # Fast bulk XOR via big integers.
    return (int.from_bytes(a, "big") ^ int.from_bytes(b, "big")).to_bytes(len(a), "big")

def encrypt(plain, key):
    nonce = os.urandom(16)
    ct = _xor(plain, _keystream(key + nonce, len(plain)))
    mac = hashlib.sha256(key + nonce + ct).digest()[:16]   # integrity / key check
    return MAGIC + nonce + mac + ct

def decrypt(blob, key):
    if blob[:5] != MAGIC:
        raise ValueError("bad container")
    nonce, mac, ct = blob[5:21], blob[21:37], blob[37:]
    if hashlib.sha256(key + nonce + ct).digest()[:16] != mac:
        raise ValueError("bad key or corrupted data")
    return _xor(ct, _keystream(key + nonce, len(ct)))

def encrypt_file(src_json, dst_enc, key):
    # Build-time: convert plaintext .json -> encrypted .enc
    open(dst_enc, "wb").write(encrypt(open(src_json, "rb").read(), key))

def load_json(enc_path, key):
    # Runtime: decrypt + parse, never touching disk in plaintext.
    return json.loads(decrypt(open(enc_path, "rb").read(), key).decode("utf-8"))
