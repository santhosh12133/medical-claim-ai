FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/app \
    HF_HOME=/home/app/.cache/huggingface \
    OMP_THREAD_LIMIT=1 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
# CPU-only PyTorch: the app never uses a GPU, and the default wheel pulls several GB of CUDA libraries.
RUN pip install --upgrade pip \
    && pip install --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install -r requirements.txt

# Run as an unprivileged user. Writable paths are created here so named volumes inherit the ownership.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin app \
    && mkdir -p /app/uploads /app/policy_uploads /app/chroma /app/logs /home/app/.cache \
    && chown -R app:app /app /home/app

COPY --chown=app:app . .

USER app

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000"]
