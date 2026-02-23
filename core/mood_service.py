from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from entity.repositories.mood_repo import MoodRepo
from entity.repositories.users_repo import UsersRepo


class MoodService:
    def __init__(self, db, settings):
        self.settings = settings
        self.repo = MoodRepo(db)
        self.users = UsersRepo(db)

    def _user_tz(self, user_id: int) -> ZoneInfo:
        tz_name = self.users.get_timezone(user_id) or self.settings.default_timezone
        try:
            return ZoneInfo(tz_name)
        except Exception:
            return ZoneInfo(self.settings.default_timezone)

    def _today_local_date(self, user_id: int):
        tz = self._user_tz(user_id)
        return datetime.now(timezone.utc).astimezone(tz).date()

    def set_today(self, user_id: int, score: int, comment: str = "") -> dict | None:
        val = int(score or 0)
        if val < 1 or val > 5:
            return None
        local_date = self._today_local_date(user_id)
        return self.repo.upsert_daily(user_id=user_id, local_date=local_date, score=val, comment=(comment or "").strip())

    def chart_rows(self, user_id: int, days: int = 7) -> list[dict]:
        safe_days = max(1, min(60, int(days or 7)))
        rows = self.repo.list_recent(user_id, safe_days)
        by_date = {r["local_date"]: int(r.get("score") or 0) for r in rows}

        today = self._today_local_date(user_id)
        out = []
        for i in range(safe_days):
            d = today - timedelta(days=i)
            out.append({"local_date": d, "score": int(by_date.get(d) or 0)})
        return out

    def chart_text(self, user_id: int, days: int = 7) -> str:
        safe_days = max(1, min(60, int(days or 7)))
        rows = self.chart_rows(user_id, safe_days)
        if not rows:
            return "😊 Настроение\nПока нет записей."

        lines = [f"😊 Настроение за {safe_days} дн.", ""]
        scores = []
        for row in rows:
            d = row["local_date"]
            score = int(row["score"] or 0)
            if score > 0:
                scores.append(score)
            bar = "█" * score if score > 0 else "-"
            score_label = str(score) if score > 0 else "нет"
            lines.append(f"• {d.strftime('%d.%m')}: {bar} ({score_label})")

        if scores:
            avg = sum(scores) / len(scores)
            lines.append("")
            lines.append(f"Среднее по заполненным дням: {avg:.2f}")
        return "\n".join(lines)

