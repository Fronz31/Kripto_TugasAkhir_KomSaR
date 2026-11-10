from flask import render_template
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

    @app.context_processor
    def inject():
        from ..auth.service import current_user
        return {"me": current_user()}

    @app.after_request
    def security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'")
        return resp

    @app.errorhandler(HTTPException)
    def http_error(e):
        msg = e.description if e.code == 400 else ERROR_TEXT.get(e.code, "Terjadi kesalahan.")
        return render_template("error.html", code=e.code, message=msg), e.code
