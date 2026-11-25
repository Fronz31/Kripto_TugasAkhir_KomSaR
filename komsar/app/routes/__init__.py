import os

from flask import render_template, request
from werkzeug.exceptions import HTTPException

from ._helpers import csrf_token, fmt_dt, protect_csrf, require_dongle, status_label

ERROR_TEXT = {401: "Silakan login terlebih dahulu.", 403: "Anda tidak berhak mengakses halaman ini.",
              404: "Halaman atau data tidak ditemukan.",
              413: "Ukuran unggahan melebihi batas yang diizinkan."}


def register_routes(app):
    from . import admin, api, auth, chat, dashboard, decrypt, transfer, users
    for module in (auth, dashboard, users, chat, transfer, decrypt, admin, api):
        app.register_blueprint(module.bp)

    app.jinja_env.globals["csrf_token"] = csrf_token      # global agar tersedia di dalam macro
    app.jinja_env.filters["dt"] = fmt_dt
    app.jinja_env.filters["status"] = status_label
    app.before_request(protect_csrf)
    app.before_request(require_dongle)

    @app.get("/healthz")
    def healthz():
        """Cek hidup untuk platform: tanpa DB, tanpa login/dongle, tanpa memuat model suara."""
        return "ok", 200, {"Content-Type": "text/plain"}

    @app.context_processor
    def inject():
        from ..auth.service import current_user
        return {"me": current_user()}

    @app.url_defaults
    def static_version(endpoint, values):
        # ?v=<mtime> agar file static boleh di-cache lama; berubah -> URL baru. Font dikecualikan karena juga
        # dirujuk dari style.css tanpa ?v (URL harus sama agar preload terpakai).
        name = values.get("filename", "")
        if endpoint == "static" and "v" not in values and not name.startswith("fonts/"):
            try:
                values["v"] = int(os.path.getmtime(os.path.join(app.static_folder, name)))
            except OSError:
                pass

    @app.after_request
    def security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        if request.endpoint == "static" and ("v" in request.args or request.path.startswith("/static/fonts/")):
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif request.endpoint == "static":
            resp.headers["Cache-Control"] = "no-cache"        # boleh disimpan, wajib revalidasi (304 via ETag)
        else:
            resp.headers["Cache-Control"] = "no-store"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'")
        return resp

    @app.errorhandler(HTTPException)
    def http_error(e):
        msg = e.description if e.code == 400 else ERROR_TEXT.get(e.code, "Terjadi kesalahan.")
        return render_template("error.html", code=e.code, message=msg), e.code
