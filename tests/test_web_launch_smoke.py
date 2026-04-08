from fastapi.testclient import TestClient

from deadlock_tracker.clients.deadlock_api import DeadlockError
from deadlock_tracker.models import (
    DeadlockHeroInfo,
    DeadlockHeroStat,
    DeadlockMatch,
    DeadlockPlayer,
    DeadlockRank,
    PlayerSummary,
)
from deadlock_tracker.web import app as web_app


def test_healthcheck_returns_ok() -> None:
    client = TestClient(web_app.app)
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_friendly_meta_error_message_rate_limit() -> None:
    message = web_app._friendly_meta_error_message(
        DeadlockError("Deadlock API rate limit hit. Try again shortly."),
        topic="hero stats",
    )

    assert message == "Deadlock API is rate-limiting hero stats right now. Try again shortly."


def test_friendly_meta_error_message_bad_filters() -> None:
    message = web_app._friendly_meta_error_message(
        DeadlockError("Deadlock API request failed with HTTP 400: bad filters"),
        topic="item stats",
    )

    assert message == "Those filters are not available for item stats right now. Try broader filters or switch modes."


def test_player_refresh_falls_back_to_cached_history(monkeypatch) -> None:
    class FakeApi:
        async def get_rank_info(self) -> list:
            return []

    class FakePlayerService:
        api = FakeApi()

        def win_rate(self, stat: DeadlockHeroStat) -> float:
            return stat.wins / stat.matches_played

        def rank_name(self, summary: PlayerSummary) -> str:
            return "Oracle 1"

        def match_result_label(self, match: DeadlockMatch) -> str:
            return "Win"

        def format_match_duration(self, seconds: int | None) -> str:
            return "10:00"

        def format_kda(self, kills: int | None, deaths: int | None, assists: int | None) -> str:
            return f"{kills or 0}/{deaths or 0}/{assists or 0}"

        async def resolve_player(self, raw_input: str) -> DeadlockPlayer:
            return DeadlockPlayer(
                account_id=123,
                personaname="Tester",
                profileurl="https://steamcommunity.com/profiles/123",
                avatarfull=None,
                countrycode="CA",
                last_updated=None,
            )

        async def build_player_summary(self, player: DeadlockPlayer, *, refresh_matches: bool = False) -> PlayerSummary:
            if refresh_matches:
                raise DeadlockError("Deadlock API force refresh is rate-limited.")
            return PlayerSummary(
                player=player,
                rank=DeadlockRank(
                    account_id=123,
                    match_id=1,
                    start_time=1,
                    player_score=1.0,
                    rank=81,
                    division=1,
                    division_tier=1,
                ),
                hero_stats=[
                    DeadlockHeroStat(
                        hero_id=1,
                        matches_played=3,
                        wins=2,
                        kills=12,
                        deaths=5,
                        assists=14,
                        last_played=1,
                    )
                ],
                recent_matches=[
                    DeadlockMatch(
                        match_id=999,
                        hero_id=1,
                        start_time=1,
                        match_duration_s=600,
                        game_mode=1,
                        match_mode=1,
                        player_team=1,
                        player_kills=5,
                        player_deaths=2,
                        player_assists=7,
                        net_worth=12345,
                        last_hits=88,
                        match_result=1,
                    )
                ],
                hero_info={
                    1: DeadlockHeroInfo(
                        hero_id=1,
                        name="Abrams",
                        icon_small=None,
                        portrait_url=None,
                        background_image_url=None,
                    )
                },
            )

    monkeypatch.setattr(web_app, "PlayerService", FakePlayerService)

    client = TestClient(web_app.app)
    response = client.get("/players/123?refresh=1")

    assert response.status_code == 200
    assert "Live refresh is temporarily limited." in response.text
    assert "Showing the latest cached match history instead" in response.text
