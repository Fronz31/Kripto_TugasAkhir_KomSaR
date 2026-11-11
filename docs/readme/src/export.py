"""Ekspor visual README (HTML di folder ini) menjadi PNG di docs/readme/ memakai Microsoft Edge headless.

Ekspor ulang semua, atau sebagian (dari root repo):
  uv run --with pillow python docs/readme/src/export.py [banner ketentuan ...]
Tinggi tiap visual ditetapkan di SIZES; periksa hasil PNG bila isi HTML berubah.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

SRC = Path(__file__).resolve().parent
OUT = SRC.parent
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
SIZES = {"banner": 480, "ketentuan": 940, "arsitektur": 660, "alur-kripto": 880, "alur-login": 680}

for name in sys.argv[1:] or SIZES:
    png = OUT / f"{name}.png"
    with tempfile.TemporaryDirectory() as prof:
        subprocess.run([EDGE, "--headless=new", "--disable-gpu", f"--user-data-dir={prof}", "--hide-scrollbars",
                        "--allow-file-access-from-files", "--virtual-time-budget=3000",
                        f"--window-size=1280,{SIZES[name]}", f"--screenshot={png}",
                        (SRC / f"{name}.html").as_uri()], check=True, capture_output=True, timeout=90)
    Image.open(png).convert("RGB").quantize(256, method=Image.Quantize.MEDIANCUT,
                                             dither=Image.Dither.NONE).save(png, optimize=True)
    print(f"{name}.png {png.stat().st_size // 1024} KB")
