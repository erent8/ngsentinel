# NGSentinel — public web server image (works on Hugging Face Spaces, Render, any Docker host)
# Includes FastQC, fastp and MultiQC so the full pipeline runs inside the container.

# ---- 1. build the React interface -------------------------------------------
FROM node:20-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. runtime: Python + bioinformatics tools ------------------------------
FROM python:3.12-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends default-jre-headless fastqc fastp procps \
 && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces run containers as user 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    NGSENTINEL_PUBLIC=1 \
    NGSENTINEL_DATA=/home/user/data \
    NGSENTINEL_MAX_UPLOAD_MB=150 \
    NGSENTINEL_RUN_TTL_HOURS=24
WORKDIR /home/user/app

COPY --chown=user requirements.txt ./
RUN pip install --no-cache-dir --user -r requirements.txt multiqc

COPY --chown=user backend ./backend
COPY --chown=user config ./config
COPY --chown=user --from=ui /ui/dist ./frontend/dist

EXPOSE 7860
CMD ["python", "-m", "uvicorn", "ngsentinel.api:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "7860"]
