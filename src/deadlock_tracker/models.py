from __future__ import annotations

from dataclasses import dataclass, field


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
    signature_ability_class_names: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DeadlockHeroAnalytics:
    hero_id: int
    wins: int
    losses: int
    matches: int
    players: int | None


@dataclass(slots=True)
class DeadlockHeroCounterStat:
    hero_id: int
    enemy_hero_id: int
    wins: int
    matches_played: int
    kills: int
    enemy_kills: int
    deaths: int
    enemy_deaths: int
    assists: int
    enemy_assists: int
    denies: int
    enemy_denies: int
    last_hits: int
    enemy_last_hits: int
    networth: int
    enemy_networth: int
    obj_damage: int
    enemy_obj_damage: int
    creeps: int
    enemy_creeps: int


@dataclass(slots=True)
class DeadlockHeroSynergyStat:
    hero_id1: int
    hero_id2: int
    wins: int
    matches_played: int
    kills1: int
    kills2: int
    deaths1: int
    deaths2: int
    assists1: int
    assists2: int
    denies1: int
    denies2: int
    last_hits1: int
    last_hits2: int
    networth1: int
    networth2: int
    obj_damage1: int
    obj_damage2: int
    creeps1: int
    creeps2: int


@dataclass(slots=True)
class DeadlockBadgeDistribution:
    badge_level: int
    total_matches: int


@dataclass(slots=True)
class DeadlockPlayerRankDistribution:
    rank: int
    players: int


@dataclass(slots=True)
class DeadlockLeaderboardEntry:
    """The Matchmaking Update stopped the game sending badge data with
    leaderboards, so entries carry placement and heroes only."""

    account_name: str | None
    rank: int | None
    possible_account_ids: list[int]
    top_hero_ids: list[int]


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
    class_name: str = ""


@dataclass(slots=True)
class DeadlockItemStat:
    item_id: int
    wins: int
    losses: int
    matches: int
    players: int | None
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
    players: int | None


@dataclass(slots=True)
class DeadlockBuildMod:
    ability_id: int
    annotation: str | None
    imbue_target_ability_id: int | None
    required_flex_slots: int | None
    sell_priority: int | None


@dataclass(slots=True)
class DeadlockBuildCategory:
    name: str
    description: str | None
    optional: bool | None
    mods: list[DeadlockBuildMod]


@dataclass(slots=True)
class DeadlockHeroBuild:
    hero_build_id: int
    hero_id: int
    author_account_id: int
    name: str
    description: str | None
    language: int
    version: int
    origin_build_id: int
    publish_timestamp: int | None
    last_updated_timestamp: int | None
    development_build: bool | None
    tags: list[int]
    mod_categories: list[DeadlockBuildCategory]
    ability_order: list[int]


@dataclass(slots=True)
class DeadlockBuild:
    hero_build: DeadlockHeroBuild
    num_favorites: int | None
    num_ignores: int | None
    num_reports: int | None
    num_weekly_favorites: int | None
    rollup_category: int | None


@dataclass(slots=True)
class DeadlockHeroBuildStat:
    hero_id: int
    hero_build_id: int
    wins: int
    losses: int
    matches: int
    players: int | None


@dataclass(slots=True)
class DeadlockRankInfo:
    """One badge tier. The game no longer ships per-subrank art, so a tier has a
    single large badge plus an optional chalk variant."""

    tier: int
    name: str
    color: str | None
    image_large: str | None
    image_chalk: str | None


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
    player_match_outcome: int | None = None
    ranked_display_badge: int | None = None
    ranked_delta: int | None = None
    ranked_calibration_match: int | None = None
    ranked_used_demotion_protection: bool | None = None


@dataclass(slots=True)
class DeadlockMatchItem:
    item_id: int
    game_time_s: int | None
    sold_time_s: int | None


@dataclass(slots=True)
class DeadlockPlayerRankData:
    """Per-player ranked movement for one match, from `player_rank_data`."""

    initial_display_rank: int | None
    initial_flat_progress: int | None
    final_flat_progress: int | None
    desired_progress_change: int | None
    initial_calibration_games: int | None
    initial_demotion_protection_games: int | None
    consumed_demotion_protection: bool | None
    initial_win_streak: int | None


@dataclass(slots=True)
class DeadlockHeroXpReward:
    hero_id: int | None
    xp_grant: int | None
    reason: int | None


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
    player_match_outcome: int | None = None
    rank_data: DeadlockPlayerRankData | None = None
    hero_xp_rewards: list[DeadlockHeroXpReward] = field(default_factory=list)


@dataclass(slots=True)
class DeadlockMatchMetadata:
    match_id: int
    start_time: int | None
    duration_s: int | None
    game_mode: int | None
    match_mode: int | None
    winning_team: int | None
    players: list[DeadlockMatchPlayer]
    average_badge_team0: int | None = None
    average_badge_team1: int | None = None
    ranked_type: int | None = None
    rank_interval: int | None = None


@dataclass(slots=True)
class DeadlockPatch:
    title: str
    pub_date: str
    link: str
    guid: str
    author: str
    category: str
    creator: str
    content_html: str
    source: str = ""


@dataclass(slots=True)
class PlayerSummary:
    player: DeadlockPlayer
    rank: DeadlockRank | None
    hero_stats: list[DeadlockHeroStat]
    recent_matches: list[DeadlockMatch]
    hero_info: dict[int, DeadlockHeroInfo]
    ranked_match: DeadlockMatch | None = None
