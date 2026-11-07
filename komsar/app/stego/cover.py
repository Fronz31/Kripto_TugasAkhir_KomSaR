"""Pemilihan gambar cover acak dari folder gambar yang disediakan."""
import secrets
from pathlib import Path

from ..errors import StegoError


def pick_random_cover(covers_dir) -> Path:
    files = sorted(Path(covers_dir).glob("*.png"))
    if not files:
        raise StegoError("Tidak ada gambar cover (*.png) di folder cover.")
    return secrets.choice(files)
