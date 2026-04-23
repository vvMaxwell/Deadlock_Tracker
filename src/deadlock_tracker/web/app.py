from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from time import time
from urllib.parse import urlencode, urlsplit

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.responses import Response as StarletteResponse

from deadlock_tracker.clients.deadlock_api import DeadlockError, friendly_rank_name
from deadlock_tracker.services.player_service import PlayerService
from deadlock_tracker.web.view_models import (
    BestItemView,
    BestHeroView,
    FilterOptionView,
    HeroStatView,
    HeroDirectoryCardView,
    HeroDetailItemView,
    HeroPeerStatView,
    ItemDirectoryCardView,
    ItemModeStatView,
    LeaderboardEntryView,
    LeaderboardRegionCardView,
    MatchDetailItemView,
    MatchLaneView,
    MatchDetailOverviewView,
    MatchDetailPlayerView,
    MatchView,
    MatchupRowView,
    PaginationLinkView,
    PatchNoteView,
    ProfileOverviewView,
    RankDistributionBarView,
    RankDistributionSummaryView,
    RankDistributionTierView,
    SearchResultView,
    StreetBrawlAbilityStepView,
    StreetBrawlBuildItemView,
    StreetBrawlGuideView,
    StreetBrawlHeroCardView,
)


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))
STATIC_CSS_VERSION = int((BASE_DIR / "static" / "site.css").stat().st_mtime)

app = FastAPI(title="Deadlock Stats Tracker", version="0.1.0")

LEADERBOARD_REGIONS: list[tuple[str, str, str, str]] = [
    ("north-america", "North America", "Top tracked Deadlock players competing in North America.", "NAmerica"),
    ("europe", "Europe", "Top tracked Deadlock players competing in Europe.", "Europe"),
    ("asia", "Asia", "Tracked leaderboard players across Asia.", "Asia"),
    ("south-america", "South America", "Tracked leaderboard players across South America.", "SAmerica"),
    ("oceania", "Oceania", "Tracked leaderboard players across Oceania.", "Oceania"),
]

LEADERBOARD_REGION_REDIRECTS: dict[str, str] = {
    "row": "north-america",
    "se_asia": "asia",
    "s_america": "south-america",
    "russia": "europe",
}


class CachedStaticFiles(StaticFiles):
    def file_response(self, *args, **kwargs) -> StarletteResponse:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "public, max-age=2592000"
        return response


app.mount("/static", CachedStaticFiles(directory=str(BASE_DIR / "static")), name="static")


def _html_response(response: HTMLResponse) -> HTMLResponse:
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


def _base_context(request: Request, **context: object) -> dict[str, object]:
    site_name = "Deadlock Stats Tracker"
    path = request.url.path
    brand_logo_url = _public_url(
        request,
        str(request.url_for("static", path="/branding/deadlock-stats-tracker-logo-transparent.webp")),
    )
    brand_symbol_url = _public_url(
        request,
        str(request.url_for("static", path="/branding/deadlock-stats-tracker-symbol-transparent.webp")),
    )
    favicon_url = _public_url(
        request,
        str(request.url_for("static", path="/branding/favicon-48.png")),
    )
    favicon_32_url = _public_url(
        request,
        str(request.url_for("static", path="/branding/favicon-32.png")),
    )
    favicon_192_url = _public_url(
        request,
        str(request.url_for("static", path="/branding/favicon-192.png")),
    )
    favicon_512_url = _public_url(
        request,
        str(request.url_for("static", path="/branding/favicon-512.png")),
    )
    apple_touch_icon_url = _public_url(
        request,
        str(request.url_for("static", path="/branding/favicon-180.png")),
    )
    favicon_ico_url = _public_url(request, str(request.url_for("favicon_ico")))
    webmanifest_url = _public_url(request, str(request.url_for("site_webmanifest")))
    canonical_url = context.pop("canonical_url", _public_url(request, str(request.url.replace(query=""))))
    page_title = context.get("page_title") or site_name
    meta_description = context.get("meta_description") or (
        "Search Deadlock players, ranks, match history, hero performance, best heroes, best items, and Street Brawl builds."
    )
    og_image = context.get("og_image") or brand_logo_url
    meta_robots = context.pop("meta_robots", None) or "index,follow"
    og_type = context.get("og_type") or "website"
    structured_data = context.pop("structured_data", None)
    site_schema = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": site_name,
        "url": _public_url(request, str(request.url_for("home"))),
        "logo": {
            "@type": "ImageObject",
            "url": brand_symbol_url,
            "contentUrl": brand_symbol_url,
            "width": 512,
            "height": 512,
        },
        "image": brand_logo_url,
    }
    if structured_data is None:
        structured_data = [site_schema]
    elif isinstance(structured_data, list):
        structured_data = [site_schema, *structured_data]
    else:
        structured_data = [site_schema, structured_data]
    if structured_data is not None:
        structured_data = json.dumps(structured_data, separators=(",", ":"))

    return {
        "site_name": site_name,
        "canonical_url": canonical_url,
        "page_title": page_title,
        "meta_description": meta_description,
        "meta_robots": meta_robots,
        "og_type": og_type,
        "og_image": og_image,
        "structured_data": structured_data,
        "brand_logo_url": brand_logo_url,
        "brand_symbol_url": brand_symbol_url,
        "favicon_url": favicon_url,
        "favicon_32_url": favicon_32_url,
        "favicon_192_url": favicon_192_url,
        "favicon_512_url": favicon_512_url,
        "favicon_ico_url": favicon_ico_url,
        "apple_touch_icon_url": apple_touch_icon_url,
        "webmanifest_url": webmanifest_url,
        "static_css_version": STATIC_CSS_VERSION,
        "request_path": path,
        **context,
    }


@app.get("/healthz")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/robots.txt")
async def robots_txt(request: Request) -> Response:
    sitemap_url = _public_url(request, str(request.url_for("sitemap_xml")))
    content = f"User-agent: *\nAllow: /\n\nSitemap: {sitemap_url}\n"
    return Response(content=content, media_type="text/plain")


@app.get("/ads.txt")
async def ads_txt() -> Response:
    content = "google.com, pub-4490992289432217, DIRECT, f08c47fec0942fa0\n"
    return Response(content=content, media_type="text/plain")


@app.get("/favicon.ico", name="favicon_ico")
async def favicon_ico(request: Request) -> RedirectResponse:
    return RedirectResponse(
        url=str(request.url_for("static", path="/branding/favicon-48.png")),
        status_code=307,
    )


@app.get("/site.webmanifest", name="site_webmanifest")
async def site_webmanifest(request: Request) -> Response:
    payload = {
        "name": "Deadlock Stats Tracker",
        "short_name": "Deadlock Stats",
        "icons": [
            {
                "src": _public_url(request, str(request.url_for("static", path="/branding/favicon-192.png"))),
                "sizes": "192x192",
                "type": "image/png",
            },
            {
                "src": _public_url(request, str(request.url_for("static", path="/branding/favicon-512.png"))),
                "sizes": "512x512",
                "type": "image/png",
            },
        ],
        "theme_color": "#13100d",
        "background_color": "#13100d",
        "display": "standalone",
    }
    return Response(
        content=json.dumps(payload, separators=(",", ":")),
        media_type="application/manifest+json",
    )


@app.get("/sitemap.xml", name="sitemap_xml")
async def sitemap_xml(request: Request) -> Response:
    api = PlayerService().api
    urls = [
        _public_url(request, str(request.url_for("home"))),
        _public_url(request, str(request.url_for("heroes_directory"))),
        _public_url(request, str(request.url_for("items_directory"))),
        _public_url(request, str(request.url_for("leaderboards"))),
        _public_url(request, str(request.url_for("rank_distribution"))),
        _public_url(request, str(request.url_for("best_heroes"))),
        _public_url(request, str(request.url_for("best_items"))),
        _public_url(request, str(request.url_for("street_brawl_builds"))),
        _public_url(request, str(request.url_for("patch_notes"))),
        _public_url(request, str(request.url_for("faq"))),
        _public_url(request, str(request.url_for("discord_bot"))),
        _public_url(request, str(request.url_for("credits"))),
        _public_url(request, str(request.url_for("disclaimers"))),
    ]
    urls.extend(
        _public_url(request, str(request.url_for("leaderboard_region", region_slug=region_slug)))
        for region_slug, _, _, _ in LEADERBOARD_REGIONS
    )
    try:
        hero_info = await api.get_hero_info()
        urls.extend(
            _public_url(
                request,
                str(
                    request.url_for(
                        "hero_detail",
                        hero_id=str(hero.hero_id),
                        hero_slug=_slugify(hero.name),
                    )
                ),
            )
            for hero in hero_info.values()
        )
        urls.extend(
            _public_url(
                request,
                str(
                    request.url_for(
                        "hero_items",
                        hero_id=str(hero.hero_id),
                        hero_slug=_slugify(hero.name),
                    )
                ),
            )
            for hero in hero_info.values()
        )
        urls.extend(
            _public_url(
                request,
                str(
                    request.url_for(
                        "hero_matchups",
                        hero_id=str(hero.hero_id),
                        hero_slug=_slugify(hero.name),
                    )
                ),
            )
            for hero in hero_info.values()
        )
        urls.extend(
            _public_url(
                request,
                str(
                    request.url_for(
                        "hero_rank_distribution",
                        hero_id=str(hero.hero_id),
                        hero_slug=_slugify(hero.name),
                    )
                ),
            )
            for hero in hero_info.values()
        )
    except DeadlockError:
        pass

    try:
        items = await api.get_all_item_info()
        urls.extend(
            _public_url(
                request,
                str(
                    request.url_for(
                        "item_detail",
                        item_id=str(item.item_id),
                        item_slug=_slugify(item.name),
                    )
                ),
            )
            for item in items.values()
            if item.item_type == "upgrade"
        )
    except DeadlockError:
        pass

    try:
        patches = await api.get_patches(limit=50)
        urls.extend(
            _public_url(
                request,
                str(
                    request.url_for(
                        "patch_note_detail",
                        patch_guid=patch.guid or _slugify(patch.title),
                        patch_slug=_slugify(patch.title),
                    )
                ),
            )
            for patch in patches
        )
    except DeadlockError:
        pass

    urls = list(dict.fromkeys(urls))
    body = "".join(f"<url><loc>{url}</loc></url>" for url in urls)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{body}"
        "</urlset>"
    )
    return Response(content=xml, media_type="application/xml")


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
                    detail_url=str(
                        request.url_for(
                            "player_profile_canonical",
                            account_id=str(player.account_id),
                            player_slug=_slugify(player.personaname),
                        )
                    ),
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
        _base_context(
            request,
            page_title="Deadlock Stats Tracker",
            meta_description=(
                "Deadlock Stats Tracker lets you search players by Steam name, profile URL, or account ID "
                "to view ranks, match history, hero stats, best heroes, best items, and Street Brawl builds."
            ),
            meta_robots="noindex,follow" if query else "index,follow",
            structured_data=[
                {
                    "@context": "https://schema.org",
                    "@type": "WebSite",
                    "name": "Deadlock Stats Tracker",
                    "url": _public_url(request, str(request.url_for("home"))),
                    "potentialAction": {
                        "@type": "SearchAction",
                        "target": f"{_public_url(request, str(request.url_for('home')))}?query={{search_term_string}}",
                        "query-input": "required name=search_term_string",
                    },
                },
                {
                    "@context": "https://schema.org",
                    "@type": "WebPage",
                    "name": "Deadlock Stats Tracker",
                    "url": _public_url(request, str(request.url_for("home"))),
                    "description": (
                        "Search Deadlock players and explore ranks, match history, best heroes, best items, and Street Brawl builds."
                    ),
                },
            ],
            query=query or "",
            results=search_results,
            error_message=error_message,
            rank_distribution=rank_distribution,
        ),
    ))


