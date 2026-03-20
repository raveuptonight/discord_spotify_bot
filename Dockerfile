# Stage 1: Librespot ビルド
FROM rust:1-bookworm AS librespot-builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends pkg-config libasound2-dev && \
    rm -rf /var/lib/apt/lists/*

RUN cargo install librespot --git https://github.com/librespot-org/librespot --tag v0.8.0

# Stage 2: ランタイム
FROM python:3.12-slim-bookworm

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libsodium23 \
        libopus0 && \
    rm -rf /var/lib/apt/lists/*

COPY --from=librespot-builder /usr/local/cargo/bin/librespot /usr/local/bin/librespot

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/cache

CMD ["python", "bot.py"]
