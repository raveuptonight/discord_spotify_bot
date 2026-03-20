import asyncio
import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True

class SpotifyHelpCommand(commands.HelpCommand):

    COLOUR = 0x1DB954  # Spotify green

    async def send_bot_help(self, mapping):
        embed = discord.Embed(
            title="コマンド一覧",
            description="Spotify 楽曲を Discord VC で再生するBotです。",
            color=self.COLOUR,
        )

        commands_info = {
            "再生": [
                ("`!play <曲名 / URL>`", "曲を検索して再生"),
                ("`!search <曲名>`", "検索結果を5件表示し、リアクションで選曲"),
                ("`!pause`", "一時停止"),
                ("`!resume`", "再生を再開"),
                ("`!skip` / `!next`", "次の曲へスキップ"),
                ("`!stop`", "再生停止 & VC 退出"),
            ],
            "情報": [
                ("`!np` / `!nowplaying`", "再生中の曲を表示（ジャケ写付き）"),
                ("`!queue` / `!q`", "再生キューを表示"),
                ("`!volume <0-100>`", "ボリューム調整"),
            ],
            "接続": [
                ("`!join`", "ボイスチャンネルに参加"),
                ("`!leave`", "ボイスチャンネルから退出"),
            ],
            "デバイス": [
                ("`!device`", "Spotify デバイス一覧を表示"),
                ("`!setdevice <名前>`", "再生先デバイスを切り替え"),
            ],
        }

        for category, cmds in commands_info.items():
            value = "\n".join(f"{cmd} - {desc}" for cmd, desc in cmds)
            embed.add_field(name=category, value=value, inline=False)

        embed.set_footer(text="!help <コマンド名> で詳細を表示")
        await self.get_destination().send(embed=embed)

    async def send_command_help(self, command):
        embed = discord.Embed(
            title=f"!{command.qualified_name}",
            description=command.help or "説明なし",
            color=self.COLOUR,
        )
        if command.aliases:
            embed.add_field(
                name="エイリアス",
                value=", ".join(f"`!{a}`" for a in command.aliases),
                inline=False,
            )
        usage = command.signature
        if usage:
            embed.add_field(
                name="使い方",
                value=f"`!{command.qualified_name} {usage}`",
                inline=False,
            )
        await self.get_destination().send(embed=embed)

    async def send_error_message(self, error):
        embed = discord.Embed(
            title="エラー", description=error, color=0xFF0000
        )
        await self.get_destination().send(embed=embed)


bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=SpotifyHelpCommand(),
)


@bot.event
async def on_ready():
    logger.info("Bot 起動完了: %s (ID: %s)", bot.user, bot.user.id)


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"引数が不足しています: `{error.param.name}`")
        return
    if isinstance(error, commands.CommandInvokeError):
        original = error.original
        logger.exception("コマンド実行エラー: %s", original)
        await ctx.send(f"エラーが発生しました: {original}")
        return
    logger.exception("未処理エラー: %s", error)
    await ctx.send(f"エラー: {error}")


async def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        logger.error("DISCORD_TOKEN が設定されていません。.env を確認してください。")
        raise SystemExit(1)

    async with bot:
        await bot.load_extension("cogs.music")
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
