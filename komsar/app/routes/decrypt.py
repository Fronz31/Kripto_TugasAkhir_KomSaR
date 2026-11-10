import io

from flask import Blueprint, abort, flash, g, render_template, request, send_file

from ..errors import IntegrityViolationError, KomSaRError, StegoKeyMismatchError, ValidationError
from ..services.audit_service import DECRYPT_FAILED, DECRYPT_SUCCESS, INTEGRITY_FAILED, audit
from ._helpers import login_required, svc

bp = Blueprint("decrypt", __name__)
KIND_CHOICES = [("", "Semua jenis"), ("text", "Pesan Biasa"), ("important_text", "Pesan Penting"),
                ("file", "File"), ("image", "Gambar"), ("asset", "Aset Penting")]
INLINE_IMAGES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp"}


@bp.route("/decrypt", methods=["GET", "POST"])
@login_required
def center():
    """Alur: gambar stego tampil -> input ID -> kunci hasil ekstraksi tampil -> input ulang kunci -> dekripsi."""
    s = svc()
    result = dl_token = step2 = None
    chosen = request.values.get("d", "")
    if request.method == "POST":
        if request.form.get("action", "extract") == "extract":                       # langkah 1
            chosen = request.form.get("delivery_id", "")
            rid = request.form.get("user_id", "")
            try:
                secret = s.decryption.extract_secret(g.user, chosen, rid,
                                                     expected_kind=request.form.get("kind") or None)
                step2 = {"token": s.cache.put_pending(g.user.id, chosen, rid, secret), "secret": secret}
            except KomSaRError as e:
                audit(DECRYPT_FAILED, target=chosen[:64], step="extract", reason=type(e).__name__)
                flash(str(e), "error")                                               # ID salah / bukan hak / dll.
        else:                                                                        # langkah 2
            token = request.form.get("token", "")
            pending = s.cache.get_pending(token, g.user.id)
            if pending is None:
                flash("Sesi dekripsi sudah berakhir. Ulangi dari langkah 1.", "error")
            else:
                chosen = pending["delivery_id"]
                step2 = {"token": token, "secret": pending["secret"]}
                try:
                    result = s.decryption.open(g.user, chosen, pending["rid"],
                                               secret_input=request.form.get("secret_key", ""))
                    s.cache.drop_pending(token)
                    dl_token, step2 = s.cache.remember(g.user.id, chosen, result), None
                    audit(DECRYPT_SUCCESS, target=chosen, kind=result.kind)
                except StegoKeyMismatchError as e:                                   # kunci input tidak sesuai
                    audit(DECRYPT_FAILED, target=chosen, step="open", reason=type(e).__name__)
                    if s.cache.fail_pending(token):
                        flash(str(e), "error")
                    else:
                        step2 = None
                        flash("Terlalu banyak kesalahan memasukkan kunci. Ulangi dari langkah 1.", "error")
                except ValidationError as e:                                         # mis. kunci kosong
                    flash(str(e), "error")
                except (IntegrityViolationError, KomSaRError) as e:
                    if isinstance(e, IntegrityViolationError):
                        audit(INTEGRITY_FAILED, target=chosen, step="open", reason=type(e).__name__)
                    else:
                        audit(DECRYPT_FAILED, target=chosen, step="open", reason=type(e).__name__)
                    s.cache.drop_pending(token)
                    step2 = None
                    flash(str(e), "error")
    return render_template("decrypt.html", items=s.messaging.inbox(g.user), kinds=KIND_CHOICES, chosen=chosen,
                           result=result, token=dl_token, step2=step2, inline_images=INLINE_IMAGES)


@bp.route("/decrypt/file/<token>")
@login_required
def download(token):
    entry = svc().cache.get_file(token, g.user.id)
    if entry is None:
        abort(404)
    inline = request.args.get("inline") == "1" and entry["mime"] in INLINE_IMAGES
    return send_file(io.BytesIO(entry["data"]), mimetype=entry["mime"] if inline else "application/octet-stream",
                     as_attachment=not inline, download_name=entry["name"])


def _own_delivery(delivery_id):
    d = svc().repo.get_delivery(delivery_id)
    if d is None or d.recipient_pk != g.user.id:
        abort(404)
    return d


@bp.route("/delivery/<delivery_id>/stego")
@login_required
def stego(delivery_id):
    d = _own_delivery(delivery_id)
    return send_file(io.BytesIO(d.stego_png or b""), mimetype="image/png", as_attachment=request.args.get("inline") != "1",
                     download_name=f"stego_{delivery_id[:8]}.png")


@bp.route("/delivery/<delivery_id>/cipher")
@login_required
def cipher(delivery_id):
    s = svc()
    d = _own_delivery(delivery_id)
    m = s.repo.get_message(d.message_id)
    if m.file_id:
        return send_file(io.BytesIO(s.repo.get_file(m.file_id).ciphertext or b""), mimetype="application/octet-stream",
                         as_attachment=True, download_name=f"cipher_{delivery_id[:8]}.enc")
    return send_file(io.BytesIO(m.ciphertext), mimetype="application/octet-stream", as_attachment=True,
                     download_name=f"cipher_{delivery_id[:8]}.bin")
