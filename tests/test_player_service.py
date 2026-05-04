import asyncio

import pytest

from deadlock_tracker.clients.deadlock_api import _match_history_rate_limit_fallback
from deadlock_tracker.models import DeadlockHeroInfo, DeadlockHeroStat, DeadlockMatch, DeadlockPlayer
from deadlock_tracker.services.player_service import PlayerService


def test_win_rate_is_zero_for_empty_stats() -> None:
    stat = DeadlockHeroStat(
        hero_id=1,
        matches_played=0,
        wins=0,
        kills=None,
        deaths=None,
        assists=None,
        last_played=None,
    )

    assert PlayerService.win_rate(stat) == 0.0


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (None, "Unknown"),
        (65, "1:05"),
        (600, "10:00"),
    ],
)
def test_format_match_duration(seconds: int | None, expected: str) -> None:
    assert PlayerService.format_match_duration(seconds) == expected


@pytest.mark.asyncio
async def test_build_player_summary_uses_default_match_history_mode() -> None:
    class FakeApi:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def get_hero_info(self) -> dict[int, DeadlockHeroInfo]:
            return {}

        async def get_player_rank(self, account_id: int):
            return None

        async def get_match_history(self, account_id: int, **kwargs: object) -> list[DeadlockMatch]:
            self.calls.append({"account_id": account_id, **kwargs})
            return [
                DeadlockMatch(
                    match_id=1,
                    hero_id=1,
                    start_time=1,
                    match_duration_s=600,
                    game_mode=1,
                    match_mode=1,
                    player_team=0,
                    player_kills=1,
                    player_deaths=1,
                    player_assists=1,
                    net_worth=1000,
                    last_hits=10,
                    match_result=0,
                )
            ]

    api = FakeApi()
    service = PlayerService(api=api)

    await service.build_player_summary(
        DeadlockPlayer(
            account_id=123,
            personaname="Tester",
            profileurl="https://steamcommunity.com/profiles/123",
            avatarfull=None,
            countrycode=None,
            last_updated=None,
        )
    )

    assert api.calls == [{"account_id": 123, "limit": 50}]


@pytest.mark.asyncio
async def test_build_player_summary_refresh_uses_force_refetch_mode() -> None:
    class FakeApi:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def get_hero_info(self) -> dict[int, DeadlockHeroInfo]:
            return {}

        async def get_player_rank(self, account_id: int):
            return None

        async def get_steam_profile(self, account_id: int) -> DeadlockPlayer | None:
            return None

        async def get_match_history(self, account_id: int, **kwargs: object) -> list[DeadlockMatch]:
            self.calls.append({"account_id": account_id, **kwargs})
            return []

    api = FakeApi()
    service = PlayerService(api=api)

    await service.build_player_summary(
        DeadlockPlayer(
            account_id=123,
            personaname="Tester",
            profileurl="https://steamcommunity.com/profiles/123",
            avatarfull=None,
            countrycode=None,
            last_updated=None,
        ),
        refresh_matches=True,
    )

    assert api.calls == [
        {
            "account_id": 123,
            "limit": 50,
            "force_refetch": True,
            "only_stored_history": False,
        }
    ]


def test_resolve_numeric_player_does_not_fall_back_to_search() -> None:
    class FakeApi:
        def __init__(self) -> None:
            self.search_called = False

        async def resolve_player_input(self, raw_input: str) -> int:
            return int(raw_input)

        async def get_steam_profile(self, account_id: int) -> None:
            return None

        async def search_players(self, query: str) -> list[DeadlockPlayer]:
            self.search_called = True
            raise AssertionError("numeric account lookup should not use steam-search")

    api = FakeApi()
    service = PlayerService(api=api)

    player = asyncio.run(service.resolve_player("123"))

    assert isinstance(player, DeadlockPlayer)
    assert player.account_id == 123
    assert player.profileurl == "https://steamcommunity.com/profiles/76561197960265851"
    assert api.search_called is False


def test_match_history_429_fallback_keeps_stored_history_payload() -> None:
    payload = _match_history_rate_limit_fallback(
        "https://api.deadlock-api.com/v1/players/123/match-history",
        params=None,
        body='[{"match_id": 1}]',
    )

    assert payload == [{"match_id": 1}]


def test_match_history_429_fallback_ignores_force_refetch_errors() -> None:
    payload = _match_history_rate_limit_fallback(
        "https://api.deadlock-api.com/v1/players/123/match-history",
        params={"force_refetch": "true"},
        body='[{"match_id": 1}]',
    )

    assert payload is None
