# Rencana Pengembangan KomSaR (Tahap 6 dan seterusnya)

Tanggal: 2026-11-10
Cakupan: implementasi kode saja. Laporan dan slide presentasi dikerjakan terpisah.
Riset pendukung: [`riset-desktop-voice-db.md`](riset-desktop-voice-db.md)

## Status implementasi

| Fase | Status |
|---|---|
| 1. Database PostgreSQL/SQLite (record, file, blok di DB) | Selesai, teruji otomatis |
| 2. User ID acak | Selesai, teruji otomatis |
| 3. Audit log, status `failed`, percakapan, riwayat file, Blockchain Records khusus admin | Selesai, teruji otomatis |
| 4. Dongle flashdisk | Selesai, teruji otomatis |
| 5. Verifikasi suara (SpeechBrain, di server) | Selesai, teruji dengan `FakeVoiceVerifier` |
| 6. Login tiga faktor, login pertama, lockout | Selesai, teruji otomatis |
| 7. Aplikasi desktop (pywebview) | Selesai, teruji otomatis tanpa GUI/mikrofon/flashdisk |
| 8. Dockerfile + panduan deploy ([`deploy.md`](deploy.md)) | Selesai, belum di-deploy sungguhan |
| 9. Hardening, test tambahan, dokumentasi, [`uji-manual.md`](uji-manual.md) | Selesai |

Belum diverifikasi (perlu dijalankan dengan checklist [`uji-manual.md`](uji-manual.md)):
- Akurasi SpeechBrain ECAPA dengan suara tim dan kalibrasi `VOICE_THRESHOLD` (skor tercatat di audit log).
- Database Neon sungguhan (koneksi pooled, kuota storage, bangun dari *scale to zero*).
- InstaCloud sungguhan (build image, RAM, waktu bangun, jumlah hop proxy, perilaku secret).
- GUI pywebview, rekam mikrofon, dan baca/tulis flashdisk di laptop Windows tim.

Keterbatasan keamanan versi akhir: [`keamanan.md`](keamanan.md).

---

## 1. Keputusan yang Sudah Disepakati

| Topik | Keputusan |
|---|---|
| Arsitektur | **Server pusat + klien desktop.** Flask di-deploy ke InstaCloud. Klien desktop (pywebview) membuka server lewat HTTPS |
| Database | **PostgreSQL di Neon** (free tier). SQLite hanya dipakai untuk test |
| Penyimpanan file | **Di database** (`bytea`): ciphertext `.enc` dan gambar stego. Folder `storage/` tidak dipakai lagi |
| Framework | **Tetap Flask** (bukan FastAPI) |
| Password | **Tetap Argon2id** |
| Login | **Tiga faktor:** username + password, lalu dongle flashdisk terdaftar, lalu verifikasi suara |
| Dongle | Flashdisk yang **didaftarkan admin**. Semua dongle terdaftar berlaku untuk **semua pengguna di perangkat mana pun**. Wajib ada saat login dan selama sesi |
| Suara | Speaker verification **SpeechBrain ECAPA-TDNN**, diproses **di server**. **Terikat ke satu akun** (akun budi hanya bisa dibuka suara budi). Akun dibuat admin; **pemilik akun mendaftarkan suaranya sendiri saat login pertama** |
| Akses | **Wajib lewat aplikasi desktop.** Browser biasa tidak bisa login karena tidak bisa membaca dongle |
| User ID | **ID acak panjang** buatan sistem (mis. `K7QX-92MF-TR4D`), menggantikan `A001` dkk |
| Fitur tambahan | Audit log, status pesan `failed`, tampilan percakapan per thread + riwayat file, Blockchain Records **khusus admin** |
| Deploy | **InstaCloud via GitHub** (auto-deploy saat push), memakai `Dockerfile` di root repo |

---

## 2. Pemetaan Ketentuan Tugas Akhir

