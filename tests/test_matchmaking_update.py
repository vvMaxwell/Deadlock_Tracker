"""Coverage for the Deadlock Matchmaking Update (2026-07-30) API changes."""

import asyncio

import pytest

from deadlock_tracker.clients.deadlock_api import DeadlockAPI
from deadlock_tracker.models import (
    DeadlockHeroInfo,
    DeadlockHeroXpReward,
    DeadlockMatch,
    DeadlockMatchMetadata,
    DeadlockMatchPlayer,
    DeadlockPlayer,
    DeadlockPlayerRankData,
    DeadlockRank,
    DeadlockRankInfo,
    PlayerSummary,
)
from deadlock_tracker.services.player_service import PlayerService
from deadlock_tracker.web import app as web_app


def _api_with_payload(payload: object) -> DeadlockAPI:
    api = DeadlockAPI()

    async def fake_get_json(url: str, params: dict[str, str] | None = None) -> object:
        return payload

    api._get_json = fake_get_json  # type: ignore[method-assign]
    return api


# ---------------------------------------------------------------- rank assets


def test_rank_info_uses_new_per_tier_art_and_ignores_deprecated_keys() -> None:
    api = _api_with_payload(
        [
            {
                "tier": 1,
                "name": "Initiate",
                "color": "#6A3E1E",
                "images": {
                    "large": "https://assets/rank01_lg.png",
                    "large_webp": "https://assets/rank01_lg.webp",
                    "chalk": "https://assets/rank01_chalk.png",
                    "chalk_webp": "https://assets/rank01_chalk.webp",
                    "small": "https://assets/old/badge_sm.png",
                    "small_subrank1_webp": "https://assets/old/badge_sm_subrank1.webp",
                    "large_subrank1_webp": "https://assets/old/badge_lg_subrank1.webp",
                },
            }
        ]
    )

    ranks = asyncio.run(api.get_rank_info())

    assert ranks == [
        DeadlockRankInfo(
            tier=1,
            name="Initiate",
            color="#6A3E1E",
            image_large="https://assets/rank01_lg.webp",
            image_chalk="https://assets/rank01_chalk.webp",
        )
    ]


def test_rank_info_falls_back_to_png_and_tolerates_missing_chalk() -> None:
    # Tier 0 (Obscurus) ships no chalk variant.
    api = _api_with_payload(
        [
            {
                "tier": 0,
                "name": "Obscurus",
                "color": "#333333",
                "images": {"large": "https://assets/rank00_lg.png"},
            }
        ]
    )

    ranks = asyncio.run(api.get_rank_info())

    assert ranks[0].image_large == "https://assets/rank00_lg.png"
    assert ranks[0].image_chalk is None


def test_rank_badge_image_url_is_shared_across_sub_ranks() -> None:
    rank_info = [
        DeadlockRankInfo(
            tier=8,
            name="Oracle",
            color="#888",
            image_large="https://assets/rank08_lg.webp",
            image_chalk="https://assets/rank08_chalk.webp",
        )
    ]

    assert web_app._rank_badge_image_url(81, rank_info) == "https://assets/rank08_lg.webp"
    assert web_app._rank_badge_image_url(86, rank_info) == "https://assets/rank08_lg.webp"
    assert web_app._rank_badge_image_url(None, rank_info) is None
    assert web_app._rank_badge_image_url(21, rank_info) is None


def test_rank_badge_image_url_falls_back_to_chalk() -> None:
    rank_info = [
        DeadlockRankInfo(tier=8, name="Oracle", color=None, image_large=None, image_chalk="https://assets/chalk.webp")
    ]

    assert web_app._rank_badge_image_url(83, rank_info) == "https://assets/chalk.webp"


# ----------------------------------------------------------------- leaderboard


