from __future__ import annotations

from pathlib import Path
from time import time

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from deadlock_tracker.clients.deadlock_api import DeadlockError
from deadlock_tracker.services.player_service import PlayerService
from deadlock_tracker.web.view_models import (
    BestItemView,
    BestHeroView,
    FilterOptionView,
    HeroStatView,
    MatchLaneView,
    MatchDetailOverviewView,
    MatchDetailPlayerView,
    MatchView,
    MatchupRowView,
    ProfileOverviewView,
    RankDistributionBarView,
    RankDistributionTierView,
    SearchResultView,
)


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Deadlock Tracker", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def _html_response(response: HTMLResponse) -> HTMLResponse:
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, query: str | None = None) -> HTMLResponse:
    player_service = PlayerService()
    api = player_service.api
    search_results: list[SearchResultView] = []
    error_message: str | None = None
    rank_distribution: list[RankDistributionTierView] = []

    if query:
        cleaned_query = query.strip()
        try:
            if _is_direct_player_lookup(cleaned_query):
                resolved = await player_service.resolve_player(cleaned_query)
                if not isinstance(resolved, list):
                    player_url = request.url_for("player_profile", player_input=str(resolved.account_id))
                    return RedirectResponse(url=str(player_url), status_code=303)

            players = await player_service.search_players(cleaned_query)
            search_results = [
                SearchResultView(
                    account_id=player.account_id,
                    personaname=player.personaname,
                    profileurl=player.profileurl,
                    avatarfull=player.avatarfull,
                    countrycode=player.countrycode,
                )
                for player in players[:8]
            ]
        except DeadlockError as error:
            error_message = str(error)

    try:
        badge_distribution = await api.get_badge_distribution()
        rank_info = await api.get_rank_info()
        rank_distribution = _build_rank_distribution_views(badge_distribution, rank_info)
    except DeadlockError:
        rank_distribution = []

    return _html_response(TEMPLATES.TemplateResponse(
        request,
        "index.html",
        {
            "query": query or "",
            "results": search_results,
            "error_message": error_message,
            "rank_distribution": rank_distribution,
        },
    ))


@app.get("/faq", response_class=HTMLResponse)
async def faq(request: Request) -> HTMLResponse:
    screenshot_rel = "/help/steam-account-url-guide.png"
    screenshot_abs = BASE_DIR / "static" / "help" / "steam-account-url-guide.png"
    return _html_response(TEMPLATES.TemplateResponse(
        request,
        "faq.html",
        {
            "screenshot_url": str(request.url_for("static", path=screenshot_rel)) if screenshot_abs.exists() else None,
        },
    ))


@app.get("/credits", response_class=HTMLResponse)
async def credits(request: Request) -> HTMLResponse:
    return _html_response(TEMPLATES.TemplateResponse(request, "credits.html", {}))


@app.get("/disclaimers", response_class=HTMLResponse)
async def disclaimers(request: Request) -> HTMLResponse:
    return _html_response(TEMPLATES.TemplateResponse(request, "disclaimers.html", {}))


@app.get("/help/steam-account-url", response_class=HTMLResponse)
async def steam_account_url_help(request: Request) -> HTMLResponse:
    return RedirectResponse(url=str(request.url_for("faq")) + "#steam-account-url", status_code=307)


