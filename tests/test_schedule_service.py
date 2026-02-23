import unittest
from datetime import datetime, date, timezone
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


class DummyQuestionnairesByDay:
    def list_by_day(self, day_index: int, qtypes=("manual",)):
        if day_index == 1:
            return [{"id": 11}, {"id": 12}]
        return []


class DummySentJobs:
    def __init__(self):
        self.calls = []

    def was_sent(self, user_id: int, content_type: str, day_index: int, for_date):
        self.calls.append((user_id, content_type, day_index, for_date))
        # Keep reminders out of this test.
        return content_type == "daily_reminder"


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

    def test_schedules_multiple_day_questionnaires_for_same_day(self):
        svc = ScheduleService.__new__(ScheduleService)
        svc.settings = type("S", (), {"delivery_grace_minutes": 15})()
        svc.lesson = type("L", (), {"get_by_day": staticmethod(lambda _day: None)})()
        svc.quest = type("Q", (), {"get_by_day": staticmethod(lambda _day: None)})()
        svc.questionnaires = DummyQuestionnairesByDay()
        svc.sent_jobs = DummySentJobs()
        svc.outbox = DummyOutbox()
        svc._user_tz = lambda _uid: ZoneInfo("UTC")
        base_date = date(2026, 2, 23)
        svc.day_index_for_local_date = lambda _uid, d: 1 if d == base_date else 2
        svc._log_job = lambda *args, **kwargs: None

        created = svc._schedule_for_user(
            user_id=951667241,
            now_utc=datetime(2026, 2, 23, 10, 0, tzinfo=timezone.utc),
            enrollment_row={"user_id": 951667241, "delivery_time": "21:00"},
        )

        self.assertEqual(created, 2)
        self.assertEqual(len(svc.outbox.created), 2)
        payloads = [row[2] for row in svc.outbox.created]
        qids = {int(p["questionnaire_id"]) for p in payloads}
        self.assertEqual(qids, {11, 12})
        self.assertTrue(all(p["kind"] == "questionnaire_broadcast" for p in payloads))
        self.assertTrue(all(p.get("optional") is False for p in payloads))

        was_sent_types = [row[1] for row in svc.sent_jobs.calls]
        self.assertIn("questionnaire:11", was_sent_types)
        self.assertIn("questionnaire:12", was_sent_types)


if __name__ == "__main__":
    unittest.main()
