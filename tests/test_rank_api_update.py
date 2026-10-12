"""Coverage for the move off the deprecated MMR endpoints.

The MMR estimate is gone: player ranks now come from
/v1/players/{account_id}/rank, and the player rank distribution comes from the
unique_players column on the badge distribution.
"""

import asyncio

from deadlock_tracker.clients.deadlock_api import DeadlockAPI
from deadlock_tracker.models import DeadlockBadgeDistribution, DeadlockPlayer, DeadlockRank, PlayerSummary
from deadlock_tracker.services.player_service import PlayerService

_LAST_MATCH = {
    "match_id": 96470110,
    "start_time": 1785396000,
    "player_rank_initial_display_rank": 81,
    "player_rank_initial_flat_progress": 0,
    "player_rank_final_flat_progress": 175,
    "player_rank_desired_progress_change": 175,
    "player_rank_initial_calibration_games": 0,
    "player_rank_initial_demotion_protection_games": 2,
    "player_rank_consumed_demotion_protection": False,
    "player_rank_initial_win_streak": 3,
}


def _api_recording_urls(payload: object) -> tuple[DeadlockAPI, list[str]]:
    api = DeadlockAPI()
    urls: list[str] = []

    async def fake_get_json(url: str, params: dict[str, str] | None = None) -> object:
        urls.append(url)
        return payload

    api._get_json = fake_get_json  # type: ignore[method-assign]
    return api, urls


# ------------------------------------------------------------------ player rank


def test_player_rank_reads_the_rank_endpoint() -> None:
    api, urls = _api_recording_urls({"badge": 82, "rank": 8, "subrank": 2, "last_match": _LAST_MATCH})

    rank = asyncio.run(api.get_player_rank(123))

    assert urls == [f"{api.base_url}/v1/players/123/rank"]
    assert rank == DeadlockRank(
        account_id=123,
        badge=82,
        tier=8,
        subrank=2,
        match_id=96470110,
        start_time=1785396000,
        progress=175,
        progress_change=175,
        calibration_games_remaining=0,
        demotion_protection_games=2,
        used_demotion_protection=False,
        win_streak=3,
    )


def test_player_rank_handles_an_account_without_a_ranked_match() -> None:
    api, _ = _api_recording_urls({"badge": 0, "rank": 0, "subrank": 0, "last_match": None})

    rank = asyncio.run(api.get_player_rank(123))

    assert rank is not None
    assert rank.badge == 0
    assert rank.match_id is None
    assert rank.start_time is None


def test_player_rank_is_none_when_the_endpoint_returns_nothing() -> None:
    api, _ = _api_recording_urls({})

    assert asyncio.run(api.get_player_rank(123)) is None


# ---------------------------------------------------------------- distributions


def test_badge_distribution_parses_unique_players() -> None:
    api, urls = _api_recording_urls(
        [{"badge_level": 81, "total_matches": 500, "unique_players": 120}]
    )

    distribution = asyncio.run(api.get_badge_distribution())

    assert urls == [f"{api.base_url}/v1/analytics/badge-distribution"]
    assert distribution == [
        DeadlockBadgeDistribution(badge_level=81, total_matches=500, unique_players=120)
    ]


def test_player_rank_distribution_uses_unique_players_and_drops_empty_badges() -> None:
    api, urls = _api_recording_urls(
        [
            {"badge_level": 16, "total_matches": 548, "unique_players": 1006},
            # Sub-ranks above 6 only ever show up as a match average, never as a
            # rank a player holds.
            {"badge_level": 17, "total_matches": 81, "unique_players": 0},
            {"badge_level": 21, "total_matches": 300, "unique_players": 539},
        ]
    )

    distribution = asyncio.run(api.get_player_rank_distribution())

    assert urls == [f"{api.base_url}/v1/analytics/badge-distribution"]
    assert [(entry.rank, entry.players) for entry in distribution] == [(16, 1006), (21, 539)]


# ------------------------------------------------------------------ rank detail


def _summary(rank: DeadlockRank | None) -> PlayerSummary:
    return PlayerSummary(
        player=DeadlockPlayer(
            account_id=1,
            personaname="Tester",
            profileurl="https://steamcommunity.com/profiles/1",
            avatarfull=None,
            countrycode=None,
            last_updated=None,
        ),
        rank=rank,
        hero_stats=[],
        recent_matches=[],
        hero_info={},
    )


def _rank(**overrides: object) -> DeadlockRank:
    values: dict[str, object] = {
        "account_id": 1,
        "badge": 82,
        "tier": 8,
        "subrank": 2,
        "match_id": 1,
        "start_time": 1,
        "progress": 175,
        "progress_change": 175,
        "calibration_games_remaining": None,
        "demotion_protection_games": None,
        "used_demotion_protection": None,
        "win_streak": None,
    }
    values.update(overrides)
    return DeadlockRank(**values)  # type: ignore[arg-type]


def test_rank_detail_text_shows_the_progress_the_last_match_awarded() -> None:
    assert (
        PlayerService.rank_detail_text(_summary(_rank()))
        == "Last Ranked Match: +175 progress"
    )
    assert (
        PlayerService.rank_detail_text(_summary(_rank(progress_change=-250)))
        == "Last Ranked Match: -250 progress"
    )


def test_rank_detail_text_shows_remaining_placement_games() -> None:
    summary = _summary(_rank(calibration_games_remaining=6))

    assert PlayerService.rank_detail_text(summary) == "Placement: 6 games left"


def test_rank_detail_text_without_a_ranked_match() -> None:
    assert PlayerService.rank_detail_text(_summary(None)) == "No ranked match on record"
    assert (
        PlayerService.rank_detail_text(_summary(_rank(badge=0, tier=0, subrank=0, match_id=None)))
        == "No ranked match on record"
    )
