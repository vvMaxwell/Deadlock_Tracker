from __future__ import annotations

from io import BytesIO
from pathlib import Path
from time import time

import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageOps

from deadlock_tracker.models import DeadlockHeroInfo, DeadlockHeroStat, DeadlockPlayer


CARD_WIDTH = 1100
CARD_HEIGHT = 830
BACKGROUND = "#0f0d0a"
PANEL = "#171411"
PANEL_ALT = "#211b16"
ACCENT = "#d3b58a"
TEXT = "#f5ecde"
MUTED = "#bda891"
PILL = "#110f0c"
OUTLINE = "#4c3f34"
SHADOW = "#080706"
HERO_HEADER = "#2a231d"
HERO_PANEL = "#1c1814"


def _load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def _fit_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text

    trimmed = text
    while trimmed and draw.textlength(f"{trimmed}...", font=font) > max_width:
        trimmed = trimmed[:-1]
    return f"{trimmed}..." if trimmed else text


def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    return mask


def _vertical_gradient(size: tuple[int, int], top: str, bottom: str) -> Image.Image:
    width, height = size
    top_rgb = tuple(int(top[i : i + 2], 16) for i in (1, 3, 5))
    bottom_rgb = tuple(int(bottom[i : i + 2], 16) for i in (1, 3, 5))
    image = Image.new("RGBA", size)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(1, height - 1)
        color = tuple(
            int(top_rgb[index] + (bottom_rgb[index] - top_rgb[index]) * ratio)
            for index in range(3)
        ) + (255,)
        draw.line((0, y, width, y), fill=color)
    return image


def _draw_panel(
    base: Image.Image,
    box: tuple[int, int, int, int],
    *,
    radius: int,
    fill: str,
    outline: str | None = None,
    shadow_offset: int = 8,
) -> None:
    draw = ImageDraw.Draw(base)
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(
        (x0 + shadow_offset, y0 + shadow_offset, x1 + shadow_offset, y1 + shadow_offset),
        radius=radius,
        fill=SHADOW,
    )
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=1 if outline else 0)


async def _fetch_image(url: str | None) -> Image.Image | None:
    if not url:
        return None

    timeout = aiohttp.ClientTimeout(total=10)
    headers = {"User-Agent": "DeadlockTracker/1.0"}
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url) as response:
                if response.status >= 400:
                    return None
                data = await response.read()
    except Exception:
        return None

    try:
        return Image.open(BytesIO(data)).convert("RGBA")
    except Exception:
        return None


def _paste_cover(base: Image.Image, image: Image.Image, box: tuple[int, int, int, int], radius: int) -> None:
    x0, y0, x1, y1 = box
    width = x1 - x0
    height = y1 - y0
    fitted = ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS)
    mask = _rounded_mask((width, height), radius)
    base.paste(fitted, (x0, y0), mask)


def _draw_pill(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    width: int,
    label: str,
    value: str,
    label_font: ImageFont.ImageFont,
    value_font: ImageFont.ImageFont,
) -> None:
    height = 46
    draw.rounded_rectangle(
        (x, y, x + width, y + height),
        radius=18,
        fill=PILL,
        outline="#2f394a",
        width=1,
    )
    label_width = draw.textlength(f"{label}:", font=label_font)
    draw.text((x + 16, y + 11), f"{label}:", font=label_font, fill=MUTED)
    draw.text((x + 24 + label_width, y + 9), value, font=value_font, fill=TEXT)


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


