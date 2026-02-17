from entity.db import Database

class QuestionnaireResponsesRepo:
    def __init__(self, db: Database):
        self.db = db

    def add(self, questionnaire_id: int, user_id: int, score: int, comment: str):
        with self.db.cursor() as cur:
            cur.execute(
                "INSERT INTO questionnaire_responses(questionnaire_id, user_id, score, comment) VALUES (%s,%s,%s,%s)",
                (questionnaire_id, user_id, score, comment),
            )
