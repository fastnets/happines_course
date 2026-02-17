import unittest
from types import SimpleNamespace

from core.habit_service import HabitService
from learning.learning_service import LearningService


class DummyAnswers:
    def __init__(self):
        self.saved = []

    def save(self, user_id: int, day_index: int, answer_text: str):
        self.saved.append((user_id, day_index, answer_text))

    def exists_for_day(self, user_id: int, day_index: int) -> bool:
        return any(uid == user_id and day == day_index for uid, day, _ in self.saved)


class DummyPoints:
    def __init__(self):
        self.added = []
        self.entries = set()

    def add_points(self, user_id: int, source_type: str, source_key: str, points: int):
        self.added.append((user_id, source_type, source_key, points))
        self.entries.add((user_id, source_type, source_key))

    def has_entry(self, user_id: int, source_type: str, source_key: str) -> bool:
        return (user_id, source_type, source_key) in self.entries


class DummyProgress:
    def __init__(self):
        self.done_calls = []
        self.viewed_calls = []

    def mark_done(self, user_id: int, day_index: int):
        self.done_calls.append((user_id, day_index))

    def mark_viewed(self, user_id: int, day_index: int):
        self.viewed_calls.append((user_id, day_index))


class DummyState:
    def __init__(self):
        self.cleared = []

    def clear_state(self, user_id: int):
        self.cleared.append(user_id)


class DummyOcc:
    def __init__(self):
        self.done_calls = []

    def mark_done(self, occurrence_id: int, user_id: int) -> bool:
        self.done_calls.append((occurrence_id, user_id))
        return True


class LearningAndHabitTests(unittest.TestCase):
    def test_submit_answer_updates_points_progress_and_state(self):
        svc = LearningService.__new__(LearningService)
        svc.answers = DummyAnswers()
        svc.points = DummyPoints()
        svc.progress = DummyProgress()
        svc.state = DummyState()

        svc.submit_answer(user_id=11, day_index=3, points=7, answer_text="my answer")

        self.assertEqual(svc.answers.saved, [(11, 3, "my answer")])
        self.assertEqual(svc.points.added, [(11, "quest", "day:3", 7)])
        self.assertEqual(svc.progress.done_calls, [(11, 3)])
        self.assertEqual(svc.state.cleared, [11])
        self.assertTrue(svc.has_quest_answer(11, 3))

    def test_has_viewed_lesson_reads_points_ledger(self):
        svc = LearningService.__new__(LearningService)
        svc.answers = DummyAnswers()
        svc.points = DummyPoints()
        svc.progress = DummyProgress()
        svc.state = DummyState()

        self.assertFalse(svc.has_viewed_lesson(22, 5))
        svc.points.add_points(22, "lesson_viewed", "day:5", 1)
        self.assertTrue(svc.has_viewed_lesson(22, 5))

    def test_habit_mark_done_is_idempotent_for_points(self):
        svc = HabitService.__new__(HabitService)
        svc.settings = SimpleNamespace(habit_bonus_points=3)
        svc.occ = DummyOcc()
        svc.points = DummyPoints()

        self.assertTrue(svc.mark_done(user_id=33, occurrence_id=1001))
        self.assertTrue(svc.mark_done(user_id=33, occurrence_id=1001))

        added = [row for row in svc.points.added if row[1] == "habit_done"]
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0], (33, "habit_done", "occ:1001", 3))


if __name__ == "__main__":
    unittest.main()
