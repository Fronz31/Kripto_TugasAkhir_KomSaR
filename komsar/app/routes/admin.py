from flask import Blueprint, render_template

from ._helpers import admin_required, svc

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/chain")
@admin_required
def chain():
    s = svc()
    return render_template("chain.html", validation=s.chain.validate(), blocks=s.assets.list_blocks())
