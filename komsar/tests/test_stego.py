import io

import pytest
from PIL import Image

from app.errors import InvalidIDError, StegoCapacityError, StegoError
from app.stego.embed import embed_key
from app.stego.extract import extract_key


def test_embed_extract_correct_id(cover_path):
    png = embed_key(cover_path, "B001", "K123")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert extract_key(png, "B001") == b"K123"


def test_wrong_id_fails(cover_path):
    png = embed_key(cover_path, "B001", "K123")
    for wrong in ("C001", "b001", "B002", ""):
        with pytest.raises(InvalidIDError):
            extract_key(png, wrong)


def test_survives_save_and_reload_as_file(cover_path, tmp_path):
    p = tmp_path / "stego.png"
    p.write_bytes(embed_key(cover_path, "B001", "rahasia-panjang-🔑" * 5))
    assert extract_key(p.read_bytes(), "B001") == ("rahasia-panjang-🔑" * 5).encode()


def test_image_visually_unchanged(cover_path):
    import numpy as np
    orig = np.array(Image.open(cover_path).convert("RGB")).astype(int)
    new = np.array(Image.open(io.BytesIO(embed_key(cover_path, "B001", "K123"))).convert("RGB")).astype(int)
    assert abs(orig - new).max() <= 1          # hanya LSB yang berubah


def test_jpeg_recompression_breaks_key(cover_path):
    png = embed_key(cover_path, "B001", "K123")
    buf = io.BytesIO(); Image.open(io.BytesIO(png)).save(buf, "JPEG", quality=95)
    with pytest.raises(StegoError):
        extract_key(buf.getvalue(), "B001")


def test_non_stego_image_rejected(cover_path):
    with pytest.raises(InvalidIDError):        # tanpa penanda: gambar biasa gagal di tag AES-GCM
        extract_key(cover_path.read_bytes(), "B001")


def test_every_cover_fits_max_payload(cover_path):
    secret = b"k" * 1024
    for cover in sorted(cover_path.parent.glob("*.png")):
        assert extract_key(embed_key(cover, "B001", secret), "B001") == secret


def test_capacity_error():
    buf = io.BytesIO(); Image.new("RGB", (8, 8)).save(buf, "PNG")
    with pytest.raises(StegoCapacityError):
        embed_key(buf.getvalue(), "B001", "K123")


def test_two_embeds_differ(cover_path):
    assert embed_key(cover_path, "B001", "K123") != embed_key(cover_path, "B001", "K123")


def _lsb_bytes(png: bytes) -> bytes:
    import numpy as np
    flat = np.array(Image.open(io.BytesIO(png)).convert("RGB"), dtype=np.uint8).reshape(-1)
    return np.packbits(flat & 1).tobytes()


def test_no_plaintext_signature_in_lsb(cover_path):
    for _ in range(3):
        assert b"KSST" not in _lsb_bytes(embed_key(cover_path, "B001", "K123"))


def test_first_32_lsbs_not_constant(cover_path):
    heads = {_lsb_bytes(embed_key(cover_path, "B001", "K123"))[:4] for _ in range(4)}
    assert len(heads) > 1                      # salt acak, bukan penanda tetap


def test_cover_is_natural_photo_from_folder(cover_path):
    from app.config import Config
    assert cover_path.parent == Config.COVER_IMAGES_DIR and cover_path.name.startswith("IMG_")
    assert max(Image.open(cover_path).size) == 1024
