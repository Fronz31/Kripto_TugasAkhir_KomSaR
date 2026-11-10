from app.extensions import db


def corrupt(file_rec, pos: int) -> bytes:
    """Balik satu bit ciphertext langsung di kolom database (simulasi penyerang dengan akses DB)."""
    raw = bytearray(file_rec.ciphertext)
    raw[pos] ^= 1
    file_rec.ciphertext = bytes(raw)
    db.session.commit()
    return bytes(raw)
