"""Rekam suara dari mikrofon: 16 kHz, mono, int16, hasil berupa bytes WAV."""

import io

import sounddevice as sd
import soundfile as sf

SAMPLE_RATE = 16000


def clamp_seconds(seconds):
    return max(2.0, min(10.0, float(seconds)))


def to_wav(samples):
    buf = io.BytesIO()
    sf.write(buf, samples, SAMPLE_RATE, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def record_wav(seconds):
    frames = int(clamp_seconds(seconds) * SAMPLE_RATE)
    samples = sd.rec(frames, samplerate=SAMPLE_RATE, channels=1, dtype="int16")
    sd.wait()
    return to_wav(samples)
