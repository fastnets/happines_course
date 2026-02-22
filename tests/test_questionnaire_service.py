import unittest

from questionnaires.questionnaire_service import QuestionnaireService, STEP_WAIT_Q_COMMENT


class DummyPoints:
    def __init__(self):
        self.calls = []

    def add_points(self, user_id: int, source_type: str, source_key: str, points: int):
        self.calls.append((user_id, source_type, source_key, points))


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


class QuestionnaireServiceTests(unittest.TestCase):
    def test_start_comment_flow_adds_points_and_sets_wait_state(self):
        svc = QuestionnaireService.__new__(QuestionnaireService)
        svc.points = DummyPoints()
        svc.r = DummyResponses()
        svc.state = DummyState()

        svc.start_comment_flow(user_id=11, qid=5, score=4, points=2)

        self.assertEqual(svc.points.calls, [(11, "questionnaire_score", "q:5", 2)])
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

        svc.submit_score_only(user_id=11, qid=7, score=3, points=1)

        self.assertEqual(svc.points.calls, [(11, "questionnaire_score", "q:7", 1)])
        self.assertEqual(svc.r.calls, [(7, 11, 3, "")])
        self.assertEqual(svc.state.set_calls, [])
        self.assertEqual(svc.state.clear_calls, [])


if __name__ == "__main__":
    unittest.main()
