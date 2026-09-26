# ---- Native pipeline stage: zero-dependency Rust kernel -----------------------
FROM rust:1-slim AS native-builder
WORKDIR /native
COPY native/ .
RUN cargo build --release

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    libgeos-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Rust kernel lives outside /app so the ./backend bind mount can't shadow it.
COPY --from=native-builder /native/target/release/bhudrishti_native /usr/local/bin/bhudrishti_native

EXPOSE 8000

# Production server mode: no --reload, single boot, ready for process managers
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
