from __future__ import annotations

import logging
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo

from entity.repositories.habits_repo import HabitsRepo
from entity.repositories.habit_occurrences_repo import HabitOccurrencesRepo
from entity.repositories.outbox_repo import OutboxRepo
from entity.repositories.users_repo import UsersRepo

log = logging.getLogger("habit_schedule")


class HabitScheduleService:
    """Plans habit occurrences and puts reminder jobs into outbox_jobs.

    Strategy:
    - Periodically (e.g., hourly) create occurrences + outbox jobs for the next N days.
    - Idempotency: habit_occurrences has UNIQUE(habit_id, scheduled_at) + outbox has job_key.
    - All calculations are performed in user's timezone, stored in UTC.
    """

    def __init__(self, db, settings):
        self.settings = settings
        self.habits = HabitsRepo(db)
        self.occ = HabitOccurrencesRepo(db)
        self.outbox = OutboxRepo(db)
        self.users = UsersRepo(db)

    @staticmethod
    def _parse_hhmm(v: str, default: str = "09:00") -> time:
        s = (v or "").strip() or default
        try:
            hh, mm = [int(x) for x in s.split(":")]
            hh = max(0, min(23, hh))
            mm = max(0, min(59, mm))
            return time(hh, mm)
        except Exception:
            hh, mm = [int(x) for x in default.split(":")]
            return time(hh, mm)

    def _user_tz(self, user_id: int) -> ZoneInfo:
        tz_name = self.users.get_timezone(user_id) or self.settings.default_timezone
        try:
            return ZoneInfo(tz_name)
        except Exception:
            return ZoneInfo(self.settings.default_timezone)

    @staticmethod
    def _matches_frequency(d: date, frequency: str) -> bool:
        wd = d.isoweekday()  # 1..7
        if frequency == "weekdays":
            return 1 <= wd <= 5
        if frequency == "weekends":
            return wd in (6, 7)
        return True

    def plan_horizon_days(self) -> int:
        try:
            return int(getattr(self.settings, "habit_plan_days", 2) or 2)
        except Exception:
            return 2

    def schedule_due_jobs(self) -> int:
        """Plan occurrences & outbox jobs for all active habits."""

        created = 0
        now_utc = datetime.now(timezone.utc)
        habits = self.habits.list_active()

        # Group by user to avoid computing tz repeatedly.
        by_user: dict[int, list[dict]] = {}
        for h in habits:
            by_user.setdefault(int(h["user_id"]), []).append(h)

        for user_id, hs in by_user.items():
            tz = self._user_tz(user_id)
            today_local = now_utc.astimezone(tz).date()
            horizon = self.plan_horizon_days()

            for i in range(horizon + 1):
                d_local = today_local + timedelta(days=i)
                for h in hs:
                    if not self._matches_frequency(d_local, (h.get("frequency") or "daily")):
                        continue

                    t_local = self._parse_hhmm(h.get("remind_time") or "09:00", "09:00")
                    local_dt = datetime.combine(d_local, t_local, tzinfo=tz)
                    run_at_utc = local_dt.astimezone(timezone.utc)

                    # Don't plan jobs too far in the past.
                    if run_at_utc < now_utc - timedelta(minutes=5):
                        continue

                    occurrence_id = self.occ.ensure_planned(
                        int(h["id"]), user_id, run_at_utc.isoformat()
                    )
                    if not occurrence_id:
                        continue

                    job_key = f"habit:{h['id']}:{occurrence_id}"
                    if self.outbox.exists_job_for(user_id, job_key):
                        continue

                    payload = {
                        "kind": "habit_reminder",
                        "habit_id": int(h["id"]),
                        "occurrence_id": int(occurrence_id),
                        "title": h.get("title") or "Привычка",
                        "job_key": job_key,
                        "for_local_date": d_local.isoformat(),
                        "for_local_time": t_local.strftime("%H:%M"),
                    }

                    self.outbox.create_job(user_id, run_at_utc.isoformat(), payload)
                    created += 1

        if created:
            log.info("habit schedule created=%s", created)
        return created
