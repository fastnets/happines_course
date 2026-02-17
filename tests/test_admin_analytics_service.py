import unittest

from analytics.admin_analytics_service import AdminAnalyticsService


class DummyRepo:
    def summary(self, days: int):
        return {
            "users_total": 100,
            "consent_total": 90,
            "timezone_total": 80,
            "enrolled_total": 70,
            "active_users": 55,
            "avg_points": 12.345,
        }

    def funnel(self, days: int):
        return {
            "users_total": 40,
            "consent_total": 30,
            "timezone_total": 20,
            "enrolled_total": 10,
            "day1_done_total": 5,
        }

    def delivery(self, days: int):
        return {
            "status": {"pending": 2, "sent": 10, "failed": 1, "cancelled": 3},
            "kinds": [
                {"kind": "day_lesson", "total": 5, "sent": 4, "failed": 0, "pending": 1, "cancelled": 0},
                {"kind": "day_quest", "total": 3, "sent": 3, "failed": 0, "pending": 0, "cancelled": 0},
            ],
        }

    def content(self, days: int):
        return {
            "sent_rows": [{"day_index": 1, "lesson_sent": 10, "quest_sent": 8}],
            "lesson_rows": [{"source_key": "day:1", "viewed": 7}],
            "quest_rows": [{"day_index": 1, "answered": 6}],
        }

    def questionnaires(self, days: int):
        return {
            "summary": {"responses_total": 20, "users_total": 12, "avg_score": 4.5},
            "top_rows": [{"id": 1, "question": "Как дела?", "responses": 20, "avg_score": 4.5}],
        }

    def reminders(self, days: int):
        return {
            "personal_created": 4,
            "personal_sent": 3,
            "personal_pending": 1,
            "personal_cancelled": 0,
            "habits_created": 2,
            "habit_sent": 5,
            "habit_done": 3,
            "habit_skipped": 1,
            "daily_sent": 8,
        }


class AdminAnalyticsServiceTests(unittest.TestCase):
    def _svc(self):
        svc = AdminAnalyticsService.__new__(AdminAnalyticsService)
        svc.repo = DummyRepo()
        return svc

    def test_summary_report_contains_core_metrics(self):
        txt = self._svc().summary_report(7)
        self.assertIn("Пользователей всего: 100", txt)
        self.assertIn("Согласие ПД: 90 (90.0%)", txt)
        self.assertIn("Средние баллы/пользователь: 12.3", txt)

    def test_funnel_report_has_percentages(self):
        txt = self._svc().funnel_report(7)
        self.assertIn("Старт: 40", txt)
        self.assertIn("День 1 завершён: 5 (12.5%)", txt)

    def test_delivery_report_contains_kind_breakdown(self):
        txt = self._svc().delivery_report(7)
        self.assertIn("Всего jobs: 16", txt)
        self.assertIn("day_lesson: 4/5 sent", txt)

    def test_content_report_formats_day_stats(self):
        txt = self._svc().content_report(7)
        self.assertIn("День 1: лекции 7/10 (70.0%)", txt)
        self.assertIn("задания 6/8 (75.0%)", txt)

    def test_questionnaires_and_reminders_reports(self):
        svc = self._svc()
        qtxt = svc.questionnaires_report(7)
        rtxt = svc.reminders_report(7)
        self.assertIn("Ответов: 20", qtxt)
        self.assertIn("Personal reminders: created=4", rtxt)


if __name__ == "__main__":
    unittest.main()
