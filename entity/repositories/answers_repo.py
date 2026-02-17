from entity.db import Database

class AnswersRepo:
    def __init__(self, db: Database):
        self.db = db

    def save(self, user_id: int, day_index: int, answer_text: str):
        with self.db.cursor() as cur:
            cur.execute(
                "INSERT INTO quest_answers(user_id, day_index, answer_text) VALUES (%s,%s,%s)",
                (user_id, day_index, answer_text),
            )

    def exists_for_day(self, user_id: int, day_index: int) -> bool:
        with self.db.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM quest_answers WHERE user_id=%s AND day_index=%s LIMIT 1",
                (user_id, day_index),
            )
            return cur.fetchone() is not None
