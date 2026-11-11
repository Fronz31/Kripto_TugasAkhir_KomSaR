"""Buat aset logo KomSaR (Lencana rantai) : SVG, PNG, favicon.ico, KomSaR.ico."""
# Jalankan dari folder komsar/: uv run --with resvg-py --with pillow python scripts/make_brand.py .
import io
import sys
from pathlib import Path

import resvg_py
from PIL import Image

KOMSAR = Path(sys.argv[1])            # folder komsar/
BRAND = KOMSAR / "app" / "static" / "brand"
NAVY, AMBER, WHITE = "#0c1a33", "#f5a623", "#ffffff"

BODY = """
  <defs>
    <mask id="k" maskUnits="userSpaceOnUse" x="0" y="0" width="100" height="100">
      <rect width="100" height="100" fill="#fff"/>
      <g stroke="#000" stroke-width="4.5" stroke-linecap="round" fill="none">
        <line x1="45" y1="53" x2="45" y2="69"/>
        <line x1="45" y1="62" x2="56" y2="53"/>
        <line x1="49" y1="59" x2="57" y2="69"/>
      </g>
    </mask>
  </defs>
  <g fill="none" stroke="{ink}" stroke-width="2.6">
    <rect x="43" y="8.5" width="14" height="7" rx="3.5"/>
    <rect x="75.9" y="27.5" width="14" height="7" rx="3.5" transform="rotate(60 82.9 31)"/>
    <rect x="75.9" y="65.5" width="14" height="7" rx="3.5" transform="rotate(120 82.9 69)"/>
    <rect x="43" y="84.5" width="14" height="7" rx="3.5"/>
    <rect x="10.1" y="65.5" width="14" height="7" rx="3.5" transform="rotate(60 17.1 69)"/>
    <rect x="10.1" y="27.5" width="14" height="7" rx="3.5" transform="rotate(120 17.1 31)"/>
  </g>
  <g fill="{ink}">
    <rect x="64" y="15.1" width="10" height="4" rx="2" transform="rotate(30 69 17.1)"/>
    <rect x="83" y="48" width="10" height="4" rx="2" transform="rotate(90 88 50)"/>
    <rect x="64" y="80.9" width="10" height="4" rx="2" transform="rotate(150 69 82.9)"/>
    <rect x="26" y="80.9" width="10" height="4" rx="2" transform="rotate(30 31 82.9)"/>
    <rect x="7" y="48" width="10" height="4" rx="2" transform="rotate(90 12 50)"/>
    <rect x="26" y="15.1" width="10" height="4" rx="2" transform="rotate(150 31 17.1)"/>
  </g>
  <path d="M40 47 V40 A10 10 0 0 1 60 40 V47" fill="none" stroke="{accent}" stroke-width="5"/>
  <rect x="33" y="46" width="34" height="30" rx="7" fill="{ink}" mask="url(#k)"/>
"""


def svg(ink, title, tile=False):
    body = BODY.format(ink=ink, accent=AMBER)
    if tile:  # ikon aplikasi: kotak navy membulat, logo putih diperkecil di tengah
        body = (f'<rect width="100" height="100" rx="22" fill="{NAVY}"/>\n'
                f'<g transform="translate(8 8) scale(0.84)">{body}</g>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" role="img" aria-label="{title}">\n'
            f'<title>{title}</title>{body}</svg>\n')


def png(svg_text, size):
    data = resvg_py.svg_to_bytes(svg_string=svg_text, width=size, height=size)
    return Image.open(io.BytesIO(bytes(data))).convert("RGBA")


BRAND.mkdir(parents=True, exist_ok=True)
files = {
    "logo.svg": svg(NAVY, "Logo KomSaR"),               # latar terang
    "logo-white.svg": svg(WHITE, "Logo KomSaR"),        # latar navy (rail)
    "app-icon.svg": svg(WHITE, "Ikon KomSaR", tile=True),
}
for name, text in files.items():
    (BRAND / name).write_text(text, encoding="utf-8")

icon = files["app-icon.svg"]
png(icon, 512).save(BRAND / "app-icon-512.png")
sizes = [16, 24, 32, 48, 64, 128, 256]
frames = [png(icon, s) for s in sizes]                   # tiap ukuran dirender sendiri, bukan diperkecil
for target in (BRAND / "favicon.ico", KOMSAR / "desktop" / "KomSaR.ico"):
    frames[-1].save(target, format="ICO", sizes=[(s, s) for s in sizes], append_images=frames[:-1])

check = Image.open(KOMSAR / "desktop" / "KomSaR.ico")
assert sorted(check.info["sizes"]) == [(s, s) for s in sizes], check.info["sizes"]
assert check.getpixel((128, 128))[3] == 255 and check.getpixel((1, 1))[3] < 255   # tile solid, sudut transparan
print("ok", sorted(p.name for p in BRAND.iterdir()), check.info["sizes"])
