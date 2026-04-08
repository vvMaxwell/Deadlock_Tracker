from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import aiohttp

from deadlock_tracker.config import get_settings
from deadlock_tracker.models import (
    DeadlockBadgeDistribution,
    DeadlockHeroAnalytics,
    DeadlockHeroInfo,
    DeadlockItemInfo,
    DeadlockItemStat,
    DeadlockHeroStat,
    DeadlockMatch,
    DeadlockMatchMetadata,
    DeadlockMatchPlayer,
    DeadlockPlayer,
    DeadlockRank,
    DeadlockRankInfo,
    DeadlockSteamProfile,
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
        self._item_info: dict[int, DeadlockItemInfo] = {}
        self._rank_info: list[DeadlockRankInfo] | None = None

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
                last_updated=_parse_last_updated(item.get("last_updated")),
            )
            for item in payload
        ]

    async def get_steam_profile(self, account_id: int) -> DeadlockPlayer | None:
        profiles = await self.get_steam_profiles([account_id])
        profile = profiles.get(account_id)
        if profile is None:
            return None
        return DeadlockPlayer(
            account_id=profile.account_id,
            personaname=profile.personaname,
            profileurl=profile.profileurl,
            avatarfull=profile.avatarfull,
            countrycode=profile.countrycode,
            last_updated=profile.last_updated,
        )

    async def get_steam_profiles(self, account_ids: list[int]) -> dict[int, DeadlockSteamProfile]:
        if not account_ids:
            return {}
        payload = await self._get_json(
            f"{self.base_url}/v1/players/steam",
            params={"account_ids": ",".join(str(account_id) for account_id in account_ids)},
        )
        return {
            item["account_id"]: DeadlockSteamProfile(
                account_id=item["account_id"],
                personaname=item["personaname"],
                profileurl=item["profileurl"],
                avatarfull=item.get("avatarfull"),
                countrycode=item.get("countrycode"),
                last_updated=_parse_last_updated(item.get("last_updated")),
            )
            for item in payload
        }

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

    async def get_match_history(
        self,
        account_id: int,
        *,
        limit: int = 10,
        force_refetch: bool = False,
        only_stored_history: bool = True,
    ) -> list[DeadlockMatch]:
        params: dict[str, str] = {}
        if force_refetch:
            params["force_refetch"] = "true"
        elif only_stored_history:
            params["only_stored_history"] = "true"

        payload = await self._get_json(
            f"{self.base_url}/v1/players/{account_id}/match-history",
            params=params or None,
        )
        return [
            DeadlockMatch(
                match_id=item["match_id"],
                hero_id=item["hero_id"],
                start_time=item["start_time"],
                match_duration_s=item.get("match_duration_s"),
                game_mode=item.get("game_mode"),
                match_mode=item.get("match_mode"),
                player_team=item.get("player_team"),
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
            and not item.get("disabled", False)
            and not item.get("in_development", False)
            and not item.get("needs_testing", False)
            and not item.get("assigned_players_only", False)
            and not item.get("prerelease_only", False)
            and not item.get("limited_testing", False)
        }
        return self._hero_info

    async def get_item_info(self, item_id: int) -> DeadlockItemInfo | None:
        if not self._item_info:
            await self.get_all_item_info()
        if item_id in self._item_info:
            return self._item_info[item_id]

        payload = await self._get_json(f"{self.assets_url}/v2/items/{item_id}")
        item = DeadlockItemInfo(
            item_id=payload["id"],
            name=payload["name"],
            image=payload.get("image"),
            shop_image=payload.get("shop_image"),
            item_slot_type=payload.get("item_slot_type"),
            item_tier=payload.get("item_tier"),
            cost=payload.get("cost"),
            is_active_item=bool(payload.get("is_active_item")),
        )
        self._item_info[item_id] = item
        return item

    async def get_all_item_info(self) -> dict[int, DeadlockItemInfo]:
        if self._item_info:
            return self._item_info

        payload = await self._get_json(f"{self.assets_url}/v2/items")
        self._item_info = {
            item["id"]: DeadlockItemInfo(
                item_id=item["id"],
                name=item["name"],
                image=item.get("image"),
                shop_image=item.get("shop_image"),
                item_slot_type=item.get("item_slot_type"),
                item_tier=item.get("item_tier"),
                cost=item.get("cost"),
                is_active_item=bool(item.get("is_active_item")),
            )
            for item in payload
        }
        return self._item_info

    async def get_rank_info(self) -> list[DeadlockRankInfo]:
        if self._rank_info is not None:
            return self._rank_info

        payload = await self._get_json(f"{self.assets_url}/v2/ranks")
        self._rank_info = [
            DeadlockRankInfo(
                tier=item["tier"],
                name=item["name"],
                color=item.get("color"),
                image_small=(item.get("images") or {}).get("small"),
            )
            for item in payload
        ]
        return self._rank_info

    async def get_item_stats(
        self,
        *,
        hero_id: int | None = None,
        game_mode: str = "normal",
        min_matches: int = 500,
        min_average_badge: int | None = None,
        min_unix_timestamp: int | None = None,
    ) -> list[DeadlockItemStat]:
        params: dict[str, str] = {
            "bucket": "no_bucket",
            "game_mode": game_mode,
            "min_matches": str(min_matches),
        }
        if hero_id is not None:
            params["hero_id"] = str(hero_id)
        if min_average_badge is not None:
            params["min_average_badge"] = str(min_average_badge)
        if min_unix_timestamp is not None:
            params["min_unix_timestamp"] = str(min_unix_timestamp)

        payload = await self._get_json(f"{self.base_url}/v1/analytics/item-stats", params=params)
        return [
            DeadlockItemStat(
                item_id=item["item_id"],
                wins=item["wins"],
                losses=item["losses"],
                matches=item["matches"],
                players=item["players"],
                avg_buy_time_s=item.get("avg_buy_time_s"),
                avg_sell_time_s=item.get("avg_sell_time_s"),
                avg_buy_time_relative=item.get("avg_buy_time_relative"),
                avg_sell_time_relative=item.get("avg_sell_time_relative"),
            )
            for item in payload
        ]

    async def get_hero_analytics(
        self,
        *,
        game_mode: str = "normal",
        min_matches: int = 500,
        min_average_badge: int | None = None,
        min_unix_timestamp: int | None = None,
    ) -> list[DeadlockHeroAnalytics]:
        params: dict[str, str] = {
            "bucket": "no_bucket",
            "game_mode": game_mode,
            "min_matches": str(min_matches),
        }
        if min_average_badge is not None:
            params["min_average_badge"] = str(min_average_badge)
        if min_unix_timestamp is not None:
            params["min_unix_timestamp"] = str(min_unix_timestamp)

        payload = await self._get_json(f"{self.base_url}/v1/analytics/hero-stats", params=params)
        return [
            DeadlockHeroAnalytics(
                hero_id=item["hero_id"],
                wins=item["wins"],
                losses=item["losses"],
                matches=item["matches"],
                players=item["players"],
            )
            for item in payload
            if item.get("hero_id") not in {None, 0}
        ]

    async def get_badge_distribution(self) -> list[DeadlockBadgeDistribution]:
        payload = await self._get_json(f"{self.base_url}/v1/analytics/badge-distribution")
        return [
            DeadlockBadgeDistribution(
                badge_level=item["badge_level"],
                total_matches=item["total_matches"],
            )
            for item in payload
        ]

    async def get_match_metadata(self, match_id: int) -> DeadlockMatchMetadata:
        payload = await self._get_json(f"{self.base_url}/v1/matches/{match_id}/metadata")
        match_info = payload.get("match_info") or {}
        players = [
            DeadlockMatchPlayer(
                account_id=item["account_id"],
                team=item.get("team"),
                hero_id=item["hero_id"],
                kills=item.get("kills"),
                deaths=item.get("deaths"),
                assists=item.get("assists"),
                net_worth=item.get("net_worth"),
                last_hits=item.get("last_hits"),
                denies=item.get("denies"),
                level=item.get("level"),
                assigned_lane=item.get("assigned_lane"),
                mvp_rank=item.get("mvp_rank"),
                player_damage=_final_stat_value(item.get("stats"), "player_damage"),
                objective_damage=_final_stat_value(item.get("stats"), "boss_damage"),
                healing=_final_stat_value(item.get("stats"), "player_healing"),
            )
            for item in match_info.get("players", [])
        ]
        return DeadlockMatchMetadata(
            match_id=match_info.get("match_id", match_id),
            start_time=match_info.get("start_time"),
            duration_s=match_info.get("duration_s"),
            game_mode=match_info.get("game_mode"),
            match_mode=match_info.get("match_mode"),
            winning_team=match_info.get("winning_team"),
            players=players,
        )

    async def _get_json(self, url: str, params: dict[str, str] | None = None) -> Any:
        headers = {"User-Agent": "DeadlockTracker/1.0"}
        timeout = aiohttp.ClientTimeout(total=20)
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(url, params=params) as response:
                    if response.status == 404:
                        raise DeadlockError("No data found for that Deadlock player.")
                    if response.status == 429:
                        if params and params.get("force_refetch") == "true":
                            raise DeadlockError(
                                "Deadlock API force refresh is rate-limited. "
                                "This Steam-backed refetch usually only works about once per hour per IP."
                            )
                        raise DeadlockError("Deadlock API rate limit hit. Try again shortly.")
                    if response.status >= 400:
                        message = await response.text()
                        raise DeadlockError(
                            f"Deadlock API request failed with HTTP {response.status}: {message[:200]}"
                        )
                    return await response.json()
        except TimeoutError:
            raise DeadlockError("Deadlock API took too long to respond. Try again in a moment.") from None
        except aiohttp.ClientError as error:
            raise DeadlockError(f"Deadlock API request failed: {error}") from error


def _parse_last_updated(raw: Any) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    if isinstance(raw, str):
        cleaned = raw.strip()
        if not cleaned:
            return None
        if cleaned.isdigit():
            return int(cleaned)
        try:
            return int(datetime.fromisoformat(cleaned.replace("Z", "+00:00")).timestamp())
        except ValueError:
            return None
    return None


def _final_stat_value(stats: Any, field: str) -> int | None:
    if not isinstance(stats, list) or not stats:
        return None
    latest = stats[-1]
    if not isinstance(latest, dict):
        return None
    value = latest.get(field)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def friendly_rank_name(rank: int | None) -> str:
    if rank is None:
        return "Unknown"
    return RANK_NAME_BY_CODE.get(rank, str(rank))
