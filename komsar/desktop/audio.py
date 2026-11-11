"""Rekam suara dari mikrofon: 16 kHz, mono, int16, hasil berupa bytes WAV."""

import io
import threading

import numpy as np
import sounddevice as sd
import soundfile as sf

SAMPLE_RATE = 16000
MIN_FRAMES = 2 * SAMPLE_RATE
MAX_FRAMES = 10 * SAMPLE_RATE
TOO_SHORT = "Rekaman terlalu pendek. Tahan tombol minimal 2 detik."


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


class Recorder:
    """Rekam selama tombol ditahan: start() membuka mikrofon, stop() menutupnya dan mengembalikan WAV.

    Callback sounddevice jalan di thread audio, start/stop dari thread pywebview. Lock frame terpisah
    dari lock kontrol supaya stream.stop() (menunggu callback selesai) tidak deadlock.
    """

    def __init__(self):
        self._ctl = threading.Lock()
        self._lock = threading.Lock()
        self._stream = None
        self._frames = []
        self._count = 0

    def _callback(self, indata, frames, time, status):
        with self._lock:
            chunk = indata[: MAX_FRAMES - self._count].copy()
            self._frames.append(chunk)
            self._count += len(chunk)
            full = self._count >= MAX_FRAMES
        if full:
            raise sd.CallbackStop  # batas 10 detik: berhenti sendiri, frame tetap disimpan

    def _close(self):
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.stop()
            stream.close()

    def start(self):
        with self._ctl:
            self._close()  # start saat masih merekam: buang rekaman lama, mulai bersih
            with self._lock:
                self._frames, self._count = [], 0
            stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", callback=self._callback)
            stream.start()
            self._stream = stream

    def stop(self):
        with self._ctl:
            if self._stream is None:
                raise RuntimeError("Rekaman belum dimulai.")
            self._close()
            with self._lock:
                frames, count = self._frames, self._count
                self._frames, self._count = [], 0
        if count < MIN_FRAMES:
            raise ValueError(TOO_SHORT)
        return to_wav(np.concatenate(frames))
