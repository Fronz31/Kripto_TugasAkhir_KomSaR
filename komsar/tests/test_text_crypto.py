import pytest

from app.crypto import aes_gcm
from app.crypto.db_layer import decrypt_from_db, encrypt_for_db
from app.crypto.key_wrap import generate_cek
from app.crypto.kdf import derive_content_keys
from app.crypto.text import decrypt_text, encrypt_text
from app.crypto.vigenere import vigenere_decrypt, vigenere_encrypt
from app.errors import DecryptionError

MSG = "Laporan siaga 🚨 pukul 06.00 — Unit A → Unit B"


def test_vigenere_roundtrip_utf8():
    key = b"\x01\x02\x03\xff"
    data = MSG.encode()
    enc = vigenere_encrypt(data, key)
    assert enc != data and vigenere_decrypt(enc, key) == data


def test_vigenere_empty_key():
    with pytest.raises(ValueError):
        vigenere_encrypt(b"x", b"")


def test_normal_message_roundtrip_and_unreadable():
    cek = generate_cek()
    blob = encrypt_text(MSG, cek)
    assert MSG.encode() not in blob and b"Laporan" not in blob
    assert decrypt_text(blob, cek) == MSG


def test_nonce_unique_per_encryption():
    cek = generate_cek()
    assert encrypt_text(MSG, cek) != encrypt_text(MSG, cek)


def test_wrong_key_and_tamper():
    cek = generate_cek()
    blob = encrypt_text(MSG, cek)
    with pytest.raises(DecryptionError):
        decrypt_text(blob, generate_cek())
    tampered = bytearray(blob); tampered[-1] ^= 1
    with pytest.raises(DecryptionError):
        decrypt_text(bytes(tampered), cek)


def test_text_is_vigenere_then_aes():
    cek = generate_cek()
    keys = derive_content_keys(cek)
    inner = aes_gcm.decrypt(keys.aes_key, encrypt_text(MSG, cek), aad=b"komsar:text:v1")
    assert inner != MSG.encode()                                   # masih lapisan Vigenère
    assert vigenere_decrypt(inner, keys.vigenere_key).decode() == MSG


def test_important_message_has_extra_db_layer():
    cek, master = generate_cek(), b"m" * 32
    message_ct = encrypt_text(MSG, cek)
    stored = encrypt_for_db(master, message_ct)
    assert stored != message_ct and MSG.encode() not in stored
    assert decrypt_from_db(master, stored) == message_ct          # aplikasi dapat membuka lapisan DB
    assert decrypt_text(decrypt_from_db(master, stored), cek) == MSG
    with pytest.raises(DecryptionError):
        decrypt_from_db(b"x" * 32, stored)
