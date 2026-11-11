import sys
from pathlib import Path
from PIL import Image
raw, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)


def save(img, name):
    p = out / name
    img = img.convert("RGB")
    img.save(p, optimize=True)
    if p.stat().st_size > 300_000:
        img.quantize(256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(p, optimize=True)
    print(name, img.size, p.stat().st_size)


save(Image.open(raw / "login.png").crop((300, 110, 980, 670)), "login.png")
save(Image.open(raw / "voice-login.png").crop((300, 140, 980, 640)), "login-suara.png")
pes = Image.open(raw / "pesan.png")
comp = Image.new("RGB", (1280, 830))
comp.paste(pes.crop((0, 0, 1280, 830)), (0, 0))
comp.paste(pes.crop((232, 620, 1280, 1450)), (232, 0))
save(comp, "pesan.png")
save(Image.open(raw / "dekripsi.png").crop((0, 0, 1280, 1050)), "dekripsi.png")
save(Image.open(raw / "admin-pengguna.png").crop((0, 0, 1280, 800)), "admin-pengguna.png")
