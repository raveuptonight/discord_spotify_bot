#!/usr/bin/env bash
set -e

ENV_FILE=".env"

echo "=== Discord Spotify Bot セットアップ ==="
echo ""

if [ -f "$ENV_FILE" ]; then
    read -rp ".env が既に存在します。上書きしますか？ (y/N): " overwrite
    if [[ ! "$overwrite" =~ ^[yY]$ ]]; then
        echo "中止しました。"
        exit 0
    fi
fi

read -rp "Discord Bot Token: " discord_token
echo ""
read -rp "Spotify Client ID: " spotify_client_id
read -rp "Spotify Client Secret: " spotify_client_secret
echo ""
read -rp "Librespot デバイス名 (デフォルト: Discord Bot): " device_name
device_name="${device_name:-Discord Bot}"

# 値をクォートして特殊文字 (#, スペース等) を安全に保存
cat > "$ENV_FILE" <<EOF
# Discord
DISCORD_TOKEN="${discord_token}"

# Spotify API (Web API 用 - 検索・再生制御)
SPOTIFY_CLIENT_ID="${spotify_client_id}"
SPOTIFY_CLIENT_SECRET="${spotify_client_secret}"
SPOTIFY_REDIRECT_URI=http://localhost:8888/callback

# Librespot 設定
LIBRESPOT_DEVICE_NAME="${device_name}"
LIBRESPOT_BITRATE=320
LIBRESPOT_CACHE=/app/cache
EOF

echo ".env を作成しました。"
echo ""
echo "次のステップ:"
echo "  1. docker compose build"
echo "  2. docker compose run -it bot python bot.py   (初回 OAuth 認証)"
echo "  3. docker compose up -d                       (通常起動)"
