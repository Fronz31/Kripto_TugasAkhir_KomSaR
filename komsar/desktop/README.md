# KomSaR Desktop

Klien Windows untuk server KomSaR. Membaca dongle flashdisk, merekam suara, lalu membuka
halaman server di jendela pywebview. Semua verifikasi tetap dilakukan di server.

## Instalasi

```powershell
uv venv --python 3.12 komsar\desktop\.venv
uv pip install --python komsar\desktop\.venv -r komsar\desktop\requirements.txt
```

## Konfigurasi

Salin `config.example.json` menjadi `config.json` di folder yang sama dengan `main.py`
(atau di samping `KomSaR.exe` hasil build), lalu isi alamat server:

```json
{"server_url": "https://komsar.contoh.app"}
```

Bila `config.json` tidak ada, aplikasi memakai variabel lingkungan `KOMSAR_SERVER_URL`.

## Menjalankan

```powershell
komsar\desktop\.venv\Scripts\python.exe komsar\desktop\main.py
```

Alur: aplikasi menampilkan "Colokkan dongle KomSaR" dan memeriksa flashdisk tiap 2 detik.
Bila `KOMSAR.DONGLE` ditemukan, klien mengirim `POST {server_url}/api/dongle/check`.
Bila diterima, jendela membuka `server_url`. Bila ditolak muncul "Dongle tidak terdaftar";
bila jaringan/server bermasalah muncul "Server tidak dapat dihubungi".

## Build

```powershell
uv pip install --python komsar\desktop\.venv pyinstaller
powershell -ExecutionPolicy Bypass -File komsar\desktop\build.ps1
```

Hasil: `komsar\desktop\dist\KomSaR\KomSaR.exe`. Log aplikasi build ada di
`%APPDATA%\KomSaR\desktop.log`.

## Test

```powershell
komsar\desktop\.venv\Scripts\python.exe -m pytest komsar\desktop\tests
```

Test tidak butuh mikrofon maupun flashdisk.

## Kontrak dengan server

### HTTP yang dipanggil klien

`POST {server_url}/api/dongle/check`, `Content-Type: application/json`:

```json
{"dongle_id": "<uuid>", "token": "<base64 32 byte>", "volume_serial": "1A2B3C4D"}
```

Server harus membalas JSON `{"ok": true}` bila dongle terdaftar dan aktif. Balasan lain
(`{"ok": false}`, status 4xx, atau bukan JSON) dianggap ditolak. Status 5xx atau gagal koneksi
dianggap server tidak dapat dihubungi. Heartbeat dongle selama sesi dikerjakan oleh JS halaman
server, bukan oleh klien Python.

### File dongle

`KOMSAR.DONGLE` di root flashdisk removable, JSON UTF-8:

```json
{"v": 1, "dongle_id": "<uuid>", "token": "<base64 dari 32 byte>"}
```

`volume_serial` adalah serial volume Windows, 8 digit hex huruf besar tanpa tanda hubung
(sama dengan perintah `vol E:` tanpa `-`).

### `window.pywebview.api.*`

Semua fungsi mengembalikan Promise. Bila terjadi error, hasilnya `{"error": "<pesan>"}`
(tidak pernah melempar exception). Fungsi hanya bekerja bila halaman yang memanggil berasal dari
origin `server_url` (skema + host + port sama). Tunggu event `pywebviewready` sebelum memanggil.
Bila `window.pywebview` tidak ada, halaman dibuka di browser biasa.

| Fungsi | Hasil sukses |
|---|---|
| `read_dongle()` | `{"dongle_id", "token", "volume_serial"}` atau `null` bila tidak ada dongle valid |
| `list_removable_drives()` | `[{"drive": "E:\\", "volume_serial": "1A2B3C4D"}]` (`volume_serial` bisa `null`) |
| `write_dongle(drive, dongle_id, token)` | `true`. `drive` harus salah satu nilai `drive` dari `list_removable_drives()`, `dongle_id` UUID, `token` base64 dari 32 byte |
| `record_voice(seconds)` | String base64 file WAV (16000 Hz, mono, PCM 16-bit). `seconds` dibatasi 2 sampai 10 |

Contoh:

```js
window.addEventListener('pywebviewready', async () => {
  const d = await window.pywebview.api.read_dongle();
  if (!d || d.error) { /* tampilkan pesan */ }
  const wav = await window.pywebview.api.record_voice(4);
  if (wav.error) { /* tampilkan wav.error */ }
});
```
