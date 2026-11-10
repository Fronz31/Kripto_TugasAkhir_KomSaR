"""Verifikasi suara (speaker verification): validasi WAV + embedding + cosine similarity.

`SpeechBrainVerifier` dipakai di server (butuh torch/speechbrain, lihat requirements-server.txt).
`FakeVoiceVerifier` dipakai test agar tidak butuh PyTorch.
"""
import io
import threading
import wave
from pathlib import Path
from typing import Protocol

import numpy as np

from ..errors import ValidationError

SAMPLE_RATE = 16000
MIN_SECONDS, MAX_SECONDS = 2, 10
MAX_WAV_BYTES = 1024 * 1024
HUB_ID = "speechbrain/spkrec-ecapa-voxceleb"


def validate_wav(data: bytes) -> np.ndarray:
    """WAV PCM16 16 kHz mono 2-10 detik, maks. 1 MB -> sampel float32 [-1, 1]."""
    if not isinstance(data, (bytes, bytearray)) or not data:
        raise ValidationError("Rekaman suara kosong.")
    if len(data) > MAX_WAV_BYTES:
        raise ValidationError("Rekaman suara melebihi 1 MB.")
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            channels, width, rate, frames = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            raw = w.readframes(frames)
    except (wave.Error, EOFError) as e:
        raise ValidationError("Rekaman suara harus berupa file WAV.") from e
    if width != 2 or rate != SAMPLE_RATE or channels != 1:
        raise ValidationError("Rekaman suara harus WAV PCM 16-bit, 16000 Hz, mono.")
    if not MIN_SECONDS <= frames / rate <= MAX_SECONDS:
        raise ValidationError(f"Durasi rekaman harus {MIN_SECONDS} sampai {MAX_SECONDS} detik.")
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    a, b = np.asarray(a, dtype=np.float64).ravel(), np.asarray(b, dtype=np.float64).ravel()
    n = np.linalg.norm(a) * np.linalg.norm(b)
    return float(a @ b / n) if n else 0.0


class VoiceVerifier(Protocol):
    def embed(self, wav_bytes: bytes) -> np.ndarray: ...
    def score(self, a: np.ndarray, b: np.ndarray) -> float: ...


class FakeVoiceVerifier:
    """Embedding = spektrum daya per 64 pita frekuensi. Hanya untuk test (bukan pengenal suara sungguhan)."""

    def embed(self, wav_bytes: bytes) -> np.ndarray:
        power = np.abs(np.fft.rfft(validate_wav(wav_bytes))) ** 2
        return np.array([b.sum() for b in np.array_split(power, 64)], dtype=np.float32)

    score = staticmethod(cosine)


class SpeechBrainVerifier:
    """ECAPA-TDNN (VoxCeleb). Model dimuat sekali per proses, saat pertama dipakai."""
    _model = None
    _lock = threading.Lock()

    def __init__(self, model_dir):
        self.model_dir = Path(model_dir)

    def _load(self):
        with self._lock:
            if SpeechBrainVerifier._model is None:
                try:
                    from speechbrain.inference.speaker import EncoderClassifier
                except ImportError:                     # speechbrain < 1.0
                    from speechbrain.pretrained import EncoderClassifier
                # model di-bake ke image; tanpa folder lokal, unduh dari hub ke folder yang sama
                local = (self.model_dir / "hyperparams.yaml").exists()
                SpeechBrainVerifier._model = EncoderClassifier.from_hparams(
                    source=str(self.model_dir) if local else HUB_ID, savedir=str(self.model_dir),
                    run_opts={"device": "cpu"})
        return SpeechBrainVerifier._model

    def embed(self, wav_bytes: bytes) -> np.ndarray:
        import torch
        samples = torch.from_numpy(validate_wav(wav_bytes)).unsqueeze(0)
        with torch.no_grad():
            emb = self._load().encode_batch(samples)
        return emb.squeeze().cpu().numpy().astype(np.float32)

    score = staticmethod(cosine)


def make_verifier(config) -> VoiceVerifier:
    backend = config.get("VOICE_BACKEND", "speechbrain")
    if backend == "fake":
        return FakeVoiceVerifier()
    if backend == "speechbrain":
        return SpeechBrainVerifier(config["VOICE_MODEL_DIR"])
    raise ValueError(f"VOICE_BACKEND tidak dikenal: {backend}")
