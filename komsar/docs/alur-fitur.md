# Alur Kerja Fitur KomSaR

Dokumen ini menjelaskan apa yang bisa dilakukan **admin** dan **pengguna biasa**, langkah demi langkah,
sesuai tampilan aplikasi desktop. Untuk checklist pengujian lengkap, lihat [`uji-manual.md`](uji-manual.md).

## Ringkasan hak akses

| Fitur | Pengguna biasa | Admin |
|---|:---:|:---:|
| Login (password, dongle, suara) | ✔ | ✔ |
| Beranda (ringkasan pesan) | ✔ | ✔ (+ jumlah pengguna dan status rantai) |
| Pesan teks (kirim, kotak masuk, terkirim, percakapan) | ✔ | ✔ |
| Kirim file, gambar, aset penting | ✔ | ✔ |
| Riwayat file | ✔ | ✔ |
| Aset penting (status integritas) | ✔ (miliknya) | ✔ (miliknya) |
| Dekripsi (Decryption Center) | ✔ | ✔ |
| Daftar pengguna | ✔ (tanpa User ID) | ✔ (dengan User ID) |
| Profil: ganti password | ✔ | ✔ |
| Tambah, ubah, nonaktifkan, hapus pengguna | – | ✔ |
| Buat ulang User ID, reset suara | – | ✔ |
| Daftarkan dan nonaktifkan dongle | – | ✔ |
| Audit log | – | ✔ |
| Catatan blockchain | – | ✔ |

User ID tidak pernah ditampilkan ke pengguna biasa. Admin menyerahkannya langsung ke pemiliknya.

---

## 1. Membuka aplikasi dan login

```
Buka KomSaR.exe
  │
  ├─ Dongle wajib? ── ya ──► flashdisk terdaftar harus tercolok, kalau tidak: "Colokkan dongle KomSaR"
  │                  tidak ─► lanjut
  ▼
Langkah 1: username + password (+ bukti dongle dibaca otomatis dari flashdisk)
  │
  ├─ Akun baru / suara di-reset ──► Login pertama (bagian 1.1)
  ├─ Akun biasa ───────────────────► Langkah 2: verifikasi suara (bagian 1.2)
  └─ Admin, saat flag uji coba KOMSAR_ADMIN_SKIP_VOICE=1 ─► langsung ke Beranda
```

- Salah password 5 kali atau gagal suara 3 kali: akun terkunci 15 menit.
- Pesan galat login sengaja umum ("Username, password, atau dongle tidak valid") agar tidak membocorkan
  bagian mana yang salah. Alasan sebenarnya tercatat di audit log.
- Langkah 2 harus selesai dalam 3 menit setelah langkah 1.
- Aplikasi mendeteksi colok/cabut flashdisk lewat event Windows (tanpa polling). Mencabut dongle langsung logout dan kembali ke
  halaman "Colokkan dongle KomSaR". Server juga mengakhiri sesi bila heartbeat (tiap 30 detik) berhenti.

### 1.1 Login pertama (akun baru)

1. Login dengan **password sementara** dari admin.
2. **Ganti password**: password baru minimal 8 karakter dan harus berbeda dari password sementara.
3. **Daftarkan suara**: rekam **3 sampel**. Setiap sampel menampilkan kalimat acak. **Tekan dan tahan** tombol
   **Tahan untuk merekam** sambil mengucapkannya, lalu lepas untuk mengirim (minimal 2 detik, maksimal 10 detik).
4. Selesai: langsung masuk ke Beranda.

Login pertama harus dilakukan dalam **24 jam** sejak akun dibuat atau suara di-reset. Lewat dari itu, akun
terkunci sampai admin me-reset suaranya.

### 1.2 Login berikutnya

1. Username + password (+ dongle).
2. Aplikasi menampilkan **kalimat acak**. **Tahan** tombol rekam sambil mengucapkannya, lalu lepas.
3. Suara dicocokkan dengan profil suara **akun itu sendiri**. Cocok: masuk ke Beranda.

Cara merekam suara:
- Selama tombol ditahan, tombol bertuliskan "Merekam… lepas untuk berhenti", ada titik merah, dan penghitung waktu.
- Keyboard: fokus ke tombol, lalu tahan **Spasi** atau **Enter**.
- Rekaman kurang dari 2 detik ditolak dan bisa diulang untuk kalimat yang sama. Lewat 10 detik, rekaman berhenti otomatis.
- `KomSaR.exe` versi lama (sebelum fitur ini) memakai tombol **Mulai rekam** yang merekam otomatis 4–5 detik.

### 1.3 Mengganti suara