| No | Ketentuan slide | Status sekarang | Yang dikerjakan | Fase |
|---|---|---|---|---|
| 1 | Login biometrik, hanya bisa dihidupkan dengan dongle | Belum (placeholder) | Voice verification + dongle flashdisk + gate aplikasi desktop | 4, 5, 6, 7 |
| 2 | Login memakai algoritma kriptografi | Sudah (Argon2id) | Tetap. Tambah lockout percobaan gagal | 6 |
| 3 | Teks: super enkripsi (klasik + modern) | Sudah (Vigenère, lalu AES-256-GCM) | Tetap. Pindah penyimpanan ke DB | 1 |
| 4 | File: kriptografi berbeda dari teks | Sudah (ChaCha20-Poly1305) | Tetap. Ciphertext disimpan di DB | 1 |
| 5 | Pesan penting dienkripsi di basis data | Lapisan ada, tapi data di memori | Simpan ke PostgreSQL dengan lapisan `db_layer` | 1 |
| 6 | Gambar diamankan dengan steganografi | Sudah (LSB) | User ID acak agar ekstraksi tidak bisa ditebak | 2 |
| 7 | Aset penting dengan blockchain sederhana | Sudah, tapi rantai di memori | Tabel `blocks` di PostgreSQL | 1 |

---

## 3. Arsitektur Target

```
┌──────────────── Klien Desktop (Windows .exe) ────────────────┐
│ pywebview  ── membuka ──► https://<app>.instacloud...         │
│ js_api:                                                       │
│   read_dongle()  → baca KOMSAR.DONGLE dari flashdisk          │
│   record_voice() → rekam mic 16 kHz mono (sounddevice)        │
│ heartbeat dongle tiap 30 detik                                │
└───────────────────────────┬───────────────────────────────────┘
                            │ HTTPS
┌───────────────────────────▼───────────────────────────────────┐
│ Server Flask (InstaCloud, Docker, gunicorn -w 1 --threads 4)  │
│ routes → services → crypto / stego / blockchain               │
│ + auth: password (Argon2id), dongle, voice (SpeechBrain)      │
│ Secrets: KOMSAR_SECRET_KEY, KOMSAR_DB_MASTER_KEY, DATABASE_URL│
└───────────────────────────┬───────────────────────────────────┘
                            │ TLS (sslmode=require)
                   ┌────────▼─────────┐
                   │ Neon PostgreSQL  │
                   └──────────────────┘
```

Prinsip utama: **semua verifikasi terjadi di server.** Klien hanya merekam suara dan membaca file dongle,
lalu mengirimkannya. Kredensial database dan master key **tidak pernah** ada di klien.

---

## 4. Fase Implementasi

### Fase 1: Database PostgreSQL (Neon)

Tujuan: semua data bertahan saat server restart atau tidur (InstaCloud *scale to zero*).

Tabel (SQLAlchemy, dibuat dengan `db.create_all()`; Alembic belum perlu):

| Tabel | Kolom penting | Relasi |
|---|---|---|
| `users` | id, username, user_code (ID acak), password_hash, role, is_active, failed_logins, locked_until, must_enroll, enroll_deadline | sudah ada, ditambah kolom |
| `messages` | id, sender_id, kind (`text`/`file`/`image`/`asset`), important, ciphertext (`bytea`), meta, created_at | `sender_id → users.id` |
| `deliveries` | id, message_id, recipient_id, wrapped_cek, wrap_salt, stego_png (`bytea`), status, error, created_at, decrypted_at | `message_id → messages.id`, `recipient_id → users.id` |
| `files` | id, message_id, original_name, size, mime, algo, ciphertext (`bytea`), ciphertext_sha256 | `message_id → messages.id` (1:1) |
| `blocks` | idx (PK), timestamp, asset_id, ciphertext_hash, metadata_json, sender, recipients_json, previous_hash, hash | `asset_id → files.id` |
| `dongles` | id, label, token_hash, volume_serial, is_active, registered_by, created_at, last_used_at | `registered_by → users.id` |
| `voice_profiles` | user_id (PK), embedding_enc, nonce, sample_count, enrolled_at | `user_id → users.id` (1:1) |
| `audit_logs` | id, user_id, action, target, ip, dongle_id, created_at | `user_id → users.id` |

Pekerjaan:
1. Ubah `MessageRecord`, `DeliveryRecord`, `FileRecord` (dataclass di `models/records.py`) menjadi model SQLAlchemy,
   atau buat `SqlRepository` yang memetakan dataclass ke tabel. **Method publik tetap sama** dengan
   `InMemoryRepository`: `add_message`, `get_message`, `get_delivery`, `get_file`, `deliveries_for_message`,
   `inbox`, `sent_messages`, `asset_files`.