def test_leaderboard_entries_parse_without_badge_fields() -> None:
    api = _api_with_payload(
        {
            "entries": [
                {
                    "account_name": "TopPlayer",
                    "rank": 1,
                    "possible_account_ids": [123],
                    "top_hero_ids": [1, 2],
                }
            ]
        }
    )

    entries = asyncio.run(api.get_leaderboard(region="Europe"))

    assert len(entries) == 1
    assert entries[0].account_name == "TopPlayer"
    assert entries[0].rank == 1
    assert entries[0].possible_account_ids == [123]
    assert not hasattr(entries[0], "badge_level")


# --------------------------------------------------------------- match history


def _match_history_payload(**overrides: object) -> list[dict[str, object]]:
    entry: dict[str, object] = {
        "match_id": 96200555,
        "hero_id": 31,
        "start_time": 1785300894,
        "match_duration_s": 2521,
        "game_mode": 1,
        "match_mode": 4,
        "player_team": 0,
        "player_kills": 9,
        "player_deaths": 4,
        "player_assists": 26,
        "net_worth": 57407,
        "last_hits": 247,
        "match_result": 0,
        "player_match_outcome": 1,
        "ranked_display_badge": 83,
        "ranked_delta": 175,
        "ranked_calibration_match": 1,
        "ranked_used_demotion_protection": False,
    }
    entry.update(overrides)
    return [entry]


def test_match_history_parses_new_ranked_fields() -> None:
    api = _api_with_payload(_match_history_payload())

    matches = asyncio.run(api.get_match_history(417357695))

    match = matches[0]
    assert match.player_match_outcome == 1
    assert match.ranked_display_badge == 83
    assert match.ranked_delta == 175
    assert match.ranked_calibration_match == 1
    assert match.ranked_used_demotion_protection is False


def test_match_history_tolerates_missing_ranked_fields() -> None:
    payload = _match_history_payload()
    for key in (
        "player_match_outcome",
        "ranked_display_badge",
        "ranked_delta",
        "ranked_calibration_match",
        "ranked_used_demotion_protection",
    ):
        payload[0].pop(key)
    api = _api_with_payload(payload)

    match = asyncio.run(api.get_match_history(417357695))[0]

    assert match.player_match_outcome is None
    assert match.ranked_display_badge is None


def _match(**overrides: object) -> DeadlockMatch:
    values: dict[str, object] = {
        "match_id": 1,
        "hero_id": 1,
        "start_time": 100,
        "match_duration_s": 600,
        "game_mode": 1,
        "match_mode": 4,
        "player_team": 0,
        "player_kills": 1,
        "player_deaths": 1,
        "player_assists": 1,
        "net_worth": 1,
        "last_hits": 1,
        "match_result": 1,
    }
    values.update(overrides)
    return DeadlockMatch(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("outcome", "expected_label", "expected_win"),
    [
        (1, "Win", True),
        (2, "Loss", False),
        (3, "Penalized", False),
        (4, "Penalized Party", False),
        (5, "Not Scored", False),
    ],
)
def test_match_result_label_uses_player_match_outcome(
    outcome: int, expected_label: str, expected_win: bool
) -> None:
    # player_team 0 vs match_result 1 would read as a loss without the outcome.
    match = _match(player_match_outcome=outcome)

    assert PlayerService.match_result_label(match) == expected_label
    assert PlayerService.is_match_win(match) is expected_win


def test_match_result_falls_back_to_team_comparison_without_outcome() -> None:
    assert PlayerService.is_match_win(_match(player_team=1, match_result=1)) is True
    assert PlayerService.is_match_win(_match(player_team=0, match_result=1)) is False


def test_latest_ranked_match_picks_the_newest_badge() -> None:
    matches = [
        _match(match_id=1, start_time=100, ranked_display_badge=81),
        _match(match_id=2, start_time=300, ranked_display_badge=83),
        _match(match_id=3, start_time=400, ranked_display_badge=None),
    ]

    latest = PlayerService.latest_ranked_match(matches)

    assert latest is not None
    assert latest.match_id == 2


def test_latest_ranked_match_is_none_without_ranked_play() -> None:
    assert PlayerService.latest_ranked_match([_match(ranked_display_badge=None)]) is None


