from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


@dataclass(slots=True)
class Settings:
    discord_token: str
    discord_guild_id: int | None
    web_host: str
    web_port: int
    deadlock_api_key: str
    deadlock_api_base_url: str = "https://api.deadlock-api.com"
    deadlock_assets_base_url: str = "https://assets.deadlock-api.com"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()

    guild_id_raw = os.getenv("DISCORD_GUILD_ID", "").strip()
    web_port_raw = os.getenv("DEADLOCK_WEB_PORT", "8000").strip()

    return Settings(
        discord_token=os.getenv("DISCORD_TOKEN", "").strip(),
        discord_guild_id=int(guild_id_raw) if guild_id_raw.isdigit() else None,
        web_host=os.getenv("DEADLOCK_WEB_HOST", "127.0.0.1").strip() or "127.0.0.1",
        web_port=int(web_port_raw) if web_port_raw.isdigit() else 8000,
        deadlock_api_key=os.getenv("DEADLOCK_API_KEY", "").strip(),
    )
