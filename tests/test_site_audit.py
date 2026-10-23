import asyncio
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from deadlock_tracker.clients.deadlock_api import DeadlockAPI, DeadlockError, friendly_rank_name
from deadlock_tracker.models import DeadlockHeroStat, DeadlockMatch, DeadlockPlayer
from deadlock_tracker.services.player_service import PlayerService
from deadlock_tracker.web import app as web
from deadlock_tracker.clients import deadlock_api as client_module


def match(**changes):
    return replace(DeadlockMatch(1, 1, 100, 600, 1, 4, 0, 10, 2, 5, 1000, 20, 0), **changes)


def player():
    return DeadlockPlayer(123, "Tester", "https://steamcommunity.com/profiles/76561197960265851", None, None, None)


@pytest.mark.parametrize("raw", ["123", "76561197960265851", "https://steamcommunity.com/profiles/76561197960265851", "steamcommunity.com/profiles/76561197960265851/"])
def test_player_ids_resolve_to_the_same_account(raw):
    assert asyncio.run(DeadlockAPI().resolve_player_input(raw)) == 123


@pytest.mark.parametrize("raw", ["0", "4294967296", "https://evil.example/steamcommunity.com/profiles/76561197960265851"])
def test_invalid_account_input_is_rejected(raw):
    with pytest.raises(DeadlockError):
        asyncio.run(DeadlockAPI().resolve_player_input(raw))


def test_current_rank_names_and_filter_labels_agree():
    for badge, name in [(31, "Acolyte"), (41, "Sentinel"), (51, "Mystic"), (61, "Ritualist"), (71, "Emissary")]:
        assert friendly_rank_name(badge) == f"{name} 1"
        assert next(x.label for x in web._rank_floor_options() if x.value == str(badge)) == f"{name}+"


def test_vanity_url_uses_steam_identity_instead_of_display_name_search():
    api = DeadlockAPI()
    async def text(url, params=None):
        assert url == 'https://steamcommunity.com/id/some-slug/'
        assert params == {'xml': '1'}
        return '<profile><steamID64>76561197960265851</steamID64></profile>'
    api._get_text = text
    assert asyncio.run(api.resolve_player_input('https://steamcommunity.com/id/some-slug/')) == 123


def test_unknown_results_and_kda_do_not_become_losses_or_zero():
    assert PlayerService.match_result_label(match(match_result=None)) == "Unknown"
    assert PlayerService.format_kda(None, 0, 5) == "—/0/5"


def test_player_hero_stats_use_current_endpoint_and_account_filter():
    api = DeadlockAPI()
    async def get(url, params=None):
        assert url.endswith('/v1/players/hero-stats')
        assert params == {"account_ids": "123", "game_mode": "normal", "match_mode": "ranked,unranked"}
        return [dict(account_id=account, hero_id=1, matches_played=200, wins=100) for account in [123, 456]]
    api._get_json = get
    assert len(asyncio.run(api.get_hero_stats(123))) == 1


def test_minimum_hero_matches_is_enforced_without_unsupported_query():
    api = DeadlockAPI()
    async def get(url, params=None):
        assert 'min_matches' not in params
        return [dict(hero_id=hero, wins=1, losses=1, matches=count) for hero, count in [(1, 99), (2, 100)]]
    api._get_json = get
    assert [x.hero_id for x in asyncio.run(api.get_hero_analytics(min_matches=100))] == [2]


def test_match_history_is_sorted_and_deduplicated_before_limit():
    api = DeadlockAPI()
    async def get(url, params=None):
        return [dict(match_id=i, hero_id=1, start_time=i) for i in [1, 3, 2, 3]]
    api._get_json = get
    assert [x.match_id for x in asyncio.run(api.get_match_history(123, limit=2))] == [3, 2]


@pytest.mark.parametrize('fail_totals', [False, True])
def test_profile_uses_tracked_totals_and_labels_partial_fallback(fail_totals):
    class API:
        async def get_hero_info(self): return {}
        async def get_player_rank(self, account): raise DeadlockError('unavailable')
        async def get_match_history(self, account, **kwargs): return [match()]
        async def get_hero_stats(self, account):
            if fail_totals: raise DeadlockError('unavailable')
            return [DeadlockHeroStat(1, 200, 100, 1000, 200, 500, 100)]
    summary = asyncio.run(PlayerService(API()).build_player_summary(player()))
    assert summary.hero_stats[0].matches_played == (1 if fail_totals else 200)
    assert summary.hero_stats_scope == ('Recent Matches' if fail_totals else 'Tracked Matches')
    assert len(summary.recent_matches) == 1
    assert summary.notices


def test_refresh_redirect_does_not_call_stats_until_canonical_route(monkeypatch):
    calls = []
    class Service:
        async def resolve_player(self, raw): return player()
        async def build_player_summary(self, *args, **kwargs): calls.append(kwargs)
    monkeypatch.setattr(web, 'PlayerService', Service)
    web._rate_limit_hits.clear()
    response = TestClient(web.app).get('/players/123?refresh=1', follow_redirects=False)
    assert response.status_code == 308
    assert response.headers['location'].endswith('/players/123/tester?refresh=1')
    assert calls == []


def test_forum_requests_do_not_receive_api_credentials(monkeypatch):
    class Response:
        status = 200
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def text(self): return 'forum content'
    class Session:
        def __init__(self, **kwargs):
            assert 'X-API-KEY' not in kwargs['headers']
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        def get(self, *args, **kwargs): return Response()
    monkeypatch.setattr(client_module.aiohttp, 'ClientSession', Session)
    api = DeadlockAPI()
    api.api_key = 'test-only-secret'
    assert asyncio.run(api._get_text('https://forums.playdeadlock.com/threads/example/')) == 'forum content'


def test_history_failure_does_not_hide_available_player_totals():
    class API:
        async def get_hero_info(self): return {}
        async def get_player_rank(self, account): return None
        async def get_match_history(self, account, **kwargs): raise DeadlockError('rate limited')
        async def get_hero_stats(self, account): return [DeadlockHeroStat(1, 200, 100, 1000, 200, 500, 100)]
    summary = asyncio.run(PlayerService(API()).build_player_summary(player()))
    assert summary.hero_stats[0].matches_played == 200
    assert summary.recent_matches == []
    assert any('history' in text for text in summary.notices)
