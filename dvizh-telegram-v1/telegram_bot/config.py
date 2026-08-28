from __future__ import annotations

import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Settings:
    bot_token: str
    pair_code: str
    database_path: str = "/var/lib/dvizh/telegram.db"
    timezone: str = "Europe/Moscow"
    quiet_start: str = "23:00"
    quiet_end: str = "09:00"
    followup_minutes: int = 20
    checkin_fresh_minutes: int = 240
    scheduler_tick_seconds: int = 30
    allow_multi_user: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        pair_code = os.environ.get("DVIZH_TELEGRAM_PAIR_CODE", "").strip()
        if not token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
        if not pair_code:
            raise RuntimeError("DVIZH_TELEGRAM_PAIR_CODE is required")

        settings = cls(
            bot_token=token,
            pair_code=pair_code,
            database_path=os.environ.get("DVIZH_TELEGRAM_DB", "/var/lib/dvizh/telegram.db"),
            timezone=os.environ.get("DVIZH_TIMEZONE", "Europe/Moscow"),
            quiet_start=os.environ.get("DVIZH_QUIET_START", "23:00"),
            quiet_end=os.environ.get("DVIZH_QUIET_END", "09:00"),
            followup_minutes=int(os.environ.get("DVIZH_FOLLOWUP_MINUTES", "20")),
            checkin_fresh_minutes=int(os.environ.get("DVIZH_CHECKIN_FRESH_MINUTES", "240")),
            scheduler_tick_seconds=int(os.environ.get("DVIZH_SCHEDULER_TICK_SECONDS", "30")),
            allow_multi_user=os.environ.get("DVIZH_ALLOW_MULTI_USER", "false").lower() in {"1", "true", "yes"},
        )
        ZoneInfo(settings.timezone)
        return settings
