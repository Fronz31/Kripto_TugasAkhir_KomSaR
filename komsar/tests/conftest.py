import pytest

from app import create_app
from app.config import TestConfig
from app.crypto.kdf import KDFParams, set_kdf_params
from app.extensions import db
from app.stego.cover import pick_random_cover


@pytest.fixture(autouse=True)
def fast_kdf():
    set_kdf_params(KDFParams(time_cost=1, memory_kib=64, parallelism=1))


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def cover_path():
    return pick_random_cover(TestConfig.COVER_IMAGES_DIR)
