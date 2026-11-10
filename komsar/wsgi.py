"""Entry point produksi (gunicorn `wsgi:app`).

Beda dengan run.py: tidak membuat .env dan tidak membuat akun contoh. Semua secret datang dari env
(`insta secrets set ...`); dengan KOMSAR_ENV=production, create_app gagal bila ada yang kosong.
"""
import threading

from app import create_app
from app.auth.voice import SpeechBrainVerifier

app = create_app()

# Muat model suara di background agar login suara pertama setelah bangun dari scale-to-zero tidak menunggu.
if app.config["VOICE_BACKEND"] == "speechbrain":
    threading.Thread(target=SpeechBrainVerifier(app.config["VOICE_MODEL_DIR"])._load, daemon=True).start()
