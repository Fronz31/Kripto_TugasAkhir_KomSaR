# KomSaR — Komunikasi Satuan Rakyat

Aplikasi komunikasi aman antarsatuan. Pesan, file, gambar, dan aset penting dienkripsi berlapis, kunci
pembukanya disembunyikan di dalam gambar (steganografi LSB), dan setiap aset penting dicatat di blockchain
sederhana agar perubahan datanya dapat terdeteksi. Login memakai tiga faktor: password, dongle flashdisk
terdaftar, dan verifikasi suara.

Arsitektur: **server Flask** (Docker, di-deploy ke **InstaCloud**) + **PostgreSQL Neon** sebagai penyimpanan
semua data + **aplikasi desktop** Windows (pywebview) yang membaca dongle, merekam suara, dan membuka halaman
server lewat HTTPS. Kode aplikasi ada di folder [`komsar/`](komsar/).

| Dokumen | Isi |
|---|---|
| [`komsar/README.md`](komsar/README.md) | menjalankan lokal, konfigurasi, alur login, halaman, dongle, suara |
| [`komsar/docs/deploy.md`](komsar/docs/deploy.md) | deploy InstaCloud + Neon, secret, bootstrap admin |
| [`komsar/desktop/README.md`](komsar/desktop/README.md) | instalasi, build, dan kontrak aplikasi desktop |
| [`komsar/docs/uji-manual.md`](komsar/docs/uji-manual.md) | checklist uji manual dengan perangkat nyata |
| [`komsar/docs/keamanan.md`](komsar/docs/keamanan.md) | keterbatasan keamanan |
| [`komsar/docs/PLAN.md`](komsar/docs/PLAN.md) | rencana dan status implementasi |

