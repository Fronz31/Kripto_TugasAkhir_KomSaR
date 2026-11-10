# KomSaR — Komunikasi Satuan Rakyat

## Cara menjalankan lokal (mode development, di browser)
Login normal butuh aplikasi desktop (dongle + mikrofon). Untuk mencoba di browser biasa, matikan dongle dan
pakai backend suara palsu; langkah suara lalu dilewati **hanya** bila `VOICE_BACKEND=fake` **dan** mode debug:
```
pip install -r requirements.txt
# PowerShell:
$env:KOMSAR_REQUIRE_DONGLE="0"; $env:KOMSAR_COOKIE_SECURE="0"; $env:VOICE_BACKEND="fake"
$env:FLASK_DEBUG="1"; $env:KOMSAR_SEED_DEMO="1"
python run.py
```
Lalu buka **http://127.0.0.1:5000**. Pertama kali dijalankan, `run.py` otomatis membuat `.env` (kunci acak). Dengan
`KOMSAR_SEED_DEMO=1` dibuat akun contoh (password semua: `komsar123`): `admin01` (admin), `andi01`, `budi01`, `citra01`,
`deni01`. User ID-nya acak (`XXXX-XXXX-XXXX`) dan dicetak di konsol saat dibuat; admin juga melihatnya di menu Pengguna.
Jangan pernah memakai kelima variabel di atas di server produksi.
Alur dekripsi: gambar steganografi tampil → penerima input User ID → kunci hasil ekstraksi ditampilkan → penerima mengetik
ulang kunci itu → sistem menggabungkan ID + kunci → data terbuka. User ID tidak ditampilkan ke pengguna (hanya admin yang
melihatnya di menu Pengguna dan menyampaikannya ke pemiliknya).
Login memakai tiga faktor: password + dongle flashdisk + suara (lihat **Alur login**). Jalankan test dengan
`python -m pytest -q`.

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
| `KOMSAR_REQUIRE_DONGLE` | `1` | login butuh dongle dan setiap request butuh heartbeat dongle; `0` hanya untuk development |
| `KOMSAR_COOKIE_SECURE` | `1` | cookie sesi hanya lewat HTTPS; `0` hanya untuk development lewat `http://127.0.0.1` |
| `KOMSAR_SEED_DEMO` | `0` | `1` = `run.py` membuat akun contoh (development) |
| `VOICE_BACKEND` | `speechbrain` | `fake` hanya untuk test/development; bersama `FLASK_DEBUG=1` langkah suara dilewati |
| `ENROLL_WINDOW_HOURS` | `24` | batas waktu login pertama (daftar suara + ganti password) |
| `DONGLE_HEARTBEAT_TIMEOUT` | `60` | detik sejak heartbeat dongle terakhir sebelum sesi dikunci |

Semua data (pengguna, pesan, ciphertext file, gambar steganografi, blok blockchain) disimpan di database dan
bertahan saat server restart. Tabel dibuat otomatis (`db.create_all()`). Database SQLite lama dari versi
sebelumnya perlu dihapus (`instance/komsar.db`) karena tabel `users` dan `audit_logs` mendapat kolom baru.

## Alur login
```
[1] /login          username + password + bukti dongle (dibaca aplikasi desktop)
        | lolos -> sesi sementara (pending), berlaku 3 menit, BELUM login
        |-- akun baru / suara di-reset (must_enroll) -> [2b] /login/enroll
        |-- punya profil suara                       -> [2a] /login/voice
        '-- tidak keduanya                           -> ditolak (hubungi admin)
[2a] /login/voice   ucapkan kalimat acak -> verifikasi suara -> dashboard
[2b] /login/enroll  ganti password sementara, lalu rekam 3 kalimat acak -> dashboard
```
- Halaman login hanya berfungsi di aplikasi desktop KomSaR (`window.pywebview`). Di browser biasa muncul
  "Gunakan aplikasi desktop KomSaR" dan tombol login dinonaktifkan.
- Pesan galat selalu sama: "Username, password, atau dongle tidak valid". Alasan sebenarnya
  (`password`, `dongle`, `locked`, `expired`) hanya dicatat di audit log.