def _rank(**overrides: object) -> DeadlockRank:
    values: dict[str, object] = {
        "account_id": 1,
        "badge": 81,
        "tier": 8,
        "subrank": 1,
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


def _summary(**overrides: object) -> PlayerSummary:
    values: dict[str, object] = {
        "player": DeadlockPlayer(
            account_id=1,
            personaname="Tester",
            profileurl="https://steamcommunity.com/profiles/1",
            avatarfull=None,
            countrycode=None,
            last_updated=None,
        ),
        "rank": _rank(),
        "hero_stats": [],
        "recent_matches": [],
        "hero_info": {},
    }
    values.update(overrides)
    return PlayerSummary(**values)  # type: ignore[arg-type]


def test_displayed_rank_prefers_the_rank_endpoint_badge() -> None:
    summary = _summary(ranked_match=_match(ranked_display_badge=113))

    assert PlayerService.displayed_rank(summary) == 81
    assert PlayerService.rank_name(summary) == "Oracle 1"


def test_displayed_rank_falls_back_to_the_match_history_badge() -> None:
    summary = _summary(rank=_rank(badge=0, tier=0, subrank=0), ranked_match=_match(ranked_display_badge=113))

    assert PlayerService.displayed_rank(summary) == 113
    assert PlayerService.rank_name(summary) == "Eternus 3"


def test_displayed_rank_is_unknown_without_any_rank() -> None:
    summary = _summary(rank=None)

    assert PlayerService.displayed_rank(summary) is None
    assert PlayerService.rank_name(summary) == "Unknown"


# -------------------------------------------------------------- match metadata


def _metadata_payload(**match_info_overrides: object) -> dict[str, object]:
    match_info: dict[str, object] = {
        "match_id": 96470110,
        "start_time": 1785396000,
        "duration_s": 1404,
        "game_mode": 1,
        "match_mode": 4,
        "winning_team": 0,
        "average_badge_team0": 0,
        "average_badge_team1": 0,
        "ranked_type": 1,
        "rank_interval": 1,
        "players": [
            {
                "account_id": 5,
                "team": 0,
                "hero_id": 35,
                "kills": 6,
                "deaths": 7,
                "assists": 11,
                "net_worth": 53174,
                "last_hits": 251,
                "denies": 2,
                "level": 36,
                "assigned_lane": 4,
                "mvp_rank": None,
                "items": [],
                "player_match_outcome": 1,
                "player_rank_data": {
                    "initial_display_rank": 81,
                    "initial_flat_progress": 0,
                    "final_flat_progress": 175,
                    "desired_progress_change": 175,
                    "initial_calibration_games": 6,
                    "initial_demotion_protection_games": 0,
                    "consumed_demotion_protection": False,
                    "initial_win_streak": 2,
                },
                "hero_xp_rewards": [
                    {"xp_grant": {"hero_id": 35, "xp_grant": 100, "reason": 0}},
                    {"xp_grant": {"hero_id": 35, "xp_grant": 25, "reason": 2}},
                ],
            }
        ],
    }
    match_info.update(match_info_overrides)
    return {"match_info": match_info}


def test_match_metadata_parses_ranked_fields() -> None:
    api = _api_with_payload(_metadata_payload())

    metadata = asyncio.run(api.get_match_metadata(96470110))

    assert metadata.ranked_type == 1
    assert metadata.rank_interval == 1
    player = metadata.players[0]
    assert player.player_match_outcome == 1
    assert player.rank_data == DeadlockPlayerRankData(
        initial_display_rank=81,
        initial_flat_progress=0,
        final_flat_progress=175,
        desired_progress_change=175,
        initial_calibration_games=6,
        initial_demotion_protection_games=0,
        consumed_demotion_protection=False,
        initial_win_streak=2,
    )
    assert player.hero_xp_rewards == [
        DeadlockHeroXpReward(hero_id=35, xp_grant=100, reason=0),
        DeadlockHeroXpReward(hero_id=35, xp_grant=25, reason=2),
    ]


def test_match_metadata_tolerates_unranked_matches() -> None:
    payload = _metadata_payload(ranked_type=None, rank_interval=None)
    payload["match_info"]["players"][0]["player_rank_data"] = None
    payload["match_info"]["players"][0]["hero_xp_rewards"] = []

    metadata = asyncio.run(_api_with_payload(payload).get_match_metadata(96470110))

    assert metadata.ranked_type is None
    assert metadata.players[0].rank_data is None
    assert metadata.players[0].hero_xp_rewards == []


# ------------------------------------------------------------------ mode names


@pytest.mark.parametrize(
    ("match_mode", "expected"),
    [
        (1, "Unranked"),
        (4, "Ranked"),
        (7, "Hero Labs"),
        (8, "New Player Placement"),
    ],
)
def test_match_mode_labels(match_mode: int, expected: str) -> None:
    assert web_app._friendly_match_mode_label(match_mode) == expected


def test_match_mode_eight_is_no_longer_calibration() -> None:
    assert web_app._friendly_match_mode_label(8) != "Calibration"


@pytest.mark.parametrize(
    ("game_mode", "match_mode", "expected"),
    [
        (1, 4, "Ranked"),
        (1, 8, "New Player Placement"),
        (4, 1, "Street Brawl"),
        (4, 4, "Street Brawl"),
        (1, None, "Normal"),
        (None, None, "Match"),
    ],
)
def test_queue_name(game_mode: int | None, match_mode: int | None, expected: str) -> None:
    assert web_app._queue_name(game_mode, match_mode) == expected


# ------------------------------------------------------------- ranked rendering


def test_ranked_delta_text_and_direction() -> None:
    assert web_app._ranked_delta_text(175) == "+175"
    assert web_app._ranked_delta_text(-1250) == "-1,250"
    assert web_app._ranked_delta_text(0) == "0"
    assert web_app._ranked_delta_text(None) is None

    assert web_app._ranked_delta_direction(175) == "up"
    assert web_app._ranked_delta_direction(-1) == "down"
    assert web_app._ranked_delta_direction(0) == "none"
    assert web_app._ranked_delta_direction(None) == "none"


def test_ranked_match_notes() -> None:
    assert web_app._ranked_match_notes(_match(ranked_calibration_match=1)) == ["Calibration match"]
    assert web_app._ranked_match_notes(
        _match(ranked_calibration_match=1, ranked_used_demotion_protection=True)
    ) == ["Calibration match", "Demotion protection used"]
    assert web_app._ranked_match_notes(_match()) is None


def _metadata_player(**overrides: object) -> DeadlockMatchPlayer:
    values: dict[str, object] = {
        "account_id": 5,
        "team": 0,
        "hero_id": 1,
        "kills": 1,
        "deaths": 1,
        "assists": 1,
        "net_worth": 1,
        "last_hits": 1,
        "denies": 1,
        "level": 1,
        "assigned_lane": 1,
        "mvp_rank": None,
        "player_damage": 1,
        "objective_damage": 1,
        "healing": 1,
        "items": [],
    }
    values.update(overrides)
    return DeadlockMatchPlayer(**values)  # type: ignore[arg-type]


def test_build_match_ranked_rows_summarises_movement_and_xp() -> None:
    metadata = DeadlockMatchMetadata(
        match_id=1,
        start_time=1,
        duration_s=1,
        game_mode=1,
        match_mode=4,
        winning_team=0,
        players=[
            _metadata_player(
                player_match_outcome=1,
                rank_data=DeadlockPlayerRankData(
                    initial_display_rank=81,
                    initial_flat_progress=1000,
                    final_flat_progress=1175,
                    desired_progress_change=175,
                    initial_calibration_games=6,
                    initial_demotion_protection_games=2,
                    consumed_demotion_protection=True,
                    initial_win_streak=3,
                ),
                hero_xp_rewards=[
                    DeadlockHeroXpReward(hero_id=1, xp_grant=100, reason=0),
                    DeadlockHeroXpReward(hero_id=1, xp_grant=25, reason=2),
                ],
            )
        ],
        ranked_type=1,
        rank_interval=1,
    )
    hero_info = {
        1: DeadlockHeroInfo(
            hero_id=1,
            name="Abrams",
            icon_small="https://assets/abrams.png",
            portrait_url=None,
            background_image_url=None,
        )
    }
    rank_info = [
        DeadlockRankInfo(tier=8, name="Oracle", color="#888", image_large="https://assets/oracle.webp", image_chalk=None)
    ]

    rows = web_app._build_match_ranked_rows(metadata, hero_info, {}, rank_info, viewed_account_id=5)

    assert len(rows) == 1
    row = rows[0]
    assert row.is_viewed_player is True
    assert row.result == "Win"
    assert row.badge_text == "Oracle 1"
    assert row.badge_image_url == "https://assets/oracle.webp"
    assert row.progress_text == "1,000 → 1,175"
    assert row.delta_text == "+175"
    assert row.delta_direction == "up"
    assert row.hero_xp_text == "+125 hero XP"
    assert row.notes == [
        "6 calibration games left",
        "3 win streak",
        "2 demotion protection games",
        "Demotion protection used",
    ]


def test_build_match_ranked_rows_is_empty_for_unranked_matches() -> None:
    metadata = DeadlockMatchMetadata(
        match_id=1,
        start_time=1,
        duration_s=1,
        game_mode=1,
        match_mode=1,
        winning_team=0,
        players=[_metadata_player()],
    )

    assert web_app._build_match_ranked_rows(metadata, {}, {}, [], viewed_account_id=5) == []


def test_match_player_result_prefers_the_reported_outcome() -> None:
    # Team 0 won, but the game scored this player as not scored.
    player = _metadata_player(team=0, player_match_outcome=5)

    assert web_app._match_player_result(player, 0) == "Not Scored"
    assert web_app._match_player_result(_metadata_player(team=0), 0) == "Win"
    assert web_app._match_player_result(_metadata_player(team=1), 0) == "Loss"
    assert web_app._match_player_result(_metadata_player(team=1), None) == "Unknown"


def test_average_rank_text_treats_zero_badges_as_missing() -> None:
    # Ranked matches come back with average_badge_team0/1 == 0.
    assert web_app._match_average_rank_text(0, 0) == "Unknown"
    assert web_app._match_average_rank_text(None, None) == "Unknown"
    assert web_app._match_average_rank_text(81, 0) == "Oracle 1"
    assert web_app._match_average_rank_text(81, 81) == "Oracle 1"
    assert web_app._match_average_rank_text(81, 91) == "Team 0 Oracle 1 / Team 1 Phantom 1"


# ------------------------------------------------------------- patch selector


def test_window_options_include_the_matchmaking_update() -> None:
    values = [option.value for option in web_app._window_options()]
    labels = [option.label for option in web_app._window_options()]

    assert web_app.MATCHMAKING_UPDATE_WINDOW in values
    assert "Since Matchmaking Update (2026-07-30)" in labels


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("7", "7"),
        ("30", "30"),
        ("90", "90"),
        ("matchmaking-update", "matchmaking-update"),
        ("999", "7"),
        ("", "7"),
        (None, "7"),
    ],
)
def test_selected_window_rejects_unknown_values(raw: str | None, expected: str) -> None:
    assert web_app._selected_window(raw) == expected


def test_window_min_timestamp_pins_to_the_patch_date() -> None:
    assert (
        web_app._window_min_timestamp(web_app.MATCHMAKING_UPDATE_WINDOW)
        == web_app.MATCHMAKING_UPDATE_TIMESTAMP
    )


def test_window_min_timestamp_is_a_rolling_window_for_day_counts() -> None:
    seven = web_app._window_min_timestamp("7")
    thirty = web_app._window_min_timestamp("30")

    assert seven - thirty == 23 * 86400