2. Buat `SqlBlockStore` dengan method yang sama: `all`, `append`, `last`.
3. Ganti penyimpanan file: `messaging_service.py`, `decryption_service.py`, dan `asset_service.py` sekarang
   membaca/menulis `enc_path` dan `stego_path` di disk. Ubah agar membaca/menulis kolom `bytea`.
   - `file_cipher` tetap bekerja per chunk ke `io.BytesIO` / file sementara, lalu hasilnya disimpan ke DB.
   - Prinsip "tidak ada plaintext parsial" tetap dipertahankan: dekripsi ke buffer sementara,
     hasil hanya dikembalikan bila semua chunk valid.
4. Ciphertext pesan penting tetap dibungkus `db_layer` (AES-GCM + master key) sebelum masuk kolom `ciphertext`.
5. Turunkan `MAX_FILE_MB` default menjadi **10** karena file disimpan di DB dan kuota Neon free terbatas
   (cek kuota storage Neon free sebelum demo).
6. Tambah `psycopg[binary]` ke `requirements.txt`. `DATABASE_URL` memakai `postgresql+psycopg://...?sslmode=require`.
7. Test: tetap SQLite in-memory agar cepat. Tambah **test restart**: buat app, kirim pesan, buat app baru
   dengan DB yang sama, pesan bisa didekripsi.

### Fase 2: User ID Acak

1. Generator ID: 12 karakter dari alfabet tanpa huruf ambigu (`ABCDEFGHJKMNPQRSTUVWXYZ23456789`),
   format `XXXX-XXXX-XXXX`, memakai `secrets.choice`. Entropi ±59 bit.
2. ID dibuat otomatis saat admin membuat pengguna. Admin melihatnya sekali di halaman detail pengguna,
   lalu menyerahkannya kepada pemiliknya. Admin bisa *regenerate* ID (pesan lama untuk ID lama tidak bisa dibuka lagi; tampilkan peringatan).
3. Input ID di Decryption Center menormalkan huruf besar/kecil dan tanda `-`.
4. Perbarui `seed.py`, test yang memakai `B001` dkk, README, dan `docs/keamanan.md` (keterbatasan No. 1 berubah).

### Fase 3: Fitur Tambahan

1. **Status `failed`**: bila enkripsi/penyisipan stego untuk satu penerima gagal, delivery ditandai `failed`
   dengan pesan error singkat, penerima lain tetap terkirim. Tampilkan di kotak terkirim.
2. **Audit log**: helper `audit(action, target)` dipanggil di: login sukses/gagal (tiap faktor), logout,
   kirim pesan/file, dekripsi sukses/gagal, aksi admin (tambah/ubah/hapus user, daftar dongle/suara),
   kegagalan integritas aset. Halaman `/admin/audit` (admin saja), dengan filter pengguna dan aksi.
   Log **tidak boleh** berisi plaintext, kunci rahasia, User ID, atau token dongle.
3. **Tampilan percakapan**: `/chat/<username>` menampilkan pesan dua arah antara dua pengguna, urut waktu.
   Isi tetap ciphertext sampai dibuka lewat Decryption Center (tombol "Buka" mengarah ke sana).
   Halaman `/files` berisi riwayat file/gambar terkirim dan diterima.
4. **Blockchain Records** tetap khusus admin (sudah sesuai).

### Fase 4: Dongle Flashdisk

Isi file `KOMSAR.DONGLE` di root flashdisk (JSON):
```json
{"v": 1, "dongle_id": "<uuid>", "token": "<32 byte acak, base64>"}
```

Server menyimpan `token_hash = SHA-256(token)` (token berentropi tinggi, jadi SHA-256 cukup) dan
`volume_serial` flashdisk.

Pendaftaran (admin, di aplikasi desktop):
1. Admin membuka `/admin/dongles`, mencolokkan flashdisk, klik "Daftarkan".
2. Klien membaca serial volume flashdisk, server membuat `dongle_id` + `token`, klien menulis file ke flashdisk.
3. Admin bisa menonaktifkan dongle (mis. flashdisk hilang).

Verifikasi (server):
- Klien mengirim `dongle_id`, `token`, dan `volume_serial`.
- Server memeriksa: dongle ada, aktif, `compare_digest(SHA-256(token), token_hash)`, serial cocok.
- Serial yang tidak cocok berarti file disalin ke flashdisk lain, jadi ditolak.

