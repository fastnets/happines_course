import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from scheduling.personal_reminder_schedule_service import PersonalReminderScheduleService


class DummyRepo:
    def __init__(self, rows):
        self.rows = rows

    def list_active(self):
        return self.rows


class DummyUsers:
    def __init__(self, tz_name: str = "UTC"):
        self.tz_name = tz_name

    def get_timezone(self, user_id: int) -> str:
        return self.tz_name


class DummyOutbox:
    def __init__(self, existing=None):
        self.existing = set(existing or [])
        self.created = []

    def exists_job_for(self, user_id: int, key: str) -> bool:
        return (user_id, key) in self.existing

    def create_job(self, user_id: int, run_at_iso: str, payload: dict):
        self.created.append((user_id, run_at_iso, payload))


class PersonalReminderScheduleServiceTests(unittest.TestCase):
    def test_creates_one_job_for_future_one_time_reminder(self):
        svc = PersonalReminderScheduleService.__new__(PersonalReminderScheduleService)
        svc.settings = SimpleNamespace(default_timezone="UTC")
        svc.repo = DummyRepo(
            [
                {
                    "id": 10,
                    "user_id": 1,
                    "text": "Позвонить маме",
                    "start_at": datetime(2026, 2, 17, 9, 30, tzinfo=timezone.utc),
                }
            ]
        )
        svc.outbox = DummyOutbox()
        svc.users = DummyUsers("UTC")
        svc._now_utc = lambda: datetime(2026, 2, 17, 8, 0, tzinfo=timezone.utc)

        created = svc.schedule_due_jobs()

        self.assertEqual(created, 1)
        self.assertEqual(len(svc.outbox.created), 1)
        user_id, run_at_iso, payload = svc.outbox.created[0]
        self.assertEqual(user_id, 1)
        self.assertIn("T", run_at_iso)
        self.assertEqual(payload["kind"], "personal_reminder")
        self.assertEqual(payload["for_local_date"], "2026-02-17")
        self.assertEqual(payload["for_local_time"], "09:30")

    def test_skips_if_job_already_exists_or_start_in_past(self):
        svc = PersonalReminderScheduleService.__new__(PersonalReminderScheduleService)
        svc.settings = SimpleNamespace(default_timezone="UTC")
        already = datetime(2026, 2, 17, 9, 30, tzinfo=timezone.utc)
        existing_key = f"personal_once:10:{already.isoformat()}"
        svc.repo = DummyRepo(
            [
                {
                    "id": 10,
                    "user_id": 1,
                    "text": "Позвонить маме",
                    "start_at": already,
                },
                {
                    "id": 11,
                    "user_id": 2,
                    "text": "Просроченная задача",
                    "start_at": datetime(2026, 2, 17, 7, 0, tzinfo=timezone.utc),
                },
            ]
        )
        svc.outbox = DummyOutbox(existing={(1, existing_key)})
        svc.users = DummyUsers("UTC")
        svc._now_utc = lambda: datetime(2026, 2, 17, 8, 0, tzinfo=timezone.utc)

        created = svc.schedule_due_jobs()

        self.assertEqual(created, 0)
        self.assertEqual(svc.outbox.created, [])


if __name__ == "__main__":
    unittest.main()
