"""Screenshot UI KomSaR untuk README: SQLite sementara, data demo lewat service, Edge headless.

Pakai (dari root repo, venv server sudah terpasang):
  komsar/.venv/Scripts/python docs/readme/src/screenshots.py komsar <folder_raw> [nama ...]
  uv run --with pillow python docs/readme/src/crop_screens.py <folder_raw> docs/readme
Semua kunci dan database dibuat acak/sementara; tidak menyentuh .env atau database asli.
"""
import base64, os, re, subprocess, sys, tempfile, threading, time
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="komsar_shots_"))
os.environ.update(KOMSAR_REQUIRE_DONGLE="0", KOMSAR_COOKIE_SECURE="0", VOICE_BACKEND="fake", FLASK_DEBUG="1",
                  KOMSAR_SEED_DEMO="1", KOMSAR_SECRET_KEY=os.urandom(16).hex(),
                  KOMSAR_DB_MASTER_KEY=base64.b64encode(os.urandom(32)).decode(),
                  DATABASE_URL=f"sqlite:///{(TMP / 'demo.db').as_posix()}",
                  ARGON2_TIME_COST="1", ARGON2_MEMORY_KIB="8192", ARGON2_PARALLELISM="1")
KOMSAR = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(KOMSAR))
os.chdir(KOMSAR)

from app import create_app                      # noqa: E402
from app.seed import DEMO_PASSWORD, seed_demo_users  # noqa: E402
from app.models.user import User                # noqa: E402
from werkzeug.serving import make_server        # noqa: E402

app = create_app()
app.debug = True
with app.app_context():
    seed_demo_users()
    s = app.extensions["komsar"]
    u = {x.username: x for x in User.query.all()}
    m = s.messaging
    m.send_text(u["citra01"], ["budi01"], "Pos C siap menerima logistik besok pagi.", "Bandeng7")
    m.send_text(u["deni01"], ["budi01", "andi01"], "Rapat koordinasi dipindah ke balai desa, pukul 09.00.", "Rapat09")
    m.send_text(u["andi01"], ["budi01"], "Jalur evakuasi utara ditutup. Gunakan jalur timur lewat jembatan Cikaso.",
                "Merapi24", important=True)
    pdf = b"%PDF-1.4\n% laporan demo\n" + b"0" * 2048
    m.send_file(u["citra01"], ["budi01"], "laporan-logistik.pdf", pdf, "Logistik3")
    m.send_file(u["andi01"], ["budi01"], "data-pengungsi.csv", b"nama,pos\nwarga,A\n" * 40, "Aset2026", kind="asset")
    m.send_text(u["budi01"], ["andi01"], "Diterima. Tim Unit B berangkat lewat jalur timur.", "Merapi24")
    budi_id = u["budi01"].user_id
    budi_pk = u["budi01"].id


def login(username):
    c = app.test_client()
    html = c.get("/login").get_data(as_text=True)
    tok = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    r = c.post("/login", data=dict(csrf_token=tok, username=username, password=DEMO_PASSWORD))
    assert r.status_code == 302 and "/login" not in r.location, r.location
    return c


def cookie(c):
    return "session=" + c.get_cookie("session").value


budi, admin = login("budi01"), login("admin01")

# Dekripsi pesan penting (langkah 1 + 2) lewat route asli, simpan HTML-nya sebagai snapshot.
html = budi.get("/decrypt").get_data(as_text=True)
csrf = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
with app.app_context():
    inbox = s.messaging.inbox(User.query.filter_by(username="budi01").one())
delivery = next(d for d in inbox if d.get("kind") == "important_text")["delivery_id"]
html = budi.post("/decrypt", data=dict(csrf_token=csrf, action="extract", delivery_id=delivery,
                                       user_id=budi_id)).get_data(as_text=True)
token = re.search(r'name="token" value="([^"]+)"', html).group(1)
decrypt_html = budi.post("/decrypt", data=dict(csrf_token=csrf, action="open", token=token,
                                               secret_key="Merapi24")).get_data(as_text=True)
assert "Jalur evakuasi" in decrypt_html, "dekripsi gagal"

# Sesi pending (langkah 2 login) untuk halaman suara.
voice = app.test_client()
voice.get("/login")
with voice.session_transaction() as sess:
    sess.update(pending_user_id=budi_pk, pending_since=int(time.time()), dongle_id=None, dongle_seen=int(time.time()))

STUB = (b'<script>window.pywebview={api:{read_dongle:function(){return new Promise(function(){})},'
        b'start_recording:function(){return Promise.resolve(true)},stop_recording:function(){return new Promise(function(){})},'
        b'record_voice:function(){return new Promise(function(){})}}};</script>')
SNAPS = {"/__snap/decrypt": decrypt_html.encode()}


def wrap(cookie_value, stub=False):
    def mw(environ, start_response):
        if cookie_value and "HTTP_COOKIE" not in environ:
            environ["HTTP_COOKIE"] = cookie_value
        path = environ.get("PATH_INFO", "")
        if path in SNAPS:
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
            return [SNAPS[path]]
        if not stub:
            return app(environ, start_response)
        body = b"".join(app(environ, lambda st, h, e=None: captured.update(st=st, h=h)))
        h = [x for x in captured["h"] if x[0].lower() != "content-length"]
        if any(k.lower() == "content-type" and "text/html" in v for k, v in h):
            body = body.replace(b"<head>", b"<head>" + STUB, 1)
        start_response(captured["st"], h + [("Content-Length", str(len(body)))])
        return [body]
    captured = {}
    return mw


servers = {5071: wrap(None), 5062: wrap(cookie(voice), stub=True), 5063: wrap(cookie(budi)), 5064: wrap(cookie(admin))}
for port, wsgi in servers.items():
    srv = make_server("127.0.0.1", port, wsgi, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
SHOTS = [("login", 5071, "/login", 800), ("voice-login", 5062, "/login/voice", 800),
         ("pesan", 5063, "/chat", 2000), ("dekripsi", 5063, "/__snap/decrypt", 2000),
         ("admin-pengguna", 5064, "/users/", 800)]
only = sys.argv[3:]
for name, port, path, h in SHOTS:
    if only and name not in only:
        continue
    prof = tempfile.mkdtemp(prefix="edge_", dir=TMP)
    r = subprocess.run([EDGE, "--headless=new", "--disable-gpu", f"--user-data-dir={prof}", "--hide-scrollbars",
                    "--virtual-time-budget=4000", f"--window-size=1280,{h}",
                    f"--screenshot={OUT / (name + '.png')}", f"http://127.0.0.1:{port}{path}"],
                   timeout=90, capture_output=True, text=True)
    print(r.returncode, r.stderr[-400:])
    print(name, (OUT / (name + ".png")).exists())
print("tmp", TMP)
