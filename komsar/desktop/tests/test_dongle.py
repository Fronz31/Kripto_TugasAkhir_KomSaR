import base64
import json
import os
import uuid

import pytest

import dongle

TOKEN = base64.b64encode(os.urandom(32)).decode()
DONGLE_ID = str(uuid.uuid4())


def drives_of(*paths):
    return lambda: [str(p) for p in paths]


def serial(_drive):
    return "1A2B3C4D"


def put(drive, content):
    (drive / dongle.DONGLE_FILE).write_text(content, encoding="utf-8")


def test_write_then_read_roundtrip(tmp_path):
    assert dongle.write_dongle(str(tmp_path), DONGLE_ID, TOKEN, drives=drives_of(tmp_path))
    data = json.loads((tmp_path / dongle.DONGLE_FILE).read_text(encoding="utf-8"))
    assert data == {"v": 1, "dongle_id": DONGLE_ID, "token": TOKEN}
    assert dongle.read_dongle(drives_of(tmp_path), serial) == {
        "dongle_id": DONGLE_ID,
        "token": TOKEN,
        "volume_serial": "1A2B3C4D",
    }


def test_no_drives_returns_none():
    assert dongle.read_dongle(drives_of(), serial) is None


def test_skips_invalid_and_picks_first_valid(tmp_path):
    empty, garbage, bad_version, short_token, good = (tmp_path / n for n in "abcde")
    for d in (empty, garbage, bad_version, short_token, good):
        d.mkdir()
    put(garbage, "not json")
    put(bad_version, json.dumps({"v": 2, "dongle_id": DONGLE_ID, "token": TOKEN}))
    put(short_token, json.dumps({"v": 1, "dongle_id": DONGLE_ID, "token": "AAAA"}))
    put(good, json.dumps({"v": 1, "dongle_id": DONGLE_ID, "token": TOKEN}))
    found = dongle.read_dongle(drives_of(empty, garbage, bad_version, short_token, good), serial)
    assert found["dongle_id"] == DONGLE_ID


def test_unreadable_serial_skipped(tmp_path):
    put(tmp_path, json.dumps({"v": 1, "dongle_id": DONGLE_ID, "token": TOKEN}))
    assert dongle.read_dongle(drives_of(tmp_path), lambda d: None) is None


def test_write_rejects_non_removable_drive(tmp_path):
    with pytest.raises(ValueError):
        dongle.write_dongle(str(tmp_path), DONGLE_ID, TOKEN, drives=drives_of())
    assert not (tmp_path / dongle.DONGLE_FILE).exists()


@pytest.mark.parametrize("dongle_id,token", [("not-a-uuid", TOKEN), (DONGLE_ID, "AAAA"), (DONGLE_ID, "!!")])
def test_write_rejects_bad_values(tmp_path, dongle_id, token):
    with pytest.raises(ValueError):
        dongle.write_dongle(str(tmp_path), dongle_id, token, drives=drives_of(tmp_path))
