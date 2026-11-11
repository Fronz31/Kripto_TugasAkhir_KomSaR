# Keterbatasan keamanan KomSaR (jujur, bukan klaim siap produksi)

KomSaR adalah prototipe tugas akhir. Daftar ini mencatat batas yang diketahui pada versi akhir
(server Flask di InstaCloud + PostgreSQL Neon + klien desktop pywebview, login tiga faktor).

## A. Login dan faktor autentikasi

1. **Verifikasi suara tidak mendeteksi rekaman ulang (*replay*).** Server memberi kalimat acak 4 kata yang
   berlaku 2 menit dan sekali pakai, tetapi isi ucapan tidak dicek dengan speech-to-text. Rekaman suara asli
   pemilik akun (kalimat apa pun) yang diputar ulang bisa lolos. Model SpeechBrain ECAPA juga bukan sistem
   anti-spoofing (suara sintetis/kloning tidak dideteksi).
2. **Akurasi suara bergantung pada kalibrasi.** Skor cosine dibandingkan dengan `VOICE_THRESHOLD` (default 0.25).
   Nilai ini belum dikalibrasi dengan suara dan mikrofon tim; skor tiap percobaan dicatat di audit log untuk
   kalibrasi (lihat `uji-manual.md`). Threshold terlalu rendah meloloskan orang lain, terlalu tinggi menolak pemilik.
3. **Pendaftaran suara pertama hanya dilindungi password sementara + dongle.** Siapa pun yang mendapat password
   sementara sebelum pemilik akun bisa mendaftarkan suaranya sendiri lebih dulu, dan setelah itu pemilik asli
   ditolak. Admin melihat password sementara, jadi admin secara teknis juga bisa mendahului pemilik. Mitigasi:
   password sementara (`secrets`, 12 karakter) ditampilkan sekali dan diserahkan langsung, batas waktu
   `ENROLL_WINDOW_HOURS` pendek, pendaftaran dicatat di audit log, hanya admin yang bisa me-reset suara.
4. **Dongle bisa dipalsukan oleh pihak yang menyalin file dongle dan mengetahui serial volumenya.** Server
   menyimpan SHA-256(token) + serial volume, sehingga file `KOMSAR.DONGLE` yang disalin ke flashdisk lain ditolak
   oleh klien resmi. Namun serial volume dilaporkan oleh klien, bukan dibuktikan secara kriptografis: penyerang
   yang memegang salinan file dan tahu serialnya (perintah `vol`) dapat mengirim bukti yang sama dari klien
   buatan sendiri. Bukti dongle juga statis (tanpa *challenge-response*), jadi bisa diputar ulang untuk heartbeat.
5. **Dongle tidak terikat ke pengguna.** Sesuai keputusan desain, semua dongle terdaftar berlaku untuk semua
   akun di perangkat mana pun. Dongle yang hilang harus segera dinonaktifkan admin.
6. **Bukti dongle saat login diambil dari langkah 1.** Setelah langkah suara selesai, sesi dianggap baru melihat
   dongle; heartbeat halaman (tiap 30 detik, batas `DONGLE_HEARTBEAT_TIMEOUT`) yang memastikan dongle masih
   tercolok. Mencabut dongle baru terdeteksi setelah batas waktu itu.
7. **Lockout per akun bisa dipakai untuk mengganggu (DoS).** Siapa pun yang tahu username dapat mengunci akun
   15 menit dengan 5 password salah. Tidak ada pembatasan percobaan login per IP (rate limit hanya ada di
   `/api/dongle/check`). Hitungan suara per sesi disimpan di cookie sesi; batas gabungan 5 kegagalan di database
   mencegah reset hitungan dengan mengulang langkah 1.
8. **Enumerasi username.** Pesan galat login selalu sama, dan untuk username tak dikenal, akun nonaktif, atau
   akun terkunci server tetap menjalankan verifikasi Argon2 terhadap hash dummy agar waktu respons serupa.
   Perbedaan waktu kecil (query database, verifikasi dongle) tetap mungkin terukur.
9. **Mode development melewati faktor login.** `VOICE_BACKEND=fake` + `FLASK_DEBUG=1` melewati langkah suara,
   `KOMSAR_REQUIRE_DONGLE=0` melewati dongle, `KOMSAR_SEED_DEMO=1` membuat akun contoh berpassword `komsar123`.
   Konfigurasi produksi (image Docker, `KOMSAR_ENV=production`) tidak memakai satu pun; jangan set di server.
