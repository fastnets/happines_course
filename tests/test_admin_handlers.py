import unittest

from admin.admin_handlers import _extract_quest_points


class ExtractQuestPointsTests(unittest.TestCase):
    def test_prefers_points_field(self):
        row = {"points": 5, "points_reply": 1}
        self.assertEqual(_extract_quest_points(row), 5)

    def test_falls_back_to_legacy_points_reply(self):
        row = {"points_reply": 4}
        self.assertEqual(_extract_quest_points(row), 4)

    def test_returns_zero_for_invalid_value(self):
        self.assertEqual(_extract_quest_points({"points": "bad"}), 0)
        self.assertEqual(_extract_quest_points({}), 0)


if __name__ == "__main__":
    unittest.main()