Pengguna **tidak bisa** mengganti suaranya sendiri. Admin menekan **Reset suara** (bagian 4.2), lalu pengguna
mengulang alur login pertama.

---

## 2. Fitur pengguna biasa

Semua fitur di bagian ini juga bisa dipakai admin.

### 2.1 Beranda

Ringkasan jumlah pesan masuk, pesan terkirim, dan aset, beserta daftar terbaru.

### 2.2 Mengirim pesan teks (menu **Pesan**)

1. Isi **penerima**: satu atau beberapa username, dipisah koma. Pengirim tidak perlu tahu User ID penerima.
2. Tulis **pesan**.
3. Isi **kunci rahasia** (minimal 4 karakter). Kunci ini **tidak dikirim** ke penerima secara langsung.
4. Centang **Pesan penting** bila perlu (tambahan lapisan enkripsi untuk penyimpanan di database).
5. Tekan **Enkripsi & kirim**.

Yang terjadi di balik layar:
- Pesan dienkripsi sekali dengan kunci acak (CEK): **Vigenère lalu AES-256-GCM** (super enkripsi).
  Pesan penting dibungkus lagi dengan AES-256-GCM memakai master key server.
- Untuk tiap penerima, CEK dibungkus dengan kunci turunan **Argon2id**(kunci rahasia + User ID penerima).
- Kunci rahasia disisipkan ke **gambar cover PNG** (steganografi LSB) yang hanya bisa dibuka dengan User ID
  penerima. Setiap penerima mendapat gambar stego sendiri.

Bila pengiriman ke satu penerima gagal, penerima lain tetap menerima pesan, dan penerima yang gagal
berstatus **failed** di daftar Terkirim.

### 2.3 Kotak masuk, terkirim, dan percakapan

- **Kotak masuk**: pesan yang diterima. Pesan yang belum dibuka bertanda **segel amber**.
- **Terkirim**: pesan yang dikirim beserta status per penerima: `sent`, `delivered`, `decrypted`, atau `failed`.
- **Percakapan**: klik nama pengguna untuk melihat semua pesan dua arah dengan orang itu, urut waktu.
  Isi tetap terenkripsi sampai dibuka lewat Dekripsi.

### 2.4 Mengirim file, gambar, atau aset penting (menu **Kirim file**)

1. Pilih **jenis kiriman**: file, gambar, atau **aset penting**.
2. Isi penerima, pilih file (maksimal 10 MB), isi kunci rahasia.
3. Tekan **Enkripsi & kirim**.

- File dan gambar dienkripsi dengan **ChaCha20-Poly1305** per potongan 64 KB (berbeda dari algoritma teks).
- **Aset penting** dienkripsi dengan **AES-256-GCM** dan otomatis dicatat sebagai **satu blok blockchain**
  (hash SHA-256 ciphertext, metadata, pengirim, penerima, hash blok sebelumnya).
- Jenis file yang diizinkan: dokumen (`pdf, doc, docx, xls, xlsx, ppt, pptx, txt, csv, rtf, odt, ods, odp, zip`)
  dan gambar (`png, jpg, jpeg, gif, bmp, webp`).

### 2.5 Riwayat file dan aset penting

- **Riwayat file**: semua file dan gambar yang dikirim dan diterima.
- **Aset penting**: daftar aset milik pengguna beserta **status integritas**:

| Status | Arti |
|---|---|
| `verified` | Ciphertext dan rantai blockchain utuh, aset boleh dibuka |
| `ciphertext_modified` | Ciphertext diubah setelah dicatat |
| `ciphertext_missing` | Ciphertext hilang |
| `block_missing` | Blok aset tidak ditemukan |
| `chain_broken` | Rantai blockchain tidak valid |
| `metadata_mismatch` | Metadata tidak sesuai catatan |

Aset dengan status selain `verified` **tidak akan didekripsi**.

### 2.6 Membuka pesan dan file (menu **Dekripsi**)

1. Pilih data yang mau dibuka. Gambar steganografinya tampil.
2. **Langkah 1**: masukkan **User ID Anda**. Sistem mengekstrak kunci rahasia dari gambar dan menampilkannya.
3. **Langkah 2**: **ketik ulang** kunci yang tampil. Sistem membuka CEK, lalu mendekripsi isi.
4. Berhasil: isi pesan tampil atau file bisa diunduh, dan segel amber "retak".

- Salah kunci 5 kali: sesi dekripsi dibatalkan, ulangi dari langkah 1.
- Data langkah 1 hanya berlaku 10 menit.
- Hasil dekripsi hanya disimpan sementara di memori server dan dihapus saat logout.
- Pesan galat sengaja sama ("tidak ditemukan atau tidak berhak") agar tidak membocorkan keberadaan data.

