from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    timezone: str
    database_url: str


def get_settings() -> Settings:
    return Settings(
        bot_token=os.getenv("BOT_TOKEN", "").strip(),
        timezone=os.getenv("TIMEZONE", "UTC").strip() or "UTC",
        database_url=os.getenv("DATABASE_URL", "sqlite:///data/scheduled_messages.db").strip(),
    )
