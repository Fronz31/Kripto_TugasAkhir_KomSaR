# Riset: Desktop App, Voice Recognition, Framework, dan SQLite

Tanggal: 2026-11-10
Status: riset, belum diimplementasikan

Ringkasan rekomendasi:

| Topik | Rekomendasi | Alasan singkat |
|---|---|---|
| Biometrik | **Voice recognition (speaker verification)** dengan SpeechBrain ECAPA-TDNN | Bisa offline, akurat, lisensi Apache-2.0 |
| Desktop app | **Tetap Flask + pywebview**, dipaket dengan PyInstaller | Semua kode, template, dan test yang ada tetap dipakai |
| Flask vs FastAPI | **Tetap Flask** | Untuk aplikasi desktop satu pengguna, FastAPI tidak memberi keuntungan nyata dan butuh tulis ulang |
| Database | **SQLite lewat SQLAlchemy** (sudah dipakai untuk tabel `users`) | Tinggal mengganti `InMemoryRepository` dan `InMemoryBlockStore` |
| Dongle | **Flashdisk berisi file kunci** yang diverifikasi saat aplikasi dibuka | Sederhana, tanpa hardware khusus |

---

## 1. Voice Recognition sebagai Login Biometrik

### Bisa atau tidak?
**Bisa.** Yang dibutuhkan adalah *speaker verification*, yaitu memastikan **siapa** yang berbicara.
Ini berbeda dengan *speech-to-text*, yang mengubah ucapan menjadi tulisan.

Cara kerjanya:
1. Model mengubah rekaman suara (beberapa detik) menjadi vektor angka (*embedding*).
2. Saat pendaftaran (*enrollment*), embedding pengguna disimpan.
3. Saat login, embedding rekaman baru dibandingkan dengan yang tersimpan memakai *cosine similarity*.
4. Jika skor di atas ambang batas (*threshold*), suara diterima.

### Pilihan library

| Library | Model | Kelebihan | Kekurangan |
|---|---|---|---|
| **SpeechBrain** (`speechbrain/spkrec-ecapa-voxceleb`) | ECAPA-TDNN | Akurat, aktif dipelihara, Apache-2.0, ada `verify_files()` siap pakai | Butuh PyTorch (ukuran besar, ratusan MB) |
| **Resemblyzer** | GE2E, embedding 256 dimensi | API sangat sederhana (`VoiceEncoder().embed_utterance(wav)`) | Rilis terakhir 0.1.4 (Okt 2023), README menyebut paling baik untuk bahasa Inggris |

**Rekomendasi: SpeechBrain ECAPA-TDNN.**
- Input: audio 16 kHz mono. Loader SpeechBrain melakukan resample otomatis.
- Model diunduh sekali dari Hugging Face ke folder `savedir`. Setelah itu folder tersebut ikut dibundel
  ke aplikasi agar bisa jalan offline. (Perlu diuji: memuat model dari path lokal tanpa internet.)

Contoh penggunaan dari model card:

```python
from speechbrain.inference.speaker import SpeakerRecognition

verifier = SpeakerRecognition.from_hparams(
    source="speechbrain/spkrec-ecapa-voxceleb",
    savedir="models/spkrec-ecapa-voxceleb",
)
score, prediction = verifier.verify_files("enroll.wav", "login.wav")
```

### Merekam suara
- **Rekam di sisi Python** dengan `sounddevice` (`samplerate=16000`, `channels=1`) lalu simpan dengan `soundfile`.
  Tombol "Rekam" di halaman memanggil fungsi Python lewat `js_api` pywebview atau endpoint Flask.
- Merekam lewat browser (`MediaRecorder`) di dalam webview juga mungkin, tetapi izin mikrofon di
  WebView2 (Windows) perlu diuji dulu. Rekam di Python lebih bisa diprediksi.

