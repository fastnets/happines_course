import unittest

from scheduling.worker import _collect_pending_backlog


class _DummyLessonRepo:
    def __init__(self, day_map):
        self.day_map = day_map

    def get_by_day(self, day_index: int):
        return self.day_map.get(day_index)


class _DummyQuestRepo:
    def __init__(self, day_map):
        self.day_map = day_map

    def get_by_day(self, day_index: int):
        return self.day_map.get(day_index)


class _DummySchedule:
    def __init__(self, lessons, quests):
        self.lesson = _DummyLessonRepo(lessons)
        self.quest = _DummyQuestRepo(quests)


class _DummyLearning:
    def __init__(self, viewed_days, answered_days):
        self.viewed_days = set(viewed_days)
        self.answered_days = set(answered_days)

    def has_viewed_lesson(self, _uid: int, day_index: int) -> bool:
        return day_index in self.viewed_days

    def has_quest_answer(self, _uid: int, day_index: int) -> bool:
        return day_index in self.answered_days


class _DummyQuestionnaireSvc:
    def __init__(self, q_by_day, responded_ids):
        self.q_by_day = q_by_day
        self.responded_ids = set(responded_ids)

    def list_for_day(self, day_index: int, qtypes=("manual", "daily")):
        _ = qtypes
        return self.q_by_day.get(day_index, [])

    def has_response(self, _uid: int, questionnaire_id: int) -> bool:
        return questionnaire_id in self.responded_ids


class DailyReminderBacklogTests(unittest.TestCase):
    def test_collect_pending_backlog_includes_previous_days(self):
        schedule = _DummySchedule(
            lessons={1: {"id": 1}, 2: {"id": 2}},
            quests={1: {"id": 10}, 2: {"id": 20}},
        )
        learning = _DummyLearning(viewed_days={2}, answered_days={1})
        qsvc = _DummyQuestionnaireSvc(
            q_by_day={1: [{"id": 101}], 2: [{"id": 201}]},
            responded_ids={201},
        )

        pending, first_lesson_day, first_quest_day = _collect_pending_backlog(
            schedule=schedule,
            learning=learning,
            qsvc=qsvc,
            user_id=42,
            day_index=2,
        )

        self.assertIn("• 📚 День 1: лекция — не отмечена «Просмотрено»", pending)
        self.assertIn("• 📝 День 2: задание — нет ответа", pending)
        self.assertIn("• 📋 День 1: анкета — нет ответа", pending)
        self.assertEqual(first_lesson_day, 1)
        self.assertEqual(first_quest_day, 2)

    def test_collect_pending_backlog_returns_empty_when_done(self):
        schedule = _DummySchedule(
            lessons={1: {"id": 1}, 2: {"id": 2}},
            quests={1: {"id": 10}, 2: {"id": 20}},
        )
        learning = _DummyLearning(viewed_days={1, 2}, answered_days={1, 2})
        qsvc = _DummyQuestionnaireSvc(
            q_by_day={1: [{"id": 101}], 2: [{"id": 201}]},
            responded_ids={101, 201},
        )

        pending, first_lesson_day, first_quest_day = _collect_pending_backlog(
            schedule=schedule,
            learning=learning,
            qsvc=qsvc,
            user_id=42,
            day_index=2,
        )

        self.assertEqual(pending, [])
        self.assertIsNone(first_lesson_day)
        self.assertIsNone(first_quest_day)


if __name__ == "__main__":
    unittest.main()

