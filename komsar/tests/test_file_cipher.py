import os

import pytest

from app.crypto import file_cipher as fc
from app.crypto.key_wrap import generate_cek
from app.errors import DecryptionError, FileTooLargeError

ALGOS = [fc.ALGO_CHACHA20, fc.ALGO_AESGCM]


@pytest.mark.parametrize("algo", ALGOS)
@pytest.mark.parametrize("size", [0, 1, 1000, fc.DEFAULT_CHUNK, fc.DEFAULT_CHUNK + 1, 3 * fc.DEFAULT_CHUNK + 17])
def test_roundtrip_bytes(algo, size):
    key, data = os.urandom(32), os.urandom(size)
    blob, res = fc.encrypt_bytes(key, data, algo=algo)
    assert res.plaintext_size == size and res.ciphertext_size == len(blob)
    assert fc.decrypt_bytes(key, blob) == data


def test_file_roundtrip_identical(tmp_path):
    key = generate_cek()
    src = tmp_path / "laporan.pdf"; src.write_bytes(b"%PDF-1.7 " + os.urandom(200_000))
    enc, dec = tmp_path / "laporan.pdf.enc", tmp_path / "hasil.pdf"
    res = fc.encrypt_file(key, src, enc)
    assert enc.read_bytes()[:4] == b"KSF1" and b"%PDF" not in enc.read_bytes()
    fc.decrypt_file(key, enc, dec)
    assert dec.read_bytes() == src.read_bytes()
    import hashlib
    assert res.ciphertext_sha256 == hashlib.sha256(enc.read_bytes()).hexdigest()


def test_wrong_key_and_tamper_and_truncation(tmp_path):
    key = os.urandom(32)
    data = os.urandom(3 * fc.DEFAULT_CHUNK)
    blob, _ = fc.encrypt_bytes(key, data)
    with pytest.raises(DecryptionError):
        fc.decrypt_bytes(os.urandom(32), blob)
    t = bytearray(blob); t[100] ^= 1
    with pytest.raises(DecryptionError):
        fc.decrypt_bytes(key, bytes(t))
    with pytest.raises(DecryptionError):          # chunk terakhir dibuang
        fc.decrypt_bytes(key, blob[:fc.HEADER_SIZE + 2 * (fc.DEFAULT_CHUNK + fc.TAG_SIZE)])
    with pytest.raises(DecryptionError):
        fc.decrypt_bytes(key, b"bukan file KomSaR")


def test_failed_decrypt_leaves_no_output_and_keeps_source(tmp_path):
    key = os.urandom(32)
    blob, _ = fc.encrypt_bytes(key, os.urandom(200_000))
    enc = tmp_path / "x.enc"; enc.write_bytes(blob)
    out = tmp_path / "x.out"
    with pytest.raises(DecryptionError):
        fc.decrypt_file(os.urandom(32), enc, out)
    assert not out.exists() and not (tmp_path / "x.out.part").exists()
    assert enc.read_bytes() == blob                       # ciphertext tidak diubah


def test_aad_binding():
    key = os.urandom(32)
    blob, _ = fc.encrypt_bytes(key, b"data", aad=b"file-1")
    assert fc.decrypt_bytes(key, blob, aad=b"file-1") == b"data"
    with pytest.raises(DecryptionError):
        fc.decrypt_bytes(key, blob, aad=b"file-2")


def test_max_size():
    with pytest.raises(FileTooLargeError):
        fc.encrypt_bytes(os.urandom(32), os.urandom(5000), max_size=1000)
