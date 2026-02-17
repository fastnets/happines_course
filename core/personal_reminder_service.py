from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from entity.repositories.outbox_repo import OutboxRepo
from entity.repositories.personal_reminders_repo import PersonalRemindersRepo
from entity.repositories.users_repo import UsersRepo


class PersonalReminderService:
    """CRUD for user-defined personal reminders."""

    def __init__(self, db, settings):
        self.settings = settings
        self.repo = PersonalRemindersRepo(db)
        self.users = UsersRepo(db)
        self.outbox = OutboxRepo(db)

    def _user_tz(self, user_id: int) -> ZoneInfo:
        tz_name = self.users.get_timezone(user_id) or self.settings.default_timezone
        try:
            return ZoneInfo(tz_name)
        except Exception:
            return ZoneInfo(self.settings.default_timezone)

    @staticmethod
    def _parse_local_datetime(raw: str) -> datetime:
        return datetime.strptime((raw or "").strip(), "%d.%m.%Y %H:%M")

    def _cancel_future_jobs(self, reminder_id: int):
        now_utc = datetime.now(timezone.utc).isoformat()
        self.outbox.cancel_future_personal_reminder_jobs(reminder_id, now_utc)

    def create(
        self,
        user_id: int,
        text: str,
        start_local: str,
    ) -> int | None:
        title = (text or "").strip()[:500]
        if not title:
            return None
        try:
            local_dt = self._parse_local_datetime(start_local).replace(tzinfo=self._user_tz(user_id))
        except Exception:
            return None

        return self.repo.create(
            user_id=user_id,
            text=title,
            start_at_iso=local_dt.astimezone(timezone.utc).isoformat(),
            remind_time=local_dt.strftime("%H:%M"),
        )

    def list_for_user(self, user_id: int):
        return self.repo.list_for_user(user_id)

    def get_owned(self, user_id: int, reminder_id: int):
        r = self.repo.get(reminder_id)
        if not r or int(r.get("user_id") or 0) != int(user_id):
            return None
        return r

    def update_text(self, user_id: int, reminder_id: int, text: str) -> bool:
        if not self.get_owned(user_id, reminder_id):
            return False
        val = (text or "").strip()[:500]
        if not val:
            return False
        return self.repo.update_text(reminder_id, user_id, val) > 0

    def update_datetime(self, user_id: int, reminder_id: int, start_local: str) -> bool:
        if not self.get_owned(user_id, reminder_id):
            return False
        try:
            local_dt = self._parse_local_datetime(start_local).replace(tzinfo=self._user_tz(user_id))
        except Exception:
            return False
        ok = self.repo.update_datetime(
            reminder_id=reminder_id,
            user_id=user_id,
            start_at_iso=local_dt.astimezone(timezone.utc).isoformat(),
            remind_time=local_dt.strftime("%H:%M"),
        )
        if ok:
            self._cancel_future_jobs(reminder_id)
        return ok > 0

    def delete(self, user_id: int, reminder_id: int) -> bool:
        if not self.get_owned(user_id, reminder_id):
            return False
        self._cancel_future_jobs(reminder_id)
        return self.repo.delete(reminder_id, user_id) > 0