- **Lockout**: 5 kali password salah, atau 3 kali suara salah dalam satu sesi login (maks. 5 kegagalan gabungan
  sebelum login berhasil), akun dikunci 15 menit (`account_locked`). Login berhasil me-reset hitungan.
- **Login pertama**: admin menambah pengguna tanpa mengetik password; sistem membuat password sementara
  12 karakter yang ditampilkan **sekali** ke admin. Pemilik akun harus login dalam `ENROLL_WINDOW_HOURS` jam,
  mengganti password (min. 8 karakter, berbeda dari password sementara), lalu merekam 3 sampel suara. Lewat
  batas waktu, login ditolak sampai admin menekan **Reset suara** (yang juga membuat password sementara baru).
  Pengguna tidak bisa mendaftar ulang suara sendiri.
- Sesi penuh: cookie `Secure`, `HttpOnly`, `SameSite=Lax`, umur maks. 8 jam. Logout menghapus seluruh sesi.

### Bootstrap admin pertama
Jalankan di laptop admin (Windows, flashdisk tercolok) dengan `.env` yang sama dengan server (`DATABASE_URL` Neon):
```
flask --app run komsar bootstrap-admin
# non-interaktif:
flask --app run komsar bootstrap-admin --username admin01 --full-name "Administrator" --drive E:\ --label "Dongle 1"
```
Perintah ini membuat akun admin (`must_enroll`, password sementara dicetak sekali), mendaftarkan flashdisk
yang dipilih, dan menulis `KOMSAR.DONGLE` ke flashdisk itu. Suara **tidak** direkam di CLI: admin mendaftarkan
suara saat login pertama di aplikasi desktop, sama seperti pengguna lain. Perintah menolak bila sudah ada admin,
kecuali diberi `--force`.

## Halaman Aplikasi
| Halaman | Akses | Isi |
|---|---|---|
| `/dashboard` | login | ringkasan |
| `/chat` | login | kirim pesan, kotak masuk, kotak terkirim (status per penerima, termasuk `Gagal`) |
| `/chat/<username>` | login | percakapan dua arah dengan satu pengguna, urut waktu, hanya ciphertext + tombol "Buka" |
| `/transfer` | login | kirim file/gambar/aset penting + daftar file terkirim beserta status |
| `/files` | login | riwayat file/gambar/aset yang dikirim dan diterima |
| `/assets` | login | aset penting + status integritas blockchain |
| `/decrypt` | login | Decryption Center (ID -> kunci stego -> dekripsi) |
| `/users/` | login (ubah: admin) | daftar pengguna, tautan percakapan; admin: tambah/ubah/hapus/regenerate ID |
| `/profile` | login | ganti password |
| `/admin/chain` | admin | Blockchain Records |
| `/admin/dongles` | admin | daftar & nonaktifkan dongle |
| `/admin/audit` | admin | audit log, filter pengguna & aksi, 50 baris/halaman |

Audit log (`app/services/audit_service.py`, nama aksi di `ACTIONS`) mencatat login sukses/gagal (beserta
alasan), langkah 1 login, verifikasi/pendaftaran/reset suara, ganti password, penguncian akun, logout,
pengiriman, dekripsi sukses/gagal, kegagalan integritas aset, aksi admin, serta daftar/nonaktif dongle,
lengkap dengan IP dan `dongle_id` sesi. Log tidak pernah berisi plaintext, kunci rahasia, User ID, token
dongle, atau password. Bila paket untuk satu penerima gagal dibuat, paket itu berstatus `failed` dan
penerima lain tetap terkirim.

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
Bukti dongle wajib saat login dan heartbeat ditegakkan selama sesi bila `KOMSAR_REQUIRE_DONGLE=1` (default).

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

Endpoint (hanya sesi login pending + header `X-CSRF-Token`): `POST /api/voice/challenge`
`{purpose: "enroll"|"verify"}`, `POST /api/voice/enroll` `{samples: [{challenge_id, wav_b64}] x3}`,
`POST /api/voice/verify` `{challenge_id, wav_b64}` -> `{ok}`. `verify` hanya untuk akun yang punya profil suara,
`enroll` hanya untuk akun `must_enroll` yang sudah mengganti password sementara. Bila `ok`, server langsung
menyelesaikan login. Helper halaman: `static/voice.js` (`komsarVoice.enroll/verify`), dipakai `static/login.js`.

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