async def render_deadlock_profile_card(
    *,
    player: DeadlockPlayer,
    rank_name: str,
    internal_rating: str,
    top_heroes: list[DeadlockHeroStat],
    hero_info: dict[int, DeadlockHeroInfo],
    accent_art_path: Path | None = None,
    cache_updated_ts: int | None,
) -> BytesIO:
    card = _vertical_gradient((CARD_WIDTH, CARD_HEIGHT), "#080706", BACKGROUND)
    draw = ImageDraw.Draw(card)

    title_font = _load_font(40, bold=True)
    heading_font = _load_font(22, bold=True)
    body_font = _load_font(22)
    small_font = _load_font(18)
    value_font = _load_font(20, bold=True)

    _draw_panel(
        card,
        (24, 24, CARD_WIDTH - 24, CARD_HEIGHT - 24),
        radius=30,
        fill=PANEL,
        outline=OUTLINE,
        shadow_offset=10,
    )

    draw.text((56, 54), f"Deadlock Profile: {player.personaname}", font=title_font, fill=TEXT)
    draw.text((56, 102), "Competitive tracking overview", font=heading_font, fill=ACCENT)

    avatar = await _fetch_image(player.avatarfull)
    if avatar is not None:
        _paste_cover(card, avatar, (CARD_WIDTH - 260, 52, CARD_WIDTH - 100, 212), radius=24)

    detail_labels = [
        ("Account ID", str(player.account_id)),
        ("Country", player.countrycode or "Unknown"),
        ("Cache Updated", _relative_time_text(cache_updated_ts)),
    ]
    x_positions = [56, 292, 528]
    for (label, value), x_pos in zip(detail_labels, x_positions, strict=False):
        draw.text((x_pos, 152), label, font=heading_font, fill=TEXT)
        draw.text((x_pos, 184), value, font=body_font, fill=TEXT)

    draw.text((56, 252), "Rank Snapshot", font=heading_font, fill=TEXT)
    draw.text((56, 284), rank_name, font=body_font, fill=TEXT)
    draw.text((56, 317), f"MMR Score: {internal_rating}", font=body_font, fill=TEXT)

    draw.rounded_rectangle((56, 360, 324, 398), radius=19, fill=PANEL_ALT, outline="#5a4b3f", width=1)
    draw.text((74, 368), "Top Heroes by Matches", font=small_font, fill=TEXT)

    panel_top = 420
    panel_width = 308
    panel_height = 312
    gap = 20

    accent_art = None
    if accent_art_path and accent_art_path.exists():
        try:
            accent_art = Image.open(accent_art_path).convert("RGBA")
        except Exception:
            accent_art = None

    for index, stat in enumerate(top_heroes[:3]):
        x_pos = 56 + index * (panel_width + gap)
        _draw_panel(
            card,
            (x_pos, panel_top, x_pos + panel_width, panel_top + panel_height),
            radius=26,
            fill=HERO_PANEL,
            outline="#514439",
            shadow_offset=6,
        )
        draw.rounded_rectangle(
            (x_pos + 14, panel_top + 14, x_pos + panel_width - 14, panel_top + 78),
            radius=20,
            fill=HERO_HEADER,
        )
        hero = hero_info.get(stat.hero_id)
        hero_name = hero.name if hero else f"Hero {stat.hero_id}"
        draw.text(
            (x_pos + 28, panel_top + 30),
            _fit_text(draw, hero_name, heading_font, panel_width - 110),
            font=heading_font,
            fill=TEXT,
        )

        hero_icon = await _fetch_image(hero.icon_small if hero else None)
        icon_box = (x_pos + panel_width - 90, panel_top + 16, x_pos + panel_width - 26, panel_top + 80)
        if hero_icon is not None:
            _paste_cover(card, hero_icon, icon_box, radius=18)
        else:
            draw.rounded_rectangle(icon_box, radius=18, fill="#3a3028")
            initials = hero_name[:2].upper()
            initials_width = draw.textlength(initials, font=small_font)
            draw.text(
                (icon_box[0] + ((icon_box[2] - icon_box[0] - initials_width) / 2), icon_box[1] + 22),
                initials,
                font=small_font,
                fill=TEXT,
            )

        win_rate = f"{(stat.wins / stat.matches_played):.1%}" if stat.matches_played else "0.0%"
        kda_value = f"{int(stat.kills or 0)}/{int(stat.deaths or 0)}/{int(stat.assists or 0)}"
        _draw_pill(draw, x_pos + 24, panel_top + 108, panel_width - 48, "Matches", str(stat.matches_played), small_font, value_font)
        _draw_pill(draw, x_pos + 24, panel_top + 178, panel_width - 48, "Win Rate", win_rate, small_font, value_font)
        _draw_pill(draw, x_pos + 24, panel_top + 248, panel_width - 48, "KDA", kda_value, small_font, value_font)

    if accent_art is not None:
        accent_thumb = ImageOps.contain(accent_art, (70, 70), method=Image.Resampling.LANCZOS)
        card.paste(accent_thumb, (56, CARD_HEIGHT - 120), accent_thumb)

    output = BytesIO()
    card.save(output, format="PNG")
    output.seek(0)
    return output
