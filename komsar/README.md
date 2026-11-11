# KomSaR — Komunikasi Satuan Rakyat

Aplikasi komunikasi aman antarsatuan (Flask): super encryption, steganografi LSB, file terenkripsi,
blockchain sederhana, dan login tiga faktor (password + dongle flashdisk + suara).

## Arsitektur
```
Aplikasi desktop (desktop/, pywebview, Windows)      Server Flask (InstaCloud, Docker, gunicorn 1 worker)
  - baca dongle KOMSAR.DONGLE di flashdisk   HTTPS     - route -> service -> crypto/stego/blockchain
  - rekam suara (mikrofon)                 ------->    - verifikasi suara SpeechBrain ECAPA (di server)
  - buka halaman server di jendela                     - semua data di PostgreSQL Neon
```
- Semua data (pengguna, pesan, ciphertext file, gambar steganografi, blok blockchain, dongle, profil suara
  terenkripsi, audit log) disimpan di database dan bertahan saat server restart/tidur. Tabel dibuat otomatis
  (`db.create_all()`). Tanpa `DATABASE_URL` dipakai SQLite lokal `instance/komsar.db` (development/test).
- User ID dibuat acak oleh sistem (`XXXX-XXXX-XXXX`, mis. `K7QX-92MF-TR4D`). Hanya admin yang melihatnya
  (menu **Pengguna**) dan menyampaikannya ke pemilik akun.
- Login hanya lewat aplikasi desktop; browser biasa tidak bisa membaca dongle.

Dokumen terkait:
- [`../README.md`](../README.md): ringkasan proyek, tangkapan layar, dan pemetaan ketentuan tugas.
- [`docs/teknis.md`](docs/teknis.md): algoritma, alur kriptografi detail, struktur kode, pengujian.
- [`docs/alur-fitur.md`](docs/alur-fitur.md): alur fitur untuk pengguna dan admin.
- [`docs/deploy.md`](docs/deploy.md): deploy ke InstaCloud + Neon, secret, bootstrap admin produksi.
- [`desktop/README.md`](desktop/README.md): instalasi, build, dan kontrak klien desktop.
- [`docs/uji-manual.md`](docs/uji-manual.md): checklist uji manual dengan perangkat nyata.
- [`docs/keamanan.md`](docs/keamanan.md): keterbatasan keamanan.
- [`docs/PLAN.md`](docs/PLAN.md): rencana dan status implementasi.

## Menjalankan lokal (mode development, di browser)
Login normal butuh aplikasi desktop (dongle + mikrofon). Untuk mencoba di browser biasa, matikan dongle dan
pakai backend suara palsu; langkah suara lalu dilewati **hanya** bila `VOICE_BACKEND=fake` **dan** mode debug:
```
uv venv --python 3.12 .venv
uv pip install --python .venv -r requirements.txt
# PowerShell:
$env:KOMSAR_REQUIRE_DONGLE="0"; $env:KOMSAR_COOKIE_SECURE="0"; $env:VOICE_BACKEND="fake"
$env:FLASK_DEBUG="1"; $env:KOMSAR_SEED_DEMO="1"
.venv\Scripts\python run.py
```
Lalu buka **http://127.0.0.1:5000**. Pertama kali dijalankan, `run.py` otomatis membuat `.env` (kunci acak).
Dengan `KOMSAR_SEED_DEMO=1` dibuat akun contoh (password semua: `komsar123`): `admin01` (admin), `andi01`,
`budi01`, `citra01`, `deni01`. User ID-nya dicetak di konsol saat dibuat; admin juga melihatnya di menu Pengguna.
**Jangan pernah memakai kelima variabel di atas di server produksi** (akun contoh hanya untuk development).

Gambar cover steganografi ada di `assets/covers/` (foto CC0/public domain, sumbernya di
`assets/covers/SUMBER.md`). Cover tambahan cukup disalin ke folder itu sebagai PNG.

Test: `.venv\Scripts\python -m pytest -q` (SQLite di memori, `VOICE_BACKEND=fake`, Argon2 diringankan).

