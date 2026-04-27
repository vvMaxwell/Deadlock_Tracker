from __future__ import annotations

from collections import defaultdict

from deadlock_tracker.clients.deadlock_api import DeadlockAPI, DeadlockError, friendly_rank_name
from deadlock_tracker.models import DeadlockHeroStat, DeadlockMatch, DeadlockPlayer, PlayerSummary


class PlayerService:
    def __init__(self, api: DeadlockAPI | None = None) -> None:
        self.api = api or DeadlockAPI()

    async def search_players(self, query: str) -> list[DeadlockPlayer]:
        cleaned = query.strip()
        if not cleaned:
            return []
        if cleaned.isdigit():
            profile = await self.api.get_steam_profile(int(cleaned))
            return [profile] if profile is not None else []
        return await self.api.search_players(cleaned)

    async def resolve_player(self, raw_input: str) -> DeadlockPlayer | list[DeadlockPlayer]:
        resolved = await self.api.resolve_player_input(raw_input)
        cleaned = str(resolved).strip()

        if cleaned.isdigit():
            account_id = int(cleaned)
            steam_profile = await self.api.get_steam_profile(account_id)
            if steam_profile is not None:
                return steam_profile
            return DeadlockPlayer(
                account_id=account_id,
                personaname=cleaned,
                profileurl=f"https://steamcommunity.com/profiles/{account_id + 76561197960265728}",
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

    async def build_player_summary(self, player: DeadlockPlayer, *, refresh_matches: bool = False) -> PlayerSummary:
        hero_info = await self.api.get_hero_info()
        rank = await self.api.get_player_rank(player.account_id)
        effective_player = player

        if refresh_matches:
            steam_profile = await self.api.get_steam_profile(player.account_id)
            if steam_profile is not None:
                effective_player = steam_profile
            match_history = await self.api.get_match_history(
                player.account_id,
                limit=50,
                force_refetch=True,
                only_stored_history=False,
            )
        else:
            match_history = await self.api.get_match_history(player.account_id, limit=50)

        hero_stats = self.hero_stats_from_matches(match_history)
        recent_matches = match_history[:10]
        return PlayerSummary(
            player=effective_player,
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
    def is_match_win(match: DeadlockMatch) -> bool:
        if match.player_team is not None and match.match_result is not None:
            return match.player_team == match.match_result
        return False

    @staticmethod
    def match_result_label(match: DeadlockMatch) -> str:
        return "Win" if PlayerService.is_match_win(match) else "Loss"

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

    @staticmethod
    def hero_stats_from_matches(matches: list[DeadlockMatch]) -> list[DeadlockHeroStat]:
        by_hero: dict[int, dict[str, int]] = defaultdict(
            lambda: {
                "matches_played": 0,
                "wins": 0,
                "kills": 0,
                "deaths": 0,
                "assists": 0,
                "last_played": 0,
            }
        )

        for match in matches:
            bucket = by_hero[match.hero_id]
            bucket["matches_played"] += 1
            bucket["wins"] += 1 if PlayerService.is_match_win(match) else 0
            bucket["kills"] += match.player_kills or 0
            bucket["deaths"] += match.player_deaths or 0
            bucket["assists"] += match.player_assists or 0
            bucket["last_played"] = max(bucket["last_played"], match.start_time)

        hero_stats = [
            DeadlockHeroStat(
                hero_id=hero_id,
                matches_played=values["matches_played"],
                wins=values["wins"],
                kills=values["kills"],
                deaths=values["deaths"],
                assists=values["assists"],
                last_played=values["last_played"] or None,
            )
            for hero_id, values in by_hero.items()
        ]
        return sorted(hero_stats, key=lambda item: item.matches_played, reverse=True)
