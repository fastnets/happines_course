import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from analytics.analytics_service import AnalyticsService
from core.achievement_service import AchievementService


class DummyAchievementRepo:
    def __init__(self):
        self._granted = {}

    def grant(self, user_id, code, title, description, icon, payload=None):
        key = (int(user_id), str(code))
        if key in self._granted:
            return None
        row = {
            "user_id": int(user_id),
            "code": str(code),
            "title": str(title),
            "description": str(description),
            "icon": str(icon),
            "payload_json": payload or {},
        }
        self._granted[key] = row
        return row


class DummyPoints:
    def __init__(self, total: int):
        self.total = total

    def total_points(self, user_id: int) -> int:
        return int(self.total)


class DummyProgress:
    def __init__(self, done_days: int):
        self.done_days = done_days

    def count_done(self, user_id: int) -> int:
        return int(self.done_days)


class DummyMetrics:
    def __init__(self):
        now = datetime.now(timezone.utc)
        self._done_rows = [now, now - timedelta(days=1), now - timedelta(days=2)]

    def done_timestamps(self, user_id: int):
        return list(self._done_rows)

    def habit_done_skipped_counts(self, user_id: int):
        return {"done": 3, "skipped": 1}

    def questionnaire_count(self, user_id: int):
        return 3

    def delivery_counts(self, user_id: int):
        return {"lessons_sent": 5, "quests_sent": 4}

    def lesson_viewed_count(self, user_id: int):
        return 4

    def quest_answered_count(self, user_id: int):
        return 3

    def points_events_since(self, user_id: int, since_utc):
        return [{"created_at": datetime.now(timezone.utc), "points": 7}]

    def done_events_since(self, user_id: int, since_utc):
        return [{"done_at": datetime.now(timezone.utc)}]

    def questionnaire_events_since(self, user_id: int, since_utc):
        return [{"created_at": datetime.now(timezone.utc), "score": 4}]


class DummyUsers:
    def get_user(self, user_id: int):
        return {"display_name": "Иван", "timezone": "UTC"}


class DummyEnroll:
    def get(self, user_id: int):
        return {"delivery_time": "09:00"}


class DummyAchievementsForAnalytics:
    def list_for_user(self, user_id: int, limit: int = 20):
        return [{"icon": "🏆", "title": "Тест", "description": "Тестовая ачивка"}]

    def count_for_user(self, user_id: int):
        return 1


class ProgressAndAchievementTests(unittest.TestCase):
    def test_achievement_service_grants_only_new(self):
        svc = AchievementService.__new__(AchievementService)
        svc.settings = SimpleNamespace(default_timezone="UTC")
        svc.repo = DummyAchievementRepo()
        svc.points = DummyPoints(total=55)
        svc.progress = DummyProgress(done_days=4)
        svc.user_progress = DummyMetrics()

        first = svc.evaluate(user_id=101)
        second = svc.evaluate(user_id=101)

        granted_codes = {row["code"] for row in first}
        self.assertIn("first_points", granted_codes)
        self.assertIn("day_1_done", granted_codes)
        self.assertIn("streak_3", granted_codes)
        self.assertIn("habit_3_done", granted_codes)
        self.assertIn("questionnaire_3", granted_codes)
        self.assertIn("points_50", granted_codes)
        self.assertNotIn("streak_7", granted_codes)
        self.assertEqual(second, [])

    def test_analytics_profile_and_report_have_extended_metrics(self):
        svc = AnalyticsService.__new__(AnalyticsService)
        svc.settings = SimpleNamespace(default_timezone="UTC")
        svc.users = DummyUsers()
        svc.enroll = DummyEnroll()
        svc.points = DummyPoints(total=42)
        svc.progress = DummyProgress(done_days=3)
        svc.user_progress = DummyMetrics()
        svc.achievements = DummyAchievementsForAnalytics()

        prof = svc.profile(user_id=202)
        self.assertEqual(prof["display_name"], "Иван")
        self.assertEqual(prof["streak"], 3)
        self.assertEqual(prof["lessons_pct"], 80.0)
        self.assertEqual(prof["quests_pct"], 75.0)
        self.assertEqual(prof["habit_done"], 3)
        self.assertEqual(prof["habit_skipped"], 1)
        self.assertEqual(prof["achievements_total"], 1)
        self.assertEqual(len(prof["weekly"]), 4)

        txt = svc.progress_report(user_id=202)
        self.assertIn("Серия (streak): 3 дн.", txt)
        self.assertIn("Лекции: 4/5 (80.0%)", txt)
        self.assertIn("Задания: 3/4 (75.0%)", txt)
        self.assertIn("Привычки: done=3, skip=1", txt)
        self.assertIn("Ачивки: 1", txt)
        self.assertIn("Динамика по неделям:", txt)


if __name__ == "__main__":
    unittest.main()

