from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..errors import KomSaRError
from ._helpers import login_required, parse_usernames, svc

bp = Blueprint("transfer", __name__)
KINDS = {"file": "File / Dokumen", "image": "Gambar", "asset": "Aset Penting"}


@bp.route("/transfer")
@login_required
def index():
    return render_template("transfer.html", kinds=KINDS,
                           max_mb=svc().messaging.max_file_bytes // (1024 * 1024))


@bp.route("/transfer/send", methods=["POST"])
@login_required
def send():
    f, up = request.form, request.files.get("file")
    kind = f.get("kind", "file")
    if up is None or not up.filename:
        flash("Pilih file terlebih dahulu.", "error")
        return redirect(url_for("transfer.index"))
    try:
        svc().messaging.send_file(g.user, parse_usernames(f.get("recipients", "")), up.filename, up.stream, f.get("secret", ""),
                                  kind=kind)
        flash(f"{KINDS.get(kind, 'File')} berhasil dienkripsi dan dikirim.", "success")
    except KomSaRError as e:
        flash(str(e), "error")
    return redirect(url_for("transfer.index"))


@bp.route("/assets")
@login_required
def assets():
    return render_template("assets.html", assets=svc().assets.list_assets(g.user, check_integrity=True))