## Konfigurasi (`.env` / secret server)
| Variabel | Default | Keterangan |
|---|---|---|
| `KOMSAR_SECRET_KEY` | (wajib) | kunci sesi Flask |
| `KOMSAR_DB_MASTER_KEY` | (wajib) | 32 byte base64, lapisan enkripsi pesan penting dan profil suara. **Cadangkan** |
| `DATABASE_URL` | SQLite `instance/komsar.db` | Neon: `postgresql://user:pass@host/db?sslmode=require` (otomatis driver psycopg) |
| `KOMSAR_ENV` | `development` | `production` = secret + `DATABASE_URL` wajib, server menolak start bila kosong |
| `KOMSAR_TRUST_PROXY` | `0` | `1` di belakang reverse proxy HTTPS (InstaCloud, 1 hop) |
| `MAX_FILE_MB` | `10` | batas ukuran file; file disimpan di database |
| `KOMSAR_REQUIRE_DONGLE` | `1` | login butuh dongle dan setiap request butuh heartbeat dongle; `0` hanya development |
| `DONGLE_HEARTBEAT_TIMEOUT` | `60` | detik sejak heartbeat dongle terakhir sebelum sesi diakhiri |
| `KOMSAR_COOKIE_SECURE` | `1` | cookie sesi hanya lewat HTTPS; `0` hanya development lewat `http://127.0.0.1` |
| `VOICE_BACKEND` | `speechbrain` | `fake` hanya test/development; bersama `FLASK_DEBUG=1` langkah suara dilewati |
| `VOICE_MODEL_DIR` | `models/spkrec-ecapa-voxceleb` | folder model SpeechBrain (di image: `/app/models/...`) |
| `VOICE_THRESHOLD` | `0.25` | skor cosine minimal; kalibrasi dengan suara tim (`docs/uji-manual.md`) |
| `ENROLL_WINDOW_HOURS` | `24` | batas waktu login pertama (ganti password + daftar suara) |
| `KOMSAR_SEED_DEMO` | `0` | `1` = `run.py` membuat akun contoh (development) |
| `FLASK_DEBUG` | `0` | `1` = mode debug `run.py` (development) |
| `ARGON2_TIME_COST`, `ARGON2_MEMORY_KIB`, `ARGON2_PARALLELISM` | `3`, `65536`, `2` | parameter KDF Argon2id |

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
  (`password`, `dongle`, `locked`, `expired`) hanya dicatat di audit log. Username tak dikenal tetap menjalankan
  verifikasi Argon2 (hash dummy) agar waktu respons serupa.
- **Lockout**: 5 kali password salah, atau 3 kali suara salah dalam satu sesi login (maks. 5 kegagalan gabungan
  sebelum login berhasil), akun dikunci 15 menit (`account_locked`). Login berhasil me-reset hitungan.
- **Login pertama**: admin menambah pengguna tanpa mengetik password; sistem membuat password sementara
  12 karakter yang ditampilkan **sekali** ke admin. Pemilik akun harus login dalam `ENROLL_WINDOW_HOURS` jam,
  mengganti password (min. 8 karakter, berbeda dari password sementara), lalu merekam 3 sampel suara. Lewat
  batas waktu, login ditolak sampai admin menekan **Reset suara** (yang juga membuat password sementara baru).
  Pengguna tidak bisa mendaftar ulang suara sendiri.
- Sesi penuh: cookie `Secure`, `HttpOnly`, `SameSite=Lax`, umur maks. 8 jam. Logout menghapus seluruh sesi.

### Bootstrap admin pertama
Dijalankan di laptop admin (Windows, flashdisk tercolok) langsung ke database Neon. Langkah lengkap dan
environment variable yang dibutuhkan ada di [`docs/deploy.md`](docs/deploy.md) bagian 7:
```
flask --app wsgi komsar bootstrap-admin
# non-interaktif:
flask --app wsgi komsar bootstrap-admin --username admin01 --full-name "Administrator" --drive E:\ --label "Dongle 1"
```
Perintah ini membuat akun admin (`must_enroll`, password sementara dicetak sekali), mendaftarkan flashdisk
yang dipilih, dan menulis `KOMSAR.DONGLE` ke flashdisk itu. Suara **tidak** direkam di CLI: admin mendaftarkan
suara saat login pertama di aplikasi desktop. Perintah menolak bila sudah ada admin, kecuali diberi `--force`.

## Halaman Aplikasi
| Halaman | Akses | Isi |
|---|---|---|
| `/dashboard` | login | ringkasan |
| `/chat` | login | kirim pesan, kotak masuk, kotak terkirim (status per penerima, termasuk `Gagal`) |
| `/chat/<username>` | login | percakapan dua arah dengan satu pengguna, urut waktu, hanya ciphertext + tombol "Buka" |
| `/transfer` | login | kirim file/gambar/aset penting + daftar file terkirim beserta status |
| `/files` | login | riwayat file/gambar/aset yang dikirim dan diterima |
| `/assets` | login | aset penting + status integritas blockchain |
| `/decrypt` | login | Decryption Center (User ID -> kunci stego -> dekripsi) |
| `/users/` | login (ubah: admin) | daftar pengguna, tautan percakapan; admin: tambah/ubah/hapus/regenerate ID/reset suara |
| `/profile` | login | ganti password |
| `/admin/chain` | admin | Blockchain Records |
| `/admin/dongles` | admin | daftarkan & nonaktifkan dongle |
| `/admin/audit` | admin | audit log, filter pengguna & aksi, 50 baris/halaman |
| `/healthz` | publik | `ok` untuk health check InstaCloud |

