from __future__ import annotations

import json
import logging
from datetime import datetime
from html.parser import HTMLParser
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import aiohttp

from deadlock_tracker.config import get_settings
from deadlock_tracker.models import (
    DeadlockAbilityOrderStat,
    DeadlockBadgeDistribution,
    DeadlockHeroAnalytics,
    DeadlockHeroCounterStat,
    DeadlockBuild,
    DeadlockBuildCategory,
    DeadlockBuildMod,
    DeadlockHeroInfo,
    DeadlockHeroBuild,
    DeadlockHeroBuildStat,
    DeadlockLeaderboardEntry,
    DeadlockHeroSynergyStat,
    DeadlockItemInfo,
    DeadlockItemStat,
    DeadlockHeroStat,
    DeadlockMatch,
    DeadlockMatchItem,
    DeadlockMatchMetadata,
    DeadlockMatchPlayer,
    DeadlockPlayer,
    DeadlockPatch,
    DeadlockPlayerRankDistribution,
    DeadlockRank,
    DeadlockRankInfo,
    DeadlockSteamProfile,
)


API_ERROR_LOGGER_NAME = "deadlock_tracker.api_errors"
API_ERROR_LOG_PATH = Path("logs") / "deadlock_api_errors.log"


def _api_error_logger() -> logging.Logger:
    logger = logging.getLogger(API_ERROR_LOGGER_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.WARNING)
    logger.propagate = False
    API_ERROR_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        API_ERROR_LOG_PATH,
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )
    logger.addHandler(handler)
    return logger


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
        self.api_key = settings.deadlock_api_key
        self._hero_info: dict[int, DeadlockHeroInfo] | None = None
        self._item_info: dict[int, DeadlockItemInfo] = {}
        self._rank_info: list[DeadlockRankInfo] | None = None

    async def search_players(self, query: str) -> list[DeadlockPlayer]:
        try:
            payload = await self._get_json(
                f"{self.base_url}/v1/players/steam-search",
                params={"search_query": query},
            )
        except DeadlockError as primary_error:
            fallback_players = await self._search_tracklock_profiles(query)
            if not fallback_players:
                fallback_players = await self._search_statlocker_profiles(query)
            if fallback_players:
                return fallback_players
            raise primary_error
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

    async def _search_tracklock_profiles(self, query: str) -> list[DeadlockPlayer]:
        url = f"https://tracklock.gg/api/search/suggestions?q={quote(query.strip())}"
        timeout = aiohttp.ClientTimeout(total=10)
        headers = {"Accept": "application/json", "User-Agent": "DeadlockStatsTracker/1.0"}
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(url) as response:
                    if response.status >= 400:
                        return []
                    payload = await response.json()
        except (TimeoutError, aiohttp.ClientError, ValueError):
            return []
        return _parse_tracklock_profiles(payload)

    async def _search_statlocker_profiles(self, query: str) -> list[DeadlockPlayer]:
        url = f"https://statlocker.gg/api/profile/search-profiles/{quote(query.strip())}"
        timeout = aiohttp.ClientTimeout(total=10)
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://statlocker.gg/",
            "User-Agent": "Mozilla/5.0 DeadlockStatsTracker/1.0",
        }
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(url) as response:
                    if response.status >= 400:
                        return []
                    payload = await response.json()
        except (TimeoutError, aiohttp.ClientError, ValueError):
            return []
        return _parse_statlocker_profiles(payload)

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
        only_stored_history: bool = False,
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
                icon_small=(item.get("images") or {}).get("icon_image_small_webp") or (item.get("images") or {}).get("icon_image_small"),
                portrait_url=(item.get("images") or {}).get("top_bar_vertical_image_webp") or (item.get("images") or {}).get("top_bar_vertical_image"),
                background_image_url=(item.get("images") or {}).get("background_image_webp") or (item.get("images") or {}).get("background_image"),
                signature_ability_class_names=[
                    class_name
                    for class_name in [
                        (item.get("items") or {}).get("signature1"),
                        (item.get("items") or {}).get("signature2"),
                        (item.get("items") or {}).get("signature3"),
                        (item.get("items") or {}).get("signature4"),
                    ]
                    if class_name
                ],
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
            class_name=payload["class_name"],
            name=payload["name"],
            image=payload.get("image"),
            shop_image=payload.get("shop_image"),
            item_slot_type=payload.get("item_slot_type"),
            item_tier=payload.get("item_tier"),
            cost=payload.get("cost"),
            is_active_item=bool(payload.get("is_active_item")),
            item_type=payload.get("type"),
            ability_type=payload.get("ability_type"),
            hero_id=payload.get("hero"),
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
                class_name=item["class_name"],
                name=item["name"],
                image=item.get("image"),
                shop_image=item.get("shop_image"),
                item_slot_type=item.get("item_slot_type"),
                item_tier=item.get("item_tier"),
                cost=item.get("cost"),
                is_active_item=bool(item.get("is_active_item")),
                item_type=item.get("type"),
                ability_type=item.get("ability_type"),
                hero_id=item.get("hero"),
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
                image_small_by_division={
                    division: image_url
                    for division in range(1, 7)
                    if (image_url := (
                        (item.get("images") or {}).get(f"small_subrank{division}_webp")
                        or (item.get("images") or {}).get(f"small_subrank{division}")
                    ))
                },
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

    async def get_hero_counter_stats(
        self,
        *,
        hero_id: int,
        game_mode: str = "normal",
        min_matches: int = 200,
        min_unix_timestamp: int | None = None,
    ) -> list[DeadlockHeroCounterStat]:
        params: dict[str, str] = {
            "hero_id": str(hero_id),
            "game_mode": game_mode,
            "min_matches": str(min_matches),
        }
        if min_unix_timestamp is not None:
            params["min_unix_timestamp"] = str(min_unix_timestamp)

        payload = await self._get_json(f"{self.base_url}/v1/analytics/hero-counter-stats", params=params)
        return [
            DeadlockHeroCounterStat(
                hero_id=item["hero_id"],
                enemy_hero_id=item["enemy_hero_id"],
                wins=item["wins"],
                matches_played=item["matches_played"],
                kills=item["kills"],
                enemy_kills=item["enemy_kills"],
                deaths=item["deaths"],
                enemy_deaths=item["enemy_deaths"],
                assists=item["assists"],
                enemy_assists=item["enemy_assists"],
                denies=item["denies"],
                enemy_denies=item["enemy_denies"],
                last_hits=item["last_hits"],
                enemy_last_hits=item["enemy_last_hits"],
                networth=item["networth"],
                enemy_networth=item["enemy_networth"],
                obj_damage=item["obj_damage"],
                enemy_obj_damage=item["enemy_obj_damage"],
                creeps=item["creeps"],
                enemy_creeps=item["enemy_creeps"],
            )
            for item in payload
        ]

    async def get_hero_synergy_stats(
        self,
        *,
        hero_id: int,
        game_mode: str = "normal",
        min_matches: int = 200,
        min_unix_timestamp: int | None = None,
    ) -> list[DeadlockHeroSynergyStat]:
        params: dict[str, str] = {
            "hero_ids": str(hero_id),
            "game_mode": game_mode,
            "min_matches": str(min_matches),
        }
        if min_unix_timestamp is not None:
            params["min_unix_timestamp"] = str(min_unix_timestamp)

        payload = await self._get_json(f"{self.base_url}/v1/analytics/hero-synergy-stats", params=params)
        return [
            DeadlockHeroSynergyStat(
                hero_id1=item["hero_id1"],
                hero_id2=item["hero_id2"],
                wins=item["wins"],
                matches_played=item["matches_played"],
                kills1=item["kills1"],
                kills2=item["kills2"],
                deaths1=item["deaths1"],
                deaths2=item["deaths2"],
                assists1=item["assists1"],
                assists2=item["assists2"],
                denies1=item["denies1"],
                denies2=item["denies2"],
                last_hits1=item["last_hits1"],
                last_hits2=item["last_hits2"],
                networth1=item["networth1"],
                networth2=item["networth2"],
                obj_damage1=item["obj_damage1"],
                obj_damage2=item["obj_damage2"],
                creeps1=item["creeps1"],
                creeps2=item["creeps2"],
            )
            for item in payload
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

    async def get_player_rank_distribution(self) -> list[DeadlockPlayerRankDistribution]:
        payload = await self._get_json(f"{self.base_url}/v1/players/mmr/distribution")
        return [
            DeadlockPlayerRankDistribution(
                rank=item["rank"],
                players=item["players"],
            )
            for item in payload
            if item.get("rank") is not None and item.get("players") is not None
        ]

    async def get_hero_rank_distribution(self, hero_id: int) -> list[DeadlockPlayerRankDistribution]:
        payload = await self._get_json(f"{self.base_url}/v1/players/mmr/distribution/{hero_id}")
        return [
            DeadlockPlayerRankDistribution(
                rank=item["rank"],
                players=item["players"],
            )
            for item in payload
            if item.get("rank") is not None and item.get("players") is not None
        ]

    async def search_builds(
        self,
        *,
        hero_id: int | None = None,
        limit: int = 12,
        sort_by: str = "weekly_favorites",
        sort_direction: str = "desc",
        only_latest: bool = True,
        min_unix_timestamp: int | None = None,
    ) -> list[DeadlockBuild]:
        params: dict[str, str] = {
            "limit": str(limit),
            "sort_by": sort_by,
            "sort_direction": sort_direction,
        }
        if hero_id is not None:
            params["hero_id"] = str(hero_id)
        if only_latest:
            params["only_latest"] = "true"
        if min_unix_timestamp is not None:
            params["min_unix_timestamp"] = str(min_unix_timestamp)

        payload = await self._get_json(f"{self.base_url}/v1/builds", params=params)
        return [
            DeadlockBuild(
                hero_build=_parse_build_hero(item.get("hero_build") or {}),
                num_favorites=item.get("num_favorites"),
                num_ignores=item.get("num_ignores"),
                num_reports=item.get("num_reports"),
                num_weekly_favorites=item.get("num_weekly_favorites"),
                rollup_category=item.get("rollup_category"),
            )
            for item in payload
            if isinstance(item, dict) and isinstance(item.get("hero_build"), dict)
        ]

    async def get_hero_build_stats(
        self,
        *,
        hero_id: int,
        min_matches: int = 20,
        min_unix_timestamp: int | None = None,
    ) -> list[DeadlockHeroBuildStat]:
        params: dict[str, str] = {
            "min_matches": str(min_matches),
        }
        if min_unix_timestamp is not None:
            params["min_unix_timestamp"] = str(min_unix_timestamp)

        payload = await self._get_json(f"{self.base_url}/v1/analytics/hero-build-stats/{hero_id}", params=params)
        return [
            DeadlockHeroBuildStat(
                hero_id=item["hero_id"],
                hero_build_id=item["hero_build_id"],
                wins=item["wins"],
                losses=item["losses"],
                matches=item["matches"],
                players=item["players"],
            )
            for item in payload
            if item.get("hero_build_id") is not None
        ]

    async def get_leaderboard(
        self,
        *,
        region: str,
        hero_id: int | None = None,
    ) -> list[DeadlockLeaderboardEntry]:
        path = (
            f"{self.base_url}/v1/leaderboard/{region}/{hero_id}"
            if hero_id is not None
            else f"{self.base_url}/v1/leaderboard/{region}"
        )
        payload = await self._get_json(path)
        entries = payload.get("entries") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            return []
        return [
            DeadlockLeaderboardEntry(
                account_name=item.get("account_name"),
                badge_level=item.get("badge_level"),
                rank=item.get("rank"),
                ranked_rank=item.get("ranked_rank"),
                ranked_subrank=item.get("ranked_subrank"),
                possible_account_ids=[
                    int(account_id)
                    for account_id in (item.get("possible_account_ids") or [])
                    if isinstance(account_id, int)
                ],
                top_hero_ids=[
                    int(hero_id_value)
                    for hero_id_value in (item.get("top_hero_ids") or [])
                    if isinstance(hero_id_value, int)
                ],
            )
            for item in entries
            if isinstance(item, dict)
        ]

    async def get_ability_order_stats(
        self,
        *,
        hero_id: int,
        game_mode: str = "normal",
        min_matches: int = 20,
        min_average_badge: int | None = None,
        min_unix_timestamp: int | None = None,
    ) -> list[DeadlockAbilityOrderStat]:
        params: dict[str, str] = {
            "hero_id": str(hero_id),
            "game_mode": game_mode,
            "min_matches": str(min_matches),
        }
        if min_average_badge is not None:
            params["min_average_badge"] = str(min_average_badge)
        if min_unix_timestamp is not None:
            params["min_unix_timestamp"] = str(min_unix_timestamp)

        payload = await self._get_json(f"{self.base_url}/v1/analytics/ability-order-stats", params=params)
        return [
            DeadlockAbilityOrderStat(
                abilities=item["abilities"],
                wins=item["wins"],
                losses=item["losses"],
                matches=item["matches"],
                players=item["players"],
            )
            for item in payload
            if item.get("abilities")
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
                items=[
                    DeadlockMatchItem(
                        item_id=entry["item_id"],
                        game_time_s=entry.get("game_time_s"),
                        sold_time_s=entry.get("sold_time_s"),
                    )
                    for entry in item.get("items", [])
                    if entry.get("item_id") is not None
                ],
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
            average_badge_team0=match_info.get("average_badge_team0"),
            average_badge_team1=match_info.get("average_badge_team1"),
        )

    async def get_patches(self, *, limit: int = 12) -> list[DeadlockPatch]:
        payload = await self._get_json(f"{self.base_url}/v1/patches")
        patches = [
            DeadlockPatch(
                title=item["title"],
                pub_date=item["pub_date"],
                link=item["link"],
                guid=(item.get("guid") or {}).get("text", ""),
                author=item.get("author", ""),
                category=(item.get("category") or {}).get("text", ""),
                creator=item.get("dc_creator", ""),
                content_html=item.get("content_encoded", ""),
            )
            for item in payload
            if item.get("title") and item.get("link")
        ]
        return patches[:limit]

    async def get_patch_full_content_html(self, url: str) -> str | None:
        try:
            html = await self._get_text(url)
        except DeadlockError:
            return None

        extractor = _ForumPostContentExtractor()
        extractor.feed(html)
        return extractor.content_html()

    async def _get_json(self, url: str, params: dict[str, str] | None = None) -> Any:
        headers = self._request_headers()
        timeout = aiohttp.ClientTimeout(total=20)
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(url, params=params) as response:
                    if response.status == 404:
                        _log_api_error(
                            "deadlock_json",
                            url=url,
                            params=params,
                            status=response.status,
                            body=await response.text(),
                        )
                        raise DeadlockError("No data found for that Deadlock player.")
                    if response.status in {401, 403}:
                        _log_api_error(
                            "deadlock_json",
                            url=url,
                            params=params,
                            status=response.status,
                            body=await response.text(),
                        )
                        raise DeadlockError(
                            "Deadlock API rejected this request. Configure DEADLOCK_API_KEY for protected endpoints."
                        )
                    if response.status == 429:
                        body = await response.text()
                        fallback_payload = _match_history_rate_limit_fallback(
                            url,
                            params=params,
                            body=body,
                        )
                        if fallback_payload is not None:
                            _log_api_error(
                                "deadlock_json_match_history_rate_limit_fallback",
                                url=url,
                                params=params,
                                status=response.status,
                                body=body,
                            )
                            return fallback_payload
                        if params and params.get("force_refetch") == "true":
                            _log_api_error(
                                "deadlock_json",
                                url=url,
                                params=params,
                                status=response.status,
                                body=body,
                            )
                            raise DeadlockError(
                                "Deadlock API force refresh is rate-limited. "
                                "This Steam-backed refetch usually only works about once per hour per IP."
                            )
                        _log_api_error(
                            "deadlock_json",
                            url=url,
                            params=params,
                            status=response.status,
                            body=body,
                        )
                        raise DeadlockError("Deadlock API rate limit hit. Try again shortly.")
                    if response.status >= 400:
                        message = await response.text()
                        _log_api_error(
                            "deadlock_json",
                            url=url,
                            params=params,
                            status=response.status,
                            body=message,
                        )
                        raise DeadlockError(_deadlock_http_error_message(response.status, message))
                    return await response.json()
        except TimeoutError:
            _log_api_error("deadlock_json_timeout", url=url, params=params)
            raise DeadlockError("Deadlock API took too long to respond. Try again in a moment.") from None
        except aiohttp.ClientError as error:
            _log_api_error("deadlock_json_client_error", url=url, params=params, error=error)
            raise DeadlockError(f"Deadlock API request failed: {error}") from error

    async def _get_text(self, url: str, params: dict[str, str] | None = None) -> str:
        headers = self._request_headers()
        timeout = aiohttp.ClientTimeout(total=20)
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(url, params=params) as response:
                    if response.status == 404:
                        _log_api_error(
                            "official_patch_text",
                            url=url,
                            params=params,
                            status=response.status,
                            body=await response.text(),
                        )
                        raise DeadlockError("That official patch post could not be found.")
                    if response.status == 429:
                        _log_api_error(
                            "official_patch_text",
                            url=url,
                            params=params,
                            status=response.status,
                            body=await response.text(),
                        )
                        raise DeadlockError("Official patch post is rate-limited right now. Try again shortly.")
                    if response.status >= 400:
                        message = await response.text()
                        _log_api_error(
                            "official_patch_text",
                            url=url,
                            params=params,
                            status=response.status,
                            body=message,
                        )
                        raise DeadlockError(
                            f"Official patch post request failed with HTTP {response.status}: {message[:200]}"
                        )
                    return await response.text()
        except TimeoutError:
            _log_api_error("official_patch_text_timeout", url=url, params=params)
            raise DeadlockError("Official patch post took too long to respond. Try again in a moment.") from None
        except aiohttp.ClientError as error:
            _log_api_error("official_patch_text_client_error", url=url, params=params, error=error)
            raise DeadlockError(f"Official patch post request failed: {error}") from error

    def _request_headers(self) -> dict[str, str]:
        headers = {"User-Agent": "DeadlockTracker/1.0"}
        if self.api_key:
            headers["X-API-KEY"] = self.api_key
        return headers


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


def _log_api_error(
    source: str,
    *,
    url: str,
    params: dict[str, str] | None = None,
    status: int | None = None,
    body: str | None = None,
    error: BaseException | None = None,
) -> None:
    _api_error_logger().warning(
        "%s url=%s status=%s params=%s error=%s body=%s",
        source,
        _sanitize_url(url),
        status,
        _sanitize_params(params),
        repr(error) if error else None,
        _sanitize_body(body),
    )


def _sanitize_params(params: dict[str, str] | None) -> dict[str, str] | None:
    if not params:
        return None
    redacted_keys = {"api_key", "key", "token", "x-api-key", "authorization"}
    return {
        key: "[redacted]" if key.casefold() in redacted_keys else value
        for key, value in params.items()
    }


def _sanitize_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.query:
        return url
    return url.replace(parsed.query, "[query-redacted]")


def _sanitize_body(body: str | None) -> str | None:
    if body is None:
        return None
    return " ".join(body.split())[:500]


def _match_history_rate_limit_fallback(
    url: str,
    *,
    params: dict[str, str] | None,
    body: str,
) -> Any | None:
    if "/match-history" not in url or (params or {}).get("force_refetch") == "true":
        return None

    try:
        payload = json.loads(body)
    except ValueError:
        return None

    return payload if isinstance(payload, list) else None


def _parse_statlocker_profiles(payload: Any) -> list[DeadlockPlayer]:
    if not isinstance(payload, list):
        return []

    players: list[DeadlockPlayer] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        account_id = item.get("accountId")
        name = item.get("name")
        if not isinstance(account_id, int) or not isinstance(name, str) or not name.strip():
            continue
        players.append(
            DeadlockPlayer(
                account_id=account_id,
                personaname=name,
                profileurl=f"https://steamcommunity.com/profiles/{account_id + 76561197960265728}",
                avatarfull=item.get("avatarUrl") if isinstance(item.get("avatarUrl"), str) else None,
                countrycode=None,
                last_updated=_parse_last_updated(item.get("lastUpdated")),
            )
        )
    return players


def _parse_tracklock_profiles(payload: Any) -> list[DeadlockPlayer]:
    if not isinstance(payload, dict):
        return []
    raw_players = payload.get("players")
    if not isinstance(raw_players, list):
        return []

    players: list[DeadlockPlayer] = []
    for item in raw_players:
        if not isinstance(item, dict):
            continue
        try:
            account_id = int(item.get("account_id"))
        except (TypeError, ValueError):
            continue
        name = item.get("personaname")
        if not isinstance(name, str) or not name.strip():
            continue
        players.append(
            DeadlockPlayer(
                account_id=account_id,
                personaname=name,
                profileurl=f"https://steamcommunity.com/profiles/{account_id + 76561197960265728}",
                avatarfull=item.get("avatarfull") if isinstance(item.get("avatarfull"), str) else None,
                countrycode=None,
                last_updated=None,
            )
        )
    return players


def _deadlock_http_error_message(status: int, body: str) -> str:
    if status >= 500:
        return f"Deadlock API is temporarily unavailable for this request (HTTP {status}). Try again shortly."

    cleaned = " ".join(body.split())
    lowered = cleaned.casefold()
    if not cleaned or cleaned.startswith("<!") or lowered.startswith("<html"):
        return f"Deadlock API request failed with HTTP {status}. Try again shortly."

    return f"Deadlock API request failed with HTTP {status}: {cleaned[:200]}"


def _parse_build_hero(payload: dict[str, Any]) -> DeadlockHeroBuild:
    details = payload.get("details") or {}
    mod_categories = [
        DeadlockBuildCategory(
            name=category.get("name", "Category"),
            description=category.get("description"),
            optional=category.get("optional"),
            mods=[
                DeadlockBuildMod(
                    ability_id=mod["ability_id"],
                    annotation=mod.get("annotation"),
                    imbue_target_ability_id=mod.get("imbue_target_ability_id"),
                    required_flex_slots=mod.get("required_flex_slots"),
                    sell_priority=mod.get("sell_priority"),
                )
                for mod in (category.get("mods") or [])
                if isinstance(mod, dict) and mod.get("ability_id") is not None
            ],
        )
        for category in (details.get("mod_categories") or [])
        if isinstance(category, dict)
    ]
    ability_order = [
        int(entry.get("ability_id"))
        for entry in (((details.get("ability_order") or {}).get("currency_changes") or []))
        if isinstance(entry, dict) and entry.get("ability_id") is not None
    ]
    return DeadlockHeroBuild(
        hero_build_id=payload["hero_build_id"],
        hero_id=payload["hero_id"],
        author_account_id=payload["author_account_id"],
        name=payload["name"],
        description=payload.get("description"),
        language=payload["language"],
        version=payload["version"],
        origin_build_id=payload["origin_build_id"],
        publish_timestamp=payload.get("publish_timestamp"),
        last_updated_timestamp=payload.get("last_updated_timestamp"),
        development_build=payload.get("development_build"),
        tags=[int(tag) for tag in (payload.get("tags") or []) if isinstance(tag, int)],
        mod_categories=mod_categories,
        ability_order=ability_order,
    )


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


class _ForumPostContentExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._capturing = False
        self._depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = {
            class_name
            for key, value in attrs
            if key == "class" and value
            for class_name in value.split()
        }
        if not self._capturing and "bbWrapper" in classes:
            self._capturing = True
            self._depth = 1
            return
        if self._capturing:
            self._depth += 1
            self._parts.append(self.get_starttag_text() or f"<{tag}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._capturing:
            self._parts.append(self.get_starttag_text() or f"<{tag} />")

    def handle_endtag(self, tag: str) -> None:
        if not self._capturing:
            return
        self._depth -= 1
        if self._depth == 0:
            self._capturing = False
            return
        self._parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self._parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._capturing:
            self._parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._capturing:
            self._parts.append(f"&#{name};")

    def content_html(self) -> str | None:
        html = "".join(self._parts).strip()
        return html or None
