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
    MatchDetailItemView,
    MatchLaneView,
    MatchDetailOverviewView,
    MatchDetailPlayerView,
    MatchView,
    MatchupRowView,
    ProfileOverviewView,
    RankDistributionBarView,
    RankDistributionTierView,
    SearchResultView,
    StreetBrawlAbilityStepView,
    StreetBrawlBuildItemView,
    StreetBrawlGuideView,
    StreetBrawlHeroCardView,
)


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Deadlock Tracker", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def _html_response(response: HTMLResponse) -> HTMLResponse:
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


@app.get("/healthz")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


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
        player_rank_distribution = await api.get_player_rank_distribution()
        rank_info = await api.get_rank_info()
        rank_distribution = _build_player_rank_distribution_views(player_rank_distribution, rank_info)
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


@app.get("/discord-bot", response_class=HTMLResponse)
async def discord_bot(request: Request) -> HTMLResponse:
    return _html_response(TEMPLATES.TemplateResponse(request, "discord_bot.html", {}))


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
    if selected_mode == "street_brawl":
        selected_rank_floor = None

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
        error_message = _friendly_meta_error_message(error, topic="item stats")

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
    if selected_mode == "street_brawl":
        selected_rank_floor = None

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
        error_message = _friendly_meta_error_message(error, topic="hero stats")

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


