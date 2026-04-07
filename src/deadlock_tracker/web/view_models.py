from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class HeroStatView:
    hero_name: str
    matches_played: int
    wins: int
    win_rate_percent: str
    kda: str


@dataclass(slots=True)
class MatchView:
    hero_name: str
    match_id: int
    result: str
    duration: str
    kda: str
    net_worth: int
    last_hits: int


@dataclass(slots=True)
class SearchResultView:
    account_id: int
    personaname: str
    profileurl: str
    avatarfull: str | None
    countrycode: str | None


@dataclass(slots=True)
class ProfileOverviewView:
    account_id: int
    personaname: str
    profileurl: str
    avatarfull: str | None
    countrycode: str | None
    rank_name: str
    rating_text: str
    cache_updated_text: str
    cache_updated_raw: int | None
