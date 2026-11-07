"""Primitif multi-penerima: satu ciphertext, CEK dibungkus per penerima, stego per penerima."""
import pytest

from app.crypto.key_wrap import generate_cek, unwrap_cek, wrap_cek
from app.crypto.text import decrypt_text, encrypt_text
from app.errors import DecryptionError, InvalidIDError
from app.stego.embed import embed_key
from app.stego.extract import extract_key

RECIPIENTS = ["B001", "C001", "D001"]


def test_each_recipient_decrypts_independently(cover_path):
    secret, cek = "K123", generate_cek()
    ciphertext = encrypt_text("Rapat pukul 08.00", cek)               # satu ciphertext
    packages = {}
    for rid in RECIPIENTS:
        w = wrap_cek(secret, rid, cek)
        packages[rid] = (w, embed_key(cover_path, rid, secret))       # stego khusus per ID
    assert len({p[1] for p in packages.values()}) == 3                # gambar berbeda

    for rid, (w, stego) in packages.items():
        k = extract_key(stego, rid)
        assert decrypt_text(ciphertext, unwrap_cek(k, rid, w.salt, w.blob)) == "Rapat pukul 08.00"


def test_other_recipient_cannot_open_package(cover_path):
    secret, cek = "K123", generate_cek()
    w_c = wrap_cek(secret, "C001", cek)
    stego_c = embed_key(cover_path, "C001", secret)
    with pytest.raises(InvalidIDError):                               # Budi pakai ID B001 pada stego Citra
        extract_key(stego_c, "B001")
    with pytest.raises(DecryptionError):                              # Budi mencoba unwrap bungkus Citra
        unwrap_cek(secret, "B001", w_c.salt, w_c.blob)


def test_wrong_secret_cannot_unwrap():
    cek = generate_cek()
    w = wrap_cek("K123", "B001", cek)
    with pytest.raises(DecryptionError):
        unwrap_cek("SALAH", "B001", w.salt, w.blob)
