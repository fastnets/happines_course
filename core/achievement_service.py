from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from entity.repositories.achievements_repo import AchievementsRepo
from entity.repositories.points_repo import PointsRepo
from entity.repositories.progress_repo import ProgressRepo
from entity.repositories.user_progress_repo import UserProgressRepo


class AchievementService:
    METRICS = {
        "points": "Баллы",
        "done_days": "Завершенные дни",
        "streak": "Серия дней",
        "habit_done": "Выполнено привычек",
        "habit_skipped": "Пропущено привычек",
        "questionnaire_count": "Заполнено анкет",
    }
    OPERATORS = {
        ">=": lambda left, right: left >= right,
        ">": lambda left, right: left > right,
        "=": lambda left, right: left == right,
        "<=": lambda left, right: left <= right,
        "<": lambda left, right: left < right,
    }

    def __init__(self, db, settings):
        self.settings = settings
        self.repo = AchievementsRepo(db)
        self.points = PointsRepo(db)
        self.progress = ProgressRepo(db)
        self.user_progress = UserProgressRepo(db)

    @staticmethod
    def _safe_int(value, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)

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

    def _rule_matches(self, stats: dict, rule: dict) -> bool:
        metric_key = str(rule.get("metric_key") or "").strip()
        operator = str(rule.get("operator") or "").strip()
        threshold = self._safe_int(rule.get("threshold"), 0)
        if metric_key not in self.METRICS:
            return False
        cmp_fn = self.OPERATORS.get(operator)
        if not cmp_fn:
            return False
        value = self._safe_int(stats.get(metric_key), 0)
        return bool(cmp_fn(value, threshold))

    def evaluate(self, user_id: int, user_timezone: str | None = None) -> list[dict]:
        stats = self.snapshot(user_id, user_timezone=user_timezone)
        rules = self.repo.list_rules(active_only=True, limit=500)
        new_items: list[dict] = []
        for rule in rules:
            if not self._rule_matches(stats, rule):
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

    @classmethod
    def metric_keys(cls) -> list[str]:
        return list(cls.METRICS.keys())

    @classmethod
    def operators(cls) -> list[str]:
        return list(cls.OPERATORS.keys())

    def list_rules(self, limit: int = 200, active_only: bool | None = None) -> list[dict]:
        return self.repo.list_rules(active_only=active_only, limit=limit)

    def get_rule(self, rule_id: int) -> dict | None:
        return self.repo.get_rule(rule_id)

    @staticmethod
    def _parse_bool(value) -> bool:
        if isinstance(value, bool):
            return value
        s = str(value or "").strip().lower()
        return s in ("1", "true", "yes", "y", "да")

    def _validate_rule(
        self,
        code: str,
        title: str,
        description: str,
        icon: str,
        metric_key: str,
        operator: str,
        threshold,
        is_active,
        sort_order,
    ) -> dict:
        norm_code = str(code or "").strip().lower()
        if not re.fullmatch(r"[a-z0-9_]{3,64}", norm_code):
            raise ValueError("code должен быть в формате [a-z0-9_], длина 3..64")

        norm_title = str(title or "").strip()
        if not norm_title or len(norm_title) > 120:
            raise ValueError("title обязателен и должен быть не длиннее 120 символов")

        norm_description = str(description or "").strip()
        if not norm_description or len(norm_description) > 500:
            raise ValueError("description обязателен и должен быть не длиннее 500 символов")

        norm_icon = str(icon or "🏅").strip() or "🏅"

        norm_metric = str(metric_key or "").strip()
        if norm_metric not in self.METRICS:
            raise ValueError(f"metric_key должен быть одним из: {', '.join(self.metric_keys())}")

        norm_operator = str(operator or "").strip()
        if norm_operator not in self.OPERATORS:
            raise ValueError(f"operator должен быть одним из: {', '.join(self.operators())}")

        norm_threshold = self._safe_int(threshold, 0)
        norm_sort_order = self._safe_int(sort_order, 100)
        norm_active = self._parse_bool(is_active)
        return {
            "code": norm_code,
            "title": norm_title,
            "description": norm_description,
            "icon": norm_icon,
            "metric_key": norm_metric,
            "operator": norm_operator,
            "threshold": norm_threshold,
            "is_active": norm_active,
            "sort_order": norm_sort_order,
        }

    def create_rule(
        self,
        code: str,
        title: str,
        description: str,
        icon: str,
        metric_key: str,
        operator: str,
        threshold,
        is_active=True,
        sort_order=100,
    ) -> dict | None:
        payload = self._validate_rule(
            code=code,
            title=title,
            description=description,
            icon=icon,
            metric_key=metric_key,
            operator=operator,
            threshold=threshold,
            is_active=is_active,
            sort_order=sort_order,
        )
        return self.repo.create_rule(**payload)

    def update_rule(
        self,
        rule_id: int,
        code: str,
        title: str,
        description: str,
        icon: str,
        metric_key: str,
        operator: str,
        threshold,
        is_active=True,
        sort_order=100,
    ) -> dict | None:
        payload = self._validate_rule(
            code=code,
            title=title,
            description=description,
            icon=icon,
            metric_key=metric_key,
            operator=operator,
            threshold=threshold,
            is_active=is_active,
            sort_order=sort_order,
        )
        return self.repo.update_rule(rule_id=int(rule_id), **payload)

    def delete_rule(self, rule_id: int) -> bool:
        return self.repo.delete_rule(rule_id=int(rule_id))
