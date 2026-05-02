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
    detail_url: str
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
    detail_url: str
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
    hero_id: int
    rank_number: int
    hero_name: str
    detail_url: str
    hero_icon_url: str | None
    win_rate_percent: str
    pick_rate_percent: str
    matches_text: str
    players_text: str
    wins_text: str
    losses_text: str


@dataclass(slots=True)
class StreetBrawlBuildItemView:
    rank_number: int
    item_name: str
    item_image_url: str | None
    slot_type: str
    tier_text: str
    cost_text: str
    win_rate_percent: str
    matches_text: str
    players_text: str
    avg_buy_time_text: str
    wins_text: str
    losses_text: str


@dataclass(slots=True)
class StreetBrawlAbilityStepView:
    step_number: int
    ability_point: str
    ability_name: str
    ability_image_url: str | None
    ability_type: str


@dataclass(slots=True)
class SkillPathCellView:
    step_number: int
    marker: str
    is_active: bool
    is_unlock: bool


@dataclass(slots=True)
class SkillPathRowView:
    ability_point: str
    ability_name: str
    ability_image_url: str | None
    cells: list[SkillPathCellView]


@dataclass(slots=True)
class StreetBrawlGuideView:
    hero_name: str
    hero_icon_url: str | None
    hero_portrait_url: str | None
    hero_background_image_url: str | None
    ability_steps: list[StreetBrawlAbilityStepView]
    skill_path_rows: list[SkillPathRowView]
    ability_path_text: str
    path_matches_text: str
    path_players_text: str
    path_win_rate_percent: str


@dataclass(slots=True)
class StreetBrawlHeroCardView:
    hero_id: int
    hero_name: str
    hero_icon_url: str | None
    hero_portrait_url: str | None
    hero_background_image_url: str | None
    build_url: str


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
    top_percent_text: str
    bars: list[RankDistributionBarView]


@dataclass(slots=True)
class MatchDetailItemView:
    item_name: str
    item_image_url: str | None


@dataclass(slots=True)
class ProfileOverviewView:
    account_id: int
    personaname: str
    profileurl: str
    avatarfull: str | None
    countrycode: str | None
    rank_name: str
    rank_badge_image_url: str | None
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
    items: list[MatchDetailItemView]
    leads_souls: bool = False
    leads_kills: bool = False
    leads_assists: bool = False
    leads_player_damage: bool = False
    leads_objective_damage: bool = False
    leads_healing: bool = False
    leads_last_hits: bool = False


@dataclass(slots=True)
class MatchDetailOverviewView:
    match_id: int
    queue_name: str
    started_text: str
    duration: str
    winning_team_label: str
    viewed_player_result: str
    viewed_player_name: str
    average_rank_text: str


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


@dataclass(slots=True)
class PatchNoteView:
    title: str
    detail_url: str
    published_text: str
    author_text: str
    summary_lines: list[str]
    full_summary_lines: list[str]
    summary_truncated: bool
    official_url: str


@dataclass(slots=True)
class HeroDetailItemView:
    item_name: str
    item_url: str
    item_image_url: str | None
    slot_type: str
    tier_text: str
    cost_text: str
    win_rate_percent: str
    matches_text: str


@dataclass(slots=True)
class HeroPeerStatView:
    hero_name: str
    hero_url: str
    hero_icon_url: str | None
    win_rate_percent: str
    matches_text: str
    summary_text: str


@dataclass(slots=True)
class PaginationLinkView:
    label: str
    url: str


@dataclass(slots=True)
class ItemModeStatView:
    mode_name: str
    win_rate_percent: str
    matches_text: str
    players_text: str
    timing_text: str


@dataclass(slots=True)
class HeroDirectoryCardView:
    hero_name: str
    detail_url: str
    build_url: str
    street_brawl_build_url: str
    hero_icon_url: str | None
    hero_portrait_url: str | None
    hero_background_image_url: str | None


@dataclass(slots=True)
class ItemDirectoryCardView:
    item_name: str
    detail_url: str
    item_image_url: str | None
    slot_type: str
    tier_text: str
    cost_text: str


@dataclass(slots=True)
class LeaderboardRegionCardView:
    region_slug: str
    region_name: str
    detail_url: str
    description: str


@dataclass(slots=True)
class LeaderboardEntryView:
    rank_number: int
    player_name: str
    player_url: str | None
    avatarfull: str | None
    hero_names_text: str
    rank_name: str
    rank_badge_image_url: str | None


@dataclass(slots=True)
class RankDistributionSummaryView:
    label: str
    value: str
    detail: str


@dataclass(slots=True)
class HeroBuildCardView:
    build_name: str
    build_id: int
    version_text: str
    updated_text: str
    description: str | None
    favorite_text: str
    weekly_favorite_text: str
    win_rate_percent: str | None
    matches_text: str | None
    players_text: str | None
    categories: list[str]
    item_names: list[str]