10. **Klien desktop tidak memakai *certificate pinning*.** Keamanan koneksi bergantung pada HTTPS InstaCloud dan
    sertifikat yang dipercaya Windows. Halaman login di browser biasa ditolak hanya oleh JS (tidak ada
    `window.pywebview`); yang benar-benar mencegah login tanpa aplikasi adalah kewajiban bukti dongle.

## B. Kriptografi dan data

11. **User ID acak, tetapi tetap bukan rahasia kuat.** ID 12 karakter dari 31 simbol (`XXXX-XXXX-XXXX`, ±59 bit),
    ditambah Argon2id per percobaan, sehingga brute force atas satu gambar stego tidak praktis. Namun ID
    disimpan apa adanya di database dan diketahui admin, sehingga pihak yang membaca database atau mendapat ID
    yang bocor dan memegang gambar stego bisa mengekstrak kunci rahasia. Regenerate ID membuat pesan lama
    tidak bisa dibuka lagi. Gambar stego tidak membawa penanda tetap (hanya salt acak di LSB awal, cover foto
    alami, nama file seperti foto kamera), tetapi steganalisis statistik LSB tetap bisa mencurigai adanya
    sisipan data; yang menjaga kerahasiaan adalah enkripsi, bukan ketersembunyian.
12. **Master key database ada di secret server.** `KOMSAR_DB_MASTER_KEY` (lapisan pesan penting dan profil suara)
    disimpan sebagai secret InstaCloud. Siapa pun yang menguasai server/secret dapat membuka lapisan itu. Bila
    kunci hilang, data terenkripsi dengan kunci itu tidak bisa dipulihkan.
13. **Semua data di database.** Ciphertext file, gambar steganografi, blok, dan embedding suara (terenkripsi)
    disimpan di PostgreSQL Neon. Pemilik akses database bisa menghapus atau mengubah baris: perubahan ciphertext
    aset terdeteksi lewat blockchain dan AEAD, perubahan file biasa ditolak AEAD saat dibuka, penghapusan baru
    terdeteksi saat data dibuka.
14. **Blockchain bersifat tamper-evident, bukan tamper-proof.** Perubahan isi blok, penyisipan, dan penghapusan di
    tengah rantai terdeteksi. Pihak yang bisa menulis ke database dan menghitung ulang seluruh hash setelah blok
    yang diubah dapat membuat rantai tampak konsisten (lihat
    `test_known_limitation_full_rewrite_not_detected_but_aead_still_protects`); ciphertext yang diubah tetap
    ditolak AEAD. Penghapusan blok paling akhir hanya terdeteksi untuk aset yang bloknya hilang. Tanpa
    Proof-of-Work dan tanpa jaringan terdistribusi.
15. **Metadata tidak terenkripsi.** Nama file asli, ukuran, tipe MIME, pengirim, penerima, dan waktu disimpan
    sebagai teks biasa; isi file dan pesan terenkripsi penuh.

## C. Deploy

16. **Gunicorn wajib 1 worker.** Cache hasil dekripsi, data langkah 1 Decryption Center, kalimat tantangan suara,
    dan rate limit dongle disimpan di memori proses. Lebih dari satu worker/instance membuat alur itu gagal acak;
    restart atau *scale to zero* menghapusnya (pengguna perlu mengulang langkah yang sedang berjalan).
17. **ProxyFix mengasumsikan tepat 1 hop proxy** (`KOMSAR_TRUST_PROXY=1`). Bila InstaCloud memakai jumlah hop
    berbeda, IP di audit log dan rate limit bisa salah atau dipalsukan lewat header `X-Forwarded-For`.
18. **Cookie sesi ditandatangani, tidak dienkripsi.** Isi sesi (ID internal pengguna, `dongle_id`, hitungan
    gagal suara) bisa dibaca pemegang cookie, tetapi tidak bisa diubah tanpa `KOMSAR_SECRET_KEY`.
19. **Belum diuji di lingkungan nyata**: akurasi SpeechBrain dengan suara tim, Neon dan InstaCloud produksi,
    serta GUI pywebview, mikrofon, dan flashdisk di laptop tim (lihat `uji-manual.md`).
