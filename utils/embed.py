import discord

SPOTIFY_GREEN = 0x1DB954


def _format_duration(ms: int) -> str:
    total_seconds = ms // 1000
    return f"{total_seconds // 60}:{total_seconds % 60:02d}"


def now_playing_embed(track: dict) -> discord.Embed:
    embed = discord.Embed(title=track["name"], color=SPOTIFY_GREEN)
    embed.add_field(name="アーティスト", value=track["artist"], inline=True)
    embed.add_field(name="アルバム", value=track["album"], inline=True)
    embed.add_field(
        name="再生時間", value=_format_duration(track["duration_ms"]), inline=True
    )
    if track.get("image_url"):
        embed.set_thumbnail(url=track["image_url"])
    embed.set_footer(text="Spotify", icon_url="https://i.imgur.com/qvdqtsc.png")
    return embed


def search_results_embed(tracks: list[dict]) -> discord.Embed:
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    lines = []
    for i, track in enumerate(tracks):
        dur = _format_duration(track["duration_ms"])
        lines.append(f"{emojis[i]} **{track['name']}** - {track['artist']} ({dur})")
    embed = discord.Embed(
        title="検索結果",
        description="\n".join(lines),
        color=SPOTIFY_GREEN,
    )
    embed.set_footer(text="リアクションで選曲してください（30秒以内）")
    return embed


def queue_embed(queue: list[dict], current: dict | None = None, total: int = 0) -> discord.Embed:
    embed = discord.Embed(title="再生キュー", color=SPOTIFY_GREEN)

    if current:
        embed.add_field(
            name="▶ 再生中",
            value=f"**{current['name']}** - {current['artist']}",
            inline=False,
        )

    if queue:
        lines = []
        for i, track in enumerate(queue[:10], start=1):
            dur = _format_duration(track["duration_ms"])
            lines.append(f"`{i}.` **{track['name']}** - {track['artist']} ({dur})")
        if total > 10:
            lines.append(f"...他 {total - 10} 曲")
        embed.add_field(name="次の曲", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="次の曲", value="キューは空です", inline=False)

    return embed