@app.get("/best-items", response_class=HTMLResponse)
async def best_items(
    request: Request,
    hero_id: str | None = None,
    rank_floor: str | None = "81",
    mode: str = "normal",
    window_days: int = 7,
    min_matches: str | None = "1000",
) -> HTMLResponse:
    player_service = PlayerService()
    api = player_service.api
    error_message: str | None = None

    selected_mode = mode if mode in {"normal", "street_brawl"} else "normal"
    selected_window_days = window_days if window_days in {7, 30, 90} else 7
    parsed_hero_id = _parse_optional_int(hero_id)
    parsed_rank_floor = _parse_optional_int(rank_floor)
    parsed_min_matches = _parse_optional_int(min_matches)
    selected_min_matches = min(max(parsed_min_matches or 1000, 100), 5000)
    selected_rank_floor = (
        parsed_rank_floor
        if parsed_rank_floor in {11, 21, 31, 41, 51, 61, 71, 81, 91, 101, 111}
        else None
    )

    hero_info = await api.get_hero_info()
    rank_options = _rank_floor_options()
    best_item_rows: list[BestItemView] = []
    selected_hero_id = parsed_hero_id if parsed_hero_id in hero_info else None

    try:
        stats = await api.get_item_stats(
            hero_id=selected_hero_id,
            game_mode=selected_mode,
            min_matches=selected_min_matches,
            min_average_badge=selected_rank_floor,
            min_unix_timestamp=int(time()) - selected_window_days * 86400,
        )
        ranked_stats = sorted(
            stats,
            key=lambda item: ((item.wins / item.matches) if item.matches else 0.0, item.matches),
            reverse=True,
        )[:24]
        item_info_map = await api.get_all_item_info()

        for stat in ranked_stats:
            item_info = item_info_map.get(stat.item_id)
            if item_info is None:
                continue
            best_item_rows.append(
                BestItemView(
                    item_id=stat.item_id,
                    item_name=item_info.name,
                    item_image_url=item_info.shop_image or item_info.image,
                    slot_type=_friendly_slot_type(item_info.item_slot_type),
                    tier_text=f"Tier {item_info.item_tier}" if item_info.item_tier else "Tier Unknown",
                    cost_text=f"{item_info.cost:,} souls" if item_info.cost else "Cost Unknown",
                    matches_text=f"{stat.matches:,} matches",
                    players_text=f"{stat.players:,} players",
                    win_rate_percent=f"{(stat.wins / stat.matches):.1%}" if stat.matches else "0.0%",
                    wins_text=f"{stat.wins:,} wins",
                    losses_text=f"{stat.losses:,} losses",
                    avg_buy_time_text=_friendly_time_seconds(stat.avg_buy_time_s),
                )
            )
    except DeadlockError as error:
        error_message = str(error)

    return _html_response(TEMPLATES.TemplateResponse(
        request,
        "best_items.html",
        {
            "hero_options": [
                FilterOptionView(value="", label="All heroes"),
                *[
                    FilterOptionView(value=str(hero.hero_id), label=hero.name)
                    for hero in sorted(hero_info.values(), key=lambda item: item.name.casefold())
                ],
            ],
            "rank_options": rank_options,
            "mode_options": [
                FilterOptionView(value="normal", label="Normal"),
                FilterOptionView(value="street_brawl", label="Street Brawl"),
            ],
            "window_options": [
                FilterOptionView(value="7", label="Last 7 days"),
                FilterOptionView(value="30", label="Last 30 days"),
                FilterOptionView(value="90", label="Last 90 days"),
            ],
            "selected_hero_id": str(selected_hero_id) if selected_hero_id is not None else "",
            "selected_rank_floor": str(selected_rank_floor) if selected_rank_floor is not None else "",
            "selected_mode": selected_mode,
            "selected_window_days": str(selected_window_days),
            "selected_min_matches": selected_min_matches,
            "items": best_item_rows,
            "error_message": error_message,
        },
    ))


@app.get("/best-heroes", response_class=HTMLResponse)
async def best_heroes(
    request: Request,
    rank_floor: str | None = "81",
    mode: str = "normal",
    window_days: int = 7,
    min_matches: str | None = "1000",
) -> HTMLResponse:
    player_service = PlayerService()
    api = player_service.api
    error_message: str | None = None

    selected_mode = mode if mode in {"normal", "street_brawl"} else "normal"
    selected_window_days = window_days if window_days in {7, 30, 90} else 7
    parsed_rank_floor = _parse_optional_int(rank_floor)
    parsed_min_matches = _parse_optional_int(min_matches)
    selected_min_matches = min(max(parsed_min_matches or 1000, 100), 5000)
    selected_rank_floor = (
        parsed_rank_floor
        if parsed_rank_floor in {11, 21, 31, 41, 51, 61, 71, 81, 91, 101, 111}
        else None
    )

    hero_info = await api.get_hero_info()
    hero_rows: list[BestHeroView] = []

    try:
        stats = await api.get_hero_analytics(
            game_mode=selected_mode,
            min_matches=selected_min_matches,
            min_average_badge=selected_rank_floor,
            min_unix_timestamp=int(time()) - selected_window_days * 86400,
        )
        filtered_stats = [item for item in stats if item.hero_id in hero_info]
        total_matches = sum(item.matches for item in filtered_stats)
        ranked_stats = sorted(
            filtered_stats,
            key=lambda item: (
                (item.wins / item.matches) if item.matches else 0.0,
                (item.matches / total_matches) if total_matches else 0.0,
                item.matches,
            ),
            reverse=True,
        )

        for index, stat in enumerate(ranked_stats, start=1):
            hero = hero_info.get(stat.hero_id)
            if hero is None:
                continue
            pick_rate = (stat.matches / total_matches) if total_matches else 0.0
            hero_rows.append(
                BestHeroView(
                    rank_number=index,
                    hero_name=hero.name,
                    hero_icon_url=hero.icon_small,
                    win_rate_percent=f"{(stat.wins / stat.matches):.1%}" if stat.matches else "0.0%",
                    pick_rate_percent=f"{pick_rate:.1%}",
                    matches_text=f"{stat.matches:,} matches",
                    players_text=f"{stat.players:,} players",
                    wins_text=f"{stat.wins:,} wins",
                    losses_text=f"{stat.losses:,} losses",
                )
            )
    except DeadlockError as error:
        error_message = str(error)

    return _html_response(TEMPLATES.TemplateResponse(
        request,
        "best_heroes.html",
        {
            "rank_options": _rank_floor_options(),
            "mode_options": [
                FilterOptionView(value="normal", label="Normal"),
                FilterOptionView(value="street_brawl", label="Street Brawl"),
            ],
            "window_options": [
                FilterOptionView(value="7", label="Last 7 days"),
                FilterOptionView(value="30", label="Last 30 days"),
                FilterOptionView(value="90", label="Last 90 days"),
            ],
            "selected_rank_floor": str(selected_rank_floor) if selected_rank_floor is not None else "",
            "selected_mode": selected_mode,
            "selected_window_days": str(selected_window_days),
            "selected_min_matches": selected_min_matches,
            "heroes": hero_rows,
            "error_message": error_message,
        },
    ))


