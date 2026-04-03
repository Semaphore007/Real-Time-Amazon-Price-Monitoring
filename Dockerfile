# ── Stage 1: Python dependencies ──────────────────────────────────────────────
FROM python:3.12-slim AS base

# System packages needed for Playwright + psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        curl \
        ca-certificates \
        fonts-liberation \
        libnss3 \
        libatk-bridge2.0-0 \
        libdrm2 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxrandr2 \
        libgbm1 \
        libasound2 \
        libxss1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python packages ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── Install Playwright browser (Chromium only) ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
RUN playwright install chromium \
    && playwright install-deps chromium

# ── Application code ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
COPY . .

# Create output dirs used at runtime
RUN mkdir -p raw_html output

EXPOSE 8000 8501

# Default: run the FastAPI backend (override in docker-compose per service)
CMD ["uvicorn", "api.fastapi_app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
