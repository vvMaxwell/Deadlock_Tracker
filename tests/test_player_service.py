import pytest

from deadlock_tracker.models import DeadlockHeroStat
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
