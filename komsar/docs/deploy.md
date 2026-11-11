# Deploy KomSaR ke InstaCloud + Neon

Server KomSaR berjalan sebagai container Docker di InstaCloud dan menyimpan data di PostgreSQL Neon.
Klien desktop (`desktop/`) tidak ikut di-deploy; klien hanya diarahkan ke URL server.

Tanda **[belum diverifikasi]** berarti perilaku InstaCloud itu belum kami cek langsung; pastikan saat deploy pertama.

## 1. Gambaran

| Komponen | Isi |
|---|---|
| `Dockerfile` (root repo) | `python:3.12-slim`, torch CPU-only, `requirements-server.txt` + gunicorn, model SpeechBrain di-*bake* ke `/app/models/spkrec-ecapa-voxceleb`, user non-root, port 8080 |
| `.dockerignore` (root repo) | Membuang `.git`, `.venv`, `komsar/tests`, `komsar/desktop` (kecuali `desktop/dongle.py` yang dipakai CLI), `.env`, `instance/`, `storage/`, `models/` |
| `komsar/wsgi.py` | Entry point produksi: `create_app()` tanpa membuat `.env` dan tanpa akun contoh. Memanaskan model suara di thread background |
| `GET /healthz` | Balas `ok` (200). Tanpa DB, tanpa login, tanpa cek dongle, tanpa memuat model suara |

Image menyetel `KOMSAR_ENV=production`, `KOMSAR_TRUST_PROXY=1`, `VOICE_BACKEND=speechbrain`,
`VOICE_MODEL_DIR=/app/models/spkrec-ecapa-voxceleb`. Dengan `KOMSAR_ENV=production` server **menolak start**
bila `KOMSAR_SECRET_KEY`, `KOMSAR_DB_MASTER_KEY`, atau `DATABASE_URL` kosong (tidak diam-diam memakai SQLite).

Gunicorn dijalankan dengan **1 worker** (`-w 1 --threads 4`). Ini wajib: cache hasil dekripsi, kalimat tantangan
suara, dan rate limit disimpan di memori proses. Jangan menaikkan jumlah worker.

## 2. Siapkan database Neon

1. Login ke <https://console.neon.tech>, buat project baru (region terdekat, mis. Singapore).
2. Di **Connection Details**, pilih **Pooled connection** lalu salin connection string. Bentuknya:
   `postgresql://USER:PASSWORD@ep-xxxx-pooler.REGION.aws.neon.tech/neondb?sslmode=require`
3. Pastikan ada `sslmode=require` di akhir. Aplikasi otomatis mengganti `postgresql://` menjadi driver `psycopg`.
4. Tabel dibuat otomatis oleh aplikasi saat start pertama (`db.create_all()`).

## 3. Buat secret

Jalankan di komputer sendiri (bukan di server), lalu simpan hasilnya:

```bash
python -c "import secrets; print(secrets.token_hex(32))"                          # KOMSAR_SECRET_KEY
python -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"   # KOMSAR_DB_MASTER_KEY
```

> **PERINGATAN: CADANGKAN `KOMSAR_DB_MASTER_KEY` DI TEMPAT AMAN DI LUAR REPO (password manager / brankas tim).**
> Kunci ini membungkus kunci-kunci di database. Bila hilang atau terganti, pesan penting dan aset terenkripsi
> **tidak bisa dibuka lagi**, dan tidak ada cara memulihkannya. Jangan pernah commit kunci ini ke Git.

`KOMSAR_SECRET_KEY` boleh diganti kapan saja (efeknya hanya semua sesi login berakhir).

## 4. Set secret di InstaCloud (`insta` CLI)

Secret disuntikkan ke container sebagai environment variable.

