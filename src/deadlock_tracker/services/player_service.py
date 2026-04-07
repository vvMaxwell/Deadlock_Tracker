from __future__ import annotations

from deadlock_tracker.clients.deadlock_api import DeadlockAPI, DeadlockError, friendly_rank_name
from deadlock_tracker.models import DeadlockHeroStat, DeadlockMatch, DeadlockPlayer, PlayerSummary


class PlayerService:
    def __init__(self, api: DeadlockAPI | None = None) -> None:
        self.api = api or DeadlockAPI()

    async def search_players(self, query: str) -> list[DeadlockPlayer]:
        return await self.api.search_players(query.strip())

    async def resolve_player(self, raw_input: str) -> DeadlockPlayer | list[DeadlockPlayer]:
        resolved = await self.api.resolve_player_input(raw_input)
        cleaned = str(resolved).strip()

        if cleaned.isdigit():
            account_id = int(cleaned)
            profiles = await self.api.search_players(cleaned)
            for profile in profiles:
                if profile.account_id == account_id:
                    return profile
            return DeadlockPlayer(
                account_id=account_id,
                personaname=cleaned,
                profileurl=f"https://steamcommunity.com/profiles/{cleaned}",
                avatarfull=None,
                countrycode=None,
                last_updated=None,
            )

        profiles = await self.api.search_players(cleaned)
        if not profiles:
            raise DeadlockError("No Deadlock player matched that search.")

        exact_matches = [
            profile for profile in profiles if profile.personaname.casefold() == cleaned.casefold()
        ]
        if len(exact_matches) == 1:
            return exact_matches[0]
        if len(profiles) == 1:
            return profiles[0]
        return profiles[:5]

    async def build_player_summary(self, player: DeadlockPlayer) -> PlayerSummary:
        hero_info = await self.api.get_hero_info()
        rank = await self.api.get_player_rank(player.account_id)
        hero_stats = await self.api.get_hero_stats(player.account_id)
        recent_matches = await self.api.get_match_history(player.account_id, limit=8)
        return PlayerSummary(
            player=player,
            rank=rank,
            hero_stats=hero_stats,
            recent_matches=recent_matches,
            hero_info=hero_info,
        )

    @staticmethod
    def top_heroes(hero_stats: list[DeadlockHeroStat], *, limit: int = 3) -> list[DeadlockHeroStat]:
        return hero_stats[:limit]

    @staticmethod
    def win_rate(stat: DeadlockHeroStat) -> float:
        if stat.matches_played == 0:
            return 0.0
        return stat.wins / stat.matches_played

    @staticmethod
    def match_result_label(match: DeadlockMatch) -> str:
        return "Win" if match.match_result == 1 else "Loss"

    @staticmethod
    def format_kda(kills: float | int | None, deaths: float | int | None, assists: float | int | None) -> str:
        return f"{int(kills or 0)}/{int(deaths or 0)}/{int(assists or 0)}"

    @staticmethod
    def format_match_duration(seconds: int | None) -> str:
        if not seconds:
            return "Unknown"
        minutes, secs = divmod(int(seconds), 60)
        return f"{minutes}:{secs:02d}"

    @staticmethod
    def rank_name(player_summary: PlayerSummary) -> str:
        return friendly_rank_name(player_summary.rank.rank) if player_summary.rank else "Unknown"
