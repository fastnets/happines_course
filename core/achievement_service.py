from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from entity.repositories.achievements_repo import AchievementsRepo
from entity.repositories.points_repo import PointsRepo
from entity.repositories.progress_repo import ProgressRepo
from entity.repositories.user_progress_repo import UserProgressRepo


class AchievementService:
    RULES = (
        {
            "code": "first_points",
            "icon": "🌟",
            "title": "Первый шаг",
            "description": "Ты получил первые баллы в курсе.",
            "check": lambda s: int(s.get("points") or 0) >= 1,
        },
        {
            "code": "day_1_done",
            "icon": "✅",
            "title": "Первый день закрыт",
            "description": "Ты завершил первый день курса.",
            "check": lambda s: int(s.get("done_days") or 0) >= 1,
        },
        {
            "code": "streak_3",
            "icon": "🔥",
            "title": "Серия 3 дня",
            "description": "Три дня подряд с завершением заданий.",
            "check": lambda s: int(s.get("streak") or 0) >= 3,
        },
        {
            "code": "streak_7",
            "icon": "🏅",
            "title": "Серия 7 дней",
            "description": "Неделя стабильной работы с курсом.",
            "check": lambda s: int(s.get("streak") or 0) >= 7,
        },
        {
            "code": "habit_3_done",
            "icon": "💪",
            "title": "Ритм привычек",
            "description": "Отмечено минимум 3 выполнения привычек.",
            "check": lambda s: int(s.get("habit_done") or 0) >= 3,
        },
        {
            "code": "questionnaire_3",
            "icon": "🧠",
            "title": "Рефлексия",
            "description": "Заполнено минимум 3 анкеты.",
            "check": lambda s: int(s.get("questionnaire_count") or 0) >= 3,
        },
        {
            "code": "points_50",
            "icon": "🏆",
            "title": "50 баллов",
            "description": "Ты набрал 50 баллов и выше.",
            "check": lambda s: int(s.get("points") or 0) >= 50,
        },
    )

    def __init__(self, db, settings):
        self.settings = settings
        self.repo = AchievementsRepo(db)
        self.points = PointsRepo(db)
        self.progress = ProgressRepo(db)
        self.user_progress = UserProgressRepo(db)

    def _resolve_tz(self, user_timezone: str | None) -> ZoneInfo:
        tz_name = (user_timezone or "").strip() or getattr(self.settings, "default_timezone", "UTC")
        try:
            return ZoneInfo(tz_name)
        except Exception:
            return ZoneInfo("UTC")

    @staticmethod
    def _to_local_date(dt: datetime, tz: ZoneInfo):
        value = dt
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(tz).date()

    def _streak(self, done_rows: list[datetime], tz: ZoneInfo) -> int:
        if not done_rows:
            return 0

        unique_dates = sorted({self._to_local_date(dt, tz) for dt in done_rows}, reverse=True)
        if not unique_dates:
            return 0

        today = datetime.now(timezone.utc).astimezone(tz).date()
        yesterday = today - timedelta(days=1)
        if unique_dates[0] not in (today, yesterday):
            return 0

        streak = 1
        prev = unique_dates[0]
        for d in unique_dates[1:]:
            if (prev - d).days == 1:
                streak += 1
                prev = d
            else:
                break
        return streak

    def snapshot(self, user_id: int, user_timezone: str | None = None) -> dict:
        tz = self._resolve_tz(user_timezone)
        points = self.points.total_points(user_id)
        done_days = self.progress.count_done(user_id)
        habits = self.user_progress.habit_done_skipped_counts(user_id)
        done_rows = self.user_progress.done_timestamps(user_id)
        questionnaire_count = self.user_progress.questionnaire_count(user_id)
        return {
            "points": int(points or 0),
            "done_days": int(done_days or 0),
            "streak": self._streak(done_rows, tz),
            "habit_done": int((habits or {}).get("done") or 0),
            "habit_skipped": int((habits or {}).get("skipped") or 0),
            "questionnaire_count": int(questionnaire_count or 0),
        }

    def evaluate(self, user_id: int, user_timezone: str | None = None) -> list[dict]:
        stats = self.snapshot(user_id, user_timezone=user_timezone)
        new_items: list[dict] = []
        for rule in self.RULES:
            try:
                ok = bool(rule["check"](stats))
            except Exception:
                ok = False
            if not ok:
                continue

            row = self.repo.grant(
                user_id=user_id,
                code=str(rule["code"]),
                title=str(rule["title"]),
                description=str(rule["description"]),
                icon=str(rule["icon"]),
                payload=stats,
            )
            if row:
                new_items.append(row)
        return new_items

    def list_for_user(self, user_id: int, limit: int = 20) -> list[dict]:
        return self.repo.list_for_user(user_id, limit=limit)