@app.get("/faq", response_class=HTMLResponse)
async def faq(request: Request) -> HTMLResponse:
    screenshot_rel = "/help/steam-account-url-guide.webp"
    screenshot_abs = BASE_DIR / "static" / "help" / "steam-account-url-guide.webp"
    return _html_response(TEMPLATES.TemplateResponse(
        request,
        "faq.html",
        _base_context(
            request,
            page_title="FAQ | Deadlock Stats Tracker",
            meta_description=(
                "Learn how to search Deadlock players by Steam name, profile URL, or account ID, and how to use Deadlock Stats Tracker."
            ),
            structured_data=[
                {
                    "@context": "https://schema.org",
                    "@type": "FAQPage",
                    "mainEntity": [
                        {
                            "@type": "Question",
                            "name": "How do I get my Steam account URL?",
                            "acceptedAnswer": {
                                "@type": "Answer",
                                "text": "Open your Steam profile page and copy the full URL from the address bar. Both numeric profile URLs and custom Steam ID URLs work.",
                            },
                        },
                        {
                            "@type": "Question",
                            "name": "What can I search?",
                            "acceptedAnswer": {
                                "@type": "Answer",
                                "text": "You can search by Steam Name, Steam Account URL, or Account ID.",
                            },
                        },
                    ],
                },
                _breadcrumb_structured_data(
                    request,
                    [
                        ("Home", str(request.url_for("home"))),
                        ("FAQ", str(request.url_for("faq"))),
                    ],
                ),
            ],
            screenshot_url=_public_url(request, str(request.url_for("static", path=screenshot_rel))) if screenshot_abs.exists() else None,
        ),
    ))


@app.get("/discord-bot", response_class=HTMLResponse)
async def discord_bot(request: Request) -> HTMLResponse:
    return _html_response(TEMPLATES.TemplateResponse(
        request,
        "discord_bot.html",
        _base_context(
            request,
            page_title="Discord Bot | Deadlock Stats Tracker",
            meta_description="Follow the upcoming Deadlock Stats Tracker Discord bot for match lookups, stat snapshots, and future automation features.",
        ),
    ))


@app.get("/credits", response_class=HTMLResponse)
async def credits(request: Request) -> HTMLResponse:
    return _html_response(TEMPLATES.TemplateResponse(
        request,
        "credits.html",
        _base_context(
            request,
            page_title="Credits | Deadlock Stats Tracker",
            meta_description="Credits and acknowledgements for the data, assets, and tools behind Deadlock Stats Tracker.",
        ),
    ))


@app.get("/disclaimers", response_class=HTMLResponse)
async def disclaimers(request: Request) -> HTMLResponse:
    return _html_response(TEMPLATES.TemplateResponse(
        request,
        "disclaimers.html",
        _base_context(
            request,
            page_title="Disclaimers | Deadlock Stats Tracker",
            meta_description="Read the disclaimers and usage notes for Deadlock Stats Tracker, including data availability and third-party attribution.",
        ),
    ))


@app.get("/patch-notes", response_class=HTMLResponse, name="patch_notes")
async def patch_notes(request: Request, page: int = 1) -> HTMLResponse:
    api = PlayerService().api
    error_message: str | None = None
    patches: list[PatchNoteView] = []
    page_size = 12
    current_page = max(page, 1)
    pagination_links: list[PaginationLinkView] = []
    has_next_page = False
    canonical_url = _public_url(
        request,
        str(request.url_for("patch_notes")) if current_page == 1 else str(request.url.include_query_params(page=current_page)),
    )

    try:
        patch_feed = await api.get_patches(limit=min((current_page * page_size) + 1, 121))
        start_index = (current_page - 1) * page_size
        end_index = start_index + page_size
        visible_patches = patch_feed[start_index:end_index]
        has_next_page = len(patch_feed) > end_index
        patches = []
        for patch in visible_patches:
            summary_lines = _patch_summary_lines(patch.content_html, limit=8)
            full_summary_lines = _patch_summary_lines(patch.content_html, limit=120)
            patches.append(
                PatchNoteView(
                    title=patch.title,
                    detail_url=str(
                        request.url_for(
                            "patch_note_detail",
                            patch_guid=patch.guid or _slugify(patch.title),
                            patch_slug=_slugify(patch.title),
                        )
                    ),
                    published_text=_patch_pub_date_text(patch.pub_date),
                    author_text=patch.creator or _patch_author_text(patch.author),
                    summary_lines=summary_lines,
                    full_summary_lines=full_summary_lines,
                    summary_truncated=(
                        len(full_summary_lines) > len(summary_lines)
                        or any(line.endswith("...") for line in summary_lines)
                    ),
                    official_url=patch.link,
                )
            )
        if current_page > 1:
            previous_url = str(request.url_for("patch_notes")) if current_page == 2 else str(request.url.include_query_params(page=current_page - 1))
            pagination_links.append(PaginationLinkView(label="Newer patch notes", url=previous_url))
        if has_next_page:
            pagination_links.append(
                PaginationLinkView(
                    label="Older patch notes",
                    url=str(request.url.include_query_params(page=current_page + 1)),
                )
            )
    except DeadlockError as error:
        error_message = _friendly_meta_error_message(error, topic="patch notes")

    return _html_response(TEMPLATES.TemplateResponse(
        request,
        "patch_notes.html",
        _base_context(
            request,
            page_title="Deadlock Patch Notes | Deadlock Stats Tracker",
            meta_description=(
                "Read recent Deadlock patch notes sourced from the official Deadlock changelog posts."
            ),
            canonical_url=canonical_url,
            structured_data=[
                {
                    "@context": "https://schema.org",
                    "@type": "CollectionPage",
                    "name": "Deadlock Patch Notes",
                    "url": canonical_url,
                },
                _breadcrumb_structured_data(
                    request,
                    [
                        ("Home", str(request.url_for("home"))),
                        ("Patch Notes", str(request.url_for("patch_notes"))),
                    ],
                ),
            ],
            patches=patches,
            current_page=current_page,
            pagination_links=pagination_links,
            error_message=error_message,
        ),
    ))


@app.get("/patch-notes/{patch_guid}/{patch_slug}", response_class=HTMLResponse, name="patch_note_detail")
async def patch_note_detail(request: Request, patch_guid: str, patch_slug: str) -> HTMLResponse:
    api = PlayerService().api

    try:
        patches = await api.get_patches(limit=50)
        patch = next(
            (
                item for item in patches
                if item.guid == patch_guid or _slugify(item.title) == patch_guid or _slugify(item.title) == patch_slug
            ),
            None,
        )
        if patch is None:
            raise DeadlockError("That patch note could not be found.")

        canonical_url = _public_url(
            request,
            str(
                request.url_for(
                    "patch_note_detail",
                    patch_guid=patch.guid or _slugify(patch.title),
                    patch_slug=_slugify(patch.title),
                )
            ),
        )
        if request.url.path != _url_path(canonical_url):
            return RedirectResponse(url=canonical_url, status_code=308)
        patch_index = next((index for index, item in enumerate(patches) if item is patch), None)
        previous_patch = patches[patch_index + 1] if patch_index is not None and patch_index + 1 < len(patches) else None
        next_patch = patches[patch_index - 1] if patch_index is not None and patch_index - 1 >= 0 else None
        patch_lines = _patch_summary_lines(patch.content_html, limit=400)
        if _patch_lines_need_forum_fallback(patch_lines):
            full_content_html = await api.get_patch_full_content_html(patch.link)
            if full_content_html:
                full_patch_lines = _patch_summary_lines(full_content_html, limit=400)
                if len(full_patch_lines) >= len(patch_lines):
                    patch_lines = full_patch_lines
    except DeadlockError as error:
        return _html_response(TEMPLATES.TemplateResponse(
            request,
            "error.html",
            _base_context(
                request,
                page_title="Patch Note Not Found | Deadlock Stats Tracker",
                meta_description="That Deadlock patch note could not be loaded right now.",
                meta_robots="noindex,follow",
                message=str(error),
            ),
            status_code=404,
        ))

    return _html_response(TEMPLATES.TemplateResponse(
        request,
        "patch_note_detail.html",
        _base_context(
            request,
            page_title=f"{patch.title} | Deadlock Patch Notes",
            meta_description=f"Read the official Deadlock patch note summary for {patch.title}.",
            canonical_url=canonical_url,
            structured_data=[
                {
                    "@context": "https://schema.org",
                    "@type": "Article",
                    "headline": patch.title,
                    "datePublished": patch.pub_date,
                    "author": {"@type": "Person", "name": patch.creator or _patch_author_text(patch.author)},
                    "publisher": {"@type": "Organization", "name": "Deadlock Forums"},
                    "url": canonical_url,
                    "mainEntityOfPage": canonical_url,
                },
                _breadcrumb_structured_data(
                    request,
                    [
                        ("Home", str(request.url_for("home"))),
                        ("Patch Notes", str(request.url_for("patch_notes"))),
                        (patch.title, str(request.url_for(
                            "patch_note_detail",
                            patch_guid=patch.guid or _slugify(patch.title),
                            patch_slug=_slugify(patch.title),
                        ))),
                    ],
                ),
            ],
            patch_title=patch.title,
            patch_published_text=_patch_pub_date_text(patch.pub_date),
            patch_author_text=patch.creator or _patch_author_text(patch.author),
            patch_lines=patch_lines,
            official_url=patch.link,
            previous_patch_url=(
                str(
                    request.url_for(
                        "patch_note_detail",
                        patch_guid=previous_patch.guid or _slugify(previous_patch.title),
                        patch_slug=_slugify(previous_patch.title),
                    )
                )
                if previous_patch is not None else None
            ),
            previous_patch_title=previous_patch.title if previous_patch is not None else None,
            next_patch_url=(
                str(
                    request.url_for(
                        "patch_note_detail",
                        patch_guid=next_patch.guid or _slugify(next_patch.title),
                        patch_slug=_slugify(next_patch.title),
                    )
                )
                if next_patch is not None else None
            ),
            next_patch_title=next_patch.title if next_patch is not None else None,
        ),
    ))


