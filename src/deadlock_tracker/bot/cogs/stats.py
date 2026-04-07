from __future__ import annotations

from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from deadlock_tracker.clients.deadlock_api import DeadlockError
from deadlock_tracker.presentation.cards import render_deadlock_profile_card
from deadlock_tracker.services.player_service import PlayerService


ACCENT_ART_PATH = Path(__file__).resolve().parents[4] / "assets" / "rem.png"


class PlayerSelect(discord.ui.Select):
    def __init__(
        self,
        *,
        cog: "StatsCog",
        requester_id: int,
        action: str,
        players: list,
    ) -> None:
        self.cog = cog
        self.requester_id = requester_id
        self.action = action
        self.players = players
        options = [
            discord.SelectOption(
                label=player.personaname[:100],
                value=str(index),
                description=f"ID {player.account_id}"[:100],
            )
            for index, player in enumerate(players[:5])
        ]
        super().__init__(
            placeholder="Choose the correct Deadlock player",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "Only the person who ran this command can choose a player.",
                ephemeral=True,
            )
            return

        player = self.players[int(self.values[0])]
        if self.action == "profile":
            await self.cog.send_profile(interaction, player)
        else:
            await self.cog.send_recent_matches(interaction, player)
        self.view.stop()


class PlayerChoiceView(discord.ui.View):
    def __init__(self, *, cog: "StatsCog", requester_id: int, action: str, players: list) -> None:
        super().__init__(timeout=60)
        self.add_item(PlayerSelect(cog=cog, requester_id=requester_id, action=action, players=players))

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True


class StatsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.player_service = PlayerService()

    @app_commands.command(name="deadlock-help", description="Show the Deadlock tracker commands.")
    async def help_command(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="Deadlock Tracker",
            description="Public commands for looking up Deadlock profiles, heroes, and recent matches.",
            color=discord.Color.dark_teal(),
        )
        embed.add_field(
            name="Commands",
            value="/deadlock-search, /deadlock-profile, /deadlock-recent",
            inline=False,
        )
        embed.add_field(
            name="Supported Input",
            value="Steam account ID, Steam profile URL, vanity URL, or player name",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="deadlock-search", description="Search for a Deadlock player.")
    async def search_command(self, interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            players = await self.player_service.search_players(query)
        except DeadlockError as error:
            await interaction.followup.send(str(error), ephemeral=True)
            return

        if not players:
            await interaction.followup.send("No Deadlock players found for that search.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Deadlock Player Search",
            description="Use an account ID or run `/deadlock-profile` for a full lookup.",
            color=discord.Color.blurple(),
        )
        for player in players[:5]:
            details = [player.profileurl, f"Account ID: `{player.account_id}`"]
            if player.countrycode:
                details.append(f"Country: `{player.countrycode}`")
            embed.add_field(name=player.personaname, value="\n".join(details), inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="deadlock-profile", description="Show a Deadlock player's profile card.")
    async def profile_command(self, interaction: discord.Interaction, player: str) -> None:
        await interaction.response.defer(thinking=True)
        try:
            resolved = await self.player_service.resolve_player(player)
        except DeadlockError as error:
            await interaction.followup.send(str(error), ephemeral=True)
            return

        if isinstance(resolved, list):
            await interaction.followup.send(
                embed=self._ambiguous_player_embed("profile", player, resolved),
                view=PlayerChoiceView(cog=self, requester_id=interaction.user.id, action="profile", players=resolved),
                ephemeral=True,
            )
            return

        await self.send_profile(interaction, resolved)

    @app_commands.command(name="deadlock-recent", description="Show recent Deadlock matches.")
    async def recent_command(self, interaction: discord.Interaction, player: str) -> None:
        await interaction.response.defer(thinking=True)
        try:
            resolved = await self.player_service.resolve_player(player)
        except DeadlockError as error:
            await interaction.followup.send(str(error), ephemeral=True)
            return

        if isinstance(resolved, list):
            await interaction.followup.send(
                embed=self._ambiguous_player_embed("recent matches", player, resolved),
                view=PlayerChoiceView(cog=self, requester_id=interaction.user.id, action="recent", players=resolved),
                ephemeral=True,
            )
            return

        await self.send_recent_matches(interaction, resolved)

    async def send_profile(self, interaction: discord.Interaction, player) -> None:
        summary = await self.player_service.build_player_summary(player)
        rank_name = self.player_service.rank_name(summary)
        rating_text = f"{(summary.rank.player_score or 0):.2f}" if summary.rank else "0.00"
        card_buffer = await render_deadlock_profile_card(
            player=summary.player,
            rank_name=rank_name,
            internal_rating=rating_text,
            top_heroes=self.player_service.top_heroes(summary.hero_stats, limit=3),
            hero_info=summary.hero_info,
            accent_art_path=ACCENT_ART_PATH,
            cache_updated_ts=summary.player.last_updated,
        )

        embed = discord.Embed(
            title=f"Deadlock Profile: {summary.player.personaname}",
            url=summary.player.profileurl,
            color=discord.Color.dark_gold(),
            description=f"Rank: **{rank_name}**",
        )
        embed.set_image(url="attachment://deadlock-profile.png")
        card_file = discord.File(card_buffer, filename="deadlock-profile.png")
        await interaction.followup.send(embed=embed, file=card_file)

    async def send_recent_matches(self, interaction: discord.Interaction, player) -> None:
        summary = await self.player_service.build_player_summary(player)
        embed = discord.Embed(
            title=f"Recent Deadlock Matches: {summary.player.personaname}",
            url=summary.player.profileurl,
            color=discord.Color.dark_blue(),
        )
        if summary.player.avatarfull:
            embed.set_thumbnail(url=summary.player.avatarfull)

        for match in summary.recent_matches[:5]:
            hero = summary.hero_info.get(match.hero_id)
            hero_name = hero.name if hero else f"Hero {match.hero_id}"
            embed.add_field(
                name=f"{hero_name} - Match `{match.match_id}`",
                value=(
                    f"{self.player_service.match_result_label(match)} | "
                    f"KDA `{self.player_service.format_kda(match.player_kills, match.player_deaths, match.player_assists)}`\n"
                    f"Duration `{self.player_service.format_match_duration(match.match_duration_s)}` | "
                    f"Net Worth `{match.net_worth or 0}` | Last Hits `{match.last_hits or 0}`"
                ),
                inline=False,
            )

        await interaction.followup.send(embed=embed)

    def _ambiguous_player_embed(self, action_name: str, query: str, players: list) -> discord.Embed:
        embed = discord.Embed(
            title="Choose the Right Deadlock Player",
            description=f"Multiple players matched `{query}`. Choose one below to open {action_name}.",
            color=discord.Color.orange(),
        )
        for player in players[:5]:
            embed.add_field(
                name=player.personaname,
                value=f"`{player.account_id}`\n{player.profileurl}",
                inline=False,
            )
        return embed
