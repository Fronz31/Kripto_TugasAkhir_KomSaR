import io
import json
import urllib.error

import pytest

import main

SERVER = "https://komsar.example"


class FakeWindow:
    def __init__(self, url):
        self.url = url

    def get_current_url(self):
        return self.url


def bridge_at(url):
    b = main.Bridge(SERVER)
    b._window = FakeWindow(url)
    return b


def test_bridge_refuses_foreign_origin(monkeypatch):
    monkeypatch.setattr(main.dongle, "read_dongle", lambda: {"dongle_id": "x"})
    assert bridge_at("https://evil.example/").read_dongle() == {"error": "Halaman bukan dari server KomSaR"}
    assert "error" in bridge_at("http://komsar.example/").read_dongle()
    assert bridge_at(SERVER + "/login").read_dongle() == {"dongle_id": "x"}


def test_bridge_wraps_errors(monkeypatch):
    def boom(*_):
        raise ValueError("Drive bukan flashdisk removable")

    monkeypatch.setattr(main.dongle, "write_dongle", boom)
    assert bridge_at(SERVER).write_dongle("C:\\", "a", "b") == {"error": "Drive bukan flashdisk removable"}


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


def fake_urlopen(result):
    def urlopen(req, timeout):
        assert req.full_url == SERVER + "/api/dongle/check"
        assert json.loads(req.data) == {"dongle_id": "d", "token": "t", "volume_serial": "S"}
        if isinstance(result, Exception):
            raise result
        return FakeResp(result)

    return urlopen


@pytest.mark.parametrize(
    "result,ok",
    [
        (b'{"ok": true}', True),
        (b'{"ok": false}', False),
        (b"<html>", False),
        (urllib.error.HTTPError(SERVER, 403, "Forbidden", {}, io.BytesIO(b'{"ok": false}')), False),
    ],
)
def test_check_dongle(monkeypatch, result, ok):
    monkeypatch.setattr(main.urllib.request, "urlopen", fake_urlopen(result))
    assert main.check_dongle(SERVER, {"dongle_id": "d", "token": "t", "volume_serial": "S"}) is ok


@pytest.mark.parametrize(
    "error",
    [urllib.error.URLError("down"), urllib.error.HTTPError(SERVER, 502, "Bad Gateway", {}, io.BytesIO(b""))],
)
def test_check_dongle_network_error_raises(monkeypatch, error):
    monkeypatch.setattr(main.urllib.request, "urlopen", fake_urlopen(error))
    with pytest.raises(OSError):
        main.check_dongle(SERVER, {"dongle_id": "d", "token": "t", "volume_serial": "S"})



def config_urlopen(result):
    def urlopen(url, timeout):
        assert url == SERVER + "/api/client-config"
        if isinstance(result, Exception):
            raise result
        return FakeResp(result)

    return urlopen


@pytest.mark.parametrize(
    "result,required",
    [
        (b'{"require_dongle": false}', False),
        (b'{"require_dongle": true}', True),
        (b"<html>", True),                                         # balasan aneh: fail closed
        (urllib.error.HTTPError(SERVER, 404, "Not Found", {}, io.BytesIO(b"")), True),   # server lama
    ],
)
def test_server_requires_dongle(monkeypatch, result, required):
    monkeypatch.setattr(main.urllib.request, "urlopen", config_urlopen(result))
    assert main.server_requires_dongle(SERVER) is required


@pytest.mark.parametrize(
    "error",
    [urllib.error.URLError("down"), urllib.error.HTTPError(SERVER, 503, "Unavailable", {}, io.BytesIO(b""))],
)
def test_server_requires_dongle_unreachable_raises(monkeypatch, error):
    monkeypatch.setattr(main.urllib.request, "urlopen", config_urlopen(error))
    with pytest.raises(OSError):
        main.server_requires_dongle(SERVER)
