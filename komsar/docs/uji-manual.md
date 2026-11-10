# Checklist Uji Manual KomSaR

Uji ini melengkapi test otomatis (`pytest`). Yang diuji di sini hanya hal yang butuh perangkat nyata:
server InstaCloud + Neon, dua laptop Windows, flashdisk, dan mikrofon.

Catat tanggal, penguji, dan hasil (lolos/gagal + catatan) di tiap bagian.

## 0. Persiapan

- [ ] Server sudah di-deploy sesuai [`deploy.md`](deploy.md); `curl https://<url>/healthz` membalas `ok`.
- [ ] Admin pertama dibuat dengan `flask --app wsgi komsar bootstrap-admin` (deploy.md bagian 7).
- [ ] Laptop A dan laptop B memasang aplikasi desktop (`desktop/README.md`), `config.json` berisi
      `{"server_url": "https://<url>"}`.
- [ ] Siapkan 4 flashdisk: **D1** dan **D2** (akan didaftarkan), **X** (tidak didaftarkan), **Y** (untuk uji salin).
- [ ] Admin mendaftarkan D1 dan D2 di menu **Dongle** (`/admin/dongles`): pilih flashdisk, isi label, klik
      **Daftarkan dongle**. Pastikan file `KOMSAR.DONGLE` muncul di root D1 dan D2.
- [ ] Admin menambah minimal tiga pengguna (mis. `andi01`, `budi01`, `citra01`) di menu **Pengguna**; catat
      password sementara yang tampil sekali.

## 1. Dongle

- [ ] Laptop A + D1: aplikasi desktop menerima dongle dan membuka halaman login.
- [ ] Laptop B + D2: sama, berhasil.
- [ ] **Tukar dongle**: laptop A + D2 dan laptop B + D1 tetap bisa login (semua dongle terdaftar berlaku untuk
      semua pengguna di perangkat mana pun).
- [ ] Flashdisk **X** (tidak terdaftar): aplikasi menampilkan "Dongle tidak terdaftar" atau tetap meminta dongle.
- [ ] Salin `KOMSAR.DONGLE` dari D1 ke **Y**, colokkan Y saja: ditolak (serial volume berbeda).
- [ ] **Cabut dongle saat sesi**: login penuh, cabut flashdisk, tunggu lebih dari `DONGLE_HEARTBEAT_TIMEOUT`
      (default 60 detik) lalu klik menu apa pun: sesi berakhir dan kembali ke halaman login.
- [ ] Admin menonaktifkan D2 di `/admin/dongles`; login dengan D2 ditolak dengan pesan galat umum.
- [ ] Browser biasa (bukan aplikasi desktop) membuka URL server: tampil "Gunakan aplikasi desktop KomSaR",
      tombol login nonaktif.

## 2. Login pertama (pendaftaran suara + ganti password)

- [ ] `andi01` login di aplikasi desktop dengan password sementara + dongle: diarahkan ke halaman
      "Ganti password sementara".
- [ ] Password baru sama dengan password sementara ditolak; konfirmasi yang berbeda ditolak.
- [ ] Setelah ganti password, rekam 3 kalimat acak: login selesai dan dashboard terbuka.
- [ ] Logout, login lagi dengan password baru + dongle + suara sendiri: berhasil.
- [ ] Akun yang dibuat lebih dari `ENROLL_WINDOW_HOURS` jam lalu tanpa login: ditolak, perlu admin menekan
      **Reset suara** (opsional, bisa diuji dengan `ENROLL_WINDOW_HOURS=0` di server uji).

## 3. Verifikasi suara

- [ ] `andi01` login dengan suara sendiri: berhasil.
- [ ] `budi01` mengucapkan kalimat untuk akun `andi01`: ditolak.
- [ ] 3 kali suara salah dalam satu sesi login: akun terkunci 15 menit (`account_locked` di audit log).
- [ ] Kalimat dibiarkan lebih dari 2 menit sebelum direkam: ditolak, perlu ulang.

### Kalibrasi threshold

Skor cosine tiap percobaan tercatat di **Audit Log** (aksi `voice_verify_success` / `voice_verify_failed`,
kolom meta `score=`). Isi tabel (minimal 5 percobaan per baris) dengan mikrofon
yang akan dipakai saat demo. Pilih `VOICE_THRESHOLD` di antara skor terendah "pemilik" dan skor tertinggi
"orang lain", lalu set dengan `insta secrets set VOICE_THRESHOLD=...`.

