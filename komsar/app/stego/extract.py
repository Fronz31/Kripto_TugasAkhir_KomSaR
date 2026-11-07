"""Ekstraksi kunci rahasia dari gambar stego menggunakan ID penerima."""
from itertools import islice

import numpy as np

from ..crypto import aes_gcm
from ..crypto.kdf import derive_id_master, hkdf
from ..errors import DecryptionError, InvalidIDError, StegoError
from . import _common as c


def extract_key(stego_image, recipient_id: str) -> bytes:
    flat, _ = c.load_rgb_array(stego_image)
    if flat.size <= c.HDR_BITS:
        raise StegoError("Gambar terlalu kecil.")

    header = c.bits_to_bytes(flat[:c.HDR_BITS] & 1)
    if header[:4] != c.MAGIC or header[4] != c.VERSION:
        raise StegoError("Gambar ini bukan gambar steganografi KomSaR (atau sudah rusak/terkompresi).")
    salt = header[5:]

    master = derive_id_master(recipient_id, salt)
    stream = c.position_stream(hkdf(master, b"stego:pos"), flat.size, c.HDR_BITS)

    def read_bits(n: int) -> np.ndarray:
        idx = np.fromiter(islice(stream, n), dtype=np.int64, count=n)
        return flat[idx] & 1

    length = int.from_bytes(c.bits_to_bytes(read_bits(c.LEN_BITS)), "big")
    min_len = aes_gcm.NONCE_SIZE + aes_gcm.TAG_SIZE + 1
    if not min_len <= length <= c.max_body_bits(flat.size) // 8 - 2:
        raise InvalidIDError("ID tidak sesuai atau gambar steganografi rusak.")
    blob = c.bits_to_bytes(read_bits(length * 8))
    try:
        return aes_gcm.decrypt(hkdf(master, b"stego:enc"), blob, aad=header)
    except DecryptionError as exc:
        raise InvalidIDError("ID tidak sesuai atau gambar steganografi rusak.") from exc
