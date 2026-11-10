# KomSaR — Komunikasi Satuan Rakyat

## Cara menjalankan (di browser)
```
pip install -r requirements.txt
python run.py
```
Lalu buka **http://127.0.0.1:5000**. Pertama kali dijalankan, `run.py` otomatis membuat `.env` (kunci acak) dan akun contoh
(password semua: `komsar123`): `admin01` (admin), `andi01`, `budi01`, `citra01`, `deni01`. User ID-nya acak (`XXXX-XXXX-XXXX`)
dan dicetak di konsol saat dibuat; admin juga melihatnya di menu Pengguna. Hapus/ganti akun ini sebelum dipakai sungguhan.
Alur dekripsi: gambar steganografi tampil → penerima input User ID → kunci hasil ekstraksi ditampilkan → penerima mengetik
ulang kunci itu → sistem menggabungkan ID + kunci → data terbuka. User ID tidak ditampilkan ke pengguna (hanya admin yang
melihatnya di menu Pengguna dan menyampaikannya ke pemiliknya).
Login memakai username + password saja (biometrik & dongle belum ada). Jalankan test dengan `python -m pytest -q`.

Aplikasi komunikasi aman antarsatuan (Flask): super encryption, steganografi LSB, file terenkripsi, blockchain sederhana.

## Menjalankan
```
pip install -r requirements.txt
cp .env.example .env        # isi KOMSAR_SECRET_KEY dan KOMSAR_DB_MASTER_KEY
python scripts/generate_covers.py   # opsional: cover contoh (ganti dengan gambar tim di assets/covers/)
python -m pytest -q
```

## Konfigurasi (`.env`)
| Variabel | Default | Keterangan |
|---|---|---|
| `KOMSAR_SECRET_KEY` | (wajib) | kunci sesi Flask |
| `KOMSAR_DB_MASTER_KEY` | (wajib) | 32 byte base64, lapisan enkripsi pesan penting di database |
| `DATABASE_URL` | SQLite `instance/komsar.db` | Neon: `postgresql://user:pass@host/db?sslmode=require` (otomatis memakai driver psycopg) |
| `MAX_FILE_MB` | `10` | batas ukuran file; file disimpan di database |
| `KOMSAR_REQUIRE_DONGLE` | `0` | `1` = setiap request butuh heartbeat dongle; sesi diakhiri bila heartbeat kedaluwarsa |
| `DONGLE_HEARTBEAT_TIMEOUT` | `60` | detik sejak heartbeat dongle terakhir sebelum sesi dikunci |

Semua data (pengguna, pesan, ciphertext file, gambar steganografi, blok blockchain) disimpan di database dan
bertahan saat server restart. Tabel dibuat otomatis (`db.create_all()`). Database SQLite lama dari versi
sebelumnya perlu dihapus (`instance/komsar.db`) karena tabel `users` mendapat kolom baru.

## Status
- Tahap 2 (modul inti): crypto, stego, auth, user management — selesai
- Tahap 3 (komunikasi): pesan biasa/penting, file, gambar, multi-penerima, Decryption Center — selesai
- Tahap 5 (UI Flask): login, dashboard, pengguna, pesan, kirim file, aset penting, dekripsi, profil, Blockchain Records (khusus admin) — selesai
- Tahap 4 (blockchain): hash chaining SHA-256 (tanpa PoW), satu blok per aset penting, validasi rantai,
  verifikasi integritas sebelum aset dibuka — selesai. Blok tidak ditampilkan ke pengguna (lihat `docs/keamanan.md`)
  (record disimpan di database lewat `app/repository.py`, blok di tabel `blocks`)

## Dongle flashdisk
File `KOMSAR.DONGLE` di root flashdisk berisi `dongle_id` dan token acak 32 byte. Server hanya menyimpan
SHA-256(token) dan serial volume flashdisk, jadi file yang disalin ke flashdisk lain ditolak.

Mendaftarkan dongle (admin, wajib lewat aplikasi desktop `desktop/`):
1. Colokkan flashdisk, buka menu **Dongle** (`/admin/dongles`).
2. Pilih flashdisk, isi label, klik **Daftarkan dongle**. Server membuat ID + token, aplikasi menulis file ke flashdisk.
3. Bila penulisan gagal, nonaktifkan entri baru itu lalu ulangi. Flashdisk hilang: klik **Nonaktifkan**.

Endpoint: `POST /api/dongle/check` (tanpa login, dipakai klien desktop, dibatasi 30 request/menit per IP),
`POST /api/dongle/register` (admin), `POST /api/dongle/heartbeat` (dikirim halaman tiap 30 detik).
Penegakan heartbeat aktif bila `KOMSAR_REQUIRE_DONGLE=1`.

## Verifikasi suara
Model `speechbrain/spkrec-ecapa-voxceleb` mengubah rekaman menjadi embedding, lalu dibandingkan dengan
cosine similarity. Server memasang `pip install -r requirements-server.txt` (torch CPU); `requirements.txt`
tetap tanpa torch, dan test memakai `VOICE_BACKEND=fake`. Model dimuat sekali per proses dari
`VOICE_MODEL_DIR` (bila folder kosong, diunduh dari Hugging Face ke folder itu).

- Rekaman: WAV PCM 16-bit, 16000 Hz, mono, 2 sampai 10 detik, maks. 1 MB (direkam aplikasi desktop).
- Pendaftaran: pemilik akun merekam **3 sampel**, masing-masing dengan kalimat acak 4 kata (berlaku 2 menit,
  sekali pakai). Embedding dirata-rata, dinormalisasi, lalu disimpan terenkripsi AES-256-GCM di `voice_profiles`.
  Rekaman WAV tidak disimpan. Pengguna tidak bisa mendaftar ulang sendiri.
- Verifikasi: dibandingkan hanya dengan profil akun itu; lolos bila skor >= `VOICE_THRESHOLD` (default 0.25,
  kalibrasi dengan suara tim).
- Reset: admin menekan **Reset suara** di halaman edit pengguna. Profil dihapus, akun `must_enroll` dengan
  batas waktu `ENROLL_WINDOW_HOURS` (default 24 jam).

Endpoint (login + header `X-CSRF-Token`): `POST /api/voice/challenge` `{purpose: "enroll"|"verify"}`,
`POST /api/voice/enroll` `{samples: [{challenge_id, wav_b64}] x3}`, `POST /api/voice/verify`
`{challenge_id, wav_b64}` -> `{ok}`. Helper halaman: `static/voice.js` (`komsarVoice.enroll/verify`).

## Pemakaian service (contoh)
```python
svc = app.extensions["komsar"]
msg = svc.messaging.send_text(sender, ["budi01", "citra01"], "Halo", "K123", important=True)
inbox = svc.messaging.inbox(budi)                       # data chatbox (tanpa plaintext)
res = svc.decryption.open(budi, inbox[0]["delivery_id"], budi.user_id)
print(res.text)
```

## Aset penting & blockchain
```python
svc.messaging.send_file(andi, ["budi01"], "kontrak.pdf", data, "K123", kind="asset")   # otomatis membuat blok
svc.assets.list_assets(budi)                 # daftar aset milik user (tanpa blok mentah)
svc.assets.verify_integrity(budi, asset_id)  # status: verified / ciphertext_modified / chain_broken / ...
svc.chain.validate()                         # validasi seluruh rantai
svc.chain.export_json("chain.json")          # ekspor blok mentah ke JSON untuk inspeksi
```
