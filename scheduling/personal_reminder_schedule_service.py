from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from entity.repositories.outbox_repo import OutboxRepo
from entity.repositories.personal_reminders_repo import PersonalRemindersRepo
from entity.repositories.users_repo import UsersRepo

log = logging.getLogger("personal_reminder_schedule")


class PersonalReminderScheduleService:
    """Plans personal reminder deliveries into outbox_jobs."""

    def __init__(self, db, settings):
        self.settings = settings
        self.repo = PersonalRemindersRepo(db)
        self.outbox = OutboxRepo(db)
        self.users = UsersRepo(db)

    def _now_utc(self) -> datetime:
        return datetime.now(timezone.utc)

    def _user_tz(self, user_id: int) -> ZoneInfo:
        tz_name = self.users.get_timezone(user_id) or self.settings.default_timezone
        try:
            return ZoneInfo(tz_name)
        except Exception:
            return ZoneInfo(self.settings.default_timezone)

    def schedule_due_jobs(self) -> int:
        created = 0
        now_utc = self._now_utc()
        reminders = self.repo.list_active()

        for r in reminders:
            user_id = int(r["user_id"])
            start_at = r.get("start_at")
            if not start_at:
                continue
            if isinstance(start_at, str):
                try:
                    start_at = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
                except Exception:
                    continue
            if start_at.tzinfo is None:
                start_at = start_at.replace(tzinfo=timezone.utc)

            # Don't plan very old reminders.
            if start_at < now_utc:
                continue

            rid = int(r["id"])
            job_key = f"personal_once:{rid}:{start_at.isoformat()}"
            if self.outbox.exists_job_for(user_id, job_key):
                continue

            tz = self._user_tz(user_id)
            local_dt = start_at.astimezone(tz)
            payload = {
                "kind": "personal_reminder",
                "reminder_id": rid,
                "text": (r.get("text") or "Напоминание"),
                "job_key": job_key,
                "for_local_date": local_dt.date().isoformat(),
                "for_local_time": local_dt.strftime("%H:%M"),
            }
            self.outbox.create_job(user_id, start_at.astimezone(timezone.utc).isoformat(), payload)
            created += 1

        if created:
            log.info("personal reminders schedule created=%s", created)
        return created
