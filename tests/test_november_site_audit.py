from types import SimpleNamespace
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient

from deadlock_tracker.clients.deadlock_api import DeadlockError
from deadlock_tracker.web import app as web


class RankingAPI:
    async def get_hero_info(self):
        return {1: SimpleNamespace(hero_id=1, name='Infernus')}

    async def get_hero_rank_distribution(self, hero_id):
        raise DeadlockError('No data found for that Deadlock player.')

    async def get_player_rank_distribution(self):
        return []

    async def get_rank_info(self):
        return {}

    async def get_all_item_info(self):
        return {}

    async def get_patches(self, **kwargs):
        return []


def test_legacy_hero_rank_bookmark_redirects_to_overall_distribution(monkeypatch):
    monkeypatch.setattr(web, 'PlayerService', lambda: SimpleNamespace(api=RankingAPI()))
    with TestClient(web.app) as client:
        response = client.get('/heroes/1/infernus/rank-distribution', follow_redirects=False)
    assert response.status_code == 308
    assert response.headers['location'] == '/rank-distribution'


def test_overall_distribution_explains_removal_and_does_not_fetch_heroes(monkeypatch):
    api = RankingAPI()

    async def unavailable():
        raise DeadlockError('Hero assets are unavailable')

    monkeypatch.setattr(api, 'get_hero_info', unavailable)
    monkeypatch.setattr(web, 'PlayerService', lambda: SimpleNamespace(api=api))
    response = TestClient(web.app).get('/rank-distribution')
    assert response.status_code == 200
    assert 'Hero-specific rank distributions are no longer available' in response.text
    assert 'Hero Rank Pages' not in response.text


def test_sitemap_omits_retired_hero_rank_pages(monkeypatch):
    monkeypatch.setattr(web, 'PlayerService', lambda: SimpleNamespace(api=RankingAPI()))
    response = TestClient(web.app).get('/sitemap.xml')
    paths = [node.text for node in ElementTree.fromstring(response.content).findall('.//{*}loc')]
    assert 'http://testserver/heroes/1/infernus' in paths
    assert [path for path in paths if path and path.endswith('/rank-distribution')] == ['http://testserver/rank-distribution']


@pytest.mark.parametrize('authority', ['deadlockstattracker.com', 'www.deadlockstattracker.com'])
def test_production_links_stay_https_behind_the_http_proxy(monkeypatch, authority):
    class SearchService:
        async def search_players(self, query):
            return [SimpleNamespace(account_id=123, personaname='Tester', profileurl=None, avatarfull=None, countrycode=None)]

    monkeypatch.setattr(web, 'PlayerService', SearchService)
    with TestClient(web.app, base_url=f'http://{authority}') as client:
        result = client.get('/api/player-search?q=Tester').json()['results'][0]
        assert result['detail_url'] == f'https://{authority}/players/123/tester'


@pytest.mark.parametrize('authority, scheme', [
    ('deadlockstattracker.com:443', 'https'),
    ('www.deadlockstattracker.com:443', 'https'),
    ('127.0.0.1:8000', 'http'),
    ('preview.example', 'http'),
])
def test_router_redirect_uses_expected_scheme(authority, scheme):
    response = TestClient(web.app).get('/heroes/', headers={'Host': authority}, follow_redirects=False)
    assert response.headers['location'] == f'{scheme}://{authority}/heroes'


def test_home_does_not_advertise_retired_hero_rank_pages():
    response = TestClient(web.app).get('/')
    assert response.status_code == 200
    assert 'hero-specific rank pages' not in response.text
