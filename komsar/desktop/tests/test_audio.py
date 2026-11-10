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
