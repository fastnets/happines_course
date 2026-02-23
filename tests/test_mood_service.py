import unittest
from datetime import date
from types import SimpleNamespace

from core.mood_service import MoodService


class DummyRepo:
    def __init__(self):
        self.upsert_calls = []
        self._rows = []

    def upsert_daily(self, user_id: int, local_date: date, score: int, comment: str = ""):
        row = {
            "user_id": int(user_id),
            "local_date": local_date,
            "score": int(score),
            "comment": comment or "",
        }
        self.upsert_calls.append(row)
        return row

    def list_recent(self, user_id: int, days: int = 7):
        return list(self._rows)[: int(days)]


class DummyUsers:
    def get_timezone(self, user_id: int):
        return "UTC"


class MoodServiceTests(unittest.TestCase):
    def _svc(self):
        svc = MoodService.__new__(MoodService)
        svc.settings = SimpleNamespace(default_timezone="UTC")
        svc.repo = DummyRepo()
        svc.users = DummyUsers()
        svc._today_local_date = lambda _uid: date(2026, 2, 23)
        return svc

    def test_set_today_saves_only_scores_1_to_5(self):
        svc = self._svc()

        self.assertIsNone(svc.set_today(10, 0))
        self.assertIsNone(svc.set_today(10, 6))
        self.assertEqual(len(svc.repo.upsert_calls), 0)

        row = svc.set_today(10, 4)
        self.assertIsNotNone(row)
        self.assertEqual(len(svc.repo.upsert_calls), 1)
        self.assertEqual(svc.repo.upsert_calls[0]["score"], 4)
        self.assertEqual(svc.repo.upsert_calls[0]["local_date"], date(2026, 2, 23))

    def test_chart_rows_fills_missing_days_with_zero(self):
        svc = self._svc()
        svc.repo._rows = [
            {"local_date": date(2026, 2, 23), "score": 5},
            {"local_date": date(2026, 2, 21), "score": 3},
        ]

        rows = svc.chart_rows(10, days=3)
        self.assertEqual(
            rows,
            [
                {"local_date": date(2026, 2, 23), "score": 5},
                {"local_date": date(2026, 2, 22), "score": 0},
                {"local_date": date(2026, 2, 21), "score": 3},
            ],
        )

    def test_chart_text_contains_average_for_filled_days(self):
        svc = self._svc()
        svc.repo._rows = [
            {"local_date": date(2026, 2, 23), "score": 5},
            {"local_date": date(2026, 2, 22), "score": 3},
        ]

        text = svc.chart_text(10, days=2)
        self.assertIn("😊 Настроение за 2 дн.", text)
        self.assertIn("• 23.02: █████ (5)", text)
        self.assertIn("• 22.02: ███ (3)", text)
        self.assertIn("Среднее по заполненным дням: 4.00", text)


if __name__ == "__main__":
    unittest.main()