@app.get("/heroes", response_class=HTMLResponse, name="heroes_directory")
async def heroes_directory(request: Request) -> HTMLResponse:
    api = PlayerService().api
    try:
        hero_info = await api.get_hero_info()
        heroes = sorted(hero_info.values(), key=lambda item: item.name.casefold())
    except DeadlockError as error:
        return _html_response(TEMPLATES.TemplateResponse(
            request,
            "error.html",
            _base_context(
                request,
                page_title="Heroes | Deadlock Stats Tracker",
                meta_description="Deadlock hero directory page.",
                meta_robots="noindex,follow",
                message=str(error),
            ),
            status_code=404,
        ))

    hero_cards = [
        HeroDirectoryCardView(
            hero_name=hero.name,
            detail_url=str(request.url_for("hero_detail", hero_id=str(hero.hero_id), hero_slug=_slugify(hero.name))),
            hero_icon_url=hero.icon_small,
            hero_portrait_url=hero.portrait_url,
            hero_background_image_url=hero.background_image_url,
        )
        for hero in heroes
    ]

    return _html_response(TEMPLATES.TemplateResponse(
        request,
        "heroes_directory.html",
        _base_context(
            request,
            page_title="Deadlock Heroes | Deadlock Stats Tracker",
            meta_description="Browse the full Deadlock hero directory and open dedicated hero guide pages.",
            structured_data=[
                {
                    "@context": "https://schema.org",
                    "@type": "CollectionPage",
                    "name": "Deadlock Heroes",
                    "url": _public_url(request, str(request.url_for("heroes_directory"))),
                    "description": "Browse the full Deadlock hero directory and open dedicated hero guide pages.",
                },
                _breadcrumb_structured_data(
                    request,
                    [
                        ("Home", str(request.url_for("home"))),
                        ("Heroes", str(request.url_for("heroes_directory"))),
                    ],
                ),
            ],
            hero_cards=hero_cards,
        ),
    ))


@app.get("/items", response_class=HTMLResponse, name="items_directory")
async def items_directory(request: Request) -> HTMLResponse:
    api = PlayerService().api
    try:
        item_info = await api.get_all_item_info()
    except DeadlockError as error:
        return _html_response(TEMPLATES.TemplateResponse(
            request,
            "error.html",
            _base_context(
                request,
                page_title="Items | Deadlock Stats Tracker",
                meta_description="Deadlock item directory page.",
                meta_robots="noindex,follow",
                message=str(error),
            ),
            status_code=404,
        ))

    items = sorted(
        [item for item in item_info.values() if item.item_type == "upgrade"],
        key=lambda item: item.name.casefold(),
    )
    item_cards = [
        ItemDirectoryCardView(
            item_name=item.name,
            detail_url=str(request.url_for("item_detail", item_id=str(item.item_id), item_slug=_slugify(item.name))),
            item_image_url=item.shop_image or item.image,
            slot_type=_friendly_slot_type(item.item_slot_type),
            tier_text=_friendly_item_tier_text(item.item_tier),
            cost_text=f"{item.cost:,} souls" if item.cost else "Cost Unknown",
        )
        for item in items
    ]

    return _html_response(TEMPLATES.TemplateResponse(
        request,
        "items_directory.html",
        _base_context(
            request,
            page_title="Deadlock Items | Deadlock Stats Tracker",
            meta_description="Browse the full Deadlock item directory and open dedicated item guide pages.",
            structured_data=[
                {
                    "@context": "https://schema.org",
                    "@type": "CollectionPage",
                    "name": "Deadlock Items",
                    "url": _public_url(request, str(request.url_for("items_directory"))),
                    "description": "Browse the full Deadlock item directory and open dedicated item guide pages.",
                },
                _breadcrumb_structured_data(
                    request,
                    [
                        ("Home", str(request.url_for("home"))),
                        ("Items", str(request.url_for("items_directory"))),
                    ],
                ),
            ],
            item_cards=item_cards,
        ),
    ))


@app.get("/leaderboards", response_class=HTMLResponse, name="leaderboards")
async def leaderboards(request: Request) -> HTMLResponse:
    api = PlayerService().api
    try:
        hero_info = await api.get_hero_info()
    except DeadlockError as error:
        return _html_response(TEMPLATES.TemplateResponse(
            request,
            "error.html",
            _base_context(
                request,
                page_title="Deadlock Leaderboards | Deadlock Stats Tracker",
                meta_description="Deadlock leaderboard hub page.",
                meta_robots="noindex,follow",
                message=str(error),
            ),
            status_code=404,
        ))

    region_cards = [
        LeaderboardRegionCardView(
            region_slug=region_slug,
            region_name=region_name,
            detail_url=str(request.url_for("leaderboard_region", region_slug=region_slug)),
            description=description,
        )
        for region_slug, region_name, description, _ in LEADERBOARD_REGIONS
    ]
    hero_cards = [
        StreetBrawlHeroCardView(
            hero_id=hero.hero_id,
            hero_name=hero.name,
            hero_icon_url=hero.icon_small,
            hero_portrait_url=hero.portrait_url,
            hero_background_image_url=hero.background_image_url,
            build_url=str(
                request.url_for(
                    "leaderboard_region_hero",
                    region_slug="north-america",
                    hero_id=str(hero.hero_id),
                    hero_slug=_slugify(hero.name),
                )
            ),
        )
        for hero in sorted(hero_info.values(), key=lambda item: item.name.casefold())
    ]

    return _html_response(TEMPLATES.TemplateResponse(
        request,
        "leaderboards.html",
        _base_context(
            request,
            page_title="Deadlock Leaderboards | Deadlock Stats Tracker",
            meta_description="Browse Deadlock leaderboard pages by region and by hero to find top tracked players.",
            structured_data=[
                {
                    "@context": "https://schema.org",
                    "@type": "CollectionPage",
                    "name": "Deadlock Leaderboards",
                    "url": _public_url(request, str(request.url_for("leaderboards"))),
                    "description": "Browse Deadlock leaderboard pages by region and hero.",
                },
                _breadcrumb_structured_data(
                    request,
                    [
                        ("Home", str(request.url_for("home"))),
                        ("Leaderboards", str(request.url_for("leaderboards"))),
                    ],
                ),
            ],
            region_cards=region_cards,
            hero_cards=hero_cards,
        ),
    ))


@app.get("/leaderboards/{region_slug}", response_class=HTMLResponse, name="leaderboard_region")
async def leaderboard_region(request: Request, region_slug: str) -> HTMLResponse:
    redirect_slug = LEADERBOARD_REGION_REDIRECTS.get(region_slug)
    if redirect_slug is not None:
        return RedirectResponse(url=str(request.url_for("leaderboard_region", region_slug=redirect_slug)), status_code=308)

    api = PlayerService().api
    region_name = _region_name(region_slug)
    if region_name is None:
        return _html_response(TEMPLATES.TemplateResponse(
            request,
            "error.html",
            _base_context(
                request,
                page_title="Leaderboard Not Found | Deadlock Stats Tracker",
                meta_description="That Deadlock leaderboard page could not be loaded right now.",
                meta_robots="noindex,follow",
                message="That leaderboard region could not be found.",
            ),
            status_code=404,
        ))

    try:
        entries = await api.get_leaderboard(region=_region_api_value(region_slug))
        hero_info = await api.get_hero_info()
        rank_info = await api.get_rank_info()
    except DeadlockError as error:
        return _html_response(TEMPLATES.TemplateResponse(
            request,
            "error.html",
            _base_context(
                request,
                page_title=f"{region_name} Leaderboard | Deadlock Stats Tracker",
                meta_description=f"That {region_name} Deadlock leaderboard page could not be loaded right now.",
                meta_robots="noindex,follow",
                message=str(error),
            ),
            status_code=404,
        ))

    rows = [
        LeaderboardEntryView(
            rank_number=index,
            player_name=entry.account_name or f"Player {index}",
            player_url=_leaderboard_player_url(request, entry.account_name, entry.possible_account_ids),
            hero_names_text=_leaderboard_hero_names(entry.top_hero_ids, hero_info),
            rank_name=friendly_rank_name(entry.badge_level or entry.rank),
            rank_badge_image_url=_rank_badge_image_url(entry.badge_level or entry.rank, rank_info),
        )
        for index, entry in enumerate(entries[:50], start=1)
    ]
    hero_cards = [
        StreetBrawlHeroCardView(
            hero_id=hero.hero_id,
            hero_name=hero.name,
            hero_icon_url=hero.icon_small,
            hero_portrait_url=hero.portrait_url,
            hero_background_image_url=hero.background_image_url,
            build_url=str(
                request.url_for(
                    "leaderboard_region_hero",
                    region_slug=region_slug,
                    hero_id=str(hero.hero_id),
                    hero_slug=_slugify(hero.name),
                )
            ),
        )
        for hero in sorted(hero_info.values(), key=lambda item: item.name.casefold())
    ]

    return _html_response(TEMPLATES.TemplateResponse(
        request,
        "leaderboard_region.html",
        _base_context(
            request,
            page_title=f"{region_name} Deadlock Leaderboard | Deadlock Stats Tracker",
            meta_description=f"Browse the top tracked Deadlock players for {region_name}, with current badge estimates and top heroes.",
            structured_data=[
                {
                    "@context": "https://schema.org",
                    "@type": "CollectionPage",
                    "name": f"{region_name} Deadlock Leaderboard",
                    "url": _public_url(request, str(request.url_for("leaderboard_region", region_slug=region_slug))),
                    "description": f"Browse the top tracked Deadlock players for {region_name}.",
                },
                _breadcrumb_structured_data(
                    request,
                    [
                        ("Home", str(request.url_for("home"))),
                        ("Leaderboards", str(request.url_for("leaderboards"))),
                        (region_name, str(request.url_for("leaderboard_region", region_slug=region_slug))),
                    ],
                ),
            ],
            region_slug=region_slug,
            region_name=region_name,
            rows=rows,
            hero_cards=hero_cards,
        ),
    ))