@app.get("/street-brawl-builds", response_class=HTMLResponse)
async def street_brawl_builds(
    request: Request,
    hero_id: str | None = None,
    item_level: str | None = "",
    min_matches: str | None = "100",
    window_days: int = 7,
) -> HTMLResponse:
    player_service = PlayerService()
    api = player_service.api
    error_message: str | None = None
    selected_window_days = window_days if window_days in {7, 30, 90} else 7
    parsed_min_matches = _parse_optional_int(min_matches)
    selected_min_matches = parsed_min_matches if parsed_min_matches in {50, 100, 250, 500, 1000} else 100

    hero_info = await api.get_hero_info()
    sorted_heroes = sorted(hero_info.values(), key=lambda item: item.name.casefold())
    parsed_hero_id = _parse_optional_int(hero_id)
    selected_hero = hero_info.get(parsed_hero_id) if parsed_hero_id is not None else None
    if not sorted_heroes:
        return _html_response(TEMPLATES.TemplateResponse(
            request,
            "error.html",
            {"message": "No active heroes are currently available."},
            status_code=404,
        ))

    selected_item_level = item_level.strip().lower() if item_level else ""
    if selected_item_level not in {"", "1", "2", "3", "4", "legendary"}:
        selected_item_level = ""

    hero_cards = [
        StreetBrawlHeroCardView(
            hero_id=hero.hero_id,
            hero_name=hero.name,
            hero_icon_url=hero.icon_small,
            hero_portrait_url=hero.portrait_url,
            hero_background_image_url=hero.background_image_url,
            build_url=(
                f"{request.url_for('street_brawl_builds')}"
                f"?hero_id={hero.hero_id}&item_level={selected_item_level}&window_days={selected_window_days}&min_matches={selected_min_matches}"
            ),
        )
        for hero in sorted_heroes
    ]

    if selected_hero is None:
        return _html_response(TEMPLATES.TemplateResponse(
            request,
            "street_brawl_builds.html",
            {
                "hero_options": [
                    FilterOptionView(value=str(hero.hero_id), label=hero.name)
                    for hero in sorted_heroes
                ],
                "item_level_options": [
                    FilterOptionView(value="", label="All item levels"),
                    FilterOptionView(value="1", label="Tier 1"),
                    FilterOptionView(value="2", label="Tier 2"),
                    FilterOptionView(value="3", label="Tier 3"),
                    FilterOptionView(value="4", label="Tier 4"),
                    FilterOptionView(value="legendary", label="Legendary"),
                ],
                "window_options": [
                    FilterOptionView(value="7", label="Last 7 days"),
                    FilterOptionView(value="30", label="Last 30 days"),
                    FilterOptionView(value="90", label="Last 90 days"),
                ],
                "sample_options": [
                    FilterOptionView(value="50", label="50+ matches"),
                    FilterOptionView(value="100", label="100+ matches"),
                    FilterOptionView(value="250", label="250+ matches"),
                    FilterOptionView(value="500", label="500+ matches"),
                    FilterOptionView(value="1000", label="1000+ matches"),
                ],
                "selected_hero_id": "",
                "selected_item_level": selected_item_level,
                "selected_window_days": str(selected_window_days),
                "selected_min_matches": str(selected_min_matches),
                "items": [],
                "guide": None,
                "hero_cards": hero_cards,
                "error_message": None,
            },
        ))

    item_rows: list[StreetBrawlBuildItemView] = []
    guide: StreetBrawlGuideView | None = None

    try:
        item_stats = await api.get_item_stats(
            hero_id=selected_hero.hero_id,
            game_mode="street_brawl",
            min_matches=selected_min_matches,
            min_unix_timestamp=int(time()) - selected_window_days * 86400,
        )
        ability_orders = await api.get_ability_order_stats(
            hero_id=selected_hero.hero_id,
            game_mode="street_brawl",
            min_matches=selected_min_matches,
            min_unix_timestamp=int(time()) - selected_window_days * 86400,
        )
        item_info_map = await api.get_all_item_info()

        filtered_items = []
        for stat in item_stats:
            item_info = item_info_map.get(stat.item_id)
            if item_info is None or item_info.item_type != "upgrade":
                continue
            if selected_item_level and not _matches_item_level_filter(item_info.item_tier, selected_item_level):
                continue
            filtered_items.append((stat, item_info))

        ranked_items = sorted(
            filtered_items,
            key=lambda entry: (
                (entry[0].wins / entry[0].matches) if entry[0].matches else 0.0,
                entry[0].matches,
            ),
            reverse=True,
        )

        for index, (stat, item_info) in enumerate(ranked_items, start=1):
            item_rows.append(
                StreetBrawlBuildItemView(
                    rank_number=index,
                    item_name=item_info.name,
                    item_image_url=item_info.shop_image or item_info.image,
                    slot_type=_friendly_slot_type(item_info.item_slot_type),
                    tier_text=_friendly_item_tier_text(item_info.item_tier),
                    cost_text=f"{item_info.cost:,} souls" if item_info.cost else "Cost Unknown",
                    win_rate_percent=f"{(stat.wins / stat.matches):.1%}" if stat.matches else "0.0%",
                    matches_text=f"{stat.matches:,} matches",
                    players_text=f"{stat.players:,} players",
                    avg_buy_time_text=_friendly_time_seconds(stat.avg_buy_time_s),
                    wins_text=f"{stat.wins:,} wins",
                    losses_text=f"{stat.losses:,} losses",
                )
            )

        most_common_path = max(ability_orders, key=lambda entry: entry.matches, default=None)
        if most_common_path is not None:
            guide = StreetBrawlGuideView(
                hero_name=selected_hero.name,
                hero_icon_url=selected_hero.icon_small,
                hero_portrait_url=selected_hero.portrait_url,
                hero_background_image_url=selected_hero.background_image_url,
                ability_steps=[
                    StreetBrawlAbilityStepView(
                        step_number=index,
                        ability_name=(item_info_map.get(ability_id).name if item_info_map.get(ability_id) else f"Ability {index}"),
                        ability_image_url=item_info_map.get(ability_id).image if item_info_map.get(ability_id) else None,
                        ability_type=_friendly_ability_type(item_info_map.get(ability_id).ability_type if item_info_map.get(ability_id) else None),
                    )
                    for index, ability_id in enumerate(most_common_path.abilities, start=1)
                ],
                path_matches_text=f"{most_common_path.matches:,} matches",
                path_players_text=f"{most_common_path.players:,} players",
                path_win_rate_percent=f"{(most_common_path.wins / most_common_path.matches):.1%}" if most_common_path.matches else "0.0%",
            )
    except DeadlockError as error:
        error_message = str(error)

    return _html_response(TEMPLATES.TemplateResponse(
        request,
        "street_brawl_builds.html",
        {
            "hero_options": [
                FilterOptionView(value=str(hero.hero_id), label=hero.name)
                for hero in sorted_heroes
            ],
            "item_level_options": [
                FilterOptionView(value="", label="All item levels"),
                FilterOptionView(value="1", label="Tier 1"),
                FilterOptionView(value="2", label="Tier 2"),
                FilterOptionView(value="3", label="Tier 3"),
                FilterOptionView(value="4", label="Tier 4"),
                FilterOptionView(value="legendary", label="Legendary"),
            ],
            "window_options": [
                FilterOptionView(value="7", label="Last 7 days"),
                FilterOptionView(value="30", label="Last 30 days"),
                FilterOptionView(value="90", label="Last 90 days"),
            ],
            "sample_options": [
                FilterOptionView(value="50", label="50+ matches"),
                FilterOptionView(value="100", label="100+ matches"),
                FilterOptionView(value="250", label="250+ matches"),
                FilterOptionView(value="500", label="500+ matches"),
                FilterOptionView(value="1000", label="1000+ matches"),
            ],
            "selected_hero_id": str(selected_hero.hero_id),
            "selected_item_level": selected_item_level,
            "selected_window_days": str(selected_window_days),
            "selected_min_matches": str(selected_min_matches),
            "items": item_rows,
            "guide": guide,
            "hero_cards": hero_cards,
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
    refresh_requested = bool(refresh)
    refresh_status: str | None = None

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

        try:
            summary = await player_service.build_player_summary(resolved, refresh_matches=refresh_requested)
            if refresh_requested:
                refresh_status = "success"
        except DeadlockError as refresh_error:
            if not refresh_requested:
                raise
            summary = await player_service.build_player_summary(resolved, refresh_matches=False)
            refresh_status = "fallback"

        rank_name = player_service.rank_name(summary)
        rank_info = await player_service.api.get_rank_info()
        rank_badge_image_url = _rank_badge_image_url(summary.rank.rank if summary.rank else None, rank_info)
        latest_match_ts = max((match.start_time for match in summary.recent_matches), default=None)
        rank_updated_ts = summary.rank.start_time if summary.rank else None
        overview = ProfileOverviewView(
            account_id=summary.player.account_id,
            personaname=summary.player.personaname,
            profileurl=summary.player.profileurl,
            avatarfull=summary.player.avatarfull,
            countrycode=summary.player.countrycode,
            rank_name=rank_name,
            rank_badge_image_url=rank_badge_image_url,
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
            "refresh_requested": refresh_requested,
            "refresh_status": refresh_status,
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
        item_info_map = await player_service.api.get_all_item_info()
        steam_profiles = await player_service.api.get_steam_profiles(
            [player.account_id for player in metadata.players if player.account_id]
        )
        stat_leaders = _build_match_stat_leaders(metadata.players)

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
                    items=_build_match_item_views(item.items, item_info_map),
                    leads_souls=(item.net_worth or 0) == stat_leaders["souls"] and stat_leaders["souls"] > 0,
                    leads_kills=(item.kills or 0) == stat_leaders["kills"] and stat_leaders["kills"] > 0,
                    leads_assists=(item.assists or 0) == stat_leaders["assists"] and stat_leaders["assists"] > 0,
                    leads_player_damage=(item.player_damage or 0) == stat_leaders["player_damage"] and stat_leaders["player_damage"] > 0,
                    leads_objective_damage=(item.objective_damage or 0) == stat_leaders["objective_damage"] and stat_leaders["objective_damage"] > 0,
                    leads_healing=(item.healing or 0) == stat_leaders["healing"] and stat_leaders["healing"] > 0,
                    leads_last_hits=(item.last_hits or 0) == stat_leaders["last_hits"] and stat_leaders["last_hits"] > 0,
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


def _friendly_ability_type(ability_type: str | None) -> str:
    mapping = {
        "signature": "Skill",
        "ultimate": "Ultimate",
        "innate": "Innate",
    }
    return mapping.get(ability_type or "", "Ability")


def _friendly_item_tier_text(item_tier: int | None) -> str:
    if item_tier == 5:
        return "Legendary"
    if item_tier:
        return f"Tier {item_tier}"
    return "Tier Unknown"


def _matches_item_level_filter(item_tier: int | None, selected_item_level: str) -> bool:
    if not selected_item_level:
        return True
    if selected_item_level == "legendary":
        return item_tier == 5
    try:
        return item_tier == int(selected_item_level)
    except ValueError:
        return False


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


def _friendly_meta_error_message(error: DeadlockError, *, topic: str) -> str:
    message = str(error)
    lowered = message.casefold()
    if "rate limit" in lowered:
        return f"Deadlock API is rate-limiting {topic} right now. Try again shortly."
    if "took too long" in lowered or "timed out" in lowered:
        return f"Deadlock API is taking longer than usual for {topic}. Try again in a moment."
    if "http 400" in lowered:
        return f"Those filters are not available for {topic} right now. Try broader filters or switch modes."
    if "http 500" in lowered or "request failed" in lowered:
        return f"Deadlock API is having trouble loading {topic} right now. Try again shortly."
    return f"We couldn't load {topic} right now. Try again shortly."


def _build_player_rank_distribution_views(
    player_rank_distribution: list,
    rank_info: list,
) -> list[RankDistributionTierView]:
    if not player_rank_distribution or not rank_info:
        return []

    max_players = max((entry.players for entry in player_rank_distribution), default=0)
    total_players = sum(entry.players for entry in player_rank_distribution)
    if max_players <= 0:
        return []

    tiers_by_id = {item.tier: item for item in rank_info}
    grouped: dict[int, list[RankDistributionBarView]] = {}

    for entry in sorted(player_rank_distribution, key=lambda item: item.rank):
        tier = entry.rank // 10
        division = entry.rank % 10
        if tier <= 0 or division <= 0:
            continue
        rank = tiers_by_id.get(tier)
        if rank is None:
            continue
        grouped.setdefault(tier, []).append(
            RankDistributionBarView(
                badge_level=entry.rank,
                tier_name=rank.name,
                division_label=str(division),
                matches_text=f"{entry.players:,} tracked players",
                share_text=f"{((entry.players / total_players) * 100):.2f}% of tracked players" if total_players else "0.00% of tracked players",
                height_percent=max(8.0, (entry.players / max_players) * 100),
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


def _rank_badge_image_url(rank: int | None, rank_info: list) -> str | None:
    if rank is None:
        return None
    tier = rank // 10
    division = rank % 10
    for item in rank_info:
        if getattr(item, "tier", None) == tier:
            by_division = getattr(item, "image_small_by_division", {}) or {}
            return by_division.get(division) or getattr(item, "image_small", None)
    return None


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


def _build_match_stat_leaders(players: list[DeadlockMatchPlayer]) -> dict[str, int]:
    def _max_value(values: list[int | None]) -> int:
        filtered = [int(value or 0) for value in values]
        return max(filtered, default=0)

    return {
        "souls": _max_value([player.net_worth for player in players]),
        "kills": _max_value([player.kills for player in players]),
        "assists": _max_value([player.assists for player in players]),
        "player_damage": _max_value([player.player_damage for player in players]),
        "objective_damage": _max_value([player.objective_damage for player in players]),
        "healing": _max_value([player.healing for player in players]),
        "last_hits": _max_value([player.last_hits for player in players]),
    }


def _build_match_item_views(
    items: list,
    item_info_map: dict[int, object],
) -> list[MatchDetailItemView]:
    current_items = sorted(
        [item for item in items if not item.sold_time_s],
        key=lambda item: (item.game_time_s is None, item.game_time_s or 0, item.item_id),
    )
    views: list[MatchDetailItemView] = []
    for item in current_items:
        item_info = item_info_map.get(item.item_id)
        if item_info is None:
            continue
        if getattr(item_info, "item_type", None) != "upgrade":
            continue
        views.append(
            MatchDetailItemView(
                item_name=item_info.name,
                item_image_url=item_info.shop_image or item_info.image,
            )
        )
    return views
