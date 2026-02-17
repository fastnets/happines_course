from __future__ import annotations

from datetime import datetime, timezone

from entity.repositories.habits_repo import HabitsRepo
from entity.repositories.habit_occurrences_repo import HabitOccurrencesRepo
from entity.repositories.points_repo import PointsRepo
from entity.repositories.outbox_repo import OutboxRepo


class HabitService:
    """CRUD + completion actions for personal habits."""

    def __init__(self, db, settings):
        self.settings = settings
        self.habits = HabitsRepo(db)
        self.occ = HabitOccurrencesRepo(db)
        self.points = PointsRepo(db)
        self.outbox = OutboxRepo(db)

    # ----------------------------
    # CRUD
    # ----------------------------
    def create(self, user_id: int, title: str, remind_time: str, frequency: str) -> int:
        title = (title or "").strip()[:200] or "Привычка"
        remind_time = (remind_time or "").strip()
        frequency = (frequency or "daily").strip()
        if frequency not in ("daily", "weekdays", "weekends"):
            frequency = "daily"
        return self.habits.create(user_id, title, remind_time, frequency)

    def list_for_user(self, user_id: int):
        return self.habits.list_for_user(user_id)

    def toggle(self, user_id: int, habit_id: int) -> bool:
        h = self.habits.get(habit_id)
        if not h or int(h["user_id"]) != int(user_id):
            return False
        new_active = not bool(h.get("is_active"))
        self.habits.set_active(habit_id, user_id, new_active)
        return True

    def delete(self, user_id: int, habit_id: int) -> bool:
        h = self.habits.get(habit_id)
        if not h or int(h.get("user_id")) != int(user_id):
            return False
        now_utc = datetime.now(timezone.utc).isoformat()
        try:
            self.occ.cancel_future_for_habit(habit_id, now_utc)
        except Exception:
            pass
        try:
            self.outbox.cancel_future_habit_jobs(habit_id, now_utc)
        except Exception:
            pass
        return self.habits.delete(habit_id, user_id) > 0

    def update_title(self, user_id: int, habit_id: int, title: str) -> bool:
        h = self.habits.get(habit_id)
        if not h or int(h.get("user_id")) != int(user_id):
            return False
        title = (title or "").strip()[:200]
        if not title:
            return False
        return self.habits.update_title(habit_id, user_id, title) > 0

    def update_time(self, user_id: int, habit_id: int, remind_time: str) -> bool:
        h = self.habits.get(habit_id)
        if not h or int(h.get("user_id")) != int(user_id):
            return False
        remind_time = (remind_time or "").strip()
        if not remind_time:
            return False
        now_utc = datetime.now(timezone.utc).isoformat()
        # Cancel future occurrences/jobs so the schedule can be rebuilt.
        self.occ.cancel_future_for_habit(habit_id, now_utc)
        self.outbox.cancel_future_habit_jobs(habit_id, now_utc)
        return self.habits.update_time(habit_id, user_id, remind_time) > 0

    def update_frequency(self, user_id: int, habit_id: int, frequency: str) -> bool:
        h = self.habits.get(habit_id)
        if not h or int(h.get("user_id")) != int(user_id):
            return False
        frequency = (frequency or "").strip()
        if frequency not in ("daily", "weekdays", "weekends"):
            return False
        now_utc = datetime.now(timezone.utc).isoformat()
        self.occ.cancel_future_for_habit(habit_id, now_utc)
        self.outbox.cancel_future_habit_jobs(habit_id, now_utc)
        return self.habits.update_frequency(habit_id, user_id, frequency) > 0

    # ----------------------------
    # Actions
    # ----------------------------
    def bonus_points(self) -> int:
        try:
            return int(getattr(self.settings, "habit_bonus_points", 3) or 3)
        except Exception:
            return 3

    def mark_done(self, user_id: int, occurrence_id: int) -> bool:
        ok = self.occ.mark_done(occurrence_id, user_id)
        if not ok:
            return False
        # Idempotent points: one ledger row per occurrence.
        key = f"occ:{occurrence_id}"
        if not self.points.has_entry(user_id, "habit_done", key):
            self.points.add_points(user_id, "habit_done", key, self.bonus_points())
        return True

    def mark_skipped(self, user_id: int, occurrence_id: int) -> bool:
        return self.occ.mark_skipped(occurrence_id, user_id)