@app.get(
    "/leaderboards/{region_slug}/{hero_id}/{hero_slug}",
    response_class=HTMLResponse,
    name="leaderboard_region_hero",
)
async def leaderboard_region_hero(
    request: Request,
    region_slug: str,
    hero_id: str,
    hero_slug: str,
) -> HTMLResponse:
    redirect_slug = LEADERBOARD_REGION_REDIRECTS.get(region_slug)
    if redirect_slug is not None:
        return RedirectResponse(
            url=str(
                request.url_for(
                    "leaderboard_region_hero",
                    region_slug=redirect_slug,
                    hero_id=hero_id,
                    hero_slug=hero_slug,
                )
            ),
            status_code=308,
        )

    api = PlayerService().api
    region_name = _region_name(region_slug)
    parsed_hero_id = _parse_optional_int(hero_id)
    if region_name is None or parsed_hero_id is None:
        return _html_response(TEMPLATES.TemplateResponse(
            request,
            "error.html",
            _base_context(
                request,
                page_title="Hero Leaderboard Not Found | Deadlock Stats Tracker",
                meta_description="That Deadlock hero leaderboard page could not be loaded right now.",
                meta_robots="noindex,follow",
                message="That hero leaderboard could not be found.",
            ),
            status_code=404,
        ))

    try:
        hero_info = await api.get_hero_info()
        hero = hero_info.get(parsed_hero_id)
        if hero is None:
            raise DeadlockError("That hero could not be found.")
        entries = await api.get_leaderboard(region=_region_api_value(region_slug), hero_id=parsed_hero_id)
        rank_info = await api.get_rank_info()
    except DeadlockError as error:
        return _html_response(TEMPLATES.TemplateResponse(
            request,
            "error.html",
            _base_context(
                request,
                page_title="Hero Leaderboard Not Found | Deadlock Stats Tracker",
                meta_description="That Deadlock hero leaderboard page could not be loaded right now.",
                meta_robots="noindex,follow",
                message=str(error),
            ),
            status_code=404,
        ))

    canonical_url = _public_url(
        request,
        str(
            request.url_for(
                "leaderboard_region_hero",
                region_slug=region_slug,
                hero_id=str(hero.hero_id),
                hero_slug=_slugify(hero.name),
            )
        ),
    )
    if request.url.path != _url_path(canonical_url):
        return RedirectResponse(url=canonical_url, status_code=308)

    rows = [
        LeaderboardEntryView(
            rank_number=index,
            player_name=entry.account_name or f"Player {index}",
            player_url=_leaderboard_player_url(request, entry.account_name, entry.possible_account_ids),
            hero_names_text=_leaderboard_hero_names(entry.top_hero_ids, hero_info),
            rank_name=friendly_rank_name(entry.badge_level or entry.rank),
            rank_badge_image_url=_rank_badge_image_url(entry.badge_level or entry.rank, rank_info),
        )
        for index, entry in enumerate(entries[:50], start=1)
    ]

    return _html_response(TEMPLATES.TemplateResponse(
        request,
        "leaderboard_hero.html",
        _base_context(
            request,
            page_title=f"Best {hero.name} Players in {region_name} | Deadlock Stats Tracker",
            meta_description=f"Browse the top tracked {hero.name} players in {region_name} with current badge estimates and linked player pages.",
            canonical_url=canonical_url,
            og_image=hero.portrait_url or hero.background_image_url or _public_url(
                request,
                str(request.url_for("static", path="/branding/deadlock-stats-tracker-logo-transparent.webp")),
            ),
            structured_data=[
                {
                    "@context": "https://schema.org",
                    "@type": "CollectionPage",
                    "name": f"Best {hero.name} Players in {region_name}",
                    "url": canonical_url,
                    "description": f"Browse the top tracked {hero.name} players in {region_name}.",
                },
                _breadcrumb_structured_data(
                    request,
                    [
                        ("Home", str(request.url_for("home"))),
                        ("Leaderboards", str(request.url_for("leaderboards"))),
                        (region_name, str(request.url_for("leaderboard_region", region_slug=region_slug))),
                        (hero.name, canonical_url),
                    ],
                ),
            ],
            region_slug=region_slug,
            region_name=region_name,
            hero=hero,
            rows=rows,
            leaderboard_region_url=str(request.url_for("leaderboard_region", region_slug=region_slug)),
            hero_detail_url=str(
                request.url_for("hero_detail", hero_id=str(hero.hero_id), hero_slug=_slugify(hero.name))
            ),
            hero_rank_distribution_url=str(
                request.url_for(
                    "hero_rank_distribution",
                    hero_id=str(hero.hero_id),
                    hero_slug=_slugify(hero.name),
                )
            ),
        ),
    ))


@app.get("/rank-distribution", response_class=HTMLResponse, name="rank_distribution")
async def rank_distribution(request: Request) -> HTMLResponse:
    api = PlayerService().api
    try:
        distribution = await api.get_player_rank_distribution()
        rank_info = await api.get_rank_info()
        hero_info = await api.get_hero_info()
    except DeadlockError as error:
        return _html_response(TEMPLATES.TemplateResponse(
            request,
            "error.html",
            _base_context(
                request,
                page_title="Deadlock Rank Distribution | Deadlock Stats Tracker",
                meta_description="Deadlock rank distribution page.",
                meta_robots="noindex,follow",
                message=str(error),
            ),
            status_code=404,
        ))

    tiers = _build_player_rank_distribution_views(distribution, rank_info)
    summary_cards = _build_rank_distribution_summary_views(distribution, rank_info)
    hero_cards = [
        StreetBrawlHeroCardView(
            hero_id=hero.hero_id,
            hero_name=hero.name,
            hero_icon_url=hero.icon_small,
            hero_portrait_url=hero.portrait_url,
            hero_background_image_url=hero.background_image_url,
            build_url=str(
                request.url_for(
                    "hero_rank_distribution",
                    hero_id=str(hero.hero_id),
                    hero_slug=_slugify(hero.name),
                )
            ),
        )
        for hero in sorted(hero_info.values(), key=lambda item: item.name.casefold())
    ]

    return _html_response(TEMPLATES.TemplateResponse(
        request,
        "rank_distribution.html",
        _base_context(
            request,
            page_title="Deadlock Rank Distribution | Deadlock Stats Tracker",
            meta_description="See the estimated Deadlock rank distribution and open hero-specific rank-distribution pages.",
            structured_data=[
                {
                    "@context": "https://schema.org",
                    "@type": "CollectionPage",
                    "name": "Deadlock Rank Distribution",
                    "url": _public_url(request, str(request.url_for("rank_distribution"))),
                    "description": "See the estimated Deadlock rank distribution and open hero-specific rank-distribution pages.",
                },
                _breadcrumb_structured_data(
                    request,
                    [
                        ("Home", str(request.url_for("home"))),
                        ("Rank Distribution", str(request.url_for("rank_distribution"))),
                    ],
                ),
            ],
            rank_distribution=tiers,
            summary_cards=summary_cards,
            hero_cards=hero_cards,
        ),
    ))


@app.get(
    "/heroes/{hero_id}/{hero_slug}/rank-distribution",
    response_class=HTMLResponse,
    name="hero_rank_distribution",
)
async def hero_rank_distribution(request: Request, hero_id: str, hero_slug: str) -> HTMLResponse:
    api = PlayerService().api
    parsed_hero_id = _parse_optional_int(hero_id)
    if parsed_hero_id is None:
        return _html_response(TEMPLATES.TemplateResponse(
            request,
            "error.html",
            _base_context(
                request,
                page_title="Hero Rank Distribution Not Found | Deadlock Stats Tracker",
                meta_description="That Deadlock hero rank distribution page could not be loaded right now.",
                meta_robots="noindex,follow",
                message="That hero could not be found.",
            ),
            status_code=404,
        ))

    try:
        hero_info = await api.get_hero_info()
        hero = hero_info.get(parsed_hero_id)
        if hero is None:
            raise DeadlockError("That hero could not be found.")
        distribution = await api.get_hero_rank_distribution(parsed_hero_id)
        rank_info = await api.get_rank_info()
    except DeadlockError as error:
        return _html_response(TEMPLATES.TemplateResponse(
            request,
            "error.html",
            _base_context(
                request,
                page_title="Hero Rank Distribution Not Found | Deadlock Stats Tracker",
                meta_description="That Deadlock hero rank distribution page could not be loaded right now.",
                meta_robots="noindex,follow",
                message=str(error),
            ),
            status_code=404,
        ))

    canonical_url = _public_url(
        request,
        str(
            request.url_for(
                "hero_rank_distribution",
                hero_id=str(hero.hero_id),
                hero_slug=_slugify(hero.name),
            )
        ),
    )
    if request.url.path != _url_path(canonical_url):
        return RedirectResponse(url=canonical_url, status_code=308)

    tiers = _build_player_rank_distribution_views(distribution, rank_info)
    summary_cards = _build_rank_distribution_summary_views(distribution, rank_info)

    return _html_response(TEMPLATES.TemplateResponse(
        request,
        "hero_rank_distribution.html",
        _base_context(
            request,
            page_title=f"{hero.name} Rank Distribution | Deadlock Stats Tracker",
            meta_description=f"See the estimated rank distribution for tracked {hero.name} players in Deadlock.",
            canonical_url=canonical_url,
            og_image=hero.portrait_url or hero.background_image_url or _public_url(
                request,
                str(request.url_for("static", path="/branding/deadlock-stats-tracker-logo-transparent.webp")),
            ),
            structured_data=[
                {
                    "@context": "https://schema.org",
                    "@type": "CollectionPage",
                    "name": f"{hero.name} Rank Distribution",
                    "url": canonical_url,
                    "description": f"See the estimated rank distribution for tracked {hero.name} players in Deadlock.",
                },
                _breadcrumb_structured_data(
                    request,
                    [
                        ("Home", str(request.url_for("home"))),
                        ("Heroes", str(request.url_for("heroes_directory"))),
                        (hero.name, str(request.url_for("hero_detail", hero_id=str(hero.hero_id), hero_slug=_slugify(hero.name)))),
                        ("Rank Distribution", canonical_url),
                    ],
                ),
            ],
            hero=hero,
            rank_distribution=tiers,
            summary_cards=summary_cards,
            hero_detail_url=str(
                request.url_for("hero_detail", hero_id=str(hero.hero_id), hero_slug=_slugify(hero.name))
            ),
            global_leaderboard_url=str(
                request.url_for(
                    "leaderboard_region_hero",
                    region_slug="row",
                    hero_id=str(hero.hero_id),
                    hero_slug=_slugify(hero.name),
                )
            ),
        ),
    ))


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
    is_default_view = (
        selected_hero_id is None
        and selected_rank_floor == 81
        and selected_mode == "normal"
        and selected_window_days == 7
        and selected_min_matches == 1000
    )

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
                    detail_url=str(
                        request.url_for(
                            "item_detail",
                            item_id=str(item_info.item_id),
                            item_slug=_slugify(item_info.name),
                        )
                    ),
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
        _base_context(
            request,
            page_title="Best Deadlock Items | Deadlock Stats Tracker",
            meta_description=(
                "Browse the best Deadlock items by win rate, hero, rank floor, mode, and time window using live meta analytics."
            ),
            meta_robots="index,follow" if is_default_view else "noindex,follow",
            structured_data=[
                {
                    "@context": "https://schema.org",
                    "@type": "CollectionPage",
                    "name": "Best Deadlock Items",
                    "url": _public_url(request, str(request.url_for("best_items"))),
                    "description": "Browse the best Deadlock items by win rate, hero, rank floor, and mode.",
                },
                _breadcrumb_structured_data(
                    request,
                    [
                        ("Home", str(request.url_for("home"))),
                        ("Best Items", str(request.url_for("best_items"))),
                    ],
                ),
            ],
            hero_options=[
                FilterOptionView(value="", label="All heroes"),
                *[
                    FilterOptionView(value=str(hero.hero_id), label=hero.name)
                    for hero in sorted(hero_info.values(), key=lambda item: item.name.casefold())
                ],
            ],
            rank_options=rank_options,
            mode_options=[
                FilterOptionView(value="normal", label="Normal"),
                FilterOptionView(value="street_brawl", label="Street Brawl"),
            ],
            window_options=[
                FilterOptionView(value="7", label="Last 7 days"),
                FilterOptionView(value="30", label="Last 30 days"),
                FilterOptionView(value="90", label="Last 90 days"),
            ],
            selected_hero_id=str(selected_hero_id) if selected_hero_id is not None else "",
            selected_rank_floor=str(selected_rank_floor) if selected_rank_floor is not None else "",
            selected_mode=selected_mode,
            selected_window_days=str(selected_window_days),
            selected_min_matches=selected_min_matches,
            items=best_item_rows,
            error_message=error_message,
        ),
    ))