```bash
insta login
insta secrets set KOMSAR_SECRET_KEY=<hasil token_hex>
insta secrets set KOMSAR_DB_MASTER_KEY=<hasil base64 32 byte>
insta secrets set DATABASE_URL='postgresql://...-pooler...neon.tech/neondb?sslmode=require'
insta secrets set KOMSAR_REQUIRE_DONGLE=1
insta secrets set VOICE_BACKEND=speechbrain
insta secrets set VOICE_THRESHOLD=0.25          # sesuaikan hasil kalibrasi suara tim
```

Opsional: `MAX_FILE_MB` (default 10), `DONGLE_HEARTBEAT_TIMEOUT` (default 60 detik),
`ENROLL_WINDOW_HOURS` (default 24).

- **[belum diverifikasi]** Apakah secret di-set per service atau per project, dan apakah perlu `--service <nama>`.
  Cek `insta secrets --help`.
- **[belum diverifikasi]** Apakah perubahan secret memicu redeploy otomatis atau perlu deploy ulang manual.
- Tanda kutip di `DATABASE_URL` penting karena ada `?` dan `&` yang dibaca shell.

## 5. Hubungkan repo GitHub

1. Di console InstaCloud buat service baru dari GitHub, pilih repo ini, branch `main`.
2. InstaCloud membangun `Dockerfile` di **root repo** (aplikasi sengaja disalin dari `komsar/` di dalam Dockerfile,
   karena pemilihan subfolder monorepo tidak terdokumentasi). Tidak ada pengaturan build/start command:
   semuanya dikendalikan oleh `Dockerfile`.
3. Port yang dipakai adalah `EXPOSE` terakhir, yaitu **8080**.
4. Setiap push ke `main` langsung di-deploy.

> **InstaCloud tidak punya rollback.** Deploy yang rusak langsung aktif. Selalu jalankan test sebelum push:
>
> ```bash
> cd komsar
> .venv/Scripts/python -m pytest -q
> ```
>
> Beri tag pada commit yang stabil (`git tag v1.0`) agar mudah kembali dengan push ulang commit lama.

Build pertama lama (mengunduh torch CPU dan model SpeechBrain). Build berikutnya lebih cepat bila layer
dependency tidak berubah **[belum diverifikasi: cache build InstaCloud]**.

## 6. Cek setelah deploy pertama

- [ ] URL service memakai **HTTPS** dan sertifikatnya valid (gembok di browser).
- [ ] `curl https://<url-service>/healthz` membalas `ok`.
- [ ] Halaman login terbuka; cookie sesi ber-flag `Secure` (DevTools > Application > Cookies).
- [ ] Log start tidak berisi `KOMSAR_ENV=production: env wajib belum diisi`.
- [ ] **RAM**: catat pemakaian setelah login suara pertama (model ECAPA + torch kira-kira beberapa ratus MB).
      Batas RAM default paket free **[belum diverifikasi]**; naikkan bila container mati karena OOM.
- [ ] **Waktu bangun**: service *scale to zero* saat idle. Biarkan idle, lalu ukur waktu `/healthz` pertama
      (container start + import Flask/SQLAlchemy). Model suara dimuat di thread background sejak start, jadi
      login suara yang datang beberapa detik setelah bangun bisa sedikit lebih lambat (menunggu model selesai dimuat).
      Koneksi Neon juga bisa butuh waktu bangun sendiri (Neon juga *scale to zero*).
- [ ] Audit log mencatat IP klien asli, bukan IP proxy (berkat `KOMSAR_TRUST_PROXY=1` / ProxyFix).
      **[belum diverifikasi]** Jumlah hop proxy InstaCloud diasumsikan 1; bila IP yang tercatat masih IP internal,
      jumlah hop perlu disesuaikan di `create_app`.

## 7. Buat admin pertama (dari komputer lokal)

Admin dibuat langsung ke database Neon dari laptop yang tercolok flashdisk dongle admin (Windows).
Tidak perlu akses ke container.

PowerShell, dari folder `komsar/` dengan `.venv` terpasang:

```powershell
$env:KOMSAR_ENV = "production"
$env:DATABASE_URL = "postgresql://...-pooler...neon.tech/neondb?sslmode=require"
$env:KOMSAR_SECRET_KEY = "<sama dengan di InstaCloud>"
$env:KOMSAR_DB_MASTER_KEY = "<SAMA PERSIS dengan di InstaCloud>"
$env:VOICE_BACKEND = "fake"          # CLI tidak memakai model suara; hindari memuat torch
.venv\Scripts\flask --app wsgi komsar bootstrap-admin
```

Pakai `--app wsgi` (bukan `run`) agar tidak terbuat `.env` lokal dengan kunci acak. `KOMSAR_DB_MASTER_KEY`
**harus sama** dengan yang dipakai server; bila beda, data yang dibuat CLI tidak bisa dibaca server.
`VOICE_BACKEND=fake` hanya untuk sesi CLI ini (wsgi.py tidak memanaskan model bila backend bukan speechbrain).

Perintah akan meminta username dan nama, menulis `KOMSAR.DONGLE` ke flashdisk, lalu menampilkan password
sementara sekali. Admin login pertama di aplikasi desktop, ganti password, lalu daftar suara.

## 8. Arahkan klien desktop

Di folder aplikasi desktop, isi `config.json`:

```json
{"server_url": "https://<url-service-instacloud>"}
```

Tanpa garis miring di akhir. Lihat `desktop/README.md` untuk build dan pemakaian klien.

## 9. Mode uji coba (tanpa dongle / admin tanpa suara)

Selama dongle fisik belum siap, server bisa dijalankan dengan dua flag sementara:

```powershell
insta --agent secrets set KOMSAR_REQUIRE_DONGLE 0     # login & sesi tanpa dongle
insta --agent secrets set KOMSAR_ADMIN_SKIP_VOICE 1   # akun admin login tanpa langkah suara
# lalu deploy ulang / insta --agent compute restart komsar
```

- Klien desktop menanyakan `GET /api/client-config` saat start. Bila `require_dongle` false, gerbang dongle dilewati,
  jadi `.exe` yang sama tetap dipakai saat dongle nanti diaktifkan kembali.
- Admin dibuat tanpa flashdisk: `flask --app wsgi komsar bootstrap-admin --no-dongle`.
- Pengguna biasa **tetap** wajib suara (login pertama: ganti password lalu daftar suara).
- Admin dengan flag ini tetap memakai password sementara sampai diganti di halaman Profil.
- **Kembalikan kedua flag ke nilai produksi** (`KOMSAR_REQUIRE_DONGLE=1`, `KOMSAR_ADMIN_SKIP_VOICE=0`) setelah dongle
  terdaftar dan suara admin didaftarkan (admin lain menekan "Reset suara" agar admin ini mendaftar di login berikutnya).

## 10. Ringkasan environment variable produksi

| Variabel | Wajib | Sumber |
|---|---|---|
| `KOMSAR_SECRET_KEY` | ya | `insta secrets set` |
| `KOMSAR_DB_MASTER_KEY` | ya (cadangkan!) | `insta secrets set` |
| `DATABASE_URL` | ya | `insta secrets set` (Neon pooled, `sslmode=require`) |
| `KOMSAR_REQUIRE_DONGLE` | disarankan `1` (default `1`) | `insta secrets set` |
| `VOICE_BACKEND` | `speechbrain` (default image) | `insta secrets set` / Dockerfile |
| `VOICE_THRESHOLD` | opsional (default 0.25) | `insta secrets set` |
| `KOMSAR_ADMIN_SKIP_VOICE` | `0` di produksi (`1` hanya uji coba) | `insta secrets set` |
| `KOMSAR_ENV`, `KOMSAR_TRUST_PROXY`, `VOICE_MODEL_DIR`, `HF_HUB_OFFLINE` | sudah di Dockerfile | — |
