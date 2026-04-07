from __future__ import annotations

from pathlib import Path
from time import time

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from deadlock_tracker.clients.deadlock_api import DeadlockError
from deadlock_tracker.services.player_service import PlayerService
from deadlock_tracker.web.view_models import HeroStatView, MatchView, ProfileOverviewView, SearchResultView


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Deadlock Tracker", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, query: str | None = None) -> HTMLResponse:
    player_service = PlayerService()
    search_results: list[SearchResultView] = []
    error_message: str | None = None

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

    return TEMPLATES.TemplateResponse(
        request,
        "index.html",
        {
            "query": query or "",
            "results": search_results,
            "error_message": error_message,
        },
    )


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
            return TEMPLATES.TemplateResponse(
                request,
                "error.html",
                {
                    "message": "That search matched multiple players. Use the search page to choose the right one.",
                },
                status_code=400,
            )

        summary = await player_service.build_player_summary(resolved)
        rank_name = player_service.rank_name(summary)
        rating_text = f"{(summary.rank.player_score or 0):.2f}" if summary.rank else "0.00"
        overview = ProfileOverviewView(
            account_id=summary.player.account_id,
            personaname=summary.player.personaname,
            profileurl=summary.player.profileurl,
            avatarfull=summary.player.avatarfull,
            countrycode=summary.player.countrycode,
            rank_name=rank_name,
            rating_text=rating_text,
            cache_updated_text=_relative_time_text(summary.player.last_updated),
            cache_updated_raw=summary.player.last_updated,
        )

        top_heroes = [
            HeroStatView(
                hero_name=summary.hero_info.get(stat.hero_id).name if summary.hero_info.get(stat.hero_id) else f"Hero {stat.hero_id}",
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
                match_id=match.match_id,
                result=player_service.match_result_label(match),
                duration=player_service.format_match_duration(match.match_duration_s),
                kda=player_service.format_kda(match.player_kills, match.player_deaths, match.player_assists),
                net_worth=match.net_worth or 0,
                last_hits=match.last_hits or 0,
            )
            for match in summary.recent_matches
        ]
    except DeadlockError as error:
        return TEMPLATES.TemplateResponse(
            request,
            "error.html",
            {"message": str(error)},
            status_code=404,
        )

    return TEMPLATES.TemplateResponse(
        request,
        "player.html",
        {
            "player": summary.player,
            "overview": overview,
            "top_heroes": top_heroes,
            "recent_matches": recent_matches,
            "refresh_requested": bool(refresh),
        },
    )


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