@app.get("/items/{item_id}/{item_slug}", response_class=HTMLResponse, name="item_detail")
async def item_detail(request: Request, item_id: str, item_slug: str) -> HTMLResponse:
    api = PlayerService().api
    parsed_item_id = _parse_optional_int(item_id)
    if parsed_item_id is None:
        return _html_response(TEMPLATES.TemplateResponse(
            request,
            "error.html",
            _base_context(
                request,
                page_title="Item Not Found | Deadlock Stats Tracker",
                meta_description="That Deadlock item page could not be loaded right now.",
                meta_robots="noindex,follow",
                error_subject="item",
                error_hints=["Try another item", "Try the item directory", "Try again in a moment"],
                message="That item could not be found.",
            ),
            status_code=404,
        ))

    try:
        item = await api.get_item_info(parsed_item_id)
        if item is None:
            raise DeadlockError("That item could not be found.")
        canonical_url = _public_url(
            request,
            str(request.url_for("item_detail", item_id=str(parsed_item_id), item_slug=_slugify(item.name))),
        )
        if request.url.path != _url_path(canonical_url):
            return RedirectResponse(url=canonical_url, status_code=308)
    except DeadlockError as error:
        return _html_response(TEMPLATES.TemplateResponse(
            request,
            "error.html",
            _base_context(
                request,
                page_title="Item Not Found | Deadlock Stats Tracker",
                meta_description="That Deadlock item page could not be loaded right now.",
                meta_robots="noindex,follow",
                error_subject="item",
                error_hints=["Try another item", "Try the item directory", "Try again in a moment"],
                message=str(error),
            ),
            status_code=404,
        ))

    mode_stats: list[ItemModeStatView] = []
    data_warning: str | None = None
    for mode_name in ("normal", "street_brawl"):
        try:
            stats = await api.get_item_stats(game_mode=mode_name, min_matches=100)
            stat = next((entry for entry in stats if entry.item_id == parsed_item_id), None)
            if stat is None:
                continue
            mode_stats.append(
                ItemModeStatView(
                    mode_name="Normal" if mode_name == "normal" else "Street Brawl",
                    win_rate_percent=f"{(stat.wins / stat.matches):.1%}" if stat.matches else "0.0%",
                    matches_text=f"{stat.matches:,} matches",
                    players_text=f"{stat.players:,} players",
                    timing_text=_friendly_time_seconds(stat.avg_buy_time_s),
                )
            )
        except DeadlockError as error:
            if data_warning is None:
                data_warning = _friendly_meta_error_message(error, topic=f"{item.name} item stats")

    return _html_response(TEMPLATES.TemplateResponse(
        request,
        "item_detail.html",
        _base_context(
            request,
            page_title=f"{item.name} Item Guide | Deadlock Stats Tracker",
            meta_description=f"See Deadlock item stats and current mode-by-mode performance for {item.name}.",
            canonical_url=canonical_url,
            structured_data=[
                {
                    "@context": "https://schema.org",
                    "@type": "WebPage",
                    "name": f"{item.name} Item Guide",
                    "url": canonical_url,
                    "description": f"See Deadlock item stats and current mode-by-mode performance for {item.name}.",
                },
                _breadcrumb_structured_data(
                    request,
                    [
                        ("Home", str(request.url_for("home"))),
                        ("Best Items", str(request.url_for("best_items"))),
                        (item.name, str(request.url_for("item_detail", item_id=str(item.item_id), item_slug=_slugify(item.name)))),
                    ],
                ),
            ],
            item=item,
            item_mode_stats=mode_stats,
            data_warning=data_warning,
        ),
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
    is_default_view = (
        selected_rank_floor == 81
        and selected_mode == "normal"
        and selected_window_days == 7
        and selected_min_matches == 1000
    )

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
                    hero_id=hero.hero_id,
                    rank_number=index,
                    hero_name=hero.name,
                    detail_url=str(
                        request.url_for(
                            "hero_detail",
                            hero_id=str(hero.hero_id),
                            hero_slug=_slugify(hero.name),
                        )
                    ),
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
        _base_context(
            request,
            page_title="Best Deadlock Heroes | Deadlock Stats Tracker",
            meta_description=(
                "Track the best Deadlock heroes by win rate, pick rate, rank floor, mode, and time window with live meta data."
            ),
            meta_robots="index,follow" if is_default_view else "noindex,follow",
            structured_data=[
                {
                    "@context": "https://schema.org",
                    "@type": "CollectionPage",
                    "name": "Best Deadlock Heroes",
                    "url": _public_url(request, str(request.url_for("best_heroes"))),
                    "description": "Track the best Deadlock heroes by win rate, pick rate, rank floor, and mode.",
                },
                _breadcrumb_structured_data(
                    request,
                    [
                        ("Home", str(request.url_for("home"))),
                        ("Best Heroes", str(request.url_for("best_heroes"))),
                    ],
                ),
            ],
            rank_options=_rank_floor_options(),
            mode_options=[
                FilterOptionView(value="normal", label="Normal"),
                FilterOptionView(value="street_brawl", label="Street Brawl"),
            ],
            window_options=[
                FilterOptionView(value="7", label="Last 7 days"),
                FilterOptionView(value="30", label="Last 30 days"),
                FilterOptionView(value="90", label="Last 90 days"),
            ],
            selected_rank_floor=str(selected_rank_floor) if selected_rank_floor is not None else "",
            selected_mode=selected_mode,
            selected_window_days=str(selected_window_days),
            selected_min_matches=selected_min_matches,
            heroes=hero_rows,
            error_message=error_message,
        ),
    ))


@app.get("/heroes/{hero_id}/{hero_slug}", response_class=HTMLResponse, name="hero_detail")
async def hero_detail(request: Request, hero_id: str, hero_slug: str) -> HTMLResponse:
    api = PlayerService().api
    parsed_hero_id = _parse_optional_int(hero_id)
    if parsed_hero_id is None:
        return _html_response(TEMPLATES.TemplateResponse(
            request,
            "error.html",
            _base_context(
                request,
                page_title="Hero Not Found | Deadlock Stats Tracker",
                meta_description="That Deadlock hero page could not be loaded right now.",
                meta_robots="noindex,follow",
                error_subject="hero",
                error_hints=["Try another hero", "Try the hero directory", "Try again in a moment"],
                message="That hero could not be found.",
            ),
            status_code=404,
        ))

    try:
        hero_info = await api.get_hero_info()
        hero = hero_info.get(parsed_hero_id)
        if hero is None:
            raise DeadlockError("That hero could not be found.")
        canonical_url = _public_url(
            request,
            str(request.url_for("hero_detail", hero_id=str(hero.hero_id), hero_slug=_slugify(hero.name))),
        )
        if request.url.path != _url_path(canonical_url):
            return RedirectResponse(url=canonical_url, status_code=308)
    except DeadlockError as error:
        return _html_response(TEMPLATES.TemplateResponse(
            request,
            "error.html",
            _base_context(
                request,
                page_title="Hero Not Found | Deadlock Stats Tracker",
                meta_description="That Deadlock hero page could not be loaded right now.",
                meta_robots="noindex,follow",
                error_subject="hero",
                error_hints=["Try another hero", "Try the hero directory", "Try again in a moment"],
                message=str(error),
            ),
            status_code=404,
        ))

    hero_stat = None
    top_items: list[HeroDetailItemView] = []
    matchup_preview: list[HeroPeerStatView] = []
    synergy_preview: list[HeroPeerStatView] = []
    data_warning: str | None = None
    try:
        analytics = await api.get_hero_analytics(game_mode="normal", min_matches=500)
        hero_stat = next((entry for entry in analytics if entry.hero_id == hero.hero_id), None)
        item_stats = await api.get_item_stats(hero_id=hero.hero_id, game_mode="normal", min_matches=100)
        counter_stats = await api.get_hero_counter_stats(hero_id=hero.hero_id, game_mode="normal", min_matches=200)
        synergy_stats = await api.get_hero_synergy_stats(hero_id=hero.hero_id, game_mode="normal", min_matches=200)
        item_info_map = await api.get_all_item_info()
        ranked_items = sorted(
            [
                (stat, item_info_map.get(stat.item_id))
                for stat in item_stats
                if item_info_map.get(stat.item_id) is not None and item_info_map[stat.item_id].item_type == "upgrade"
            ],
            key=lambda entry: (((entry[0].wins / entry[0].matches) if entry[0].matches else 0.0), entry[0].matches),
            reverse=True,
        )[:10]
        top_items = [
            HeroDetailItemView(
                item_name=item.name,
                item_url=str(request.url_for("item_detail", item_id=str(item.item_id), item_slug=_slugify(item.name))),
                item_image_url=item.shop_image or item.image,
                slot_type=_friendly_slot_type(item.item_slot_type),
                tier_text=_friendly_item_tier_text(item.item_tier),
                cost_text=f"{item.cost:,} souls" if item.cost else "Cost Unknown",
                win_rate_percent=f"{(stat.wins / stat.matches):.1%}" if stat.matches else "0.0%",
                matches_text=f"{stat.matches:,} matches",
            )
            for stat, item in ranked_items
            if item is not None
        ]
        matchup_preview = _build_counter_views(counter_stats, hero_info, request=request, view="favorable", limit=3)
        synergy_preview = _build_synergy_views(synergy_stats, hero.hero_id, hero_info, request=request, limit=3)
    except DeadlockError as error:
        data_warning = _friendly_meta_error_message(error, topic=f"{hero.name} hero details")

    return _html_response(TEMPLATES.TemplateResponse(
        request,
        "hero_detail.html",
        _base_context(
            request,
            page_title=f"{hero.name} Guide | Deadlock Stats Tracker",
            meta_description=f"See current Deadlock stats, win rate, and top items for {hero.name}.",
            canonical_url=canonical_url,
            og_image=hero.portrait_url or hero.background_image_url or _public_url(
                request, str(request.url_for("static", path="/community-assets/graphics/background-city.png"))
            ),
            structured_data=[
                {
                    "@context": "https://schema.org",
                    "@type": "WebPage",
                    "name": f"{hero.name} Guide",
                    "url": canonical_url,
                    "description": f"See current Deadlock stats, win rate, and top items for {hero.name}.",
                },
                _breadcrumb_structured_data(
                    request,
                    [
                        ("Home", str(request.url_for("home"))),
                        ("Best Heroes", str(request.url_for("best_heroes"))),
                        (hero.name, str(request.url_for("hero_detail", hero_id=str(hero.hero_id), hero_slug=_slugify(hero.name)))),
                    ],
                ),
            ],
            hero=hero,
            hero_stat=hero_stat,
            hero_top_items=top_items,
            hero_matchup_preview=matchup_preview,
            hero_synergy_preview=synergy_preview,
            data_warning=data_warning,
            hero_items_url=str(request.url_for("hero_items", hero_id=str(hero.hero_id), hero_slug=_slugify(hero.name))),
            hero_matchups_url=str(request.url_for("hero_matchups", hero_id=str(hero.hero_id), hero_slug=_slugify(hero.name))),
            hero_rank_distribution_url=str(
                request.url_for(
                    "hero_rank_distribution",
                    hero_id=str(hero.hero_id),
                    hero_slug=_slugify(hero.name),
                )
            ),
            hero_global_leaderboard_url=str(
                request.url_for(
                    "leaderboard_region_hero",
                    region_slug="north-america",
                    hero_id=str(hero.hero_id),
                    hero_slug=_slugify(hero.name),
                )
            ),
        ),
    ))


