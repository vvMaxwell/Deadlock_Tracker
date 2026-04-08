from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class HeroStatView:
    hero_name: str
    hero_icon_url: str | None
    matches_played: int
    wins: int
    win_rate_percent: str
    kda: str


@dataclass(slots=True)
class MatchView:
    hero_name: str
    hero_icon_url: str | None
    detail_url: str
    queue_name: str
    result: str
    duration: str
    played_text: str
    kda: str
    net_worth: int
    last_hits: int


@dataclass(slots=True)
class ModeSummaryView:
    label: str
    count: int


@dataclass(slots=True)
class SearchResultView:
    account_id: int
    personaname: str
    profileurl: str
    avatarfull: str | None
    countrycode: str | None


@dataclass(slots=True)
class FilterOptionView:
    value: str
    label: str


@dataclass(slots=True)
class BestItemView:
    item_id: int
    item_name: str
    item_image_url: str | None
    slot_type: str
    tier_text: str
    cost_text: str
    matches_text: str
    players_text: str
    win_rate_percent: str
    wins_text: str
    losses_text: str
    avg_buy_time_text: str


@dataclass(slots=True)
class BestHeroView:
    rank_number: int
    hero_name: str
    hero_icon_url: str | None
    win_rate_percent: str
    pick_rate_percent: str
    matches_text: str
    players_text: str
    wins_text: str
    losses_text: str


@dataclass(slots=True)
class RankDistributionBarView:
    badge_level: int
    tier_name: str
    division_label: str
    matches_text: str
    share_text: str
    height_percent: float
    color: str


@dataclass(slots=True)
class RankDistributionTierView:
    tier_name: str
    bars: list[RankDistributionBarView]


@dataclass(slots=True)
class ProfileOverviewView:
    account_id: int
    personaname: str
    profileurl: str
    avatarfull: str | None
    countrycode: str | None
    rank_name: str
    rank_updated_text: str
    rank_is_stale: bool
    cache_updated_text: str
    latest_match_text: str


@dataclass(slots=True)
class MatchDetailPlayerView:
    account_id: int
    personaname: str
    profileurl: str
    avatarfull: str | None
    hero_name: str
    hero_icon_url: str | None
    team: int | None
    result: str
    is_viewed_player: bool
    kills: int
    deaths: int
    assists: int
    kda: str
    souls: int
    player_damage: int
    objective_damage: int
    healing: int
    last_hits: int
    denies: int
    level: int
    lane_number: int | None
    lane_text: str


@dataclass(slots=True)
class MatchDetailOverviewView:
    match_id: int
    queue_name: str
    started_text: str
    duration: str
    winning_team_label: str
    viewed_player_result: str
    viewed_player_name: str


@dataclass(slots=True)
class MatchLaneView:
    lane_number: int | None
    lane_text: str
    team_zero: list[MatchDetailPlayerView]
    team_one: list[MatchDetailPlayerView]


@dataclass(slots=True)
class MatchupRowView:
    lane_number: int | None
    lane_text: str
    left_player: MatchDetailPlayerView | None
    right_player: MatchDetailPlayerView | None