def _is_direct_player_lookup(query: str) -> bool:
    normalized = query.casefold()
    return (
        query.isdigit()
        or "steamcommunity.com/profiles/" in normalized
        or "steamcommunity.com/id/" in normalized
    )


@app.get("/players/{player_input}", response_class=HTMLResponse)
async def player_profile(request: Request, player_input: str, refresh: int = 0) -> HTMLResponse:
    player_service = PlayerService()

    try:
        resolved = await player_service.resolve_player(player_input)
        if isinstance(resolved, list):
            return _html_response(TEMPLATES.TemplateResponse(
                request,
                "error.html",
                {
                    "message": "That search matched multiple players. Use the search page to choose the right one.",
                },
                status_code=400,
            ))

        summary = await player_service.build_player_summary(resolved, refresh_matches=bool(refresh))
        rank_name = player_service.rank_name(summary)
        latest_match_ts = max((match.start_time for match in summary.recent_matches), default=None)
        rank_updated_ts = summary.rank.start_time if summary.rank else None
        overview = ProfileOverviewView(
            account_id=summary.player.account_id,
            personaname=summary.player.personaname,
            profileurl=summary.player.profileurl,
            avatarfull=summary.player.avatarfull,
            countrycode=summary.player.countrycode,
            rank_name=rank_name,
            rank_updated_text=_relative_time_text(rank_updated_ts),
            rank_is_stale=bool(rank_updated_ts and latest_match_ts and rank_updated_ts < latest_match_ts),
            cache_updated_text=_relative_time_text(summary.player.last_updated),
            latest_match_text=_relative_time_text(latest_match_ts),
        )

        top_heroes = [
            HeroStatView(
                hero_name=summary.hero_info.get(stat.hero_id).name if summary.hero_info.get(stat.hero_id) else f"Hero {stat.hero_id}",
                hero_icon_url=summary.hero_info.get(stat.hero_id).icon_small if summary.hero_info.get(stat.hero_id) else None,
                matches_played=stat.matches_played,
                wins=stat.wins,
                win_rate_percent=f"{player_service.win_rate(stat):.1%}",
                kda=player_service.format_kda(stat.kills, stat.deaths, stat.assists),
            )
            for stat in summary.hero_stats[:6]
        ]
        recent_matches = [
            MatchView(
                hero_name=summary.hero_info.get(match.hero_id).name if summary.hero_info.get(match.hero_id) else f"Hero {match.hero_id}",
                hero_icon_url=summary.hero_info.get(match.hero_id).icon_small if summary.hero_info.get(match.hero_id) else None,
                detail_url=str(request.url_for("match_detail", player_input=str(summary.player.account_id), match_id=str(match.match_id))),
                queue_name=_friendly_mode_label(match.game_mode) or "Match",
                result=player_service.match_result_label(match),
                duration=player_service.format_match_duration(match.match_duration_s),
                played_text=_relative_time_text(match.start_time),
                kda=player_service.format_kda(match.player_kills, match.player_deaths, match.player_assists),
                net_worth=match.net_worth or 0,
                last_hits=match.last_hits or 0,
            )
            for match in summary.recent_matches
        ]
    except DeadlockError as error:
        return _html_response(TEMPLATES.TemplateResponse(
            request,
            "error.html",
            {"message": str(error)},
            status_code=404,
        ))

    return _html_response(TEMPLATES.TemplateResponse(
        request,
        "player.html",
        {
            "player": summary.player,
            "overview": overview,
            "top_heroes": top_heroes,
            "recent_matches": recent_matches,
            "refresh_requested": bool(refresh),
        },
    ))


