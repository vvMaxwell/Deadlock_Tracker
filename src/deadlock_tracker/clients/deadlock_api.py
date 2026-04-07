from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import aiohttp

from deadlock_tracker.config import get_settings
from deadlock_tracker.models import (
    DeadlockHeroInfo,
    DeadlockHeroStat,
    DeadlockMatch,
    DeadlockPlayer,
    DeadlockRank,
)


RANK_NAME_BY_CODE = {
    0: "Obscurus",
    11: "Initiate 1",
    12: "Initiate 2",
    13: "Initiate 3",
    14: "Initiate 4",
    15: "Initiate 5",
    16: "Initiate 6",
    21: "Seeker 1",
    22: "Seeker 2",
    23: "Seeker 3",
    24: "Seeker 4",
    25: "Seeker 5",
    26: "Seeker 6",
    31: "Alchemist 1",
    32: "Alchemist 2",
    33: "Alchemist 3",
    34: "Alchemist 4",
    35: "Alchemist 5",
    36: "Alchemist 6",
    41: "Arcanist 1",
    42: "Arcanist 2",
    43: "Arcanist 3",
    44: "Arcanist 4",
    45: "Arcanist 5",
    46: "Arcanist 6",
    51: "Ritualist 1",
    52: "Ritualist 2",
    53: "Ritualist 3",
    54: "Ritualist 4",
    55: "Ritualist 5",
    56: "Ritualist 6",
    61: "Emissary 1",
    62: "Emissary 2",
    63: "Emissary 3",
    64: "Emissary 4",
    65: "Emissary 5",
    66: "Emissary 6",
    71: "Archon 1",
    72: "Archon 2",
    73: "Archon 3",
    74: "Archon 4",
    75: "Archon 5",
    76: "Archon 6",
    81: "Oracle 1",
    82: "Oracle 2",
    83: "Oracle 3",
    84: "Oracle 4",
    85: "Oracle 5",
    86: "Oracle 6",
    91: "Phantom 1",
    92: "Phantom 2",
    93: "Phantom 3",
    94: "Phantom 4",
    95: "Phantom 5",
    96: "Phantom 6",
    101: "Ascendant 1",
    102: "Ascendant 2",
    103: "Ascendant 3",
    104: "Ascendant 4",
    105: "Ascendant 5",
    106: "Ascendant 6",
    111: "Eternus 1",
    112: "Eternus 2",
    113: "Eternus 3",
    114: "Eternus 4",
    115: "Eternus 5",
    116: "Eternus 6",
}


class DeadlockError(Exception):
    """Raised when the Deadlock API cannot fulfill a request."""


class DeadlockAPI:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.deadlock_api_base_url
        self.assets_url = settings.deadlock_assets_base_url
        self._hero_info: dict[int, DeadlockHeroInfo] | None = None

    async def search_players(self, query: str) -> list[DeadlockPlayer]:
        payload = await self._get_json(
            f"{self.base_url}/v1/players/steam-search",
            params={"search_query": query},
        )
        return [
            DeadlockPlayer(
                account_id=item["account_id"],
                personaname=item["personaname"],
                profileurl=item["profileurl"],
                avatarfull=item.get("avatarfull"),
                countrycode=item.get("countrycode"),
                last_updated=item.get("last_updated"),
            )
            for item in payload
        ]

    async def resolve_player_input(self, raw: str) -> str | int:
        cleaned = raw.strip()
        if cleaned.isdigit():
            return int(cleaned)

        if "steamcommunity.com/" not in cleaned:
            return cleaned

        parsed = urlparse(cleaned)
        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) < 2:
            raise DeadlockError("That Steam profile URL could not be parsed.")

        kind, value = path_parts[0], path_parts[1]
        if kind == "profiles":
            if not value.isdigit():
                raise DeadlockError("That Steam profile URL does not contain a valid Steam64 ID.")
            return int(value) - 76561197960265728

        if kind == "id":
            profiles = await self.search_players(value)
            if not profiles:
                raise DeadlockError("No Steam profile matched that vanity URL.")
            exact = [profile for profile in profiles if profile.personaname.casefold() == value.casefold()]
            if len(exact) == 1:
                return exact[0].account_id
            return value

        raise DeadlockError("Unsupported Steam profile URL format.")

    async def get_player_rank(self, account_id: int) -> DeadlockRank | None:
        payload = await self._get_json(
            f"{self.base_url}/v1/players/mmr",
            params={"account_ids": str(account_id)},
        )
        if not payload:
            return None
        item = payload[0]
        return DeadlockRank(
            account_id=item["account_id"],
            match_id=item.get("match_id"),
            start_time=item.get("start_time"),
            player_score=item.get("player_score"),
            rank=item.get("rank"),
            division=item.get("division"),
            division_tier=item.get("division_tier"),
        )

    async def get_hero_stats(self, account_id: int) -> list[DeadlockHeroStat]:
        payload = await self._get_json(f"{self.base_url}/v1/players/{account_id}/hero-stats")
        stats = [
            DeadlockHeroStat(
                hero_id=item["hero_id"],
                matches_played=item["matches_played"],
                wins=item["wins"],
                kills=item.get("kills"),
                deaths=item.get("deaths"),
                assists=item.get("assists"),
                last_played=item.get("last_played"),
            )
            for item in payload
        ]
        return sorted(stats, key=lambda item: item.matches_played, reverse=True)

    async def get_match_history(self, account_id: int, *, limit: int = 10) -> list[DeadlockMatch]:
        payload = await self._get_json(
            f"{self.base_url}/v1/players/{account_id}/match-history",
            params={"only_stored_history": "true"},
        )
        return [
            DeadlockMatch(
                match_id=item["match_id"],
                hero_id=item["hero_id"],
                start_time=item["start_time"],
                match_duration_s=item.get("match_duration_s"),
                player_kills=item.get("player_kills"),
                player_deaths=item.get("player_deaths"),
                player_assists=item.get("player_assists"),
                net_worth=item.get("net_worth"),
                last_hits=item.get("last_hits"),
                match_result=item.get("match_result"),
            )
            for item in payload[:limit]
        ]

    async def get_hero_info(self) -> dict[int, DeadlockHeroInfo]:
        if self._hero_info is not None:
            return self._hero_info

        payload = await self._get_json(f"{self.assets_url}/v2/heroes")
        self._hero_info = {
            item["id"]: DeadlockHeroInfo(
                hero_id=item["id"],
                name=item["name"],
                icon_small=(item.get("images") or {}).get("icon_image_small"),
            )
            for item in payload
            if item.get("player_selectable", True)
        }
        return self._hero_info

    async def _get_json(self, url: str, params: dict[str, str] | None = None) -> Any:
        headers = {"User-Agent": "DeadlockTracker/1.0"}
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url, params=params) as response:
                if response.status == 404:
                    raise DeadlockError("No data found for that Deadlock player.")
                if response.status == 429:
                    raise DeadlockError("Deadlock API rate limit hit. Try again shortly.")
                if response.status >= 400:
                    message = await response.text()
                    raise DeadlockError(
                        f"Deadlock API request failed with HTTP {response.status}: {message[:200]}"
                    )
                return await response.json()


def friendly_rank_name(rank: int | None) -> str:
    if rank is None:
        return "Unknown"
    return RANK_NAME_BY_CODE.get(rank, str(rank))