Kapan dicek:
1. **Saat aplikasi dibuka**: klien menolak menampilkan halaman login bila tidak ada dongle terdaftar
   (`/api/dongle/check`).
2. **Saat login**: bukti dongle wajib dikirim bersama username + password.
3. **Selama sesi**: klien mengirim heartbeat tiap 30 detik. Server mencatat `last_dongle_seen` di sesi.
   Request apa pun ditolak dan sesi diakhiri bila heartbeat terakhir lebih dari 60 detik.
   Mencabut flashdisk berarti sesi terkunci.

Klien membaca flashdisk di Windows lewat `ctypes` (`GetLogicalDrives`, `GetDriveTypeW == DRIVE_REMOVABLE`,
`GetVolumeInformationW` untuk serial). Tanpa dependensi tambahan.

### Fase 5: Voice Recognition

Server:
1. Modul `app/auth/voice.py` dengan antarmuka `VoiceVerifier`:
   - `embed(wav_bytes) -> np.ndarray`
   - `score(embedding_a, embedding_b) -> float` (cosine similarity)
2. Implementasi `SpeechBrainVerifier` memuat model `speechbrain/spkrec-ecapa-voxceleb` **sekali** saat start
   (lazy, cache di proses). Model di-*bake* ke Docker image saat build, agar tidak mengunduh saat runtime.
3. `FakeVoiceVerifier` untuk test (embedding deterministik dari isi file), agar test tidak butuh PyTorch.
4. Validasi upload: WAV, 16 kHz mono, durasi 2 sampai 10 detik, ukuran maksimal 1 MB.

Pendaftaran (**oleh pemilik akun sendiri, saat login pertama**):
1. Admin membuat akun dengan **password sementara**. Akun ditandai `must_enroll = true` dan diberi
   `enroll_deadline` (mis. 24 jam). Lewat batas waktu, akun terkunci sampai admin me-reset.
2. Login pertama: username + password sementara + dongle. Langkah suara dilewati karena belum ada profil.
3. Pengguna langsung diarahkan ke halaman wajib **"Daftarkan suara"** dan **"Ganti password"**.
   Halaman lain tidak bisa diakses sebelum keduanya selesai.
4. Rekam **3 sampel** ±5 detik, masing-masing dengan kalimat acak berbeda.
   Embedding dirata-rata lalu dinormalisasi. Simpan ke `voice_profiles`, dienkripsi AES-256-GCM via `db_layer`.
5. Rekaman WAV **tidak disimpan**, hanya embedding terenkripsi.
6. Setelah terdaftar, pengguna **tidak bisa mengganti suaranya sendiri**. Bila perlu daftar ulang
   (suara berubah, mikrofon baru), admin menekan **"Reset suara"**. Akun kembali ke status `must_enroll`
   dengan password sementara baru.

Verifikasi saat login berikutnya:
1. Server memberi **kalimat acak** (mis. 4 kata dari daftar kata) yang berlaku 2 menit.
2. Klien merekam ±4 detik dan mengirimkannya.
3. Server membandingkan dengan **profil suara milik akun itu saja**. Skor ≥ `VOICE_THRESHOLD` berarti lolos.
4. **Kalibrasi threshold** dengan suara anggota tim: rekam suara sendiri dan suara orang lain, pilih nilai di antaranya.
   Simpan sebagai konfigurasi (`VOICE_THRESHOLD`, default awal 0.25, sesuaikan setelah kalibrasi).

Keterbatasan yang dicatat di `docs/keamanan.md`:
- Rekaman ulang (*replay*) suara asli belum bisa dideteksi karena isi kalimat tidak dicek dengan speech-to-text.
- Login pertama hanya dilindungi password sementara + dongle. Siapa pun yang mendapat password sementara
  sebelum pemilik akun bisa mendaftarkan suaranya sendiri lebih dulu. Mitigasi: password sementara
  diserahkan langsung, `enroll_deadline` pendek, dan pendaftaran suara dicatat di audit log.

### Fase 6: Alur Login Baru dan Hardening

```
[Aplikasi dibuka] → dongle terdaftar? ─ tidak → layar "Colokkan dongle"
        │ ya
[1] username + password + bukti dongle
        │ lolos
[2] ucapkan kalimat acak → verifikasi suara
        │ lolos
[Dashboard]  (heartbeat dongle tiap 30 detik)
```

