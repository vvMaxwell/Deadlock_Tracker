"""Contract tests for the October gold source, hero swap, and convar additions."""

import asyncio

import pytest

from deadlock_tracker.clients.deadlock_api import DeadlockAPI, DeadlockError
from deadlock_tracker.web.app import TEMPLATES


def api_with_payload(payload):
    api = DeadlockAPI()
    calls = []

    async def get_json(url, params=None):
        calls.append((url, params))
        return payload

    api._get_json = get_json
    return api, calls


def test_metadata_preserves_all_gold_sources_from_final_snapshot():
    names = [
        "players", "lane_creeps", "neutrals", "bosses", "treasure", "assists",
        "denies", "team_bonus", "ability_assassinate", "item_trophy_collector",
        "item_cultist_sacrifice", "breakable", "item_goose_egg",
    ]
    sources = [dict(source=i, kills=i, damage=i * 10, gold=i * 100, gold_orbs=0)
               for i in range(1, 14)]
    sources += [dict(source=99, gold=None)]
    api, _ = api_with_payload({"match_info": {"players": [{
        "account_id": 1, "hero_id": 2,
        "stats": [
            {"gold_sources": [{"source": 1, "gold": 90}]},
            {"gold_sources": sources, "player_damage": 1234},
        ],
    }]}})
    player = asyncio.run(api.get_match_metadata(10)).players[0]
    assert player.player_damage == 1234
    assert [entry.name for entry in player.gold_sources[:-1]] == names
    for entry, expected in zip(player.gold_sources, sources):
        assert entry.gold == expected["gold"]
        assert entry.kills == expected.get("kills")
        assert entry.damage == expected.get("damage")
        assert entry.gold_orbs == expected.get("gold_orbs")
    assert player.gold_sources[-1].name == "source_99"
    html = TEMPLATES.env.get_template("gold_sources.html").render(gold_sources=player.gold_sources)
    assert "Show soul sources" in html
    assert "Goose Egg" in html
    assert "Souls 100" in html
    assert "Orb souls 0" in html
    assert "Souls —" in html


@pytest.mark.parametrize("stats", [None, [], {}, [None], [{}], [{"gold_sources": None}],
                                    [{"gold_sources": [None, {}, {"source": None}]}]])
def test_old_or_incomplete_metadata_has_no_fabricated_gold_sources(stats):
    api, _ = api_with_payload({"match_info": {"players": [{
        "account_id": 1, "hero_id": 2, "stats": stats,
    }]}})
    player = asyncio.run(api.get_match_metadata(10)).players[0]
    assert player.gold_sources == []
    assert not TEMPLATES.env.get_template("gold_sources.html").render(gold_sources=[]).strip()


def test_hero_swaps_use_supported_filters_and_preserve_sample_counts():
    api, calls = api_with_payload([{
        "hero_id": 2, "bucket": 0, "matches": 100, "swapped_in": 20,
        "swapped_in_wins": 12, "pregame_picks": 90, "swapped_away": 10,
        "future_field": True,
    }])
    row, = asyncio.run(api.get_hero_swap_stats(
        match_mode="ranked", min_unix_timestamp=0, max_unix_timestamp=123,
        min_average_badge=0, max_average_badge=116,
    ))
    assert row.matches == 100
    assert (row.swapped_in, row.swapped_in_wins, row.pregame_picks, row.swapped_away) == (20, 12, 90, 10)
    assert calls == [(f"{api.base_url}/v1/analytics/hero-swap-stats", {
        "bucket": "no_bucket", "match_mode": "ranked", "min_unix_timestamp": "0",
        "max_unix_timestamp": "123", "min_average_badge": "0", "max_average_badge": "116",
    })]


@pytest.mark.parametrize("value", [False, 0, 1.5, "", [1, 2, 3, 4]])
def test_convars_keep_native_default_values_and_use_main_api(value):
    payload = {"type": "test", "default": value, "flags": 131074}
    api, calls = api_with_payload({"test": payload})
    convars = asyncio.run(api.get_convars(client_version=6774))
    assert convars["test"].default == value
    assert type(convars["test"].default) is type(value)
    assert convars["test"].description is None
    assert calls == [(f"{api.base_url}/v1/assets/convars", {"client_version": "6774"})]
    api, calls = api_with_payload(payload)
    assert asyncio.run(api.get_convar("test/name")).flags == 131074
    assert calls == [(f"{api.base_url}/v1/assets/convars/test%2Fname", None)]


def test_new_endpoints_propagate_api_errors():
    api = DeadlockAPI()

    async def fail(url, params=None):
        raise DeadlockError("Unavailable")

    api._get_json = fail
    for call in (api.get_convars, lambda: api.get_convar("unknown"), api.get_hero_swap_stats):
        with pytest.raises(DeadlockError, match="Unavailable"):
            asyncio.run(call())
