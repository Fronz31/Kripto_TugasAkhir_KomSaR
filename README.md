# KomSaR — Komunikasi Satuan Rakyat

Aplikasi web (Flask) untuk komunikasi aman antarsatuan. Pesan, file, gambar, dan aset penting
dienkripsi berlapis, kunci pembukanya disembunyikan di dalam gambar (steganografi LSB), dan setiap aset
penting dicatat di blockchain sederhana agar perubahan datanya dapat terdeteksi.

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
7. [Akun Contoh](#akun-contoh)
8. [Halaman Aplikasi](#halaman-aplikasi)
9. [Konfigurasi](#konfigurasi)
10. [Pemakaian Service dari Kode](#pemakaian-service-dari-kode)
11. [Pengujian](#pengujian)
12. [Status Pengembangan](#status-pengembangan)
13. [Keterbatasan Keamanan](#keterbatasan-keamanan)

---

## Fitur

| Fitur | Penjelasan |
|---|---|
| **Login** | Username + password, password disimpan sebagai hash **Argon2id**. Sesi dilindungi token CSRF. |
| **Manajemen pengguna** | Admin dapat menambah, mengubah, menonaktifkan, dan menghapus pengguna. Semua pengguna dapat melihat dan mencari daftar pengguna. |
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
AES-256-GCM untuk aset penting). Ekstensi dan ukuran divalidasi (default maks. 25 MB), nama file
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
komsar/
├── run.py                  # titik masuk: buat .env otomatis, akun contoh, jalankan server
├── requirements.txt
├── .env.example            # contoh konfigurasi
├── assets/covers/          # gambar cover PNG untuk steganografi
├── scripts/generate_covers.py   # membuat cover contoh (opsional)
├── storage/                # file terenkripsi dan gambar stego (tidak masuk git)
├── instance/               # database SQLite (tidak masuk git)
├── docs/keamanan.md        # catatan keterbatasan keamanan
├── tests/                  # pengujian pytest
└── app/
    ├── __init__.py         # create_app(): konfigurasi, database, service, route
    ├── config.py           # konfigurasi dari environment/.env
    ├── errors.py           # exception khusus
    ├── seed.py             # akun contoh
    ├── repository.py       # penyimpanan record pesan/file (sementara di memori)
    ├── auth/               # password (Argon2id), session, placeholder biometrik dan dongle
    ├── crypto/             # aes_gcm, vigenere, text, file_cipher, kdf, key_wrap, db_layer
    ├── stego/              # embed, extract, cover, utilitas LSB
    ├── blockchain/         # block, chain, store
    ├── models/             # User (SQLAlchemy) dan record pesan/file (dataclass)
    ├── services/           # messaging, decryption, asset, user, result_cache, validators
    ├── routes/             # auth, dashboard, users, chat, transfer, decrypt, admin
    ├── templates/          # halaman HTML (Jinja2)
    └── static/             # CSS dan JS
```

Arsitektur berlapis: **route** (HTTP) → **service** (logika bisnis) → **crypto / stego / blockchain**
(modul murni tanpa ketergantungan ke Flask). Semua service dirakit di `services/container.py`
dan diakses lewat `app.extensions["komsar"]`.

---

## Instalasi dan Menjalankan

Prasyarat: Python 3.10+ (kode memakai sintaks tipe `list[str]` dan `X | None`).

```bash
pip install -r requirements.txt
python run.py
```

Buka **http://127.0.0.1:5000**.

Saat pertama kali dijalankan, `run.py` otomatis:
1. membuat file `.env` berisi `KOMSAR_SECRET_KEY` dan `KOMSAR_DB_MASTER_KEY` acak,
2. membuat akun contoh bila belum ada pengguna.

> Simpan `.env` baik-baik dan jangan dibagikan. **Jika `KOMSAR_DB_MASTER_KEY` hilang atau diganti,
> pesan penting yang sudah tersimpan tidak dapat dibuka lagi.**

Alternatif manual:
```bash
cp .env.example .env     # lalu isi KOMSAR_SECRET_KEY dan KOMSAR_DB_MASTER_KEY
python scripts/generate_covers.py   # opsional: buat cover contoh baru
```
Gambar cover bisa diganti dengan gambar milik tim (format `*.png`) di `assets/covers/`.
Gunakan gambar yang cukup besar agar kapasitas penyisipan memadai.

---

## Akun Contoh

Password semua akun: `komsar123`

| Username | User ID | Peran |
|---|---|---|
| `admin01` | ADM1 | Admin |
| `andi01` | A001 | Pengguna (Unit A) |
| `budi01` | B001 | Pengguna (Unit B) |
| `citra01` | C001 | Pengguna (Unit C) |
| `deni01` | D001 | Pengguna (Unit D) |

> Hapus atau ganti akun ini sebelum dipakai sungguhan. User ID tidak ditampilkan kepada pengguna biasa;
> admin melihatnya di menu **Pengguna** dan menyampaikannya kepada pemiliknya.

### Mencoba alur lengkap
1. Login sebagai `andi01` → **Chat** → kirim pesan ke `budi01` dengan kunci rahasia, misalnya `K123`.
2. Logout, login sebagai `budi01` → **Decryption Center**.
3. Pilih pesan, masukkan User ID `B001` → kunci tampil → ketik ulang kunci → pesan terbuka.

---

## Halaman Aplikasi

| Rute | Fungsi | Akses |
|---|---|---|
| `/login`, `/logout` | Masuk dan keluar | Semua |
| `/dashboard` | Ringkasan pesan masuk/terkirim/aset (admin: jumlah pengguna dan status rantai) | Login |
| `/users` | Daftar dan pencarian pengguna | Login |
| `/users/add`, `/users/<id>/edit`, `/users/<id>/delete` | Tambah, ubah, hapus pengguna | Admin |
| `/chat` | Kirim pesan teks, lihat kotak masuk dan terkirim | Login |
| `/transfer` | Kirim file, gambar, atau aset penting | Login |
| `/assets` | Daftar aset penting beserta status integritas | Login |
| `/decrypt` | Decryption Center (dekripsi dua langkah) | Login |
| `/profile` | Ganti password | Login |
| `/admin/chain` | Blockchain Records (blok dan validitas rantai) | Admin |

Perlindungan web: token CSRF pada setiap form, cookie sesi `HttpOnly` + `SameSite=Lax`, header
`Content-Security-Policy`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, dan `Cache-Control: no-store`.

---

## Konfigurasi

Dibaca dari environment / file `.env` (lihat `.env.example`):

| Variabel | Default | Keterangan |
|---|---|---|
| `KOMSAR_SECRET_KEY` | (wajib) | Kunci penandatangan sesi Flask |
| `KOMSAR_DB_MASTER_KEY` | (wajib) | 32 byte (base64), untuk lapisan enkripsi pesan penting |
| `DATABASE_URL` | SQLite di `instance/komsar.db` | URI database pengguna |
| `STORAGE_DIR` | `storage` | Lokasi file terenkripsi dan gambar stego |
| `MAX_FILE_MB` | `25` | Batas ukuran file |
| `ARGON2_TIME_COST` | `3` | Parameter Argon2id |
| `ARGON2_MEMORY_KIB` | `65536` | Parameter Argon2id |
| `ARGON2_PARALLELISM` | `2` | Parameter Argon2id |

Jenis file yang diizinkan: dokumen (`pdf, doc, docx, xls, xlsx, ppt, pptx, txt, csv, rtf, odt, ods, odp, zip`)
dan gambar (`png, jpg, jpeg, gif, bmp, webp`).

---

## Pemakaian Service dari Kode

```python
svc = app.extensions["komsar"]

# Kirim pesan penting ke dua penerima
msg = svc.messaging.send_text(sender, ["budi01", "citra01"], "Halo", "K123", important=True)

# Kotak masuk (data chatbox, tanpa plaintext)
inbox = svc.messaging.inbox(budi)

# Dekripsi: ID penerima (+ kunci rahasia)
res = svc.decryption.open(budi, inbox[0]["delivery_id"], "B001")
print(res.text)
```

Aset penting dan blockchain:

```python
# Mengirim aset otomatis membuat satu blok
svc.messaging.send_file(andi, ["budi01"], "kontrak.pdf", data, "K123", kind="asset")

svc.assets.list_assets(budi)                  # daftar aset milik user (tanpa blok mentah)
svc.assets.verify_integrity(budi, asset_id)   # verified / ciphertext_modified / chain_broken / ...
svc.chain.validate()                          # validasi seluruh rantai
svc.chain.export_json("chain.json")           # ekspor blok mentah untuk inspeksi
```

---

## Pengujian

```bash
python -m pytest -q
```

Berkas pengujian di `tests/`: `test_text_crypto`, `test_file_cipher`, `test_stego`, `test_multi_recipient`,
`test_communication`, `test_blockchain`, `test_users_auth`, `test_web`. Pengujian memakai `TestConfig`
(kunci acak saat runtime, database SQLite di memori, parameter Argon2 diringankan agar cepat).

---

## Status Pengembangan

- [x] **Tahap 2: modul inti**: crypto, steganografi, autentikasi, manajemen pengguna
- [x] **Tahap 3: komunikasi**: pesan biasa/penting, file, gambar, multi-penerima, Decryption Center
- [x] **Tahap 4: blockchain**: hash chaining SHA-256, satu blok per aset, validasi rantai, verifikasi sebelum aset dibuka
- [x] **Tahap 5: antarmuka Flask**: login, dashboard, pengguna, pesan, kirim file, aset penting, dekripsi, profil, Blockchain Records
- [ ] Login **biometrik (pengenalan wajah)**: baru placeholder di `app/auth/biometric.py`
- [ ] Aktivasi **dongle**: baru placeholder di `app/auth/dongle.py`
- [ ] Penyimpanan record pesan dan rantai blockchain di **database** (saat ini di memori)

Login saat ini memakai **username + password saja**. Modul biometrik dan dongle sengaja tidak mensimulasikan
autentikasi apa pun sampai benar-benar diimplementasikan.

---

## Keterbatasan Keamanan

Rinciannya ada di [`docs/keamanan.md`](docs/keamanan.md). Ringkasnya:

1. **User ID bukan rahasia yang kuat.** ID (mis. `A001`, `B001`) mudah ditebak. Siapa pun yang memegang
   gambar stego dan dapat menebak ID penerima dapat mengekstrak kunci rahasia. Argon2id memperlambat
   penebakan tetapi tidak menghilangkannya.
2. **Blockchain bersifat *tamper-evident*, bukan *tamper-proof*.** Perubahan, penyisipan, dan penghapusan
   di tengah rantai terdeteksi. Namun pihak yang bisa menulis ke penyimpanan **dan** menghitung ulang seluruh
   hash setelah blok yang diubah dapat membuat rantai tampak konsisten. Tidak ada Proof-of-Work dan
   tidak ada jaringan terdistribusi. Meski begitu, ciphertext aset tetap terlindungi oleh AEAD.
3. **Record pesan dan rantai blockchain disimpan di memori.** Data hilang saat server restart
   (file terenkripsi di `storage/` tetap ada, tetapi catatannya hilang sehingga tidak bisa dibuka lewat aplikasi).
4. **Nama file asli** disimpan sebagai metadata biasa (tidak terenkripsi). Isi file terenkripsi penuh.
5. **Master key database** berada di environment server. Siapa pun yang menguasai server dan `.env`
   dapat membuka lapisan enkripsi pesan penting.
6. Server dijalankan dengan server pengembangan Flask pada `127.0.0.1`. Untuk penggunaan nyata
   diperlukan server WSGI, HTTPS, dan pembatasan percobaan login.
