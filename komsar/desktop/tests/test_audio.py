import io
import wave

import numpy as np
import pytest

import audio


class FakeSD:
    def __init__(self):
        self.calls = []

    def rec(self, frames, samplerate, channels, dtype):
        self.calls.append((frames, samplerate, channels, dtype))
        return np.full((frames, channels), 1234, dtype=dtype)

    def wait(self):
        pass


@pytest.mark.parametrize("asked,expected", [(0, 2), (3, 3), (99, 10)])
def test_record_wav_clamps_and_encodes(monkeypatch, asked, expected):
    fake = FakeSD()
    monkeypatch.setattr(audio, "sd", fake)
    data = audio.record_wav(asked)
    assert fake.calls == [(expected * 16000, 16000, 1, "int16")]
    with wave.open(io.BytesIO(data)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 16000)
        assert w.getnframes() == expected * 16000
        assert np.frombuffer(w.readframes(1), dtype="<i2")[0] == 1234


class CallbackStop(Exception):
    pass


class FakeStream:
    def __init__(self, samplerate, channels, dtype, callback):
        assert (samplerate, channels, dtype) == (16000, 1, "int16")
        self.callback = callback
        self.started = self.stopped = self.closed = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True

    def feed(self, seconds, value=7):
        """Kirim audio dalam blok 0,1 detik seperti PortAudio; berhenti bila callback minta stop."""
        block = np.full((1600, 1), value, dtype="int16")
        for _ in range(round(seconds * 10)):
            try:
                self.callback(block, 1600, None, None)
            except CallbackStop:
                return


class FakeStreamSD:
    CallbackStop = CallbackStop

    def __init__(self):
        self.streams = []

    def InputStream(self, **kw):
        self.streams.append(FakeStream(**kw))
        return self.streams[-1]


@pytest.fixture
def sd_streams(monkeypatch):
    fake = FakeStreamSD()
    monkeypatch.setattr(audio, "sd", fake)
    return fake


def frames_of(data):
    with wave.open(io.BytesIO(data)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 16000)
        return w.getnframes(), np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")


def test_recorder_returns_held_audio(sd_streams):
    rec = audio.Recorder()
    rec.start()
    s = sd_streams.streams[0]
    assert s.started
    s.feed(3.2)
    n, samples = frames_of(rec.stop())
    assert n == 32 * 1600 and (samples == 7).all()
    assert s.stopped and s.closed


def test_recorder_caps_at_ten_seconds(sd_streams):
    rec = audio.Recorder()
    rec.start()
    sd_streams.streams[0].feed(15)
    assert frames_of(rec.stop())[0] == 10 * 16000


def test_recorder_too_short(sd_streams):
    rec = audio.Recorder()
    rec.start()
    sd_streams.streams[0].feed(1.5)
    with pytest.raises(ValueError, match="Tahan tombol minimal 2 detik"):
        rec.stop()
    with pytest.raises(RuntimeError):  # rekaman sudah ditutup
        rec.stop()


def test_recorder_stop_without_start(sd_streams):
    with pytest.raises(RuntimeError, match="belum dimulai"):
        audio.Recorder().stop()


def test_recorder_restart_discards_old_audio(sd_streams):
    rec = audio.Recorder()
    rec.start()
    first = sd_streams.streams[0]
    first.feed(5, value=1)
    rec.start()
    assert first.closed and len(sd_streams.streams) == 2
    sd_streams.streams[1].feed(2, value=9)
    n, samples = frames_of(rec.stop())
    assert n == 2 * 16000 and (samples == 9).all()