### Alur yang diusulkan
**Pendaftaran suara** (oleh pengguna setelah login password, atau oleh admin):
1. Pengguna merekam 3 sampel, masing-masing ±5 detik.
2. Hitung embedding tiap sampel, lalu rata-ratakan.
3. Simpan embedding ke tabel `voice_profiles`, **dienkripsi AES-256-GCM** memakai lapisan `db_layer`
   yang sudah ada. Embedding suara adalah data biometrik, jadi tidak boleh disimpan polos.

**Login**:
1. Username + password (Argon2id, sudah ada).
2. Aplikasi menampilkan **kalimat acak** untuk diucapkan, lalu merekam ±4 detik.
3. Bandingkan embedding dengan profil. Skor ≥ threshold berarti lolos.
4. Batasi percobaan, misalnya 3 kali gagal lalu akun dikunci sementara.

### Hal yang perlu diperhatikan
- **Threshold harus dikalibrasi** dengan rekaman anggota tim sendiri (mikrofon dan ruangan yang sama).
  Uji: berapa skor suara sendiri dan berapa skor suara orang lain.
- **Serangan rekaman ulang (*replay*)**: speaker verification saja tidak bisa membedakan suara asli dan rekaman.
  Kalimat acak membantu sebagai kontrol, tetapi baru benar-benar efektif jika isi ucapan dicek dengan
  speech-to-text. Cukup dicatat sebagai keterbatasan di laporan.
- Embedding tidak bisa di-*hash* seperti password, karena dua rekaman suara yang sama tidak pernah identik.
  Karena itu dipakai enkripsi, bukan hash.
- Ukuran aplikasi akan naik signifikan karena PyTorch.

---

## 2. Dongle (aktivasi aplikasi)

Slide meminta aplikasi "hanya dapat dihidupkan menggunakan bantuan dongle". Usulan paling sederhana:

1. Flashdisk berisi file `komsar.dongle`. Isinya ID dongle dan tanda tangan HMAC-SHA256
   (atau tanda tangan Ed25519) atas ID tersebut plus serial volume flashdisk.
2. Saat aplikasi start, cek semua drive *removable*, cari file itu, lalu verifikasi tanda tangannya.
3. Jika tidak ada atau tidak valid, aplikasi menolak membuka jendela utama.
4. Pengecekan diulang berkala. Jika dongle dicabut, sesi dikunci.

Mengikat ke serial volume membuat file yang disalin ke flashdisk lain tidak berlaku.
Keterbatasannya: serial volume bisa dipalsukan oleh orang yang paham. Untuk tugas akhir ini cukup.

---

## 3. Apakah Flask bisa jadi Desktop App?

**Bisa.** Polanya: Flask berjalan di `127.0.0.1` pada thread terpisah, lalu sebuah jendela native
menampilkan halaman tersebut. Pengguna melihat aplikasi desktop biasa, bukan browser.

### Pilihan pembungkus

| Opsi | Cara kerja | Perubahan kode | Catatan |
|---|---|---|---|
| **pywebview** | Jendela native memakai WebView2 (Windows) | Kecil: tambah `desktop.py` | Paling cocok. Ada `js_api` untuk memanggil Python dari JS (rekam suara, cek dongle) |
| flaskwebgui | Membuka Chrome/Edge dalam mode app | Kecil | Bergantung pada browser terpasang, kurang terasa native |
| NiceGUI (`ui.run(native=True)`) | Framework UI sendiri, jendela via pywebview | **Tulis ulang semua halaman** | Tidak sepadan, UI sudah jadi |
| Flet | UI Flutter | **Tulis ulang semua halaman** | Bisa ke HP nanti, tapi biayanya besar sekarang |
| Electron / Tauri | Shell JS + backend Python | Besar | Dua bahasa, packaging rumit |

**Rekomendasi: pywebview.** Kerangka kasarnya:

```python
# desktop.py
import threading
import webview
from app import create_app

app = create_app()

def run_server():
    app.run(host="127.0.0.1", port=5000, use_reloader=False)

threading.Thread(target=run_server, daemon=True).start()
webview.create_window("KomSaR", "http://127.0.0.1:5000", width=1200, height=800)
webview.start()
```

