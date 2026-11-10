from pathlib import Path

from flask import Flask

from .config import Config, load_db_master_key
from .crypto.kdf import KDFParams, set_kdf_params
from .extensions import db


def create_app(config_class=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    if not app.config.get("SECRET_KEY") or not app.config.get("DB_MASTER_KEY_B64"):
        raise RuntimeError(
            "KOMSAR_SECRET_KEY dan KOMSAR_DB_MASTER_KEY wajib diisi (lihat .env.example)."
        )
    app.config["DB_MASTER_KEY"] = load_db_master_key(app.config)

    for key in ("ENCRYPTED_FILES_DIR", "STEGO_IMAGES_DIR"):
        Path(app.config[key]).mkdir(parents=True, exist_ok=True)
    (Path(app.root_path).parent / "instance").mkdir(exist_ok=True)

    set_kdf_params(KDFParams(
        time_cost=app.config["ARGON2_TIME_COST"],
        memory_kib=app.config["ARGON2_MEMORY_KIB"],
        parallelism=app.config["ARGON2_PARALLELISM"],
    ))

    app.config.setdefault("MAX_CONTENT_LENGTH", app.config["MAX_FILE_BYTES"] + 2 * 1024 * 1024)
    db.init_app(app)
    from .blockchain import store  # noqa: F401  (daftarkan model)
    from .models import records, security, user  # noqa: F401
    from .services.container import build_services
    with app.app_context():
        db.create_all()
        app.extensions["komsar"] = build_services(app)      # blok genesis dibuat di DB bila belum ada
    from .routes import register_routes
    register_routes(app)
    return app