Alur dekripsi: gambar steganografi tampil -> penerima input User ID -> kunci hasil ekstraksi ditampilkan ->
penerima mengetik ulang kunci itu -> sistem menggabungkan ID + kunci -> data terbuka.

Audit log (`app/services/audit_service.py`, nama aksi di `ACTIONS`) mencatat login sukses/gagal (beserta
alasan), langkah 1 login, verifikasi suara (beserta skor cosine untuk kalibrasi), pendaftaran/reset suara,
ganti password, penguncian akun, logout, pengiriman, dekripsi sukses/gagal, kegagalan integritas aset, aksi
admin, serta daftar/nonaktif dongle, lengkap dengan IP dan `dongle_id` sesi. Log tidak pernah berisi plaintext,
kunci rahasia, User ID, token dongle, atau password. Bila paket untuk satu penerima gagal dibuat, paket itu
berstatus `failed` dan penerima lain tetap terkirim.

## Dongle flashdisk
File `KOMSAR.DONGLE` di root flashdisk berisi `dongle_id` dan token acak 32 byte. Server hanya menyimpan
SHA-256(token) dan serial volume flashdisk, jadi file yang disalin ke flashdisk lain ditolak. Semua dongle
terdaftar berlaku untuk semua pengguna.

Mendaftarkan dongle (admin, wajib lewat aplikasi desktop):
1. Colokkan flashdisk, buka menu **Dongle** (`/admin/dongles`).
2. Pilih flashdisk, isi label, klik **Daftarkan dongle**. Server membuat ID + token, aplikasi menulis file ke flashdisk.
3. Bila penulisan gagal, nonaktifkan entri baru itu lalu ulangi. Flashdisk hilang: klik **Nonaktifkan**.

Endpoint: `POST /api/dongle/check` (tanpa login, dipakai klien desktop, dibatasi 30 request/menit per IP),
`POST /api/dongle/register` (admin), `POST /api/dongle/heartbeat` (dikirim halaman tiap 30 detik).

## Verifikasi suara
Model `speechbrain/spkrec-ecapa-voxceleb` mengubah rekaman menjadi embedding, lalu dibandingkan dengan
cosine similarity. Server memasang `requirements-server.txt` (torch CPU, model di-*bake* ke image Docker);
`requirements.txt` tetap tanpa torch, dan test memakai `VOICE_BACKEND=fake`.

- Rekaman: WAV PCM 16-bit, 16000 Hz, mono, 2 sampai 10 detik, maks. 1 MB (direkam aplikasi desktop).
- Pendaftaran: pemilik akun merekam **3 sampel**, masing-masing dengan kalimat acak 4 kata (berlaku 2 menit,
  sekali pakai). Embedding dirata-rata, dinormalisasi, lalu disimpan terenkripsi AES-256-GCM di `voice_profiles`.
  Rekaman WAV tidak disimpan.
- Verifikasi: dibandingkan hanya dengan profil akun itu; lolos bila skor >= `VOICE_THRESHOLD`.
- Reset: admin menekan **Reset suara** di halaman edit pengguna.

Endpoint (hanya sesi login pending + header `X-CSRF-Token`): `POST /api/voice/challenge`
`{purpose: "enroll"|"verify"}`, `POST /api/voice/enroll` `{samples: [{challenge_id, wav_b64}] x3}`,
`POST /api/voice/verify` `{challenge_id, wav_b64}` -> `{ok}`. Bila `ok`, server langsung menyelesaikan login.

## Pemakaian service (contoh)
```python
svc = app.extensions["komsar"]
msg = svc.messaging.send_text(sender, ["budi01", "citra01"], "Halo", "K123", important=True)
inbox = svc.messaging.inbox(budi)                       # data chatbox (tanpa plaintext)
res = svc.decryption.open(budi, inbox[0]["delivery_id"], budi.user_id)

svc.messaging.send_file(andi, ["budi01"], "kontrak.pdf", data, "K123", kind="asset")   # otomatis membuat blok
svc.assets.verify_integrity(budi, asset_id)  # verified / ciphertext_modified / chain_broken / ...
svc.chain.validate()                         # validasi seluruh rantai
```

## Status
Semua fase (database, User ID acak, audit/status `failed`/percakapan, dongle, suara, login tiga faktor,
aplikasi desktop, deploy, hardening) sudah diimplementasikan dan teruji otomatis. Yang belum diverifikasi di
perangkat nyata: lihat bagian "Status implementasi" di [`docs/PLAN.md`](docs/PLAN.md).
