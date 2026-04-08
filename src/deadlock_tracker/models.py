from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DeadlockPlayer:
    account_id: int
    personaname: str
    profileurl: str
    avatarfull: str | None
    countrycode: str | None
    last_updated: int | None


@dataclass(slots=True)
class DeadlockSteamProfile:
    account_id: int
    personaname: str
    profileurl: str
    avatarfull: str | None
    countrycode: str | None
    last_updated: int | None


@dataclass(slots=True)
class DeadlockRank:
    account_id: int
    match_id: int | None
    start_time: int | None
    player_score: float | None
    rank: int | None
    division: int | None
    division_tier: int | None


@dataclass(slots=True)
class DeadlockHeroStat:
    hero_id: int
    matches_played: int
    wins: int
    kills: float | None
    deaths: float | None
    assists: float | None
    last_played: int | None


@dataclass(slots=True)
class DeadlockHeroInfo:
    hero_id: int
    name: str
    icon_small: str | None
    portrait_url: str | None
    background_image_url: str | None


@dataclass(slots=True)
class DeadlockHeroAnalytics:
    hero_id: int
    wins: int
    losses: int
    matches: int
    players: int


@dataclass(slots=True)
class DeadlockBadgeDistribution:
    badge_level: int
    total_matches: int


@dataclass(slots=True)
class DeadlockPlayerRankDistribution:
    rank: int
    players: int


@dataclass(slots=True)
class DeadlockItemInfo:
    item_id: int
    name: str
    image: str | None
    shop_image: str | None
    item_slot_type: str | None
    item_tier: int | None
    cost: int | None
    is_active_item: bool
    item_type: str | None
    ability_type: str | None
    hero_id: int | None


@dataclass(slots=True)
class DeadlockItemStat:
    item_id: int
    wins: int
    losses: int
    matches: int
    players: int
    avg_buy_time_s: float | None
    avg_sell_time_s: float | None
    avg_buy_time_relative: float | None
    avg_sell_time_relative: float | None


@dataclass(slots=True)
class DeadlockAbilityOrderStat:
    abilities: list[int]
    wins: int
    losses: int
    matches: int
    players: int


@dataclass(slots=True)
class DeadlockRankInfo:
    tier: int
    name: str
    color: str | None
    image_small: str | None


@dataclass(slots=True)
class DeadlockMatch:
    match_id: int
    hero_id: int
    start_time: int
    match_duration_s: int | None
    game_mode: int | None
    match_mode: int | None
    player_team: int | None
    player_kills: int | None
    player_deaths: int | None
    player_assists: int | None
    net_worth: int | None
    last_hits: int | None
    match_result: int | None


@dataclass(slots=True)
class DeadlockMatchItem:
    item_id: int
    game_time_s: int | None
    sold_time_s: int | None


@dataclass(slots=True)
class DeadlockMatchPlayer:
    account_id: int
    team: int | None
    hero_id: int
    kills: int | None
    deaths: int | None
    assists: int | None
    net_worth: int | None
    last_hits: int | None
    denies: int | None
    level: int | None
    assigned_lane: int | None
    mvp_rank: int | None
    player_damage: int | None
    objective_damage: int | None
    healing: int | None
    items: list[DeadlockMatchItem]


@dataclass(slots=True)
class DeadlockMatchMetadata:
    match_id: int
    start_time: int | None
    duration_s: int | None
    game_mode: int | None
    match_mode: int | None
    winning_team: int | None
    players: list[DeadlockMatchPlayer]


@dataclass(slots=True)
class PlayerSummary:
    player: DeadlockPlayer
    rank: DeadlockRank | None
    hero_stats: list[DeadlockHeroStat]
    recent_matches: list[DeadlockMatch]
    hero_info: dict[int, DeadlockHeroInfo]
