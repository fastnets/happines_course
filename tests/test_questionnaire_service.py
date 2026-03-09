import unittest

from questionnaires.questionnaire_service import QuestionnaireService, STEP_WAIT_Q_COMMENT


class DummyPoints:
    def __init__(self):
        self.calls = []
        self.entries = set()

    def add_points(self, user_id: int, source_type: str, source_key: str, points: int):
        self.calls.append((user_id, source_type, source_key, points))
        self.entries.add((user_id, source_type, source_key))

    def has_entry(self, user_id: int, source_type: str, source_key: str) -> bool:
        return (user_id, source_type, source_key) in self.entries


class DummyResponses:
    def __init__(self):
        self.calls = []

    def add(self, questionnaire_id: int, user_id: int, score: int, comment: str):
        self.calls.append((questionnaire_id, user_id, score, comment))


class DummyState:
    def __init__(self):
        self.set_calls = []
        self.clear_calls = []

    def set_state(self, user_id: int, step: str, payload: dict | None = None):
        self.set_calls.append((user_id, step, payload or {}))

    def clear_state(self, user_id: int):
        self.clear_calls.append(user_id)


class DummyQuestionnaireRepo:
    def __init__(self):
        self.responded = set()
        self.points_by_qid = {}

    def has_user_response(self, user_id: int, questionnaire_id: int) -> bool:
        return (user_id, questionnaire_id) in self.responded

    def get(self, qid: int):
        return {"id": qid, "points": self.points_by_qid.get(qid, 0)}


class QuestionnaireServiceTests(unittest.TestCase):
    def test_start_comment_flow_sets_wait_state_without_points(self):
        svc = QuestionnaireService.__new__(QuestionnaireService)
        svc.points = DummyPoints()
        svc.r = DummyResponses()
        svc.state = DummyState()
        svc.q = DummyQuestionnaireRepo()

        svc.start_comment_flow(user_id=11, qid=5, score=4, points=2)

        self.assertEqual(svc.points.calls, [])
        self.assertEqual(svc.r.calls, [])
        self.assertEqual(
            svc.state.set_calls,
            [(11, STEP_WAIT_Q_COMMENT, {"questionnaire_id": 5, "score": 4})],
        )
        self.assertEqual(svc.state.clear_calls, [])

    def test_submit_score_only_adds_points_and_response_without_state(self):
        svc = QuestionnaireService.__new__(QuestionnaireService)
        svc.points = DummyPoints()
        svc.r = DummyResponses()
        svc.state = DummyState()
        svc.q = DummyQuestionnaireRepo()

        created = svc.submit_score_only(user_id=11, qid=7, score=3, points=1)

        self.assertTrue(created)
        self.assertEqual(svc.points.calls, [(11, "questionnaire_score", "q:7", 1)])
        self.assertEqual(svc.r.calls, [(7, 11, 3, "")])
        self.assertEqual(svc.state.set_calls, [])
        self.assertEqual(svc.state.clear_calls, [])

    def test_submit_score_only_when_already_answered_does_nothing(self):
        svc = QuestionnaireService.__new__(QuestionnaireService)
        svc.points = DummyPoints()
        svc.r = DummyResponses()
        svc.state = DummyState()
        svc.q = DummyQuestionnaireRepo()
        svc.q.responded.add((11, 7))

        created = svc.submit_score_only(user_id=11, qid=7, score=3, points=1)

        self.assertFalse(created)
        self.assertEqual(svc.points.calls, [])
        self.assertEqual(svc.r.calls, [])

    def test_save_comment_adds_response_points_and_clears_state(self):
        svc = QuestionnaireService.__new__(QuestionnaireService)
        svc.points = DummyPoints()
        svc.r = DummyResponses()
        svc.state = DummyState()
        svc.q = DummyQuestionnaireRepo()
        svc.q.points_by_qid[5] = 4

        saved = svc.save_comment(user_id=11, qid=5, score=4, comment="ok")

        self.assertTrue(saved)
        self.assertEqual(svc.points.calls, [(11, "questionnaire_score", "q:5", 4)])
        self.assertEqual(svc.r.calls, [(5, 11, 4, "ok")])
        self.assertEqual(svc.state.clear_calls, [11])

    def test_save_comment_when_already_answered_does_not_duplicate(self):
        svc = QuestionnaireService.__new__(QuestionnaireService)
        svc.points = DummyPoints()
        svc.r = DummyResponses()
        svc.state = DummyState()
        svc.q = DummyQuestionnaireRepo()
        svc.q.responded.add((11, 5))

        saved = svc.save_comment(user_id=11, qid=5, score=4, comment="ok")

        self.assertFalse(saved)
        self.assertEqual(svc.points.calls, [])
        self.assertEqual(svc.r.calls, [])
        self.assertEqual(svc.state.clear_calls, [11])


if __name__ == "__main__":
    unittest.main()
