import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

def _csv_ints(v: str) -> list[int]:
    if not v:
        return []
    return [int(x.strip()) for x in v.split(",") if x.strip()]


def _opt_int(v: str | None) -> int | None:
    s = (v or "").strip()
    if not s:
        return None
    return int(s)

@dataclass(frozen=True)
class Settings:
    bot_token: str
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    owner_tg_id: int | None
    admin_tg_ids: list[int]
    admin_events_chat_id: int | None
    default_timezone: str
    delivery_grace_minutes: int
    remind_after_hours: int
    quiet_hours_start: str
    quiet_hours_end: str
    reminder_fallback_time: str
    habit_bonus_points: int
    habit_plan_days: int

def get_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("BOT_TOKEN is required")
    return Settings(
        bot_token=token,
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=int(os.getenv("DB_PORT", "5432")),
        db_name=os.getenv("DB_NAME", "happiness"),
        db_user=os.getenv("DB_USER", "postgres"),
        db_password=os.getenv("DB_PASSWORD", "postgres"),
        owner_tg_id=_opt_int(os.getenv("OWNER_TG_ID", "")),
        admin_tg_ids=_csv_ints(os.getenv("ADMIN_TG_IDS", "")),
        admin_events_chat_id=_opt_int(os.getenv("ADMIN_EVENTS_CHAT_ID", "")),
        default_timezone=os.getenv("DEFAULT_TIMEZONE", "Europe/Moscow"),
        delivery_grace_minutes=int(os.getenv("DELIVERY_GRACE_MINUTES", "15")),
        remind_after_hours=int(os.getenv("REMIND_AFTER_HOURS", "12")),
        quiet_hours_start=os.getenv("QUIET_HOURS_START", "22:00"),
        quiet_hours_end=os.getenv("QUIET_HOURS_END", "09:00"),
        reminder_fallback_time=os.getenv("FALLBACK_SEND_TIME", "09:30"),
        habit_bonus_points=int(os.getenv("HABIT_BONUS_POINTS", "3")),
        habit_plan_days=int(os.getenv("HABIT_PLAN_DAYS", "2")),
    )
