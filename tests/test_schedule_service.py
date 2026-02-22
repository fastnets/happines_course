import unittest
from zoneinfo import ZoneInfo

from scheduling.schedule_service import ScheduleService


class DummyUsers:
    def list_user_ids(self, limit: int = 20000):
        return [1, 2, 3]


class DummyOutbox:
    def __init__(self, existing_users=None):
        self.existing_users = set(existing_users or [])
        self.checked = []
        self.created = []

    def exists_job_for(self, user_id: int, key: str) -> bool:
        self.checked.append((user_id, key))
        return user_id in self.existing_users

    def create_job(self, user_id: int, run_at_iso: str, payload: dict):
        self.created.append((user_id, run_at_iso, payload))


class ScheduleServiceTests(unittest.TestCase):
    def test_viewed_callback_roundtrip(self):
        svc = ScheduleService.__new__(ScheduleService)

        data = svc.make_viewed_cb(day_index=4, points=9)
        self.assertEqual(data, "lesson:viewed:day=4:p=9")
        self.assertEqual(svc.parse_viewed_payload(data), {"day_index": 4, "points": 9})
        self.assertIsNone(svc.parse_viewed_payload("lesson:viewed:broken"))
        self.assertIsNone(svc.parse_viewed_payload("other:data"))

    def test_questionnaire_broadcast_skips_existing_jobs(self):
        svc = ScheduleService.__new__(ScheduleService)
        svc.users = DummyUsers()
        svc.outbox = DummyOutbox(existing_users={2})
        svc._user_tz = lambda user_id: ZoneInfo("UTC")

        created = svc.schedule_questionnaire_broadcast(questionnaire_id=77, hhmm="09:30", optional=True)

        self.assertEqual(created, 2)
        self.assertEqual(len(svc.outbox.created), 2)

        created_user_ids = {row[0] for row in svc.outbox.created}
        self.assertEqual(created_user_ids, {1, 3})

        for user_id, run_at_iso, payload in svc.outbox.created:
            self.assertIsInstance(user_id, int)
            self.assertIn("T", run_at_iso)
            self.assertEqual(payload["kind"], "questionnaire_broadcast")
            self.assertEqual(payload["questionnaire_id"], 77)
            self.assertTrue(payload["optional"])
            self.assertTrue(payload["job_key"].startswith("qcast:77:"))


if __name__ == "__main__":
    unittest.main()
