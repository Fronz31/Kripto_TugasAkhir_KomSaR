"""Membuat gambar cover PNG contoh untuk development (ganti dengan gambar milik tim jika ada)."""
from pathlib import Path

import numpy as np
from PIL import Image

OUT = Path(__file__).resolve().parent.parent / "assets" / "covers"
OUT.mkdir(parents=True, exist_ok=True)

for i in range(5):
    rng = np.random.default_rng(1000 + i)
    h = w = 512
    y, x = np.mgrid[0:h, 0:w]
    base = np.stack([
        127 + 100 * np.sin(x / (40 + 15 * i) + i),
        127 + 100 * np.sin(y / (55 + 10 * i) + 2 * i),
        127 + 100 * np.sin((x + y) / (70 + 8 * i)),
    ], axis=-1)
    img = np.clip(base + rng.normal(0, 8, base.shape), 0, 255).astype(np.uint8)
    Image.fromarray(img, "RGB").save(OUT / f"cover_{i + 1}.png")
print("OK ->", OUT)