@app.get("/players/{player_input}/matches/{match_id}", response_class=HTMLResponse)
async def match_detail(request: Request, player_input: str, match_id: str) -> HTMLResponse:
    player_service = PlayerService()

    try:
        resolved = await player_service.resolve_player(player_input)
        if isinstance(resolved, list):
            return _html_response(TEMPLATES.TemplateResponse(
                request,
                "error.html",
                {"message": "That player lookup matched multiple profiles."},
                status_code=400,
            ))

        metadata = await player_service.api.get_match_metadata(int(match_id))
        hero_info = await player_service.api.get_hero_info()
        steam_profiles = await player_service.api.get_steam_profiles(
            [player.account_id for player in metadata.players if player.account_id]
        )

        player_rows: list[MatchDetailPlayerView] = []
        viewed_player_result = "Unknown"
        for item in metadata.players:
            profile = steam_profiles.get(item.account_id)
            hero = hero_info.get(item.hero_id)
            result = "Win" if metadata.winning_team is not None and item.team == metadata.winning_team else "Loss"
            if item.account_id == resolved.account_id:
                viewed_player_result = result
            player_rows.append(
                MatchDetailPlayerView(
                    account_id=item.account_id,
                    personaname=profile.personaname if profile else str(item.account_id),
                    profileurl=profile.profileurl if profile else f"https://steamcommunity.com/profiles/{item.account_id}",
                    avatarfull=profile.avatarfull if profile else None,
                    hero_name=hero.name if hero else f"Hero {item.hero_id}",
                    hero_icon_url=hero.icon_small if hero else None,
                    team=item.team,
                    result=result,
                    is_viewed_player=item.account_id == resolved.account_id,
                    kills=item.kills or 0,
                    deaths=item.deaths or 0,
                    assists=item.assists or 0,
                    kda=player_service.format_kda(item.kills, item.deaths, item.assists),
                    souls=item.net_worth or 0,
                    player_damage=item.player_damage or 0,
                    objective_damage=item.objective_damage or 0,
                    healing=item.healing or 0,
                    last_hits=item.last_hits or 0,
                    denies=item.denies or 0,
                    level=item.level or 0,
                    lane_number=item.assigned_lane,
                    lane_text=_lane_text(item.assigned_lane),
                )
            )

        player_rows.sort(key=lambda item: (item.team if item.team is not None else 99, -item.souls, item.personaname.casefold()))
        team_zero = [player for player in player_rows if player.team == 0]
        team_one = [player for player in player_rows if player.team == 1]
        matchup_rows = _build_matchup_rows(player_rows)

        overview = MatchDetailOverviewView(
            match_id=metadata.match_id,
            queue_name=_friendly_mode_label(metadata.game_mode) or "Match",
            started_text=_relative_time_text(metadata.start_time),
            duration=player_service.format_match_duration(metadata.duration_s),
            winning_team_label=_team_label(metadata.winning_team),
            viewed_player_result=viewed_player_result,
            viewed_player_name=resolved.personaname,
        )
    except DeadlockError as error:
        return _html_response(TEMPLATES.TemplateResponse(
            request,
            "error.html",
            {"message": str(error)},
            status_code=404,
        ))

    return _html_response(TEMPLATES.TemplateResponse(
        request,
        "match_detail.html",
        {
            "player": resolved,
            "overview": overview,
            "matchup_rows": matchup_rows,
        },
    ))


def _relative_time_text(timestamp: int | None) -> str:
    if not timestamp:
        return "Unknown"
    delta = max(0, int(time()) - int(timestamp))
    if delta < 60:
        return "just now"
    if delta < 3600:
        minutes = delta // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    if delta < 86400:
        hours = delta // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = delta // 86400
    return f"{days} day{'s' if days != 1 else ''} ago"


def _friendly_mode_label(game_mode: int | None) -> str | None:
    mapping = {
        1: "Normal",
        4: "Street Brawl",
    }
    return mapping.get(game_mode)


def _team_label(team: int | None) -> str:
    return {0: "Team 0", 1: "Team 1"}.get(team, "Unknown Team")


