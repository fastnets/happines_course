from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from entity.repositories.achievements_repo import AchievementsRepo
from entity.repositories.enrollment_repo import EnrollmentRepo
from entity.repositories.points_repo import PointsRepo
from entity.repositories.progress_repo import ProgressRepo
from entity.repositories.user_progress_repo import UserProgressRepo
from entity.repositories.users_repo import UsersRepo


class AnalyticsService:
    def __init__(self, db, settings):
        self.settings = settings
        self.users = UsersRepo(db)
        self.points = PointsRepo(db)
        self.enroll = EnrollmentRepo(db)
        self.progress = ProgressRepo(db)
        self.user_progress = UserProgressRepo(db)
        self.achievements = AchievementsRepo(db)

    @staticmethod
    def _safe_int(value) -> int:
        try:
            return int(value or 0)
        except Exception:
            return 0

    @staticmethod
    def _pct(done: int, total: int) -> float:
        if total <= 0:
            return 0.0
        return round((100.0 * float(done) / float(total)), 1)

    def _resolve_tz(self, user: dict | None) -> ZoneInfo:
        tz_name = (user or {}).get("timezone") or getattr(self.settings, "default_timezone", "UTC")
        try:
            return ZoneInfo(tz_name)
        except Exception:
            return ZoneInfo("UTC")

    @staticmethod
    def _to_local_date(dt: datetime, tz: ZoneInfo) -> date:
        value = dt
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(tz).date()

    def _streak(self, done_rows: list[datetime], tz: ZoneInfo) -> int:
        if not done_rows:
            return 0

        dates = sorted({self._to_local_date(dt, tz) for dt in done_rows}, reverse=True)
        if not dates:
            return 0

        today = datetime.now(timezone.utc).astimezone(tz).date()
        yesterday = today - timedelta(days=1)
        if dates[0] not in (today, yesterday):
            return 0

        streak = 1
        prev = dates[0]
        for d in dates[1:]:
            if (prev - d).days == 1:
                streak += 1
                prev = d
            else:
                break
        return streak

    @staticmethod
    def _week_start(local_day: date) -> date:
        return local_day - timedelta(days=local_day.weekday())

    def _weekly(self, user_id: int, tz: ZoneInfo, weeks: int = 4) -> list[dict]:
        n = max(1, int(weeks or 4))
        now_local = datetime.now(timezone.utc).astimezone(tz)
        this_week_start = self._week_start(now_local.date())
        week_starts = [this_week_start - timedelta(days=7 * i) for i in range(n - 1, -1, -1)]

        earliest_local = datetime.combine(week_starts[0], time.min, tzinfo=tz)
        since_utc = earliest_local.astimezone(timezone.utc)

        points_rows = self.user_progress.points_events_since(user_id, since_utc)
        done_rows = self.user_progress.done_events_since(user_id, since_utc)
        q_rows = self.user_progress.questionnaire_events_since(user_id, since_utc)

        buckets: dict[date, dict] = {
            ws: {"points": 0, "done_days": set(), "scores": []} for ws in week_starts
        }

        for row in points_rows:
            dt = row.get("created_at")
            if not dt:
                continue
            d = self._to_local_date(dt, tz)
            ws = self._week_start(d)
            if ws in buckets:
                buckets[ws]["points"] += self._safe_int(row.get("points"))

        for row in done_rows:
            dt = row.get("done_at")
            if not dt:
                continue
            d = self._to_local_date(dt, tz)
            ws = self._week_start(d)
            if ws in buckets:
                buckets[ws]["done_days"].add(d)

        for row in q_rows:
            dt = row.get("created_at")
            if not dt:
                continue
            d = self._to_local_date(dt, tz)
            ws = self._week_start(d)
            if ws in buckets:
                try:
                    buckets[ws]["scores"].append(float(row.get("score") or 0.0))
                except Exception:
                    pass

        out: list[dict] = []
        for ws in week_starts:
            b = buckets[ws]
            scores = b["scores"]
            avg_score = round(sum(scores) / len(scores), 2) if scores else None
            out.append(
                {
                    "label": f"{ws.strftime('%d.%m')}–{(ws + timedelta(days=6)).strftime('%d.%m')}",
                    "points": int(b["points"]),
                    "done_days": len(b["done_days"]),
                    "avg_score": avg_score,
                }
            )
        return out

    def profile(self, user_id: int):
        user = self.users.get_user(user_id) or {}
        enrollment = self.enroll.get(user_id)
        tz = self._resolve_tz(user)

        points = self.points.total_points(user_id)
        done_days = self.progress.count_done(user_id)
        done_rows = self.user_progress.done_timestamps(user_id)
        streak = self._streak(done_rows, tz)

        deliveries = self.user_progress.delivery_counts(user_id)
        lessons_sent = self._safe_int(deliveries.get("lessons_sent"))
        quests_sent = self._safe_int(deliveries.get("quests_sent"))

        lessons_viewed = self.user_progress.lesson_viewed_count(user_id)
        quests_answered = self.user_progress.quest_answered_count(user_id)

        habits = self.user_progress.habit_done_skipped_counts(user_id)
        habit_done = self._safe_int(habits.get("done"))
        habit_skipped = self._safe_int(habits.get("skipped"))

        questionnaire_count = self.user_progress.questionnaire_count(user_id)
        achievements = self.achievements.list_for_user(user_id, limit=6)
        achievements_total = self.achievements.count_for_user(user_id)

        return {
            "display_name": user.get("display_name") or "Без имени",
            "enrolled": bool(enrollment),
            "delivery_time": (enrollment.get("delivery_time") if enrollment else None),
            "points": self._safe_int(points),
            "done_days": self._safe_int(done_days),
            "streak": streak,
            "lessons_sent": lessons_sent,
            "lessons_viewed": lessons_viewed,
            "lessons_pct": self._pct(lessons_viewed, lessons_sent),
            "quests_sent": quests_sent,
            "quests_answered": quests_answered,
            "quests_pct": self._pct(quests_answered, quests_sent),
            "habit_done": habit_done,
            "habit_skipped": habit_skipped,
            "questionnaire_count": self._safe_int(questionnaire_count),
            "weekly": self._weekly(user_id, tz, weeks=4),
            "achievements_total": achievements_total,
            "achievements": achievements,
        }

    def progress_report(self, user_id: int) -> str:
        prof = self.profile(user_id)
        lines = [
            "📊 Мой прогресс",
            f"Баллы: {prof['points']}",
            f"Серия (streak): {prof['streak']} дн.",
            f"Завершено дней курса: {prof['done_days']}",
            (
                "Лекции: "
                f"{prof['lessons_viewed']}/{prof['lessons_sent']} "
                f"({prof['lessons_pct']:.1f}%)"
            ),
            (
                "Задания: "
                f"{prof['quests_answered']}/{prof['quests_sent']} "
                f"({prof['quests_pct']:.1f}%)"
            ),
            f"Привычки: done={prof['habit_done']}, skip={prof['habit_skipped']}",
            f"Анкеты: {prof['questionnaire_count']}",
            f"Ачивки: {prof['achievements_total']}",
        ]

        achievements = prof.get("achievements") or []
        if achievements:
            lines.append("")
            lines.append("Последние ачивки:")
            for row in achievements[:3]:
                icon = (row.get("icon") or "🏅").strip() or "🏅"
                title = (row.get("title") or "Ачивка").strip()
                lines.append(f"• {icon} {title}")

        weekly = prof.get("weekly") or []
        if weekly:
            lines.append("")
            lines.append("Динамика по неделям:")
            for row in weekly:
                avg = "-" if row.get("avg_score") is None else f"{float(row['avg_score']):.2f}"
                lines.append(
                    f"• {row['label']}: баллы={row['points']}, done={row['done_days']}, анкеты avg={avg}"
                )

        return "\n".join(lines)