1. Sesi sementara di antara langkah 1 dan 2 (`pending_user_id`, kedaluwarsa 3 menit). Belum dianggap login.
2. Akun dengan `must_enroll = true`: setelah langkah 1, langsung ke pendaftaran suara + ganti password,
   bukan ke verifikasi suara. Akun tanpa profil suara dan tanpa `must_enroll` ditolak.
3. **Lockout**: 5 kali gagal password atau 3 kali gagal suara, akun terkunci 15 menit. Dicatat di audit log.
4. Pesan galat login disamakan ("username, password, atau dongle tidak valid").
5. **Bootstrap admin pertama**: perintah CLI `flask --app run komsar bootstrap-admin` dijalankan di laptop
   admin dengan `DATABASE_URL` Neon. Perintah ini membuat akun admin (password sementara, `must_enroll`) dan
   mendaftarkan flashdisk yang dicolok. Suara admin didaftarkan saat login pertama di aplikasi desktop.
6. Hapus akun contoh `komsar123` dari seed produksi. Seed contoh hanya untuk mode development/test.
7. Cookie sesi: `Secure`, `HttpOnly`, `SameSite=Lax`, batas umur sesi 8 jam.

### Fase 7: Aplikasi Desktop

1. `desktop/main.py`:
   - Cek dongle dulu. Bila tidak ada, tampilkan halaman lokal "Colokkan dongle" dan cek ulang tiap 2 detik.
   - Bila ada, buka `webview.create_window("KomSaR", SERVER_URL, js_api=Bridge())`.
   - `Bridge` menyediakan `read_dongle()`, `write_dongle(...)` (pendaftaran admin), `record_voice(seconds)`.
   - Thread heartbeat: tiap 30 detik membaca dongle dan memanggil `/api/dongle/heartbeat`.
     Bila flashdisk dicabut, arahkan jendela ke layar terkunci.
   - Batasi navigasi hanya ke `SERVER_URL`, agar `js_api` tidak terbuka untuk situs lain.
2. Dependensi klien terpisah (`desktop/requirements.txt`): `pywebview`, `sounddevice`, `numpy`, `soundfile`.
   **Tanpa PyTorch** (model suara ada di server), jadi `.exe` tetap kecil.
3. Template web memanggil `window.pywebview.api.*` untuk tombol "Rekam suara" dan pendaftaran dongle.
   Bila `window.pywebview` tidak ada (dibuka di browser), tampilkan "Gunakan aplikasi desktop KomSaR".
4. Build: `pyinstaller --onedir -w desktop/main.py`, `SERVER_URL` dibaca dari file konfigurasi di samping `.exe`.
   Arahkan `stdout`/`stderr` ke file log (masalah build `-w` yang diketahui).

### Fase 8: Deploy ke InstaCloud

1. `Dockerfile` di **root repo** (aplikasi ada di subfolder `komsar/`):
   - Base `python:3.12-slim`.
   - Install PyTorch **CPU-only** (`--index-url https://download.pytorch.org/whl/cpu`) agar image tidak membengkak.
   - `COPY komsar/ /app`, install `requirements.txt`.
   - Unduh model SpeechBrain saat build ke `/app/models/`.
   - `EXPOSE 8080`, `CMD gunicorn -w 1 --threads 4 -b 0.0.0.0:8080 "app:create_app()"`.
   - **1 worker wajib**: cache hasil dekripsi dan state dekripsi dua langkah ada di memori proses.
2. `.dockerignore`: `.venv`, `tests`, `*.zip`, `instance/`, `storage/`, `.env`.
3. Tambah `gunicorn`, `speechbrain`, `torch`, `torchaudio` ke `requirements.txt` server
   (pertimbangkan `requirements-server.txt` agar test lokal tetap ringan).
4. Secrets: `insta secrets set KOMSAR_SECRET_KEY=...`, `KOMSAR_DB_MASTER_KEY=...`, `DATABASE_URL=...` (Neon).
   **Simpan cadangan `KOMSAR_DB_MASTER_KEY` di tempat aman.** Bila hilang, pesan penting tidak bisa dibuka.
5. Hubungkan repo GitHub di console InstaCloud. Setiap push ke `main` langsung deploy dan **tidak ada rollback**,
   jadi jalankan `pytest` sebelum push.
