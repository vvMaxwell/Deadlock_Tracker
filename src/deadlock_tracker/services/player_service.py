from __future__ import annotations

from collections import defaultdict

from deadlock_tracker.clients.deadlock_api import (
    _account_id,
    PLAYER_MATCH_OUTCOME_NAME_BY_CODE,
    PLAYER_MATCH_OUTCOME_WIN,
    DeadlockAPI,
    DeadlockError,
    friendly_rank_name,
)
from deadlock_tracker.models import DeadlockHeroStat, DeadlockMatch, DeadlockPlayer, PlayerSummary


class PlayerService:
    def __init__(self, api: DeadlockAPI | None = None) -> None:
        self.api = api or DeadlockAPI()

    async def search_players(self, query: str) -> list[DeadlockPlayer]:
        cleaned = query.strip()
        if not cleaned:
            return []
        if cleaned.isdigit():
            profile = await self.api.get_steam_profile(_account_id(int(cleaned)))
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
        notices: list[str] = []
        try:
            hero_info = await self.api.get_hero_info()
        except DeadlockError:
            hero_info = {}
            notices.append("Hero images and names are temporarily unavailable.")
        effective_player = player

        if refresh_matches:
            try:
                steam_profile = await self.api.get_steam_profile(player.account_id)
            except DeadlockError:
                steam_profile = None
            if steam_profile is not None:
                effective_player = steam_profile
            match_history = await self.api.get_match_history(
                player.account_id,
                limit=50,
                force_refetch=True,
            )
        else:
            try:
                match_history = await self.api.get_match_history(player.account_id, limit=50)
            except DeadlockError:
                match_history = []
                notices.append("Recent match history is temporarily unavailable. Tracked hero totals may still be available.")

        # Rank must be read after a refresh, which can ingest newer ranked matches.
        try:
            rank = await self.api.get_player_rank(player.account_id)
        except DeadlockError:
            rank = None
            notices.append("Current rank is temporarily unavailable; showing a match badge when available.")

        hero_stats_scope = "Tracked Matches"
        try:
            hero_stats = await self.api.get_hero_stats(player.account_id)
        except DeadlockError:
            hero_stats = self.hero_stats_from_matches(match_history)
            hero_stats_scope = "Recent Matches"
            notices.append("Hero totals are temporarily unavailable. Showing only the loaded recent matches.")
        recent_matches = match_history[:10]
        return PlayerSummary(
            player=effective_player,
            rank=rank,
            hero_stats=hero_stats,
            recent_matches=recent_matches,
            hero_info=hero_info,
            ranked_match=self.latest_ranked_match(match_history),
            hero_stats_scope=hero_stats_scope,
            notices=notices,
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
        # player_match_outcome is how the game scored the match for this player,
        # so it beats comparing the team against the winning team.
        if match.player_match_outcome is not None:
            if match.player_match_outcome == PLAYER_MATCH_OUTCOME_WIN:
                return True
            if match.player_match_outcome in PLAYER_MATCH_OUTCOME_NAME_BY_CODE:
                return False
        if match.player_team is not None and match.match_result is not None:
            return match.player_team == match.match_result
        return False

    @staticmethod
    def match_result_label(match: DeadlockMatch) -> str:
        label = PLAYER_MATCH_OUTCOME_NAME_BY_CODE.get(match.player_match_outcome)
        if label is not None:
            return label
        if match.player_team in {0, 1} and match.match_result in {0, 1}:
            return "Win" if PlayerService.is_match_win(match) else "Loss"
        return "Unknown"

    @staticmethod
    def latest_ranked_match(matches: list[DeadlockMatch]) -> DeadlockMatch | None:
        """Most recent match the game attached a ranked badge to. This is real
        rank data, unlike the MMR estimate, so profiles prefer it."""
        ranked = [match for match in matches if match.ranked_display_badge]
        if not ranked:
            return None
        return max(ranked, key=lambda match: match.start_time)

    @staticmethod
    def format_kda(kills: float | int | None, deaths: float | int | None, assists: float | int | None) -> str:
        return "/".join("—" if value is None else str(int(value)) for value in (kills, deaths, assists))

    @staticmethod
    def format_match_duration(seconds: int | None) -> str:
        if not seconds:
            return "Unknown"
        minutes, secs = divmod(int(seconds), 60)
        return f"{minutes}:{secs:02d}"

    @staticmethod
    def displayed_rank(player_summary: PlayerSummary) -> int | None:
        """The badge shown on a profile. The rank endpoint reports the badge
        Valve attached to the account's latest ranked match anywhere in the
        API's match database, so it beats the badge on the match history the
        profile happens to have loaded; that badge is the fallback."""
        if player_summary.rank is not None and player_summary.rank.badge:
            return player_summary.rank.badge
        if player_summary.ranked_match is not None:
            return player_summary.ranked_match.ranked_display_badge
        return None

    @staticmethod
    def rank_name(player_summary: PlayerSummary) -> str:
        return friendly_rank_name(PlayerService.displayed_rank(player_summary))

    @staticmethod
    def rank_detail_text(player_summary: PlayerSummary) -> str:
        """One line about how the badge last moved, in place of the retired MMR
        score. Rank progress is a running total across the whole ladder rather
        than a position inside the sub-rank, so the change the match awarded is
        what gets shown."""
        rank = player_summary.rank
        if rank is None or rank.match_id is None:
            return "No ranked match on record"
        if rank.calibration_games_remaining:
            games = rank.calibration_games_remaining
            return f"Placement: {games} game{'s' if games != 1 else ''} left"
        if rank.progress_change is None:
            return "Last Ranked Match: Unknown"
        return f"Last Ranked Match: {rank.progress_change:+,} progress"

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
