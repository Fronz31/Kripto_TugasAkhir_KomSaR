# Keterbatasan keamanan KomSaR (jujur, bukan klaim siap produksi)

1. **User ID bukan rahasia kuat.** ID dipakai sebagai bagian dari kunci sesuai konsep tugas. Siapa pun yang
   memegang gambar steganografi *dan* dapat menebak ID penerima (mis. A001, B001) dapat mengekstrak kunci rahasia.
   Argon2id memperlambat penebakan tetapi tidak menghilangkan risiko. Cara memperkuatnya dibahas belakangan.
2. **Blockchain bersifat tamper-evident, bukan tamper-proof.** Perubahan isi blok, penyisipan, dan penghapusan
   di tengah rantai terdeteksi. Pihak yang bisa menulis ke penyimpanan dan menghitung ulang seluruh hash
   setelah blok yang diubah dapat membuat rantai tampak konsisten (lihat
   `test_known_limitation_full_rewrite_not_detected_but_aead_still_protects`). Penghapusan blok paling akhir
   hanya terdeteksi untuk aset yang bloknya hilang. Tidak memakai Proof-of-Work.
3. **Data tersimpan di database** (PostgreSQL/Neon, atau SQLite lokal), termasuk ciphertext file dan gambar
   steganografi (kolom biner). Isi tetap terenkripsi, tetapi pemilik akses database bisa menghapus atau mengubah
   baris; perubahan ciphertext aset terdeteksi lewat blockchain dan AEAD, penghapusan hanya terdeteksi saat dibuka.
4. **Nama file asli** disimpan sebagai metadata biasa (tidak terenkripsi); isi file terenkripsi penuh.
5. **Master key database** (lapisan pesan penting) berada di environment server; siapa pun yang menguasai
   server dan `.env` dapat membuka lapisan itu.