6. `ProxyFix` di Flask agar `request.scheme` = `https` di belakang proxy InstaCloud.
7. Setelah deploy: cek URL memakai HTTPS dan sertifikat valid, cek waktu bangun dari *scale to zero*
   (termasuk memuat model suara), cek pemakaian RAM.

### Fase 9: Pengujian Menyeluruh dan Dokumentasi

Otomatis (pytest):
- Repository dan block store SQL (method sama seperti versi memori).
- Restart: data bertahan setelah app dibuat ulang.
- Dongle: token salah, serial salah, dongle nonaktif, heartbeat kedaluwarsa.
- Voice (fake verifier): skor di bawah threshold ditolak, kalimat kedaluwarsa, lockout,
  suara akun lain ditolak.
- Login pertama: wajib daftar suara + ganti password sebelum halaman lain terbuka, `enroll_deadline` lewat ditolak,
  pengguna tidak bisa daftar ulang suara sendiri, reset suara oleh admin, non-admin tidak bisa mendaftarkan dongle.
- Audit log tercatat dan tidak berisi data rahasia.
- Status `failed`, tampilan percakapan, User ID acak.

Manual (checklist di `docs/uji-manual.md`):
- Dua laptop, dua dongle terdaftar, saling tukar dongle tetap bisa login.
- Flashdisk tidak terdaftar ditolak. File dongle disalin ke flashdisk lain ditolak.
- Cabut dongle saat sesi, sesi terkunci.
- Akun baru: login pertama, daftar suara, ganti password, logout, lalu login dengan suara sendiri berhasil.
- Suara anggota lain ditolak untuk akun yang bukan miliknya. Kalibrasi threshold dicatat hasilnya.
- Kirim teks biasa, teks penting, file, gambar, aset penting ke banyak penerima. Buka di laptop lain.
- Ubah ciphertext aset langsung di DB, sistem menolak dengan `ciphertext_modified`.
- Server tidur lalu bangun, semua data masih ada.

Dokumentasi:
- Perbarui README (arsitektur baru, cara deploy, cara build desktop, bootstrap admin).
- Perbarui `docs/keamanan.md` (User ID acak, voice replay, dongle bisa disalin bersama serial palsu,
  file disimpan di DB, master key di secret server).

---

## 5. Urutan dan Ketergantungan

```
Fase 1 (DB) ──► Fase 2 (User ID) ──► Fase 3 (fitur tambahan)
     │
     └──► Fase 4 (dongle) ──► Fase 5 (suara) ──► Fase 6 (alur login) ──► Fase 7 (desktop)
                                                                              │
Fase 8 (deploy) bisa dimulai setelah Fase 1, lalu diulang tiap fase ◄─────────┘
Fase 9 (uji + dokumentasi) terakhir
```

Fase 1 wajib duluan: InstaCloud *scale to zero* akan menghapus semua data yang masih di memori.

---

## 6. Risiko dan Hal yang Perlu Dicek

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Kuota storage Neon free terbatas, file disimpan di DB | DB penuh saat demo | Batas file 10 MB, cek kuota Neon, hapus data uji sebelum demo |
| Image Docker besar karena PyTorch | Build lambat, bangun dari tidur lambat | Torch CPU-only, model di-*bake* saat build |
| RAM InstaCloud free (batas atas 4 GB, default belum diketahui) | Server crash saat memuat model | Ukur pemakaian RAM setelah deploy pertama |
| Kredit InstaCloud $10/bulan habis | Server di-pause sampai bulan berikutnya | Pantau pemakaian, matikan saat tidak dipakai |
| Threshold suara tidak pas | Pengguna asli ditolak atau orang lain lolos | Kalibrasi dengan mikrofon yang dipakai saat demo |
| Login pertama tanpa suara | Pemegang password sementara bisa mendaftarkan suaranya sendiri | Password sementara diserahkan langsung, batas waktu pendaftaran pendek, dicatat di audit log |
| Izin mikrofon dan akses flashdisk di Windows | Rekam/baca dongle gagal | Rekam di Python (`sounddevice`), bukan di webview. Uji di laptop tiap anggota |
| `KOMSAR_DB_MASTER_KEY` hilang | Pesan penting tidak bisa dibuka | Cadangkan di tempat aman di luar repo |
| Tidak ada rollback di InstaCloud | Deploy rusak langsung aktif | `pytest` sebelum push, tag commit versi stabil |
