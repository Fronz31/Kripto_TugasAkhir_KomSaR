"""Klien desktop KomSaR: gerbang dongle lalu membuka server di pywebview."""

import base64
import functools
import json
import os
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

import webview

import audio
import dongle

FROZEN = getattr(sys, "frozen", False)
BASE_DIR = os.path.dirname(sys.executable if FROZEN else os.path.abspath(__file__))
POLL_SECONDS = 2

GATE_HTML = """<!doctype html>
<html lang="id"><head><meta charset="utf-8"><title>KomSaR</title>
<style>
body{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
font-family:Segoe UI,sans-serif;background:#0f172a;color:#e2e8f0;text-align:center}
h1{font-size:1.6rem;margin:0 0 .5rem}p{color:#94a3b8;margin:0}
</style></head>
<body><div><h1 id="msg">Colokkan dongle KomSaR</h1>
<p>Aplikasi memeriksa flashdisk setiap 2 detik.</p></div>
<script>function setMsg(t){document.getElementById('msg').textContent=t}</script>
</body></html>"""


def load_server_url():
    try:
        with open(os.path.join(BASE_DIR, "config.json"), encoding="utf-8") as f:
            url = json.load(f).get("server_url")
    except (OSError, ValueError):
        url = None
    url = url or os.environ.get("KOMSAR_SERVER_URL")
    if not url:
        raise SystemExit("server_url tidak ditemukan di config.json atau KOMSAR_SERVER_URL")
    return url.rstrip("/")


def origin(url):
    parts = urlsplit(url or "")
    return (parts.scheme.lower(), parts.netloc.lower())


def check_dongle(server_url, found):
    """True bila server menerima dongle. Raise OSError bila server tidak terjangkau."""
    req = urllib.request.Request(
        server_url + "/api/dongle/check",
        data=json.dumps(found).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read()
    except urllib.error.HTTPError as e:
        if e.code >= 500:
            raise
        body = e.read()  # 4xx dengan {"ok": false} berarti dongle ditolak
    try:
        data = json.loads(body)
    except ValueError:
        return False
    return isinstance(data, dict) and data.get("ok") is True


def _safe(fn):
    @functools.wraps(fn)
    def wrapper(self, *args):
        try:
            if origin(self._window.get_current_url()) != self._origin:
                raise PermissionError("Halaman bukan dari server KomSaR")
            return fn(self, *args)
        except Exception as e:  # noqa: BLE001 - semua error dikirim ke JS, bukan crash
            return {"error": str(e)}

    return wrapper


class Bridge:
    """Dipanggil dari JS halaman server lewat window.pywebview.api.*"""

    def __init__(self, server_url):
        self._origin = origin(server_url)
        self._window = None

    @_safe
    def read_dongle(self):
        return dongle.read_dongle()

    @_safe
    def list_removable_drives(self):
        return [{"drive": d, "volume_serial": dongle.volume_serial(d)} for d in dongle.list_removable_drives()]

    @_safe
    def write_dongle(self, drive, dongle_id, token):
        return dongle.write_dongle(drive, dongle_id, token)

    @_safe
    def record_voice(self, seconds):
        return base64.b64encode(audio.record_wav(seconds)).decode()


def gate(window, server_url):
    """Tahan di halaman lokal sampai dongle terdaftar terdeteksi, lalu buka server."""
    shown = None
    while True:
        found = dongle.read_dongle()
        if found is None:
            msg = "Colokkan dongle KomSaR"
        else:
            try:
                if check_dongle(server_url, found):
                    break
                msg = "Dongle tidak terdaftar"
            except OSError:
                msg = "Server tidak dapat dihubungi"
        if msg != shown:
            window.evaluate_js(f"setMsg({json.dumps(msg)})")
            shown = msg
        time.sleep(POLL_SECONDS)

    def stay_on_server():
        if origin(window.get_current_url()) != origin(server_url):
            window.load_url(server_url)

    window.events.loaded += stay_on_server
    window.load_url(server_url)


def redirect_output():
    log_dir = os.path.join(os.environ.get("APPDATA", BASE_DIR), "KomSaR")
    os.makedirs(log_dir, exist_ok=True)
    log = open(os.path.join(log_dir, "desktop.log"), "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log


def main():
    if FROZEN:
        redirect_output()
    server_url = load_server_url()
    bridge = Bridge(server_url)
    window = webview.create_window("KomSaR", html=GATE_HTML, js_api=bridge, width=1100, height=750)
    bridge._window = window
    webview.start(gate, (window, server_url))


if __name__ == "__main__":
    main()
