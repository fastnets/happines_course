import json
from entity.repositories.questionnaire_repo import QuestionnaireRepo
from entity.repositories.questionnaire_responses_repo import QuestionnaireResponsesRepo
from entity.repositories.points_repo import PointsRepo
from entity.repositories.state_repo import StateRepo

STEP_WAIT_Q_COMMENT = "wait_q_comment"

class QuestionnaireService:
    def __init__(self, db, settings):
        self.q = QuestionnaireRepo(db)
        self.r = QuestionnaireResponsesRepo(db)
        self.points = PointsRepo(db)
        self.state = StateRepo(db)

    def create(
        self,
        question: str,
        qtype: str,
        use_in_charts: bool,
        points: int,
        created_by: int | None,
        day_index: int | None = None,
    ):
        return self.q.create(question, qtype, use_in_charts, points, created_by, day_index=day_index)

    def list_latest(self, limit=50):
        return self.q.list_latest(limit)

    def get(self, qid: int):
        return self.q.get(qid)

    def list_for_day(self, day_index: int, qtypes: tuple[str, ...] = ("manual",)):
        return self.q.list_by_day(day_index, qtypes=qtypes)

    def has_response(self, user_id: int, questionnaire_id: int) -> bool:
        return self.q.has_user_response(user_id, questionnaire_id)

    def update(
        self,
        qid: int,
        question: str,
        qtype: str,
        use_in_charts: bool,
        points: int,
        day_index: int | None = None,
    ):
        self.q.update(qid, question, qtype, use_in_charts, points, day_index=day_index)

    def delete(self, qid: int) -> bool:
        return self.q.delete(qid)

    @staticmethod
    def _score_key(qid: int) -> str:
        return f"q:{qid}"

    def _add_score_points_once(self, user_id: int, qid: int, points: int) -> bool:
        source_type = "questionnaire_score"
        source_key = self._score_key(qid)
        has_entry = getattr(self.points, "has_entry", None)
        if callable(has_entry) and has_entry(user_id, source_type, source_key):
            return False
        self.points.add_points(user_id, source_type, source_key, points)
        return True

    def start_comment_flow(self, user_id: int, qid: int, score: int, points: int):
        self.state.set_state(user_id, STEP_WAIT_Q_COMMENT, {"questionnaire_id": qid, "score": score})

    def submit_score_only(self, user_id: int, qid: int, score: int, points: int) -> bool:
        if self.q.has_user_response(user_id, qid):
            return False
        self._add_score_points_once(user_id, qid, points)
        self.r.add(qid, user_id, score, "")
        return True

    def save_comment(self, user_id: int, qid: int, score: int, comment: str) -> bool:
        if self.q.has_user_response(user_id, qid):
            self.state.clear_state(user_id)
            return False
        qrow = self.q.get(qid)
        points = int((qrow or {}).get("points") or 0)
        self._add_score_points_once(user_id, qid, points)
        self.r.add(qid, user_id, score, comment)
        self.state.clear_state(user_id)
        return True
