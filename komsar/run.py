"""Menjalankan KomSaR (mode pengembangan/pengujian).

Pertama kali: membuat .env berisi kunci acak dan akun contoh bila belum ada pengguna.
Buka http://127.0.0.1:5000 di browser.
"""
import base64
import os
import secrets
from pathlib import Path

ENV = Path(__file__).resolve().parent / ".env"
if not ENV.exists():
    ENV.write_text(
        f"KOMSAR_SECRET_KEY={secrets.token_hex(32)}\n"
        f"KOMSAR_DB_MASTER_KEY={base64.b64encode(os.urandom(32)).decode()}\n", encoding="utf-8")
    print("File .env dibuat dengan kunci acak baru. Simpan baik-baik; jangan dibagikan.")

from app import create_app          # noqa: E402  (setelah .env tersedia)
from app.seed import DEMO_PASSWORD, seed_demo_users   # noqa: E402

app = create_app()

if __name__ == "__main__":
    with app.app_context():
        created = seed_demo_users()
    if created:
        print(f"Akun contoh dibuat (password: {DEMO_PASSWORD}). User ID untuk Decryption Center:")
        for username, uid in created:
            print(f"  {username:<10} {uid}")
    print("Buka http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