def _lane_text(lane: int | None) -> str:
    mapping = {
        1: "Yellow",
        4: "Green",
        6: "Blue",
    }
    if lane in mapping:
        return mapping[lane]
    if lane is None:
        return "Unknown"
    return f"Lane {lane}"


def _friendly_slot_type(slot_type: str | None) -> str:
    mapping = {
        "weapon": "Weapon",
        "vitality": "Vitality",
        "spirit": "Spirit",
    }
    return mapping.get(slot_type or "", "Utility")


def _friendly_time_seconds(seconds: float | None) -> str:
    if seconds is None:
        return "Unknown timing"
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}:{secs:02d} avg buy"


def _parse_optional_int(raw: str | None) -> int | None:
    if raw is None:
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def _build_rank_distribution_views(
    badge_distribution: list,
    rank_info: list,
) -> list[RankDistributionTierView]:
    if not badge_distribution or not rank_info:
        return []

    max_matches = max((entry.total_matches for entry in badge_distribution), default=0)
    total_matches = sum(entry.total_matches for entry in badge_distribution)
    if max_matches <= 0:
        return []

    tiers_by_id = {item.tier: item for item in rank_info}
    grouped: dict[int, list[RankDistributionBarView]] = {}

    for entry in sorted(badge_distribution, key=lambda item: item.badge_level):
        tier = entry.badge_level // 10
        division = entry.badge_level % 10
        if tier <= 0 or division <= 0:
            continue
        rank = tiers_by_id.get(tier)
        if rank is None:
            continue
        grouped.setdefault(tier, []).append(
            RankDistributionBarView(
                badge_level=entry.badge_level,
                tier_name=rank.name,
                division_label=str(division),
                matches_text=f"{entry.total_matches:,} matches",
                share_text=f"{((entry.total_matches / total_matches) * 100):.2f}% of tracked matches" if total_matches else "0.00% of tracked matches",
                height_percent=max(8.0, (entry.total_matches / max_matches) * 100),
                color=rank.color or "#d3b58a",
            )
        )

    return [
        RankDistributionTierView(
            tier_name=tiers_by_id[tier].name,
            bars=grouped[tier],
        )
        for tier in sorted(grouped)
        if grouped[tier]
    ]


def _rank_floor_options() -> list[FilterOptionView]:
    return [
        FilterOptionView(value="", label="All ranks"),
        FilterOptionView(value="11", label="Initiate+"),
        FilterOptionView(value="21", label="Seeker+"),
        FilterOptionView(value="31", label="Alchemist+"),
        FilterOptionView(value="41", label="Arcanist+"),
        FilterOptionView(value="51", label="Ritualist+"),
        FilterOptionView(value="61", label="Emissary+"),
        FilterOptionView(value="71", label="Archon+"),
        FilterOptionView(value="81", label="Oracle+"),
        FilterOptionView(value="91", label="Phantom+"),
        FilterOptionView(value="101", label="Ascendant+"),
        FilterOptionView(value="111", label="Eternus+"),
    ]


def _build_lane_views(players: list[MatchDetailPlayerView]) -> list[MatchLaneView]:
    lane_order = sorted({player.lane_number for player in players}, key=lambda value: (value is None, value))
    lanes: list[MatchLaneView] = []
    for lane_number in lane_order:
        lane_players = [player for player in players if player.lane_number == lane_number]
        team_zero = sorted(
            [player for player in lane_players if player.team == 0],
            key=lambda player: (-player.souls, player.personaname.casefold()),
        )
        team_one = sorted(
            [player for player in lane_players if player.team == 1],
            key=lambda player: (-player.souls, player.personaname.casefold()),
        )
        lanes.append(
            MatchLaneView(
                lane_number=lane_number,
                lane_text=_lane_text(lane_number),
                team_zero=team_zero,
                team_one=team_one,
            )
        )
    return lanes


def _build_matchup_rows(players: list[MatchDetailPlayerView]) -> list[MatchupRowView]:
    rows: list[MatchupRowView] = []
    for lane in _build_lane_views(players):
        max_rows = max(len(lane.team_zero), len(lane.team_one))
        for index in range(max_rows):
            left_player = lane.team_zero[index] if index < len(lane.team_zero) else None
            right_player = lane.team_one[index] if index < len(lane.team_one) else None
            rows.append(
                MatchupRowView(
                    lane_number=lane.lane_number,
                    lane_text=lane.lane_text,
                    left_player=left_player,
                    right_player=right_player,
                )
            )
    return rows
