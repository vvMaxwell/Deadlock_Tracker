from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.errors import HTTPException, NotFound
from discord.ext import commands

from deadlock_tracker.bot.cogs.stats import StatsCog
from deadlock_tracker.config import get_settings


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


class DeadlockTrackerBot(commands.Bot):
    def __init__(self) -> None:
        self.settings = get_settings()
        intents = discord.Intents.default()
        intents.guilds = True
        super().__init__(command_prefix="!", intents=intents, help_command=None)

    async def setup_hook(self) -> None:
        await self.add_cog(StatsCog(self))

        if self.settings.discord_guild_id:
            guild = discord.Object(id=self.settings.discord_guild_id)
            self.tree.clear_commands(guild=guild)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logging.info("Synced slash commands to guild %s", self.settings.discord_guild_id)
        else:
            await self.tree.sync()
            logging.info("Synced global slash commands")

    async def on_ready(self) -> None:
        if self.user is not None:
            logging.info("Logged in as %s (%s)", self.user, self.user.id)


def build_bot() -> DeadlockTrackerBot:
    bot = DeadlockTrackerBot()

    @bot.tree.error
    async def on_app_command_error(
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        original_error = getattr(error, "original", error)
        responder = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message

        if isinstance(error, app_commands.CommandOnCooldown):
            await responder(
                f"That command is cooling down. Try again in {error.retry_after:.1f}s.",
                ephemeral=True,
            )
            return

        if isinstance(error, app_commands.MissingPermissions):
            await responder("You do not have permission to use that command.", ephemeral=True)
            return

        if isinstance(original_error, (NotFound, HTTPException)):
            logging.warning("Interaction expired before a response could be sent.")
            return

        logging.exception("App command failed", exc_info=error)
        await responder("Something went wrong while running that command.", ephemeral=True)

    return bot


def main() -> None:
    bot = build_bot()
    if not bot.settings.discord_token:
        raise RuntimeError("Missing DISCORD_TOKEN. Add it to your environment or .env file.")
    bot.run(bot.settings.discord_token, log_handler=None)