Proyek ini dibuat sebagai tugas akhir mata kuliah Kriptografi. Ini adalah prototipe pembelajaran,
**bukan sistem siap produksi** (lihat bagian [Keterbatasan](#keterbatasan-keamanan)).

---

## Daftar Isi
1. [Fitur](#fitur)
2. [Cara Kerja Singkat](#cara-kerja-singkat)
3. [Algoritma yang Dipakai](#algoritma-yang-dipakai)
4. [Alur Detail](#alur-detail)
5. [Struktur Proyek](#struktur-proyek)
6. [Instalasi dan Menjalankan](#instalasi-dan-menjalankan)
7. [Pengujian](#pengujian)
8. [Status Pengembangan](#status-pengembangan)
9. [Keterbatasan Keamanan](#keterbatasan-keamanan)

---

## Fitur

| Fitur | Penjelasan |
|---|---|
| **Login tiga faktor** | (1) username + password (hash **Argon2id**) + bukti **dongle flashdisk** terdaftar, lalu (2) **verifikasi suara** (SpeechBrain ECAPA, di server). Lockout 15 menit setelah gagal berulang. Sesi dilindungi token CSRF dan heartbeat dongle. |
| **Login pertama** | Admin membuat akun dengan password sementara; pemilik akun mengganti password lalu mendaftarkan suaranya sendiri. |
| **Manajemen pengguna** | Admin dapat menambah, mengubah, menonaktifkan, menghapus pengguna, membuat ulang User ID acak, dan me-reset suara. Semua pengguna dapat melihat dan mencari daftar pengguna. |
| **Audit log** | Login, pengiriman, dekripsi, kegagalan integritas, dan aksi admin dicatat tanpa data rahasia (khusus admin). |
| **Pesan teks** | *Super encryption*: Vigenère lalu AES-256-GCM. Tersedia jenis **Pesan Biasa** dan **Pesan Penting** (dengan lapisan enkripsi tambahan untuk penyimpanan). |
| **Kirim file dan gambar** | File/gambar dienkripsi per-potongan (chunk) dengan ChaCha20-Poly1305. |
| **Aset penting** | Dienkripsi dengan AES-256-GCM dan dicatat sebagai satu blok di blockchain. Integritasnya diverifikasi sebelum dibuka. |
| **Multi-penerima** | Satu pengiriman bisa ke banyak penerima. Isi dienkripsi sekali, kunci dibungkus terpisah untuk tiap penerima. |
| **Steganografi** | Kunci rahasia disisipkan ke gambar cover PNG (metode LSB, posisi bit diacak) dan hanya bisa diekstrak dengan User ID penerima. |
| **Decryption Center** | Satu halaman untuk membuka semua jenis data lewat alur dua langkah. |
| **Blockchain Records** | Halaman khusus admin untuk melihat blok dan status validitas rantai. |

---

## Cara Kerja Singkat

```
PENGIRIM                                         PENERIMA
  │  isi (teks/file) + "kunci rahasia"             │
  ▼                                                │
1. Buat CEK acak (32 byte)                         │
2. Enkripsi isi dengan CEK (sekali saja)           │
3. Untuk tiap penerima:                            │
     a. Bungkus CEK  ← Argon2id(kunci rahasia,     │
                        User ID penerima, salt)    │
     b. Sisipkan kunci rahasia ke gambar cover     │
        (LSB), dikunci dengan User ID penerima     │
  │                                                │
  └──────── cipherteks + gambar stego ────────────►│
                                                   ▼
                              4. Input User ID → ekstrak kunci dari gambar
                              5. Kunci tampil → penerima mengetik ulang kunci
                              6. ID + kunci → buka CEK → dekripsi isi
```

Ide utamanya: **dua hal harus dimiliki penerima** untuk membuka data, yaitu *User ID* dan *kunci rahasia*
yang tersembunyi di gambar. Pengirim cukup memasukkan username penerima, sistem sendiri yang mencari
User ID-nya dari database.

---

## Algoritma yang Dipakai

| Kebutuhan | Algoritma | Lokasi kode |
|---|---|---|
| Hash password | **Argon2id** | `app/auth/password.py` |
| Turunan kunci dari password/ID | **Argon2id** (`hash_secret_raw`) + **HKDF-SHA256** | `app/crypto/kdf.py` |
| Enkripsi teks (super encryption) | **Vigenère** (level byte, mod 256) → **AES-256-GCM** | `app/crypto/vigenere.py`, `aes_gcm.py`, `text.py` |
| Enkripsi file/gambar biasa | **ChaCha20-Poly1305**, per-chunk 64 KB | `app/crypto/file_cipher.py` |
| Enkripsi aset penting | **AES-256-GCM**, per-chunk 64 KB | `app/crypto/file_cipher.py` |
| Pembungkus kunci per penerima | AES-256-GCM dengan kunci hasil Argon2id + HKDF | `app/crypto/key_wrap.py` |
| Lapisan enkripsi pesan penting | AES-256-GCM dengan kunci turunan *master key* | `app/crypto/db_layer.py` |
| Steganografi | **LSB** pada kanal RGB PNG, posisi acak dari keystream **ChaCha20** | `app/stego/` |
| Integritas aset | **SHA-256** (hash ciphertext + hash chaining blok) | `app/blockchain/` |

Catatan desain:
- **CEK** (*Content Encryption Key*) acak 32 byte dibuat untuk setiap pengiriman, lalu dipecah dengan
  HKDF menjadi subkey independen: `vigenere_key`, `aes_key`, `file_key` (label `info` berbeda agar tidak tertukar).
- Mode AEAD (GCM / Poly1305) menjamin kerahasiaan **dan** keaslian: ciphertext yang diubah akan
  gagal didekripsi, bukan menghasilkan teks rusak.
- Dekripsi file ditulis ke berkas sementara `.part` dan baru dipindahkan bila **semua** chunk valid,
  sehingga tidak pernah ada plaintext parsial.

---

## Alur Detail

### 1. Mengirim pesan teks
1. Pengirim mengisi penerima (username, boleh banyak), pesan, dan **kunci rahasia** (minimal 4 karakter).
2. Sistem membuat CEK, lalu mengenkripsi teks: Vigenère → AES-256-GCM.
3. Jika **Pesan Penting**, hasilnya dibungkus lagi dengan AES-256-GCM memakai kunci turunan *master key*.
4. Untuk setiap penerima: CEK dibungkus (`wrap_cek`) dan kunci rahasia disisipkan ke gambar cover acak.

### 2. Mengirim file / gambar / aset penting
Sama seperti teks, tetapi isi dienkripsi dengan `file_cipher` (ChaCha20-Poly1305 untuk file dan gambar,
AES-256-GCM untuk aset penting). Ekstensi dan ukuran divalidasi (default maks. 10 MB, `MAX_FILE_MB`), nama file
dibersihkan dari path traversal. Khusus **aset penting**, sistem otomatis membuat satu blok blockchain.

### 3. Steganografi (`app/stego/`)
Tata letak data di gambar:
- Header polos di awal: `MAGIC "KSST"` (4 byte) + versi (1) + salt (16).
- Sisanya: panjang (2 byte) + kunci rahasia terenkripsi AES-GCM, **tersebar di posisi acak**.
- Posisi acak diturunkan dari **User ID + salt** lewat keystream ChaCha20.
- Bila User ID salah, posisi yang dibaca salah, tag AES-GCM gagal, dan sistem menolak dengan `InvalidIDError`.
- Gambar disimpan sebagai **PNG** (lossless). Format yang dikompresi (JPEG) akan merusak bit LSB.
- Pemakaian kapasitas dibatasi ¼ dari slot tersisa agar pencarian posisi tetap efisien.

### 4. Dekripsi dua langkah (Decryption Center)
1. **Langkah 1**: gambar stego tampil, penerima memasukkan **User ID**. Sistem mengekstrak kunci rahasia
   dan menampilkannya.
2. **Langkah 2**: penerima **mengetik ulang** kunci itu. Sistem menggabungkan ID + kunci, membuka CEK,
   lalu mendekripsi isi.
- Data langkah 1 disimpan di memori server (bukan di halaman atau cookie), kedaluwarsa 10 menit,
  dan sesi dibatalkan setelah **5 kesalahan** memasukkan kunci.
- Hasil dekripsi disimpan sementara **di memori** (bukan database, log, atau cookie) dan dibersihkan saat logout.
- Pesan galat sengaja disamakan ("tidak ditemukan atau tidak berhak") agar tidak membocorkan keberadaan data.

### 5. Blockchain aset penting (`app/blockchain/`)
- Rantai sederhana dengan **hash chaining SHA-256, tanpa Proof-of-Work**.
- **Satu blok per aset penting.** Isi blok: `index`, `timestamp`, `asset_id`, `ciphertext_hash`, `metadata`,
  `sender`, `recipients`, `previous_hash`, `hash`. Blok **tidak** menyimpan plaintext, kunci, ataupun file.
- Blok pertama (*genesis*) berisi `previous_hash` 64 nol.
- `validate()` memeriksa: urutan nomor blok, kecocokan `hash` dengan isi, kecocokan `previous_hash`
  dengan blok sebelumnya, dan urutan timestamp.
- Sebelum aset dibuka, sistem memeriksa: file ciphertext ada → blok ada → rantai valid →
  hash ciphertext cocok → metadata cocok. Hasilnya salah satu status:

| Status | Arti |
|---|---|
| `verified` | Semua pemeriksaan lolos |
| `ciphertext_modified` | Hash ciphertext tidak cocok dengan catatan blok |
| `ciphertext_missing` | File ciphertext hilang |
| `block_missing` | Blok untuk aset ini tidak ditemukan |
| `chain_broken` | Rantai blockchain tidak valid |
| `metadata_mismatch` | Metadata tidak sesuai catatan blok |

Jika status bukan `verified`, aset **tidak didekripsi** (`IntegrityViolationError`).

---

## Struktur Proyek

```
Dockerfile                  # image server untuk InstaCloud (torch CPU, model suara di-bake, gunicorn 1 worker)
komsar/
├── run.py                  # development: buat .env otomatis, akun contoh opsional, server Flask lokal
├── wsgi.py                 # produksi (gunicorn): create_app() tanpa .env otomatis/akun contoh
├── requirements.txt        # server tanpa torch (cukup untuk test)
├── requirements-server.txt # + speechbrain/torch untuk verifikasi suara
├── .env.example            # contoh konfigurasi
├── assets/covers/          # gambar cover PNG untuk steganografi
├── scripts/generate_covers.py
├── instance/               # SQLite lokal untuk development (tidak masuk git)
├── docs/                   # deploy, uji manual, keamanan, rencana
├── tests/                  # pengujian pytest server
├── desktop/                # aplikasi desktop Windows (pywebview): dongle, rekam suara, build PyInstaller
└── app/
    ├── __init__.py         # create_app(): konfigurasi, database, service, route
    ├── config.py           # konfigurasi dari environment/.env
    ├── cli.py              # flask komsar bootstrap-admin
    ├── seed.py             # akun contoh (development)
    ├── repository.py       # SqlRepository: record pesan/penerima/file di database
    ├── auth/               # password (Argon2id), sesi & lockout, dongle, verifikasi suara
    ├── crypto/             # aes_gcm, vigenere, text, file_cipher, kdf, key_wrap, db_layer
    ├── stego/              # embed, extract, cover, utilitas LSB
    ├── blockchain/         # block, chain, store (tabel `blocks`)
    ├── models/             # SQLAlchemy: user, records (pesan/file), security (dongle, suara, audit)
    ├── services/           # messaging, decryption, asset, user, voice, audit, result_cache, validators
    ├── routes/             # auth, api (dongle/suara), dashboard, users, chat, transfer, decrypt, admin
    ├── templates/          # halaman HTML (Jinja2)
    └── static/             # CSS dan JS (login, heartbeat dongle, rekam suara lewat pywebview)
```

Arsitektur berlapis: **route** (HTTP) → **service** (logika bisnis) → **crypto / stego / blockchain**
(modul murni tanpa ketergantungan ke Flask). Semua service dirakit di `services/container.py`
dan diakses lewat `app.extensions["komsar"]`. Semua data disimpan di database (PostgreSQL Neon di produksi,
SQLite untuk development/test): pengguna, pesan, ciphertext file dan gambar stego (kolom biner), blok,
dongle, profil suara terenkripsi, dan audit log.

---

## Instalasi dan Menjalankan

Prasyarat: Python 3.12 dan [`uv`](https://docs.astral.sh/uv/).

- **Development lokal di browser** (tanpa dongle/suara, akun contoh `komsar123`): lihat
  [`komsar/README.md`](komsar/README.md#menjalankan-lokal-mode-development-di-browser). Variabel
  `KOMSAR_REQUIRE_DONGLE=0`, `VOICE_BACKEND=fake`, `FLASK_DEBUG=1`, `KOMSAR_SEED_DEMO=1`,
  `KOMSAR_COOKIE_SECURE=0` **hanya** untuk development, jangan dipakai di server.
- **Produksi** (InstaCloud + Neon, admin pertama lewat `bootstrap-admin`): lihat
  [`komsar/docs/deploy.md`](komsar/docs/deploy.md). Tidak ada akun contoh di produksi.
- **Aplikasi desktop** (instalasi, `config.json`, build `.exe`): lihat
  [`komsar/desktop/README.md`](komsar/desktop/README.md).

> Simpan `KOMSAR_DB_MASTER_KEY` baik-baik dan jangan dibagikan. **Jika kunci ini hilang atau diganti,
> pesan penting dan profil suara yang sudah tersimpan tidak dapat dibuka lagi.**

User ID dibuat **acak** oleh sistem (format `XXXX-XXXX-XXXX`, mis. `K7QX-92MF-TR4D`). User ID tidak ditampilkan
kepada pengguna biasa; admin melihatnya di menu **Pengguna** dan menyampaikannya kepada pemiliknya. Admin dapat
membuat ulang ID; pesan yang dikirim untuk ID lama tidak dapat dibuka lagi.

---

## Pengujian

```bash
cd komsar
uv venv --python 3.12 .venv && uv pip install --python .venv -r requirements.txt
.venv/Scripts/python -m pytest -q                       # server

uv venv --python 3.12 desktop/.venv && uv pip install --python desktop/.venv -r desktop/requirements.txt pytest
desktop/.venv/Scripts/python -m pytest -q desktop/tests # aplikasi desktop
```

Test server memakai `TestConfig` (kunci acak saat runtime, SQLite di memori, `VOICE_BACKEND=fake`, Argon2
diringankan) dan mencakup kriptografi, steganografi, blockchain (termasuk tamper langsung di database),
repository SQL dan persistensi setelah restart, dongle, suara, login tiga faktor, audit log, status `failed`,
percakapan, dan User ID acak. Uji dengan perangkat nyata ada di
[`komsar/docs/uji-manual.md`](komsar/docs/uji-manual.md).

---

## Status Pengembangan

- [x] Modul inti: crypto, steganografi, manajemen pengguna
- [x] Komunikasi: pesan biasa/penting, file, gambar, multi-penerima, Decryption Center
- [x] Blockchain aset penting: hash chaining SHA-256, validasi rantai, verifikasi sebelum aset dibuka
- [x] Antarmuka Flask
- [x] Penyimpanan di database (PostgreSQL Neon / SQLite), data bertahan saat restart
- [x] User ID acak, audit log, status `failed`, tampilan percakapan dan riwayat file
- [x] Dongle flashdisk, verifikasi suara, login tiga faktor + login pertama + lockout
- [x] Aplikasi desktop (pywebview) dan deploy (Dockerfile untuk InstaCloud)
- [ ] Uji di lingkungan nyata: akurasi suara + kalibrasi threshold, Neon dan InstaCloud produksi, GUI desktop
      dengan mikrofon dan flashdisk di laptop tim (checklist `komsar/docs/uji-manual.md`)

---

## Keterbatasan Keamanan

Rinciannya ada di [`komsar/docs/keamanan.md`](komsar/docs/keamanan.md). Ringkasnya:

1. **Suara bisa diputar ulang (*replay*)** dan akurasinya bergantung pada `VOICE_THRESHOLD` yang harus dikalibrasi.
2. **Login pertama** hanya dilindungi password sementara + dongle; pemegang password sementara bisa mendaftarkan
   suaranya lebih dulu.
3. **Dongle bisa dipalsukan** oleh pihak yang menyalin file dongle dan mengetahui serial volumenya (serial
   dilaporkan klien, bukti statis). Dongle tidak terikat ke pengguna tertentu.
4. **User ID acak, tetapi tetap bukan kata sandi.** ID diketahui admin dan disimpan apa adanya di database.
5. **Blockchain bersifat *tamper-evident*, bukan *tamper-proof*.** Penulisan ulang seluruh rantai setelah blok
   yang diubah tidak terdeteksi oleh rantai, tetapi ciphertext yang diubah tetap ditolak AEAD.
6. **Master key database** berada di secret server; siapa pun yang menguasai server bisa membuka lapisan itu.
7. **Nama file asli dan metadata** tidak terenkripsi; isi file terenkripsi penuh.
8. **Server wajib 1 worker gunicorn** karena sebagian state (cache dekripsi, tantangan suara, rate limit) ada
   di memori proses; ProxyFix mengasumsikan 1 hop proxy.