@app.get("/heroes/{hero_id}/{hero_slug}/items", response_class=HTMLResponse, name="hero_items")
async def hero_items(request: Request, hero_id: str, hero_slug: str) -> HTMLResponse:
    api = PlayerService().api
    parsed_hero_id = _parse_optional_int(hero_id)
    if parsed_hero_id is None:
        return _html_response(TEMPLATES.TemplateResponse(
            request,
            "error.html",
            _base_context(
                request,
                page_title="Hero Items Not Found | Deadlock Stats Tracker",
                meta_description="That Deadlock hero item page could not be loaded right now.",
                meta_robots="noindex,follow",
                error_subject="hero",
                error_hints=["Try another hero", "Try the hero directory", "Try again in a moment"],
                message="That hero could not be found.",
            ),
            status_code=404,
        ))

    try:
        hero_info = await api.get_hero_info()
        hero = hero_info.get(parsed_hero_id)
        if hero is None:
            raise DeadlockError("That hero could not be found.")
        canonical_url = _public_url(
            request,
            str(request.url_for("hero_items", hero_id=str(hero.hero_id), hero_slug=_slugify(hero.name))),
        )
        if request.url.path != _url_path(canonical_url):
            return RedirectResponse(url=canonical_url, status_code=308)
    except DeadlockError as error:
        return _html_response(TEMPLATES.TemplateResponse(
            request,
            "error.html",
            _base_context(
                request,
                page_title="Hero Items Not Found | Deadlock Stats Tracker",
                meta_description="That Deadlock hero item page could not be loaded right now.",
                meta_robots="noindex,follow",
                error_subject="hero",
                error_hints=["Try another hero", "Try the hero directory", "Try again in a moment"],
                message=str(error),
            ),
            status_code=404,
        ))

    top_items: list[HeroDetailItemView] = []
    data_warning: str | None = None
    try:
        item_stats = await api.get_item_stats(hero_id=hero.hero_id, game_mode="normal", min_matches=80)
        item_info_map = await api.get_all_item_info()
        ranked_items = sorted(
            [
                (stat, item_info_map.get(stat.item_id))
                for stat in item_stats
                if item_info_map.get(stat.item_id) is not None and item_info_map[stat.item_id].item_type == "upgrade"
            ],
            key=lambda entry: (((entry[0].wins / entry[0].matches) if entry[0].matches else 0.0), entry[0].matches),
            reverse=True,
        )
        top_items = [
            HeroDetailItemView(
                item_name=item.name,
                item_url=str(request.url_for("item_detail", item_id=str(item.item_id), item_slug=_slugify(item.name))),
                item_image_url=item.shop_image or item.image,
                slot_type=_friendly_slot_type(item.item_slot_type),
                tier_text=_friendly_item_tier_text(item.item_tier),
                cost_text=f"{item.cost:,} souls" if item.cost else "Cost Unknown",
                win_rate_percent=f"{(stat.wins / stat.matches):.1%}" if stat.matches else "0.0%",
                matches_text=f"{stat.matches:,} matches",
            )
            for stat, item in ranked_items
            if item is not None
        ]
    except DeadlockError as error:
        data_warning = _friendly_meta_error_message(error, topic="hero item trends")

    return _html_response(TEMPLATES.TemplateResponse(
        request,
        "hero_items.html",
        _base_context(
            request,
            page_title=f"Best Items for {hero.name} | Deadlock Stats Tracker",
            meta_description=f"See the strongest tracked items and current build trends for {hero.name} in Deadlock.",
            canonical_url=canonical_url,
            og_image=hero.portrait_url or hero.background_image_url or _public_url(
                request, str(request.url_for("static", path="/community-assets/graphics/background-city.png"))
            ),
            structured_data=[
                {
                    "@context": "https://schema.org",
                    "@type": "CollectionPage",
                    "name": f"Best Items for {hero.name}",
                    "url": canonical_url,
                    "description": f"See the strongest tracked items and current build trends for {hero.name} in Deadlock.",
                },
                _breadcrumb_structured_data(
                    request,
                    [
                        ("Home", str(request.url_for("home"))),
                        ("Heroes", str(request.url_for("heroes_directory"))),
                        (hero.name, str(request.url_for("hero_detail", hero_id=str(hero.hero_id), hero_slug=_slugify(hero.name)))),
                        ("Best Items", str(request.url_for("hero_items", hero_id=str(hero.hero_id), hero_slug=_slugify(hero.name)))),
                    ],
                ),
            ],
            hero=hero,
            hero_top_items=top_items,
            data_warning=data_warning,
            hero_detail_url=str(request.url_for("hero_detail", hero_id=str(hero.hero_id), hero_slug=_slugify(hero.name))),
            hero_matchups_url=str(request.url_for("hero_matchups", hero_id=str(hero.hero_id), hero_slug=_slugify(hero.name))),
        ),
    ))


