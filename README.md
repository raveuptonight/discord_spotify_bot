# Discord Spotify Bot

Discord のボイスチャンネルで Spotify の楽曲を再生する Bot です。
[Librespot](https://github.com/librespot-org/librespot) を使ってコンテナ内で音声を受信し、Discord にストリーミングします。

## 必要なもの

- **Spotify Premium アカウント**（再生制御 API に必要）
- **Docker / Docker Compose**
- **Discord Bot Token**
- **Spotify Developer App**（Client ID / Secret）

## セットアップ

### 1. Discord Bot を作成

1. [Discord Developer Portal](https://discord.com/developers/applications) でアプリケーション作成
2. **Bot** タブでトークンを取得
3. **Privileged Gateway Intents** で `Message Content Intent` を有効化
4. **OAuth2 → URL Generator** で以下の権限を付けて招待リンクを生成
   - Scopes: `bot`
   - Permissions: `Send Messages`, `Connect`, `Speak`

### 2. Spotify Developer App を作成

1. [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) でアプリケーション作成
2. **Client ID** と **Client Secret** をメモ
3. **Redirect URI** に `http://localhost:8888/callback` を追加

### 3. 環境変数を設定

```bash
# 対話式セットアップ
./setup.sh

# または手動
cp .env.example .env
# .env を編集
```

### 4. 初回起動（Spotify OAuth 認証）

初回のみ対話モードで起動し、Spotify アカウントを認証します。

```bash
docker compose build
docker compose run -it bot python bot.py
```

ログに認証 URL が表示されるので：
1. URL をブラウザで開く
2. Spotify にログイン
3. リダイレクトされた URL をターミナルに貼り付け

Bot が起動したら `Ctrl+C` で停止して OK。

### 5. 通常起動

```bash
docker compose up -d
```

以降は自動でトークンがリフレッシュされます。

## コマンド一覧

| コマンド | 説明 |
|----------|------|
| `!play <曲名 / URL>` | 曲を検索して再生（再生中はキューに追加） |
| `!search <曲名>` | 検索結果5件からリアクションで選曲 |
| `!pause` | 一時停止 |
| `!resume` | 再生再開 |
| `!skip` / `!next` | 次の曲へスキップ |
| `!stop` | 再生停止 & VC 退出 |
| `!np` / `!nowplaying` | 再生中の曲を表示 |
| `!queue` / `!q` | 再生キューを表示 |
| `!volume <0-100>` | ボリューム調整 |
| `!join` | VC に参加 |
| `!leave` | VC から退出 |
| `!device` | Spotify デバイス一覧 |
| `!setdevice <名前>` | 再生先デバイス切り替え |
| `!help` | ヘルプ表示 |

**対応 URL 形式:** トラック、アルバム、プレイリストの Spotify URL / URI に対応しています。

## 注意事項

- **Spotify Premium が必須です。** Free プランでは再生制御 API が使えません。
- このBotは [Librespot](https://github.com/librespot-org/librespot)（非公式 Spotify Connect クライアント）を使用しています。Spotify の利用規約に抵触する可能性があるため、**利用は自己責任**でお願いします。
- 1つの Spotify アカウントで同時に再生できるデバイスは1つだけです。Bot が再生中に別デバイスで再生すると切り替わります。

## ライセンス

MIT
