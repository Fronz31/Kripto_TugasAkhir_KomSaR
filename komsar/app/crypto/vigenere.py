"""Vigenère cipher pada level byte (mod 256) agar mendukung semua karakter UTF-8."""


def vigenere_encrypt(data: bytes, key: bytes) -> bytes:
    if not key:
        raise ValueError("Kunci Vigenère tidak boleh kosong.")
    k = len(key)
    return bytes((b + key[i % k]) & 0xFF for i, b in enumerate(data))


def vigenere_decrypt(data: bytes, key: bytes) -> bytes:
    if not key:
        raise ValueError("Kunci Vigenère tidak boleh kosong.")
    k = len(key)
    return bytes((b - key[i % k]) & 0xFF for i, b in enumerate(data))