### 2.7 Pengguna dan profil

- **Pengguna**: daftar dan pencarian pengguna (username, nama, unit). Klik username untuk membuka percakapan.
- **Profil**: ganti password (perlu password saat ini, password baru minimal 8 karakter).

---

## 3. Persiapan awal sistem (admin pertama)

Dilakukan sekali oleh pengelola server, dari laptop yang terhubung ke database:

```powershell
flask --app wsgi komsar bootstrap-admin            # dengan dongle: pilih flashdisk
flask --app wsgi komsar bootstrap-admin --no-dongle  # uji coba tanpa dongle
```

Perintah ini membuat akun admin dengan **password sementara** (tampil sekali) dan, bila memakai dongle,
menulis file `KOMSAR.DONGLE` ke flashdisk. Detail: [`deploy.md`](deploy.md).

---

## 4. Fitur admin

### 4.1 Menambah pengguna (menu **Pengguna**)

1. Isi **username**, **nama lengkap**, **unit/satuan**. Centang **Jadikan admin** bila perlu.
2. Simpan. Sistem membuat:
   - **User ID acak** (format `XXXX-XXXX-XXXX`),
   - **password sementara** yang **ditampilkan sekali**.
3. Serahkan username, password sementara, dan User ID langsung ke pemiliknya.
4. Pengguna wajib login pertama dalam 24 jam (bagian 1.1).

### 4.2 Mengelola pengguna (tombol **Edit**)

| Aksi | Efek |
|---|---|
| **Simpan perubahan** | Ubah nama, unit, status **Aktif**, peran **Admin**, atau set password baru |
| **Buat ulang User ID** | User ID baru. Pesan lama untuk User ID lama **tidak bisa dibuka lagi** |
| **Reset suara** | Profil suara dihapus dan password sementara baru tampil sekali. Pengguna mengulang login pertama |
| **Hapus** | Akun dihapus. Catatan audit dan dongle yang pernah ia daftarkan tetap ada |

Menonaktifkan akun (hilangkan centang **Aktif**) lebih aman daripada menghapus bila data pengguna masih dibutuhkan.

### 4.3 Dongle (menu **Dongle**)

Mendaftarkan dongle (harus dari aplikasi desktop):
1. Colokkan flashdisk.
2. Tekan **Muat ulang daftar flashdisk**, pilih flashdisk, isi **label** (mis. "Flashdisk Unit B").
3. Tekan **Daftarkan dongle**. Sistem menulis file `KOMSAR.DONGLE` ke flashdisk dan mencatat serial flashdisk.

- Semua dongle terdaftar bisa dipakai **siapa saja di perangkat mana saja**.
- File dongle yang disalin ke flashdisk lain ditolak, karena serialnya berbeda.
- Flashdisk hilang: tekan **Nonaktifkan** pada dongle itu.

### 4.4 Audit log (menu **Audit log**)

Riwayat kejadian penting, terbaru di atas, bisa difilter per username dan aksi. Contoh aksi yang dicatat:
login sukses/gagal (beserta alasannya), akun terkunci, logout, kirim pesan/file/aset, dekripsi sukses/gagal,
kegagalan integritas aset, tambah/ubah/hapus pengguna, buat ulang User ID, reset suara, pendaftaran suara,
daftar/nonaktifkan dongle. Verifikasi suara mencatat **skor kemiripan**, berguna untuk mengkalibrasi
`VOICE_THRESHOLD`.

Audit log **tidak pernah** menyimpan isi pesan, kunci rahasia, password, User ID, atau token dongle.

### 4.5 Catatan blockchain (menu **Blockchain**)

Daftar blok aset penting dan **status validitas rantai**. Blok hanya berisi hash dan metadata, tanpa isi file
atau kunci. Rantai bersifat *tamper-evident*: perubahan, sisipan, atau penghapusan blok terdeteksi.

---

## 5. Mode uji coba saat ini

Server sedang berjalan dengan dua flag sementara:

| Flag | Nilai uji coba | Efek | Nilai produksi |
|---|---|---|---|
| `KOMSAR_REQUIRE_DONGLE` | `0` | Login dan sesi tanpa dongle | `1` |
| `KOMSAR_ADMIN_SKIP_VOICE` | `1` | Admin login tanpa langkah suara | `0` |

Pengguna biasa **tetap wajib** mendaftarkan dan memverifikasi suara. Cara mengubah flag: [`deploy.md`](deploy.md),
bagian "Mode uji coba".
