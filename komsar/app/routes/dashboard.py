from flask import Blueprint, g, render_template

from ..services import user_service as us
from ._helpers import login_required, svc

bp = Blueprint("dashboard", __name__)


@bp.route("/dashboard")
@login_required
def index():
    s = svc()
    inbox = s.messaging.inbox(g.user)
    stats = {
        "inbox": len(inbox),
        "unopened": sum(1 for i in inbox if i["status"] != "decrypted"),
        "sent": len(s.messaging.sent(g.user)),
        "assets": len(s.assets.list_assets(g.user)),
    }
    admin = None
    if g.user.is_admin:
        v = s.chain.validate()
        admin = {"users": len(us.list_users()), "chain_length": v.length, "chain_valid": v.valid}
    return render_template("dashboard.html", stats=stats, recent=inbox[:5], admin=admin)
