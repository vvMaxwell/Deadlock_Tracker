import json

from fastapi.testclient import TestClient

from deadlock_tracker.clients.deadlock_api import DeadlockAPI
from deadlock_tracker.clients.deadlock_api import DeadlockError
from deadlock_tracker.models import (
    DeadlockAbilityOrderStat,
    DeadlockHeroInfo,
    DeadlockHeroCounterStat,
    DeadlockHeroStat,
    DeadlockHeroSynergyStat,
    DeadlockItemInfo,
    DeadlockItemStat,
    DeadlockMatch,
    DeadlockPatch,
    DeadlockPlayer,
    DeadlockPlayerRankDistribution,
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


def test_robots_txt_lists_sitemap() -> None:
    client = TestClient(web_app.app)
    response = client.get("/robots.txt")

    assert response.status_code == 200
    assert "User-agent: *" in response.text
    assert "Sitemap:" in response.text


def test_sitemap_lists_core_pages() -> None:
    client = TestClient(web_app.app)
    response = client.get("/sitemap.xml")

    assert response.status_code == 200
    assert "<loc>http://testserver/</loc>" in response.text
    assert "<loc>http://testserver/heroes</loc>" in response.text
    assert "<loc>http://testserver/items</loc>" in response.text
    assert "<loc>http://testserver/leaderboards</loc>" in response.text
    assert "<loc>http://testserver/rank-distribution</loc>" in response.text
    assert "<loc>http://testserver/best-heroes</loc>" in response.text
    assert "<loc>http://testserver/best-items</loc>" in response.text
    assert "<loc>http://testserver/street-brawl-builds</loc>" in response.text
    assert "<loc>http://testserver/patch-notes</loc>" in response.text


def test_sitemap_lists_hero_item_and_patch_detail_pages(monkeypatch) -> None:
    class FakeApi:
        async def get_hero_info(self) -> dict[int, DeadlockHeroInfo]:
            return {
                1: DeadlockHeroInfo(
                    hero_id=1,
                    name="Abrams",
                    icon_small=None,
                    portrait_url=None,
                    background_image_url=None,
                )
            }

        async def get_all_item_info(self) -> dict[int, DeadlockItemInfo]:
            return {
                101: DeadlockItemInfo(
                    item_id=101,
                    name="Mystic Shot",
                    image=None,
                    shop_image=None,
                    item_slot_type="weapon",
                    item_tier=1,
                    cost=500,
                    is_active_item=False,
                    item_type="upgrade",
                    ability_type=None,
                    hero_id=None,
                )
            }

        async def get_patches(self, *, limit: int = 50) -> list[DeadlockPatch]:
            return [
                DeadlockPatch(
                    title="04-10-2026 Update",
                    pub_date="2026-04-11T04:03:53Z",
                    link="https://forums.playdeadlock.com/threads/04-10-2026-update.125825/",
                    guid="125825",
                    author="invalid@example.com (Yoshi)",
                    category="Changelog",
                    creator="Yoshi",
                    content_html="<div>Test</div>",
                )
            ]

    class FakePlayerService:
        def __init__(self) -> None:
            self.api = FakeApi()

    monkeypatch.setattr(web_app, "PlayerService", FakePlayerService)

    client = TestClient(web_app.app)
    response = client.get("/sitemap.xml")

    assert "<loc>http://testserver/heroes/1/abrams</loc>" in response.text
    assert "<loc>http://testserver/heroes/1/abrams/items</loc>" in response.text
    assert "<loc>http://testserver/heroes/1/abrams/matchups</loc>" in response.text
    assert "<loc>http://testserver/heroes/1/abrams/rank-distribution</loc>" in response.text
    assert "<loc>http://testserver/items/101/mystic-shot</loc>" in response.text
    assert "<loc>http://testserver/patch-notes/125825/04-10-2026-update</loc>" in response.text


def test_home_json_ld_is_valid_json() -> None:
    client = TestClient(web_app.app)
    response = client.get("/")

    marker = '<script type="application/ld+json">'
    start = response.text.index(marker) + len(marker)
    end = response.text.index("</script>", start)
    payload = response.text[start:end]

    parsed = json.loads(payload)
    assert isinstance(parsed, list)
    assert parsed[0]["@type"] == "Organization"
    assert parsed[0]["logo"]["@type"] == "ImageObject"
    assert parsed[1]["@type"] == "WebSite"


def test_home_head_exposes_standard_favicon_links() -> None:
    client = TestClient(web_app.app)
    response = client.get("/")

    assert 'rel="manifest" href="http://testserver/site.webmanifest"' in response.text
    assert 'rel="shortcut icon" href="http://testserver/favicon.ico"' in response.text
    assert 'sizes="32x32" href="http://testserver/static/branding/favicon-32.png"' in response.text
    assert 'sizes="192x192" href="http://testserver/static/branding/favicon-192.png"' in response.text


def test_favicon_ico_redirects_to_png_asset() -> None:
    client = TestClient(web_app.app)
    response = client.get("/favicon.ico", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "http://testserver/static/branding/favicon-48.png"


def test_site_webmanifest_lists_brand_icons() -> None:
    client = TestClient(web_app.app)
    response = client.get("/site.webmanifest")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/manifest+json")
    payload = response.json()
    assert payload["name"] == "Deadlock Stats Tracker"
    assert payload["icons"][0]["src"] == "http://testserver/static/branding/favicon-192.png"
    assert payload["icons"][1]["src"] == "http://testserver/static/branding/favicon-512.png"


def test_home_menu_drawer_renders_outside_header() -> None:
    client = TestClient(web_app.app)
    response = client.get("/")

    assert 'id="site-drawer-backdrop"' in response.text
    assert '<aside class="site-drawer" id="site-drawer">' in response.text
    assert '<a class="menu-button" href="#site-drawer" aria-label="Open menu">' in response.text
    assert '#site-drawer:target' in response.text
    assert '<span class="menu-button-label">Menu</span>' in response.text
    assert "Main Screen" in response.text


def test_home_stylesheet_url_is_versioned() -> None:
    client = TestClient(web_app.app)
    response = client.get("/")

    assert f'/static/site.css?v={web_app.STATIC_CSS_VERSION}' in response.text


def test_rank_distribution_includes_top_percent_labels() -> None:
    tiers = web_app._build_player_rank_distribution_views(
        [
            type("RankRow", (), {"rank": 11, "players": 50})(),
            type("RankRow", (), {"rank": 12, "players": 50})(),
            type("RankRow", (), {"rank": 81, "players": 20})(),
            type("RankRow", (), {"rank": 82, "players": 20})(),
            type("RankRow", (), {"rank": 111, "players": 10})(),
            type("RankRow", (), {"rank": 112, "players": 10})(),
        ],
        [
            DeadlockRankInfo(tier=1, name="Initiate", color="#111", image_small=None, image_small_by_division={}),
            DeadlockRankInfo(tier=8, name="Oracle", color="#888", image_small=None, image_small_by_division={}),
            DeadlockRankInfo(tier=11, name="Eternus", color="#0f0", image_small=None, image_small_by_division={}),
        ],
    )

    by_name = {tier.tier_name: tier.top_percent_text for tier in tiers}
    assert by_name["Eternus"] == "Top 12.5%"
    assert by_name["Oracle"] == "Top 37.5%"
    assert by_name["Initiate"] == "Top 100.0%"


def test_faq_json_ld_is_valid_json() -> None:
    client = TestClient(web_app.app)
    response = client.get("/faq")

    marker = '<script type="application/ld+json">'
    start = response.text.index(marker) + len(marker)
    end = response.text.index("</script>", start)
    payload = response.text[start:end]

    parsed = json.loads(payload)
    assert isinstance(parsed, list)
    assert parsed[0]["@type"] == "FAQPage"


def test_patch_notes_page_renders_official_posts(monkeypatch) -> None:
    class FakeApi:
        async def get_patches(self, *, limit: int = 12) -> list[DeadlockPatch]:
            return [
                DeadlockPatch(
                    title="04-10-2026 Update",
                    pub_date="2026-04-11T04:03:53Z",
                    link="https://forums.playdeadlock.com/threads/04-10-2026-update.125825/",
                    guid="125825",
                    author="invalid@example.com (Yoshi)",
                    category="Changelog",
                    creator="Yoshi",
                    content_html=(
                        '<div class="bbWrapper"><b>[ General ]</b><br />'
                        '- Parrying is now allowed while ground dashing<br />'
                        '<a href="https://forums.playdeadlock.com/threads/04-10-2026-update.125825/">Read more</a></div>'
                    ),
                )
            ]

    class FakePlayerService:
        def __init__(self) -> None:
            self.api = FakeApi()

    monkeypatch.setattr(web_app, "PlayerService", FakePlayerService)

    client = TestClient(web_app.app)
    response = client.get("/patch-notes")

    assert response.status_code == 200
    assert "Deadlock Patch Notes" in response.text
    assert "04-10-2026 Update" in response.text
    assert "forums.playdeadlock.com" in response.text
    assert "Parrying is now allowed while ground dashing" in response.text
    assert "Read more" not in response.text


def test_patch_note_detail_page_renders(monkeypatch) -> None:
    class FakeApi:
        async def get_patches(self, *, limit: int = 50) -> list[DeadlockPatch]:
            return [
                DeadlockPatch(
                    title="04-12-2026 Update",
                    pub_date="2026-04-12T04:03:53Z",
                    link="https://forums.playdeadlock.com/threads/04-12-2026-update.126000/",
                    guid="126000",
                    author="invalid@example.com (Yoshi)",
                    category="Changelog",
                    creator="Yoshi",
                    content_html="<div>- Newer patch</div>",
                ),
                DeadlockPatch(
                    title="04-10-2026 Update",
                    pub_date="2026-04-11T04:03:53Z",
                    link="https://forums.playdeadlock.com/threads/04-10-2026-update.125825/",
                    guid="125825",
                    author="invalid@example.com (Yoshi)",
                    category="Changelog",
                    creator="Yoshi",
                    content_html="<div>- Parrying is now allowed while ground dashing</div>",
                )
            ]

    class FakePlayerService:
        def __init__(self) -> None:
            self.api = FakeApi()

    monkeypatch.setattr(web_app, "PlayerService", FakePlayerService)

    client = TestClient(web_app.app)
    response = client.get("/patch-notes/125825/04-10-2026-update")

    assert response.status_code == 200
    assert "04-10-2026 Update" in response.text
    assert "Parrying is now allowed while ground dashing" in response.text
    assert "04-12-2026 Update" in response.text


def test_patch_notes_archive_page_renders(monkeypatch) -> None:
    class FakeApi:
        async def get_patches(self, *, limit: int = 25) -> list[DeadlockPatch]:
            return [
                DeadlockPatch(
                    title=f"04-{index:02d}-2026 Update",
                    pub_date="2026-04-11T04:03:53Z",
                    link=f"https://forums.playdeadlock.com/threads/{index}/",
                    guid=str(index),
                    author="invalid@example.com (Yoshi)",
                    category="Changelog",
                    creator="Yoshi",
                    content_html="<div>- Test</div>",
                )
                for index in range(1, 15)
            ]

    class FakePlayerService:
        def __init__(self) -> None:
            self.api = FakeApi()

    monkeypatch.setattr(web_app, "PlayerService", FakePlayerService)

    client = TestClient(web_app.app)
    response = client.get("/patch-notes?page=2")

    assert response.status_code == 200
    assert "Archive page 2" in response.text
    assert "Newer patch notes" in response.text


def test_hero_detail_page_renders(monkeypatch) -> None:
    class FakeApi:
        async def get_hero_info(self) -> dict[int, DeadlockHeroInfo]:
            return {
                1: DeadlockHeroInfo(
                    hero_id=1,
                    name="Abrams",
                    icon_small="https://example.com/abrams.png",
                    portrait_url=None,
                    background_image_url=None,
                )
            }

        async def get_hero_analytics(self, **_: object) -> list:
            from deadlock_tracker.models import DeadlockHeroAnalytics

            return [DeadlockHeroAnalytics(hero_id=1, wins=60, losses=40, matches=100, players=80)]

        async def get_item_stats(self, **_: object) -> list[DeadlockItemStat]:
            return [
                DeadlockItemStat(
                    item_id=101,
                    wins=60,
                    losses=40,
                    matches=100,
                    players=70,
                    avg_buy_time_s=120.0,
                    avg_sell_time_s=None,
                    avg_buy_time_relative=None,
                    avg_sell_time_relative=None,
                )
            ]

        async def get_all_item_info(self) -> dict[int, DeadlockItemInfo]:
            return {
                101: DeadlockItemInfo(
                    item_id=101,
                    name="Mystic Shot",
                    image=None,
                    shop_image="https://example.com/item.png",
                    item_slot_type="weapon",
                    item_tier=1,
                    cost=500,
                    is_active_item=False,
                    item_type="upgrade",
                    ability_type=None,
                    hero_id=None,
                )
            }

        async def get_hero_counter_stats(self, **_: object) -> list[DeadlockHeroCounterStat]:
            return [
                DeadlockHeroCounterStat(
                    hero_id=1,
                    enemy_hero_id=2,
                    wins=60,
                    matches_played=100,
                    kills=500,
                    enemy_kills=420,
                    deaths=300,
                    enemy_deaths=350,
                    assists=600,
                    enemy_assists=540,
                    denies=100,
                    enemy_denies=90,
                    last_hits=5000,
                    enemy_last_hits=4700,
                    networth=900000,
                    enemy_networth=850000,
                    obj_damage=110000,
                    enemy_obj_damage=100000,
                    creeps=2500,
                    enemy_creeps=2400,
                )
            ]

        async def get_hero_synergy_stats(self, **_: object) -> list[DeadlockHeroSynergyStat]:
            return [
                DeadlockHeroSynergyStat(
                    hero_id1=1,
                    hero_id2=2,
                    wins=66,
                    matches_played=100,
                    kills1=500,
                    kills2=450,
                    deaths1=300,
                    deaths2=280,
                    assists1=600,
                    assists2=650,
                    denies1=100,
                    denies2=95,
                    last_hits1=5000,
                    last_hits2=4800,
                    networth1=900000,
                    networth2=880000,
                    obj_damage1=110000,
                    obj_damage2=102000,
                    creeps1=2500,
                    creeps2=2400,
                )
            ]

    class FakePlayerService:
        def __init__(self) -> None:
            self.api = FakeApi()

    monkeypatch.setattr(web_app, "PlayerService", FakePlayerService)

    client = TestClient(web_app.app)
    response = client.get("/heroes/1/abrams")

    assert response.status_code == 200
    assert "Abrams" in response.text
    assert "Mystic Shot" in response.text
    assert "Abrams matchups" in response.text


def test_hero_detail_page_degrades_gracefully_when_meta_calls_fail(monkeypatch) -> None:
    class FakeApi:
        async def get_hero_info(self) -> dict[int, DeadlockHeroInfo]:
            return {
                1: DeadlockHeroInfo(
                    hero_id=1,
                    name="Abrams",
                    icon_small="https://example.com/abrams.png",
                    portrait_url=None,
                    background_image_url=None,
                )
            }

        async def get_hero_analytics(self, **_: object) -> list:
            raise DeadlockError("Deadlock API took too long to respond. Try again in a moment.")

    class FakePlayerService:
        def __init__(self) -> None:
            self.api = FakeApi()

    monkeypatch.setattr(web_app, "PlayerService", FakePlayerService)

    client = TestClient(web_app.app)
    response = client.get("/heroes/1/abrams")

    assert response.status_code == 200
    assert "Abrams" in response.text
    assert "taking longer than usual" in response.text


def test_hero_items_page_renders(monkeypatch) -> None:
    class FakeApi:
        async def get_hero_info(self) -> dict[int, DeadlockHeroInfo]:
            return {
                1: DeadlockHeroInfo(
                    hero_id=1,
                    name="Abrams",
                    icon_small="https://example.com/abrams.png",
                    portrait_url=None,
                    background_image_url=None,
                )
            }

        async def get_item_stats(self, **_: object) -> list[DeadlockItemStat]:
            return [
                DeadlockItemStat(
                    item_id=101,
                    wins=60,
                    losses=40,
                    matches=100,
                    players=70,
                    avg_buy_time_s=120.0,
                    avg_sell_time_s=None,
                    avg_buy_time_relative=None,
                    avg_sell_time_relative=None,
                )
            ]

        async def get_all_item_info(self) -> dict[int, DeadlockItemInfo]:
            return {
                101: DeadlockItemInfo(
                    item_id=101,
                    name="Mystic Shot",
                    image=None,
                    shop_image="https://example.com/item.png",
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
    response = client.get("/heroes/1/abrams/items")

    assert response.status_code == 200
    assert "Best Items for Abrams" in response.text
    assert "Mystic Shot" in response.text


def test_hero_matchups_page_renders(monkeypatch) -> None:
    class FakeApi:
        async def get_hero_info(self) -> dict[int, DeadlockHeroInfo]:
            return {
                1: DeadlockHeroInfo(
                    hero_id=1,
                    name="Abrams",
                    icon_small="https://example.com/abrams.png",
                    portrait_url=None,
                    background_image_url=None,
                ),
                2: DeadlockHeroInfo(
                    hero_id=2,
                    name="Bebop",
                    icon_small="https://example.com/bebop.png",
                    portrait_url=None,
                    background_image_url=None,
                ),
            }

        async def get_hero_counter_stats(self, **_: object) -> list[DeadlockHeroCounterStat]:
            return [
                DeadlockHeroCounterStat(
                    hero_id=1,
                    enemy_hero_id=2,
                    wins=60,
                    matches_played=100,
                    kills=500,
                    enemy_kills=420,
                    deaths=300,
                    enemy_deaths=350,
                    assists=600,
                    enemy_assists=540,
                    denies=100,
                    enemy_denies=90,
                    last_hits=5000,
                    enemy_last_hits=4700,
                    networth=900000,
                    enemy_networth=850000,
                    obj_damage=110000,
                    enemy_obj_damage=100000,
                    creeps=2500,
                    enemy_creeps=2400,
                )
            ]

        async def get_hero_synergy_stats(self, **_: object) -> list[DeadlockHeroSynergyStat]:
            return [
                DeadlockHeroSynergyStat(
                    hero_id1=1,
                    hero_id2=2,
                    wins=66,
                    matches_played=100,
                    kills1=500,
                    kills2=450,
                    deaths1=300,
                    deaths2=280,
                    assists1=600,
                    assists2=650,
                    denies1=100,
                    denies2=95,
                    last_hits1=5000,
                    last_hits2=4800,
                    networth1=900000,
                    networth2=880000,
                    obj_damage1=110000,
                    obj_damage2=102000,
                    creeps1=2500,
                    creeps2=2400,
                )
            ]

    class FakePlayerService:
        def __init__(self) -> None:
            self.api = FakeApi()

    monkeypatch.setattr(web_app, "PlayerService", FakePlayerService)

    client = TestClient(web_app.app)
    response = client.get("/heroes/1/abrams/matchups")

    assert response.status_code == 200
    assert "Abrams Matchups" in response.text
    assert "Bebop" in response.text


def test_item_detail_page_renders(monkeypatch) -> None:
    class FakeApi:
        async def get_item_info(self, item_id: int) -> DeadlockItemInfo:
            return DeadlockItemInfo(
                item_id=item_id,
                name="Mystic Shot",
                image=None,
                shop_image="https://example.com/item.png",
                item_slot_type="weapon",
                item_tier=1,
                cost=500,
                is_active_item=False,
                item_type="upgrade",
                ability_type=None,
                hero_id=None,
            )

        async def get_item_stats(self, **kwargs: object) -> list[DeadlockItemStat]:
            mode = kwargs.get("game_mode")
            if mode == "normal":
                return [
                    DeadlockItemStat(
                        item_id=101,
                        wins=55,
                        losses=45,
                        matches=100,
                        players=80,
                        avg_buy_time_s=120.0,
                        avg_sell_time_s=None,
                        avg_buy_time_relative=None,
                        avg_sell_time_relative=None,
                    )
                ]
            return []

    class FakePlayerService:
        def __init__(self) -> None:
            self.api = FakeApi()

    monkeypatch.setattr(web_app, "PlayerService", FakePlayerService)

    client = TestClient(web_app.app)
    response = client.get("/items/101/mystic-shot")

    assert response.status_code == 200
    assert "Mystic Shot" in response.text
    assert "100 matches" in response.text


def test_item_detail_page_degrades_gracefully_when_stats_fail(monkeypatch) -> None:
    class FakeApi:
        async def get_item_info(self, item_id: int) -> DeadlockItemInfo:
            return DeadlockItemInfo(
                item_id=item_id,
                name="Mystic Shot",
                image=None,
                shop_image="https://example.com/item.png",
                item_slot_type="weapon",
                item_tier=1,
                cost=500,
                is_active_item=False,
                item_type="upgrade",
                ability_type=None,
                hero_id=None,
            )

        async def get_item_stats(self, **kwargs: object) -> list[DeadlockItemStat]:
            raise DeadlockError("Deadlock API took too long to respond. Try again in a moment.")

    class FakePlayerService:
        def __init__(self) -> None:
            self.api = FakeApi()

    monkeypatch.setattr(web_app, "PlayerService", FakePlayerService)

    client = TestClient(web_app.app)
    response = client.get("/items/101/mystic-shot")

    assert response.status_code == 200
    assert "Mystic Shot" in response.text
    assert "taking longer than usual" in response.text


def test_heroes_directory_page_renders(monkeypatch) -> None:
    class FakeApi:
        async def get_hero_info(self) -> dict[int, DeadlockHeroInfo]:
            return {
                1: DeadlockHeroInfo(
                    hero_id=1,
                    name="Abrams",
                    icon_small="https://example.com/abrams.png",
                    portrait_url=None,
                    background_image_url=None,
                )
            }

    class FakePlayerService:
        def __init__(self) -> None:
            self.api = FakeApi()

    monkeypatch.setattr(web_app, "PlayerService", FakePlayerService)

    client = TestClient(web_app.app)
    response = client.get("/heroes")

    assert response.status_code == 200
    assert "All Deadlock Heroes" in response.text
    assert "/heroes/1/abrams" in response.text


def test_items_directory_page_renders(monkeypatch) -> None:
    class FakeApi:
        async def get_all_item_info(self) -> dict[int, DeadlockItemInfo]:
            return {
                101: DeadlockItemInfo(
                    item_id=101,
                    name="Mystic Shot",
                    image=None,
                    shop_image="https://example.com/item.png",
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
    response = client.get("/items")

    assert response.status_code == 200
    assert "All Deadlock Items" in response.text
    assert "/items/101/mystic-shot" in response.text


def test_leaderboards_hub_page_renders(monkeypatch) -> None:
    class FakeApi:
        async def get_hero_info(self) -> dict[int, DeadlockHeroInfo]:
            return {
                1: DeadlockHeroInfo(
                    hero_id=1,
                    name="Abrams",
                    icon_small="https://example.com/abrams.png",
                    portrait_url=None,
                    background_image_url=None,
                )
            }

    class FakePlayerService:
        def __init__(self) -> None:
            self.api = FakeApi()

    monkeypatch.setattr(web_app, "PlayerService", FakePlayerService)

    client = TestClient(web_app.app)
    response = client.get("/leaderboards")

    assert response.status_code == 200
    assert "Deadlock Leaderboards" in response.text
    assert "/leaderboards/north-america" in response.text
    assert "/leaderboards/north-america/1/abrams" in response.text


def test_leaderboard_region_page_renders(monkeypatch) -> None:
    class FakeApi:
        async def get_leaderboard(self, *, region: str, hero_id: int | None = None) -> list:
            assert region == "NAmerica"
            assert hero_id is None
            return [
                type(
                    "LeaderboardEntry",
                    (),
                    {
                        "account_name": "TopPlayer",
                        "badge_level": 81,
                        "rank": 81,
                        "ranked_rank": None,
                        "ranked_subrank": None,
                        "possible_account_ids": [123],
                        "top_hero_ids": [1],
                    },
                )()
            ]

        async def get_hero_info(self) -> dict[int, DeadlockHeroInfo]:
            return {
                1: DeadlockHeroInfo(
                    hero_id=1,
                    name="Abrams",
                    icon_small="https://example.com/abrams.png",
                    portrait_url=None,
                    background_image_url=None,
                )
            }

        async def get_rank_info(self) -> list[DeadlockRankInfo]:
            return [
                DeadlockRankInfo(
                    tier=8,
                    name="Oracle",
                    color="#888",
                    image_small="https://example.com/oracle.png",
                    image_small_by_division={1: "https://example.com/oracle-1.png"},
                )
            ]

    class FakePlayerService:
        def __init__(self) -> None:
            self.api = FakeApi()

    monkeypatch.setattr(web_app, "PlayerService", FakePlayerService)

    client = TestClient(web_app.app)
    response = client.get("/leaderboards/north-america")

    assert response.status_code == 200
    assert "North America Deadlock Leaderboard" in response.text
    assert "TopPlayer" in response.text
    assert "/players/123/topplayer" in response.text
    assert "/leaderboards/north-america/1/abrams" in response.text


def test_rank_distribution_page_renders(monkeypatch) -> None:
    class FakeApi:
        async def get_player_rank_distribution(self) -> list[DeadlockPlayerRankDistribution]:
            return [
                DeadlockPlayerRankDistribution(rank=11, players=50),
                DeadlockPlayerRankDistribution(rank=81, players=20),
            ]

        async def get_rank_info(self) -> list[DeadlockRankInfo]:
            return [
                DeadlockRankInfo(tier=1, name="Initiate", color="#111", image_small=None, image_small_by_division={}),
                DeadlockRankInfo(tier=8, name="Oracle", color="#888", image_small=None, image_small_by_division={}),
            ]

        async def get_hero_info(self) -> dict[int, DeadlockHeroInfo]:
            return {
                1: DeadlockHeroInfo(
                    hero_id=1,
                    name="Abrams",
                    icon_small="https://example.com/abrams.png",
                    portrait_url=None,
                    background_image_url=None,
                )
            }

    class FakePlayerService:
        def __init__(self) -> None:
            self.api = FakeApi()

    monkeypatch.setattr(web_app, "PlayerService", FakePlayerService)

    client = TestClient(web_app.app)
    response = client.get("/rank-distribution")

    assert response.status_code == 200
    assert "Deadlock Rank Distribution" in response.text
    assert "Tracked Players" in response.text
    assert "/heroes/1/abrams/rank-distribution" in response.text


def test_filtered_best_heroes_page_is_noindex(monkeypatch) -> None:
    class FakeApi:
        async def get_hero_info(self) -> dict[int, DeadlockHeroInfo]:
            return {}

        async def get_hero_analytics(self, **_: object) -> list:
            return []

    class FakePlayerService:
        def __init__(self) -> None:
            self.api = FakeApi()

    monkeypatch.setattr(web_app, "PlayerService", FakePlayerService)

    client = TestClient(web_app.app)
    response = client.get("/best-heroes?window_days=30")

    assert response.status_code == 200
    assert '<meta name="robots" content="noindex,follow">' in response.text


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
    assert "Manual refresh is temporarily limited." in response.text
    assert "Showing the latest available match history instead" in response.text
    assert "oracle-1.png" in response.text
    assert '<link rel="canonical" href="http://testserver/players/123/tester">' in response.text


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


def test_legacy_player_url_redirects_to_canonical_slug(monkeypatch) -> None:
    class FakeApi:
        async def get_rank_info(self) -> list:
            return []

    class FakePlayerService:
        api = FakeApi()

        def rank_name(self, summary: PlayerSummary) -> str:
            return "Unknown"

        def win_rate(self, stat: DeadlockHeroStat) -> float:
            return 0.0

        def match_result_label(self, match: DeadlockMatch) -> str:
            return "Loss"

        def format_match_duration(self, seconds: int | None) -> str:
            return "0:00"

        def format_kda(self, kills: int | None, deaths: int | None, assists: int | None) -> str:
            return "0/0/0"

        async def resolve_player(self, raw_input: str) -> DeadlockPlayer:
            return DeadlockPlayer(
                account_id=123,
                personaname="Test Player",
                profileurl="https://steamcommunity.com/profiles/123",
                avatarfull=None,
                countrycode="CA",
                last_updated=None,
            )

        async def build_player_summary(self, player: DeadlockPlayer, *, refresh_matches: bool = False) -> PlayerSummary:
            return PlayerSummary(
                player=player,
                rank=None,
                hero_stats=[],
                recent_matches=[],
                hero_info={},
            )

    monkeypatch.setattr(web_app, "PlayerService", FakePlayerService)

    client = TestClient(web_app.app, follow_redirects=False)
    response = client.get("/players/123")

    assert response.status_code == 308
    assert response.headers["location"] == "http://testserver/players/123/test-player"


def test_canonical_player_url_does_not_redirect_forever_on_public_host(monkeypatch) -> None:
    class FakeApi:
        async def get_rank_info(self) -> list:
            return []

    class FakePlayerService:
        api = FakeApi()

        def rank_name(self, summary: PlayerSummary) -> str:
            return "Unknown"

        def win_rate(self, stat: DeadlockHeroStat) -> float:
            return 0.0

        def match_result_label(self, match: DeadlockMatch) -> str:
            return "Loss"

        def format_match_duration(self, seconds: int | None) -> str:
            return "0:00"

        def format_kda(self, kills: int | None, deaths: int | None, assists: int | None) -> str:
            return "0/0/0"

        async def resolve_player(self, raw_input: str) -> DeadlockPlayer:
            return DeadlockPlayer(
                account_id=123,
                personaname="Test Player",
                profileurl="https://steamcommunity.com/profiles/123",
                avatarfull=None,
                countrycode="CA",
                last_updated=None,
            )

        async def build_player_summary(self, player: DeadlockPlayer, *, refresh_matches: bool = False) -> PlayerSummary:
            return PlayerSummary(
                player=player,
                rank=None,
                hero_stats=[],
                recent_matches=[],
                hero_info={},
            )

    monkeypatch.setattr(web_app, "PlayerService", FakePlayerService)

    client = TestClient(web_app.app, follow_redirects=False)
    response = client.get("/players/123/test-player", headers={"host": "deadlockstattracker.com"})

    assert response.status_code == 200


def test_canonical_match_url_does_not_redirect_forever_on_public_host(monkeypatch) -> None:
    class FakeApi:
        async def get_match_metadata(self, match_id: int):
            from deadlock_tracker.models import DeadlockMatchMetadata

            return DeadlockMatchMetadata(
                match_id=match_id,
                start_time=1,
                duration_s=600,
                game_mode=1,
                match_mode=1,
                winning_team=0,
                players=[],
            )

        async def get_hero_info(self) -> dict[int, DeadlockHeroInfo]:
            return {}

        async def get_all_item_info(self) -> dict[int, DeadlockItemInfo]:
            return {}

        async def get_steam_profiles(self, account_ids: list[int]) -> dict[int, object]:
            return {}

    class FakePlayerService:
        def __init__(self) -> None:
            self.api = FakeApi()

        def format_kda(self, kills: int | None, deaths: int | None, assists: int | None) -> str:
            return "0/0/0"

        def format_match_duration(self, seconds: int | None) -> str:
            return "10:00"

        async def resolve_player(self, raw_input: str) -> DeadlockPlayer:
            return DeadlockPlayer(
                account_id=123,
                personaname="Test Player",
                profileurl="https://steamcommunity.com/profiles/123",
                avatarfull=None,
                countrycode="CA",
                last_updated=None,
            )

    monkeypatch.setattr(web_app, "PlayerService", FakePlayerService)

    client = TestClient(web_app.app, follow_redirects=False)
    response = client.get(
        "/players/123/test-player/matches/999",
        headers={"host": "deadlockstattracker.com"},
    )

    assert response.status_code == 200


def test_deadlock_api_adds_api_key_header(monkeypatch) -> None:
    monkeypatch.setattr("deadlock_tracker.clients.deadlock_api.get_settings", lambda: type(
        "Settings",
        (),
        {
            "deadlock_api_base_url": "https://api.deadlock-api.com",
            "deadlock_assets_base_url": "https://assets.deadlock-api.com",
            "deadlock_api_key": "test-key",
        },
    )())

    api = DeadlockAPI()

    assert api._request_headers()["X-API-KEY"] == "test-key"


def test_player_page_does_not_render_api_key(monkeypatch) -> None:
    secret = "super-secret-api-key-value"

    class FakeApi:
        async def get_rank_info(self) -> list:
            return []

    class FakePlayerService:
        api = FakeApi()

        def rank_name(self, summary: PlayerSummary) -> str:
            return "Unknown"

        def win_rate(self, stat: DeadlockHeroStat) -> float:
            return 0.0

        def match_result_label(self, match: DeadlockMatch) -> str:
            return "Loss"

        def format_match_duration(self, seconds: int | None) -> str:
            return "0:00"

        def format_kda(self, kills: int | None, deaths: int | None, assists: int | None) -> str:
            return "0/0/0"

        async def resolve_player(self, raw_input: str) -> DeadlockPlayer:
            return DeadlockPlayer(
                account_id=123,
                personaname="Test Player",
                profileurl="https://steamcommunity.com/profiles/123",
                avatarfull=None,
                countrycode="CA",
                last_updated=None,
            )

        async def build_player_summary(self, player: DeadlockPlayer, *, refresh_matches: bool = False) -> PlayerSummary:
            return PlayerSummary(
                player=player,
                rank=None,
                hero_stats=[],
                recent_matches=[],
                hero_info={},
            )

    monkeypatch.setattr(web_app, "PlayerService", FakePlayerService)
    monkeypatch.setattr("deadlock_tracker.clients.deadlock_api.get_settings", lambda: type(
        "Settings",
        (),
        {
            "deadlock_api_base_url": "https://api.deadlock-api.com",
            "deadlock_assets_base_url": "https://assets.deadlock-api.com",
            "deadlock_api_key": secret,
        },
    )())

    client = TestClient(web_app.app, follow_redirects=False)
    response = client.get("/players/123/test-player")

    assert response.status_code == 200
    assert secret not in response.text
