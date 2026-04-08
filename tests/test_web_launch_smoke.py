from fastapi.testclient import TestClient

from deadlock_tracker.clients.deadlock_api import DeadlockError
from deadlock_tracker.models import (
    DeadlockAbilityOrderStat,
    DeadlockHeroInfo,
    DeadlockHeroStat,
    DeadlockItemInfo,
    DeadlockItemStat,
    DeadlockMatch,
    DeadlockPlayer,
    DeadlockRank,
    DeadlockRankInfo,
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
            return [
                DeadlockRankInfo(
                    tier=8,
                    name="Oracle",
                    color="#955138",
                    image_small=None,
                    image_small_by_division={1: "https://example.com/oracle-1.png"},
                )
            ]

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
    assert "oracle-1.png" in response.text


def test_street_brawl_selected_hero_stays_on_build_page_without_guide(monkeypatch) -> None:
    class FakeApi:
        async def get_hero_info(self) -> dict[int, DeadlockHeroInfo]:
            return {
                15: DeadlockHeroInfo(
                    hero_id=15,
                    name="Bebop",
                    icon_small="https://example.com/bebop.png",
                    portrait_url="https://example.com/bebop-portrait.png",
                    background_image_url="https://example.com/bebop-bg.png",
                )
            }

        async def get_item_stats(self, **_: object) -> list[DeadlockItemStat]:
            return [
                DeadlockItemStat(
                    item_id=101,
                    wins=12,
                    losses=8,
                    matches=20,
                    players=18,
                    avg_buy_time_s=120.0,
                    avg_sell_time_s=None,
                    avg_buy_time_relative=None,
                    avg_sell_time_relative=None,
                )
            ]

        async def get_ability_order_stats(self, **_: object) -> list[DeadlockAbilityOrderStat]:
            return []

        async def get_all_item_info(self) -> dict[int, DeadlockItemInfo]:
            return {
                101: DeadlockItemInfo(
                    item_id=101,
                    name="Mystic Shot",
                    image="https://example.com/item.png",
                    shop_image="https://example.com/item-shop.png",
                    item_slot_type="weapon",
                    item_tier=1,
                    cost=500,
                    is_active_item=False,
                    item_type="upgrade",
                    ability_type=None,
                    hero_id=None,
                )
            }

    class FakePlayerService:
        def __init__(self) -> None:
            self.api = FakeApi()

    monkeypatch.setattr(web_app, "PlayerService", FakePlayerService)

    client = TestClient(web_app.app)
    response = client.get("/street-brawl-builds?hero_id=15")

    assert response.status_code == 200
    assert "Choose A Hero" not in response.text
    assert "Best Items By Win Rate" in response.text
    assert "Mystic Shot" in response.text
    assert "We do not have enough tracked Street Brawl ability-order data for Bebop yet" in response.text