| Akun | Pembicara | Laptop/mikrofon | Skor 1 | Skor 2 | Skor 3 | Skor 4 | Skor 5 | Lolos? |
|---|---|---|---|---|---|---|---|---|
| andi01 | Andi (pemilik) | | | | | | | |
| andi01 | Budi | | | | | | | |
| andi01 | Citra | | | | | | | |
| budi01 | Budi (pemilik) | | | | | | | |
| budi01 | Andi | | | | | | | |

Threshold dipilih: ______  Tanggal: ______

## 4. Komunikasi multi-penerima

Kirim dari `andi01` (laptop A) ke `budi01` **dan** `citra01`, lalu buka di laptop B lewat **Dekripsi**
(User ID dari admin, lalu ketik ulang kunci yang diekstrak dari gambar stego).

- [ ] Teks biasa: kedua penerima bisa membuka; isi sama.
- [ ] Teks penting: label "penting" tampil; kedua penerima bisa membuka.
- [ ] File (mis. PDF): hasil unduhan identik dengan file asli.
- [ ] Gambar: tidak ada pratinjau sebelum didekripsi, pratinjau tampil setelahnya.
- [ ] Aset penting: muncul di **Aset Penting** dengan status integritas `verified`, bisa dibuka.
- [ ] User ID salah: tidak ada kunci yang tampil. Kunci salah 5 kali: langkah dibatalkan.
- [ ] Status di kotak terkirim berubah menjadi "Sudah dibuka" setelah penerima membuka.
- [ ] Tampilan percakapan `/chat/<username>` menampilkan pesan dua arah urut waktu, hanya ciphertext + tombol "Buka".

## 5. Tamper ciphertext aset di Neon

Di Neon Console > SQL Editor (gunakan branch uji, bukan data demo bila memungkinkan):

```sql
-- cari aset terbaru
SELECT id, original_name, block_index FROM files WHERE block_index IS NOT NULL ORDER BY block_index DESC LIMIT 1;
-- balik 1 byte di tengah ciphertext
UPDATE files SET ciphertext = overlay(ciphertext placing '\x00'::bytea from 100 for 1) WHERE id = '<id>';
```

- [ ] Halaman **Aset Penting** menampilkan status `ciphertext_modified` untuk aset itu.
- [ ] Membuka aset lewat **Dekripsi** ditolak (data berubah), tidak ada file yang terunduh.
- [ ] Audit log mencatat kegagalan integritas.
- [ ] Ubah satu baris blok: `UPDATE blocks SET asset_id = 'palsu' WHERE idx = 1;` lalu buka **Blockchain
      Records** (`/admin/chain`): rantai tidak valid. (Kembalikan dengan `UPDATE` ke nilai asal setelah uji.)

## 6. Server tidur lalu bangun

- [ ] Biarkan server idle sampai InstaCloud *scale to zero* (dan Neon ikut tidur).
- [ ] Buka aplikasi desktop lagi: server bangun (catat waktu bangun: ______ detik).
- [ ] Pengguna, pesan, file, aset, blok, dongle, dan profil suara masih ada; pesan lama masih bisa dibuka.
- [ ] Sesi lama mungkin perlu login ulang; itu wajar (cache dekripsi dan tantangan suara ada di memori).

## 7. Halaman admin

- [ ] **Pengguna** (`/users/`): tambah, ubah, regenerate User ID, Reset suara, hapus pengguna tanpa riwayat.
      Non-admin tidak melihat User ID dan tidak bisa mengubah.
- [ ] **Dongle** (`/admin/dongles`): daftar dongle, waktu terakhir dipakai, nonaktifkan.
- [ ] **Audit Log** (`/admin/audit`): filter per pengguna dan aksi berfungsi; tidak ada password, kunci,
      User ID, token dongle, atau plaintext di kolom mana pun; IP yang tercatat adalah IP klien (bukan IP proxy).
- [ ] **Blockchain Records** (`/admin/chain`): blok tampil, status rantai valid (sebelum uji tamper).
- [ ] Non-admin membuka `/admin/dongles`, `/admin/audit`, dan `/admin/chain`: ditolak (403). Di `/users/`
      non-admin tidak melihat form tambah pengguna maupun tombol ubah/hapus.