@app.get("/heroes/{hero_id}/{hero_slug}/matchups", response_class=HTMLResponse, name="hero_matchups")
async def hero_matchups(request: Request, hero_id: str, hero_slug: str) -> HTMLResponse:
    api = PlayerService().api
    parsed_hero_id = _parse_optional_int(hero_id)
    if parsed_hero_id is None:
        return _html_response(TEMPLATES.TemplateResponse(
            request,
            "error.html",
            _base_context(
                request,
                page_title="Hero Matchups Not Found | Deadlock Stats Tracker",
                meta_description="That Deadlock hero matchup page could not be loaded right now.",
                meta_robots="noindex,follow",
                error_subject="hero",
                error_hints=["Try another hero", "Try the hero directory", "Try again in a moment"],
                message="That hero could not be found.",
            ),
            status_code=404,
        ))

    try:
        hero_info = await api.get_hero_info()
        hero = hero_info.get(parsed_hero_id)
        if hero is None:
            raise DeadlockError("That hero could not be found.")
        canonical_url = _public_url(
            request,
            str(request.url_for("hero_matchups", hero_id=str(hero.hero_id), hero_slug=_slugify(hero.name))),
        )
        if request.url.path != _url_path(canonical_url):
            return RedirectResponse(url=canonical_url, status_code=308)
    except DeadlockError as error:
        return _html_response(TEMPLATES.TemplateResponse(
            request,
            "error.html",
            _base_context(
                request,
                page_title="Hero Matchups Not Found | Deadlock Stats Tracker",
                meta_description="That Deadlock hero matchup page could not be loaded right now.",
                meta_robots="noindex,follow",
                error_subject="hero",
                error_hints=["Try another hero", "Try the hero directory", "Try again in a moment"],
                message=str(error),
            ),
            status_code=404,
        ))

    favorable_matchups: list[HeroPeerStatView] = []
    difficult_matchups: list[HeroPeerStatView] = []
    synergy_rows: list[HeroPeerStatView] = []
    data_warning: str | None = None
    try:
        counter_stats = await api.get_hero_counter_stats(hero_id=hero.hero_id, game_mode="normal", min_matches=200)
        synergy_stats = await api.get_hero_synergy_stats(hero_id=hero.hero_id, game_mode="normal", min_matches=200)
        favorable_matchups = _build_counter_views(counter_stats, hero_info, request=request, view="favorable", limit=12)
        difficult_matchups = _build_counter_views(counter_stats, hero_info, request=request, view="difficult", limit=12)
        synergy_rows = _build_synergy_views(synergy_stats, hero.hero_id, hero_info, request=request, limit=12)
    except DeadlockError as error:
        data_warning = _friendly_meta_error_message(error, topic="hero matchup data")

    return _html_response(TEMPLATES.TemplateResponse(
        request,
        "hero_matchups.html",
        _base_context(
            request,
            page_title=f"{hero.name} Matchups | Deadlock Stats Tracker",
            meta_description=f"See favorable lanes, difficult opponents, and top synergy partners for {hero.name} in Deadlock.",
            canonical_url=canonical_url,
            og_image=hero.portrait_url or hero.background_image_url or _public_url(
                request, str(request.url_for("static", path="/community-assets/graphics/background-city.png"))
            ),
            structured_data=[
                {
                    "@context": "https://schema.org",
                    "@type": "CollectionPage",
                    "name": f"{hero.name} Matchups",
                    "url": canonical_url,
                    "description": f"See favorable lanes, difficult opponents, and top synergy partners for {hero.name} in Deadlock.",
                },
                _breadcrumb_structured_data(
                    request,
                    [
                        ("Home", str(request.url_for("home"))),
                        ("Heroes", str(request.url_for("heroes_directory"))),
                        (hero.name, str(request.url_for("hero_detail", hero_id=str(hero.hero_id), hero_slug=_slugify(hero.name)))),
                        ("Matchups", str(request.url_for("hero_matchups", hero_id=str(hero.hero_id), hero_slug=_slugify(hero.name)))),
                    ],
                ),
            ],
            hero=hero,
            favorable_matchups=favorable_matchups,
            difficult_matchups=difficult_matchups,
            synergy_rows=synergy_rows,
            data_warning=data_warning,
            hero_detail_url=str(request.url_for("hero_detail", hero_id=str(hero.hero_id), hero_slug=_slugify(hero.name))),
            hero_items_url=str(request.url_for("hero_items", hero_id=str(hero.hero_id), hero_slug=_slugify(hero.name))),
        ),
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
    is_default_view = (
        hero_id in {None, ""}
        and not item_level
        and selected_window_days == 7
        and selected_min_matches == 100
    )

    hero_info = await api.get_hero_info()
    sorted_heroes = sorted(hero_info.values(), key=lambda item: item.name.casefold())
    parsed_hero_id = _parse_optional_int(hero_id)
    selected_hero = hero_info.get(parsed_hero_id) if parsed_hero_id is not None else None
    if not sorted_heroes:
        return _html_response(TEMPLATES.TemplateResponse(
            request,
            "error.html",
            _base_context(
                request,
                page_title="Street Brawl Builds Unavailable | Deadlock Stats Tracker",
                meta_description="Street Brawl builds are temporarily unavailable because no active heroes were returned.",
                meta_robots="noindex,follow",
                message="No active heroes are currently available.",
            ),
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
                _base_context(
                    request,
                    page_title="Street Brawl Builds | Deadlock Stats Tracker",
                    meta_description=(
                        "Find the best Street Brawl builds in Deadlock, including high-win-rate items and common ability paths by hero."
                    ),
                    structured_data=[
                        {
                            "@context": "https://schema.org",
                            "@type": "CollectionPage",
                            "name": "Street Brawl Builds",
                            "url": _public_url(request, str(request.url_for("street_brawl_builds"))),
                            "description": (
                                "Find the best Street Brawl builds in Deadlock, including high-win-rate items and common ability paths by hero."
                            ),
                        },
                        _breadcrumb_structured_data(
                            request,
                            [
                                ("Home", str(request.url_for("home"))),
                                ("Street Brawl Builds", str(request.url_for("street_brawl_builds"))),
                            ],
                        ),
                    ],
                    hero_options=[
                        FilterOptionView(value=str(hero.hero_id), label=hero.name)
                        for hero in sorted_heroes
                ],
                item_level_options=[
                    FilterOptionView(value="", label="All item levels"),
                    FilterOptionView(value="1", label="Tier 1"),
                    FilterOptionView(value="2", label="Tier 2"),
                    FilterOptionView(value="3", label="Tier 3"),
                    FilterOptionView(value="4", label="Tier 4"),
                    FilterOptionView(value="legendary", label="Legendary"),
                ],
                window_options=[
                    FilterOptionView(value="7", label="Last 7 days"),
                    FilterOptionView(value="30", label="Last 30 days"),
                    FilterOptionView(value="90", label="Last 90 days"),
                ],
                sample_options=[
                    FilterOptionView(value="50", label="50+ matches"),
                    FilterOptionView(value="100", label="100+ matches"),
                    FilterOptionView(value="250", label="250+ matches"),
                    FilterOptionView(value="500", label="500+ matches"),
                    FilterOptionView(value="1000", label="1000+ matches"),
                ],
                selected_hero_id="",
                selected_item_level=selected_item_level,
                selected_window_days=str(selected_window_days),
                selected_min_matches=str(selected_min_matches),
                items=[],
                guide=None,
                selected_hero_name=None,
                hero_cards=hero_cards,
                error_message=None,
            ),
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
        _base_context(
            request,
            page_title=(
                f"{selected_hero.name} Street Brawl Build | Deadlock Stats Tracker"
                if selected_hero is not None
                else "Street Brawl Builds | Deadlock Stats Tracker"
            ),
            meta_description=(
                f"See the latest {selected_hero.name} Street Brawl build in Deadlock, including high-win-rate items and tracked ability path data."
                if selected_hero is not None
                else "Find the best Street Brawl builds in Deadlock, including high-win-rate items and common ability paths by hero."
            ),
            meta_robots="index,follow" if is_default_view else "noindex,follow",
            structured_data=[
                {
                    "@context": "https://schema.org",
                    "@type": "CollectionPage",
                    "name": "Street Brawl Builds",
                    "url": _public_url(request, str(request.url_for("street_brawl_builds"))),
                    "description": "Deadlock Street Brawl builds, item boards, and ability upgrade paths.",
                },
                _breadcrumb_structured_data(
                    request,
                    [
                        ("Home", str(request.url_for("home"))),
                        ("Street Brawl Builds", str(request.url_for("street_brawl_builds"))),
                    ],
                ),
            ],
            hero_options=[
                FilterOptionView(value=str(hero.hero_id), label=hero.name)
                for hero in sorted_heroes
            ],
            item_level_options=[
                FilterOptionView(value="", label="All item levels"),
                FilterOptionView(value="1", label="Tier 1"),
                FilterOptionView(value="2", label="Tier 2"),
                FilterOptionView(value="3", label="Tier 3"),
                FilterOptionView(value="4", label="Tier 4"),
                FilterOptionView(value="legendary", label="Legendary"),
            ],
            window_options=[
                FilterOptionView(value="7", label="Last 7 days"),
                FilterOptionView(value="30", label="Last 30 days"),
                FilterOptionView(value="90", label="Last 90 days"),
            ],
            sample_options=[
                FilterOptionView(value="50", label="50+ matches"),
                FilterOptionView(value="100", label="100+ matches"),
                FilterOptionView(value="250", label="250+ matches"),
                FilterOptionView(value="500", label="500+ matches"),
                FilterOptionView(value="1000", label="1000+ matches"),
            ],
            selected_hero_id=str(selected_hero.hero_id),
            selected_item_level=selected_item_level,
            selected_window_days=str(selected_window_days),
            selected_min_matches=str(selected_min_matches),
            items=item_rows,
            guide=guide,
            selected_hero_name=selected_hero.name,
            hero_cards=hero_cards,
            error_message=error_message,
        ),
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
                _base_context(
                    request,
                    page_title="Player Search Ambiguous | Deadlock Stats Tracker",
                    meta_description="That player search matched multiple Deadlock profiles. Refine the search to find the right player.",
                    meta_robots="noindex,follow",
                    message="That search matched multiple players. Use the search page to choose the right one.",
                ),
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

        canonical_player_url = _public_url(request, str(
            request.url_for(
                "player_profile_canonical",
                account_id=str(summary.player.account_id),
                player_slug=_slugify(summary.player.personaname),
            )
        ))
        if request.url.path != _url_path(canonical_player_url):
            redirect_url = canonical_player_url
            if refresh_requested:
                redirect_url = f"{redirect_url}?{urlencode({'refresh': '1'})}"
            return RedirectResponse(url=redirect_url, status_code=308)

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
        refresh_url = f"{canonical_player_url}?{urlencode({'refresh': '1'})}"

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
                detail_url=str(
                    request.url_for(
                        "match_detail_canonical",
                        account_id=str(summary.player.account_id),
                        player_slug=_slugify(summary.player.personaname),
                        match_id=str(match.match_id),
                    )
                ),
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
            _base_context(
                request,
                page_title="Player Not Found | Deadlock Stats Tracker",
                meta_description="That Deadlock player profile could not be loaded right now.",
                meta_robots="noindex,follow",
                message=str(error),
            ),
            status_code=404,
        ))

    return _html_response(TEMPLATES.TemplateResponse(
        request,
        "player.html",
        _base_context(
            request,
            page_title=f"{summary.player.personaname} Stats | Deadlock Stats Tracker",
            meta_description=(
                f"View {summary.player.personaname}'s Deadlock rank, recent matches, hero stats, and profile summary."
            ),
            canonical_url=canonical_player_url,
            og_type="profile",
            structured_data=[
                {
                    "@context": "https://schema.org",
                    "@type": "ProfilePage",
                    "name": f"{summary.player.personaname} Stats",
                    "url": canonical_player_url,
                    "mainEntity": {
                        "@type": "Person",
                        "name": summary.player.personaname,
                    },
                },
                _breadcrumb_structured_data(
                    request,
                    [
                        ("Home", str(request.url_for("home"))),
                        (
                            summary.player.personaname,
                            str(
                                request.url_for(
                                    "player_profile_canonical",
                                    account_id=str(summary.player.account_id),
                                    player_slug=_slugify(summary.player.personaname),
                                )
                            ),
                        ),
                    ],
                ),
            ],
            player=summary.player,
            overview=overview,
            top_heroes=top_heroes,
            recent_matches=recent_matches,
            player_profile_url=canonical_player_url,
            player_refresh_url=refresh_url,
            refresh_requested=refresh_requested,
            refresh_status=refresh_status,
        ),
    ))


@app.get("/players/{account_id}/{player_slug}", response_class=HTMLResponse, name="player_profile_canonical")
async def player_profile_canonical(
    request: Request,
    account_id: str,
    player_slug: str,
    refresh: int = 0,
) -> HTMLResponse:
    return await player_profile(request, account_id, refresh)


@app.get("/players/{player_input}/matches/{match_id}", response_class=HTMLResponse)
async def match_detail(request: Request, player_input: str, match_id: str) -> HTMLResponse:
    player_service = PlayerService()

    try:
        resolved = await player_service.resolve_player(player_input)
        if isinstance(resolved, list):
            return _html_response(TEMPLATES.TemplateResponse(
                request,
                "error.html",
                _base_context(
                    request,
                    page_title="Player Search Ambiguous | Deadlock Stats Tracker",
                    meta_description="That player lookup matched multiple Deadlock profiles. Refine the search to find the right player.",
                    meta_robots="noindex,follow",
                    message="That player lookup matched multiple profiles.",
                ),
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
        canonical_match_url = _public_url(request, str(
            request.url_for(
                "match_detail_canonical",
                account_id=str(resolved.account_id),
                player_slug=_slugify(resolved.personaname),
                match_id=str(metadata.match_id),
            )
        ))
        canonical_player_url = _public_url(request, str(
            request.url_for(
                "player_profile_canonical",
                account_id=str(resolved.account_id),
                player_slug=_slugify(resolved.personaname),
            )
        ))
        if request.url.path != _url_path(canonical_match_url):
            return RedirectResponse(url=canonical_match_url, status_code=308)
    except DeadlockError as error:
        return _html_response(TEMPLATES.TemplateResponse(
            request,
            "error.html",
            _base_context(
                request,
                page_title="Match Not Found | Deadlock Stats Tracker",
                meta_description="That Deadlock match detail page could not be loaded right now.",
                meta_robots="noindex,follow",
                message=str(error),
            ),
            status_code=404,
        ))

    return _html_response(TEMPLATES.TemplateResponse(
        request,
        "match_detail.html",
        _base_context(
            request,
            page_title=f"Match {metadata.match_id} | Deadlock Stats Tracker",
            meta_description=(
                f"View Deadlock match {metadata.match_id} for {resolved.personaname}, including matchup lines, players, items, and outcome."
            ),
            canonical_url=canonical_match_url,
            player=resolved,
            overview=overview,
            matchup_rows=matchup_rows,
            player_profile_url=canonical_player_url,
        ),
    ))


@app.get(
    "/players/{account_id}/{player_slug}/matches/{match_id}",
    response_class=HTMLResponse,
    name="match_detail_canonical",
)
async def match_detail_canonical(
    request: Request,
    account_id: str,
    player_slug: str,
    match_id: str,
) -> HTMLResponse:
    return await match_detail(request, account_id, match_id)


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


def _region_name(region_slug: str) -> str | None:
    for slug, name, _, _ in LEADERBOARD_REGIONS:
        if slug == region_slug:
            return name
    return None


def _region_api_value(region_slug: str) -> str:
    for slug, _, _, api_value in LEADERBOARD_REGIONS:
        if slug == region_slug:
            return api_value
    return region_slug


def _leaderboard_player_url(
    request: Request,
    account_name: str | None,
    possible_account_ids: list[int],
) -> str | None:
    if not possible_account_ids:
        return None
    player_name = (account_name or "player").strip() or "player"
    return str(
        request.url_for(
            "player_profile_canonical",
            account_id=str(possible_account_ids[0]),
            player_slug=_slugify(player_name),
        )
    )


def _leaderboard_hero_names(top_hero_ids: list[int], hero_info: dict[int, object]) -> str:
    names = [
        hero_info[hero_id].name
        for hero_id in top_hero_ids[:3]
        if hero_id in hero_info
    ]
    return ", ".join(names) if names else "Top heroes unavailable"


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


def _build_counter_views(
    stats: list,
    hero_info: dict[int, object],
    *,
    request: Request,
    view: str,
    limit: int,
) -> list[HeroPeerStatView]:
    filtered = [
        stat
        for stat in stats
        if stat.enemy_hero_id in hero_info
        and stat.matches_played > 0
        and stat.hero_id != stat.enemy_hero_id
    ]
    if view == "favorable":
        ranked = sorted(
            filtered,
            key=lambda stat: ((stat.wins / stat.matches_played), stat.matches_played),
            reverse=True,
        )
    else:
        ranked = sorted(
            filtered,
            key=lambda stat: ((stat.wins / stat.matches_played), -stat.matches_played),
        )

    rows: list[HeroPeerStatView] = []
    for stat in ranked[:limit]:
        enemy = hero_info[stat.enemy_hero_id]
        rows.append(
            HeroPeerStatView(
                hero_name=enemy.name,
                hero_url=str(request.url_for("hero_detail", hero_id=str(enemy.hero_id), hero_slug=_slugify(enemy.name))),
                hero_icon_url=enemy.icon_small,
                win_rate_percent=f"{(stat.wins / stat.matches_played):.1%}",
                matches_text=f"{stat.matches_played:,} lane matchups",
                summary_text=(
                    f"{_per_match(stat.kills, stat.matches_played):.1f} / "
                    f"{_per_match(stat.deaths, stat.matches_played):.1f} / "
                    f"{_per_match(stat.assists, stat.matches_played):.1f} avg KDA"
                ),
            )
        )
    return rows


def _build_synergy_views(
    stats: list,
    hero_id: int,
    hero_info: dict[int, object],
    *,
    request: Request,
    limit: int,
) -> list[HeroPeerStatView]:
    filtered = [
        stat
        for stat in stats
        if stat.matches_played > 0
        and stat.hero_id1 == hero_id
        and stat.hero_id2 in hero_info
        and stat.hero_id2 != hero_id
    ]
    ranked = sorted(
        filtered,
        key=lambda stat: ((stat.wins / stat.matches_played), stat.matches_played),
        reverse=True,
    )

    rows: list[HeroPeerStatView] = []
    for stat in ranked[:limit]:
        teammate = hero_info[stat.hero_id2]
        rows.append(
            HeroPeerStatView(
                hero_name=teammate.name,
                hero_url=str(request.url_for("hero_detail", hero_id=str(teammate.hero_id), hero_slug=_slugify(teammate.name))),
                hero_icon_url=teammate.icon_small,
                win_rate_percent=f"{(stat.wins / stat.matches_played):.1%}",
                matches_text=f"{stat.matches_played:,} tracked duos",
                summary_text=(
                    f"{_per_match(stat.kills2, stat.matches_played):.1f} kills and "
                    f"{_per_match(stat.assists2, stat.matches_played):.1f} assists avg"
                ),
            )
        )
    return rows


def _per_match(total: int, matches: int) -> float:
    if matches <= 0:
        return 0.0
    return total / matches


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


def _breadcrumb_structured_data(request: Request, crumbs: list[tuple[str, str]]) -> dict[str, object]:
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": index,
                "name": name,
                "item": _public_url(request, url),
            }
            for index, (name, url) in enumerate(crumbs, start=1)
        ],
    }


def _patch_author_text(author: str) -> str:
    match = re.search(r"\(([^()]+)\)\s*$", author)
    return match.group(1).strip() if match else (author.strip() or "Valve")


def _patch_pub_date_text(raw: str) -> str:
    try:
        timestamp = int(datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return raw
    return _absolute_date_text(timestamp)


def _absolute_date_text(timestamp: int | None) -> str:
    if not timestamp:
        return "Unknown"
    return datetime.fromtimestamp(int(timestamp), UTC).strftime("%B %d, %Y")


def _patch_summary_lines(content_html: str, *, limit: int = 18) -> list[str]:
    parser = _PatchHtmlSummaryParser()
    parser.feed(content_html)
    lines = parser.lines()
    if not lines:
        return ["Open the official post for the full patch notes."]
    return lines[:limit]


def _patch_lines_need_forum_fallback(lines: list[str]) -> bool:
    if not lines:
        return True
    return any(line.endswith("...") for line in lines)


class _PatchHtmlSummaryParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"br", "p", "div", "li"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"p", "div", "li"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self._parts.append(text)

    def lines(self) -> list[str]:
        text = "".join(self._parts)
        cleaned = re.sub(r"\n{2,}", "\n", text)
        raw_lines = [line.strip(" -\t") for line in cleaned.splitlines()]
        lines = [line for line in raw_lines if line and line.casefold() != "read more"]
        return lines


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "player"


def _public_origin(request: Request) -> str:
    host = request.headers.get("host", "testserver")
    if host.startswith("testserver"):
        return f"{request.url.scheme}://{host}"
    return f"https://{host}"


def _public_url(request: Request, url: str) -> str:
    split = urlsplit(url)
    query = f"?{split.query}" if split.query else ""
    fragment = f"#{split.fragment}" if split.fragment else ""
    if split.scheme and split.netloc:
        return f"{_public_origin(request)}{split.path}{query}{fragment}"
    return f"{_public_origin(request)}{url}{fragment}"


def _url_path(url: str) -> str:
    return urlsplit(url).path or "/"


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
    tier_totals: dict[int, int] = {}

    for entry in sorted(player_rank_distribution, key=lambda item: item.rank):
        tier = entry.rank // 10
        division = entry.rank % 10
        if tier <= 0 or division <= 0:
            continue
        rank = tiers_by_id.get(tier)
        if rank is None:
            continue
        tier_totals[tier] = tier_totals.get(tier, 0) + entry.players
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

    sorted_tiers = [tier for tier in sorted(grouped) if grouped[tier]]
    cumulative_share = 0.0
    top_percent_by_tier: dict[int, str] = {}
    for tier in reversed(sorted_tiers):
        cumulative_share += (tier_totals.get(tier, 0) / total_players) * 100 if total_players else 0.0
        top_percent_by_tier[tier] = f"Top {cumulative_share:.1f}%"

    return [
        RankDistributionTierView(
            tier_name=tiers_by_id[tier].name,
            top_percent_text=top_percent_by_tier.get(tier, "Top 0.0%"),
            bars=grouped[tier],
        )
        for tier in sorted_tiers
    ]


def _build_rank_distribution_summary_views(
    player_rank_distribution: list,
    rank_info: list,
) -> list[RankDistributionSummaryView]:
    if not player_rank_distribution or not rank_info:
        return []

    total_players = sum(entry.players for entry in player_rank_distribution)
    highest_rank = max((entry.rank for entry in player_rank_distribution if entry.players > 0), default=None)
    most_common_rank = max(player_rank_distribution, key=lambda entry: entry.players, default=None)
    highest_tier_name = friendly_rank_name(highest_rank) if highest_rank is not None else "Unknown"
    most_common_name = friendly_rank_name(most_common_rank.rank) if most_common_rank is not None else "Unknown"
    most_common_share = (
        f"{(most_common_rank.players / total_players) * 100:.1f}%"
        if most_common_rank is not None and total_players
        else "0.0%"
    )
    return [
        RankDistributionSummaryView(
            label="Tracked Players",
            value=f"{total_players:,}",
            detail="Estimated from the current tracked leaderboard and badge data.",
        ),
        RankDistributionSummaryView(
            label="Most Common Badge",
            value=most_common_name,
            detail=f"{most_common_share} of tracked players sit in this exact sub-rank." if total_players else "No tracked players yet.",
        ),
        RankDistributionSummaryView(
            label="Highest Badge Seen",
            value=highest_tier_name,
            detail="Highest populated tracked sub-rank in the current distribution snapshot.",
        ),
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
