# KomSaR server untuk InstaCloud. Dockerfile di root repo karena aplikasi ada di subfolder komsar/.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Torch CPU-only dulu, supaya requirements-server.txt tidak menarik wheel CUDA (beberapa GB).
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch torchaudio

WORKDIR /app
COPY komsar/requirements.txt komsar/requirements-server.txt ./
RUN pip install -r requirements-server.txt gunicorn

# create_app membuat /app/instance; model ditulis ke /app/models -> /app milik user non-root.
RUN useradd --create-home --uid 1000 komsar && chown komsar:komsar /app
COPY --chown=komsar:komsar komsar/ /app/
USER komsar

# Model SpeechBrain di-bake ke image lewat loader yang sama dengan aplikasi, jadi runtime tidak butuh internet.
# Diunduh sebagai user komsar: savedir bisa berisi symlink ke cache HF di home user ini.
RUN python -c "from app.auth.voice import SpeechBrainVerifier as V; V('/app/models/spkrec-ecapa-voxceleb')._load()"

ENV KOMSAR_ENV=production \
    KOMSAR_TRUST_PROXY=1 \
    VOICE_BACKEND=speechbrain \
    VOICE_MODEL_DIR=/app/models/spkrec-ecapa-voxceleb \
    HF_HUB_OFFLINE=1

EXPOSE 8080
# WAJIB 1 worker: cache hasil dekripsi, kalimat tantangan suara, dan rate limit disimpan di memori proses.
# Worker kedua punya memori sendiri -> dekripsi dua langkah/verifikasi suara gagal acak. Skala lewat --threads.
CMD ["gunicorn", "-w", "1", "--threads", "4", "-b", "0.0.0.0:8080", "--timeout", "120", "wsgi:app"]