### Packaging ke `.exe` (PyInstaller)
- Folder `templates/`, `static/`, `assets/covers/`, dan model suara harus ikut dibundel dengan `--add-data`.
  Path-nya dibaca lewat `sys._MEIPASS` saat aplikasi berjalan dari `.exe`.
- Database, `storage/`, dan `.env` **jangan** diletakkan di folder bundel, karena folder itu sementara.
  Simpan di folder data pengguna, misalnya `%APPDATA%\KomSaR\`.
- Disarankan memakai mode `--onedir` dulu, bukan `--onefile`. Mode `--onefile` dengan PyTorch lambat
  saat start karena harus mengekstrak ratusan MB setiap kali dibuka.
- Masalah yang pernah dilaporkan: build tanpa console (`-w`) dengan Flask bisa gagal karena `stdout` kosong.
  Solusinya, arahkan `sys.stdout`/`sys.stderr` ke file log.

---

## 4. Flask atau FastAPI?

| Aspek | Flask | FastAPI |
|---|---|---|
| Model | WSGI, sinkron | ASGI, async |
| Keunggulan utama | Render HTML (Jinja2), form, session, ekosistem ekstensi | API JSON bertipe, validasi otomatis, dokumentasi OpenAPI |
| Performa | Cukup untuk satu pengguna lokal | Lebih cepat untuk API dengan banyak request bersamaan |
| Di proyek ini | **Sudah jadi**: 7 blueprint, 14 template, CSRF, session, 105 test | Harus menulis ulang route, CSRF, session, dan test web |

**Kesimpulan: tetap Flask.** Keunggulan FastAPI ada pada throughput API dengan banyak pengguna bersamaan.
Aplikasi desktop dipakai satu orang di satu komputer, sehingga keunggulan itu tidak terasa.
Modul `crypto/`, `stego/`, dan `blockchain/` tidak bergantung pada Flask, jadi tetap bisa dipakai jika
suatu saat pindah framework.

FastAPI baru layak dipertimbangkan jika arsitekturnya menjadi **server pusat + banyak klien**
(lihat bagian 6) dan klien berbicara lewat API JSON.

---

## 5. Database SQLite

SQLite sudah dipakai lewat Flask-SQLAlchemy untuk tabel `users`. Yang perlu ditambahkan adalah
versi database untuk `InMemoryRepository` dan `InMemoryBlockStore` dengan method yang sama,
sehingga service dan test tidak perlu banyak diubah.

### Usulan tabel dan relasi

```
users ──1:N──► messages (pengirim)
messages ──1:N──► deliveries ◄──N:1── users (penerima)
messages ──1:1──► files            (jika jenisnya file/gambar/aset)
files ──1:1──► blocks              (hanya untuk aset penting)
users ──1:1──► voice_profiles
users ──1:N──► audit_logs
```

| Tabel | Kolom penting | Keterangan |
|---|---|---|
| `users` | id, username, user_id_code, password_hash, role, is_active | Sudah ada |
| `messages` | id, sender_id, kind (`text`/`file`/`image`/`asset`), important, ciphertext, nonce, created_at | Satu baris per pengiriman. Isi dienkripsi sekali |
| `deliveries` | id, message_id, recipient_id, wrapped_cek, wrap_salt, stego_path, status, created_at | Satu baris per penerima. Status: `sent`/`delivered`/`decrypted`/`failed` |
| `files` | id, message_id, original_name, size, enc_path, mime | Ciphertext tetap di `storage/` sebagai `.enc`, DB hanya menyimpan path |
| `blocks` | index (PK), timestamp, asset_id, ciphertext_hash, metadata_json, sender, recipients_json, previous_hash, hash | Satu blok per aset penting |
| `voice_profiles` | user_id, embedding_enc, nonce, enrolled_at | Embedding dienkripsi |
| `audit_logs` | id, user_id, action, target, created_at | Login, kirim, dekripsi, gagal dekripsi |

Catatan:
- Kolom ciphertext pesan penting tetap dibungkus lapisan `db_layer` (AES-GCM dengan master key).
  Ini memenuhi kriteria "pesan penting dienkripsi pada basis data".
- Aktifkan `PRAGMA foreign_keys=ON` (default SQLite: mati) dan `journal_mode=WAL`.
- Tabel `blocks` bersifat *append-only* di level aplikasi. Validasi rantai tetap memakai `validate()` yang sudah ada.
- Perlu test baru: data tetap ada setelah aplikasi dibuat ulang (simulasi restart).

---

## 6. Keputusan yang Harus Diambil Tim Sebelum Implementasi

**Bagaimana pesan berpindah antar komputer?**
Dalam versi web, semua pengguna mengakses satu server, jadi pesan cukup disimpan di satu database.
Dalam versi desktop, tiap komputer punya SQLite sendiri. Pesan dari komputer A tidak otomatis sampai ke komputer B.

| Opsi | Cara | Kelebihan | Kekurangan |
|---|---|---|---|
| A. Satu komputer, banyak akun | Semua pengguna login bergantian di satu aplikasi | Paling mudah, cukup untuk demo presentasi | Bukan komunikasi antar perangkat sungguhan |
| B. Server pusat + klien desktop | Satu komputer menjalankan server (Flask + SQLite), yang lain membuka lewat aplikasi desktop | Komunikasi nyata di jaringan LAN | Butuh jaringan; DB hanya di server |
| C. Ekspor/impor paket | Pengirim mengekspor paket (`.enc` + gambar stego), dikirim lewat flashdisk/email, lalu diimpor penerima | Cocok dengan tema stego | Alur manual |

Saran: **opsi A untuk demo**, dengan struktur kode yang tidak menghalangi opsi B nanti.
Keputusan ini memengaruhi desain database, jadi perlu disepakati dulu.

Pertanyaan lain:
1. Voice login menggantikan password, atau sebagai faktor kedua? (Saran: faktor kedua.)
2. Pendaftaran suara dilakukan pengguna sendiri, atau harus disetujui admin?
3. Satu dongle untuk semua pengguna, atau satu dongle per pengguna?

---

## 7. Urutan Pengerjaan yang Disarankan

1. **SQLite**: repository dan block store versi database, plus test restart.
2. **Desktop**: `desktop.py` dengan pywebview, pindahkan data ke `%APPDATA%`, uji build PyInstaller.
3. **Dongle**: cek file kunci di flashdisk saat start.
4. **Voice**: rekam via `sounddevice`, enrollment, verifikasi, kalibrasi threshold.
5. Uji manual menyeluruh, lalu perbarui README dan `docs/keamanan.md`.

---

## Sumber

- SpeechBrain ECAPA-TDNN: <https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb>
- Resemblyzer: <https://pypi.org/project/Resemblyzer-python3.9/0.1.4/>
- pywebview freezing guide (v6.1): <https://sources.debian.org/src/python-pywebview/6.1%2Bdfsg-1/docs/guide/freezing.md>
- pywebview + Flask tanpa console (issue #343): <https://github.com/r0x0r/pywebview//issues/343>
- pywebview `http_server` lambat (issue #1025): <https://github.com/r0x0r/pywebview/issues/1025>
- Contoh Flask + pywebview: <https://dev.to/artydev/desktop-apps-with-flask-an-pywebview-34gl>
- NiceGUI native mode: <https://nicegui.io/documentation/section_configuration_deployment>
- Flet: <https://www.linux-magazine.com/Issues/2026/311/Flet>
- Flask vs FastAPI: <https://www.contentful.com/blog/fastapi-vs-flask>
- Rekam audio 16 kHz dengan sounddevice: <https://huggingface.co/spaces/anaszil/whisper-darija/blob/main/record.py>
