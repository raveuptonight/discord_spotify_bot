import asyncio
import logging
import os

import discord
from discord.ext import commands

from cogs.spotify import SpotifyClient
from utils.audio import LibrespotManager
from utils.embed import now_playing_embed, search_results_embed, queue_embed

logger = logging.getLogger(__name__)

NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]


class Music(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.spotify = SpotifyClient()
        self.librespot = LibrespotManager()

    async def cog_load(self):
        self.librespot.start()

    async def cog_unload(self):
        self.librespot.stop()

    def _get_vc(self, ctx: commands.Context) -> discord.VoiceClient | None:
        return ctx.voice_client

    async def _ensure_connected(self, ctx: commands.Context) -> discord.VoiceClient:
        vc = self._get_vc(ctx)
        if vc and vc.is_connected():
            return vc

        if not ctx.author.voice:
            raise commands.CommandError("先にボイスチャンネルに参加してください。")

        channel = ctx.author.voice.channel
        vc = await channel.connect()

        source = self.librespot.create_audio_source()
        vc.play(source, after=lambda e: logger.error("再生エラー: %s", e) if e else None)
        logger.info("VC接続: %s", channel.name)
        return vc

    # ---- テスト用 (owner only) ----

    @commands.command(hidden=True)
    @commands.is_owner()
    async def testplay(self, ctx: commands.Context):
        """テストトーンで再生テスト"""
        if not ctx.author.voice:
            raise commands.CommandError("先にボイスチャンネルに参加してください。")
        vc = self._get_vc(ctx)
        if not vc:
            vc = await ctx.author.voice.channel.connect()
        if vc.is_playing():
            vc.stop()
        source = discord.FFmpegPCMAudio(
            "sine=frequency=440:duration=300",
            before_options="-f lavfi",
        )
        vc.play(source)
        await ctx.send("🔊 テストトーン再生中 (5分)")

    @commands.command(hidden=True)
    @commands.is_owner()
    async def testcapture(self, ctx: commands.Context, seconds: int = 15):
        """PCM ファイルから切り出して再生テスト"""
        if not ctx.author.voice:
            raise commands.CommandError("先にボイスチャンネルに参加してください。")

        from utils.audio import BYTES_PER_SEC_48K, LibrespotManager

        audio_file = LibrespotManager.AUDIO_FILE
        if not os.path.exists(audio_file):
            await ctx.send("音声ファイルがまだありません。Spotify で何か再生してください。")
            return

        target_bytes = seconds * BYTES_PER_SEC_48K
        file_size = os.path.getsize(audio_file)
        capture_bytes = min(target_bytes, file_size)
        actual_secs = capture_bytes / BYTES_PER_SEC_48K

        raw_path = "/tmp/capture.raw"
        with open(audio_file, "rb") as src, open(raw_path, "wb") as dst:
            dst.write(src.read(capture_bytes))

        await ctx.send(f"✅ {actual_secs:.1f}秒分を切り出しました。再生します...")

        vc = self._get_vc(ctx)
        if not vc:
            vc = await ctx.author.voice.channel.connect()
        if vc.is_playing():
            vc.stop()

        source = discord.FFmpegPCMAudio(
            raw_path,
            before_options="-f s16le -ar 48000 -ac 2",
        )
        vc.play(source)
        await ctx.send(f"▶ ファイル再生中 ({actual_secs:.1f}秒)")

    # ---- コマンド ----

    @commands.command()
    async def join(self, ctx: commands.Context):
        """ボイスチャンネルに参加"""
        await self._ensure_connected(ctx)
        await ctx.send("🔊 ボイスチャンネルに接続しました。")

    @commands.command()
    async def leave(self, ctx: commands.Context):
        """ボイスチャンネルから退出"""
        vc = self._get_vc(ctx)
        if vc and vc.is_connected():
            vc.stop()
            await vc.disconnect()
            await ctx.send("👋 ボイスチャンネルから退出しました。")
        else:
            await ctx.send("ボイスチャンネルに接続していません。")

    @commands.command()
    async def play(self, ctx: commands.Context, *, query: str):
        """曲を検索して再生（再生中はキューに追加）"""
        await self._ensure_connected(ctx)

        parsed = SpotifyClient.parse_spotify_uri(query)
        if parsed:
            kind, uri = parsed

            # album / playlist → そのまま再生開始
            if kind != "track":
                await self.spotify.play(context_uri=uri)
                self.librespot.flush()
                await asyncio.sleep(0.5)
                track = await self.spotify.get_current_track()
                if track:
                    await ctx.send(embed=now_playing_embed(track))
                else:
                    await ctx.send("▶ 再生を開始しました。")
                return

            # track: 再生中ならキューに追加
            current = await self.spotify.get_current_track()
            if current and current.get("is_playing"):
                await self.spotify.add_to_queue(uri=uri)
                track_info = await self.spotify.get_track(uri)
                if track_info:
                    await ctx.send(
                        f"🎵 キューに追加: **{track_info['name']}** - {track_info['artist']}"
                    )
                else:
                    await ctx.send("🎵 キューに追加しました。")
                return

            await self.spotify.play(uri=uri)
            self.librespot.flush()
            await asyncio.sleep(0.5)
            track = await self.spotify.get_current_track()
            if track:
                await ctx.send(embed=now_playing_embed(track))
            else:
                await ctx.send("▶ 再生を開始しました。")
            return

        # テキスト検索
        results = await self.spotify.search_tracks(query, limit=1)
        if not results:
            await ctx.send("曲が見つかりませんでした。")
            return

        track = results[0]
        current = await self.spotify.get_current_track()
        if current and current.get("is_playing"):
            await self.spotify.add_to_queue(uri=track["uri"])
            await ctx.send(f"🎵 キューに追加: **{track['name']}** - {track['artist']}")
            return

        await self.spotify.play(uri=track["uri"])
        self.librespot.flush()
        await ctx.send(embed=now_playing_embed(track))

    @commands.command()
    async def search(self, ctx: commands.Context, *, query: str):
        """検索結果を5件表示し、リアクションで選曲"""
        results = await self.spotify.search_tracks(query, limit=5)
        if not results:
            await ctx.send("曲が見つかりませんでした。")
            return

        embed = search_results_embed(results)
        msg = await ctx.send(embed=embed)

        for i in range(len(results)):
            await msg.add_reaction(NUMBER_EMOJIS[i])

        def check(reaction: discord.Reaction, user: discord.User) -> bool:
            return (
                user == ctx.author
                and reaction.message.id == msg.id
                and str(reaction.emoji) in NUMBER_EMOJIS[: len(results)]
            )

        try:
            reaction, _ = await self.bot.wait_for("reaction_add", check=check, timeout=30.0)
        except asyncio.TimeoutError:
            await msg.clear_reactions()
            await ctx.send("選曲がタイムアウトしました。")
            return

        idx = NUMBER_EMOJIS.index(str(reaction.emoji))
        selected = results[idx]

        await self._ensure_connected(ctx)

        current = await self.spotify.get_current_track()
        if current and current.get("is_playing"):
            await self.spotify.add_to_queue(uri=selected["uri"])
            await ctx.send(
                f"🎵 キューに追加: **{selected['name']}** - {selected['artist']}"
            )
        else:
            await self.spotify.play(uri=selected["uri"])
            self.librespot.flush()
            await ctx.send(embed=now_playing_embed(selected))

    @commands.command()
    async def pause(self, ctx: commands.Context):
        """一時停止"""
        await self.spotify.pause()
        await ctx.send("⏸ 一時停止しました。")

    @commands.command()
    async def resume(self, ctx: commands.Context):
        """再生を再開"""
        await self.spotify.resume()
        await ctx.send("▶ 再生を再開しました。")

    @commands.command(aliases=["next"])
    async def skip(self, ctx: commands.Context):
        """次の曲へスキップ"""
        await self.spotify.skip()
        self.librespot.flush()
        await asyncio.sleep(1)
        track = await self.spotify.get_current_track()
        if track:
            await ctx.send(embed=now_playing_embed(track))
        else:
            await ctx.send("⏭ スキップしました。")

    @commands.command()
    async def stop(self, ctx: commands.Context):
        """再生停止 & VC 退出"""
        await self.spotify.pause()
        vc = self._get_vc(ctx)
        if vc and vc.is_connected():
            vc.stop()
            await vc.disconnect()
        await ctx.send("⏹ 再生を停止しました。")

    @commands.command(aliases=["q"])
    async def queue(self, ctx: commands.Context):
        """再生キューを表示"""
        data = await self.spotify.get_queue()
        embed = queue_embed(data["queue"], data["current"], data["total"])
        await ctx.send(embed=embed)

    @commands.command(aliases=["nowplaying"])
    async def np(self, ctx: commands.Context):
        """再生中の曲情報を表示"""
        track = await self.spotify.get_current_track()
        if track:
            await ctx.send(embed=now_playing_embed(track))
        else:
            await ctx.send("現在再生中の曲はありません。")

    @commands.command()
    async def volume(self, ctx: commands.Context, vol: int):
        """ボリューム調整 (0-100)"""
        if not 0 <= vol <= 100:
            await ctx.send("ボリュームは 0〜100 の範囲で指定してください。")
            return
        await self.spotify.set_volume(vol)
        await ctx.send(f"🔉 ボリュームを {vol} に設定しました。")

    @commands.command()
    async def device(self, ctx: commands.Context):
        """Spotify デバイス一覧"""
        devices = await self.spotify.get_devices()
        if not devices:
            await ctx.send("デバイスが見つかりません。Librespot が起動しているか確認してください。")
            return
        lines = []
        for d in devices:
            active = " ✅" if d.get("is_active") else ""
            lines.append(f"• **{d['name']}** ({d['type']}){active}")
        embed = discord.Embed(
            title="Spotify デバイス一覧",
            description="\n".join(lines),
            color=0x1DB954,
        )
        await ctx.send(embed=embed)

    @commands.command()
    async def setdevice(self, ctx: commands.Context, *, device_name: str):
        """再生先デバイスを切り替え"""
        devices = await self.spotify.get_devices()
        for d in devices:
            if device_name.lower() in d["name"].lower():
                await self.spotify.transfer_playback(d["id"])
                await ctx.send(f"🔄 再生デバイスを **{d['name']}** に切り替えました。")
                return
        await ctx.send(f"デバイス '{device_name}' が見つかりません。`!device` で一覧を確認してください。")


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
