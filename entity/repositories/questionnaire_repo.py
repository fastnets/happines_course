from entity.db import Database

class QuestionnaireRepo:
    def __init__(self, db: Database):
        self.db = db

    def create(self, question: str, qtype: str, use_in_charts: bool, points: int, created_by: int | None):
        with self.db.cursor() as cur:
            cur.execute(
                "INSERT INTO questionnaires(question, qtype, use_in_charts, points, created_by) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                (question, qtype, use_in_charts, points, created_by),
            )
            return int(cur.fetchone()["id"])

    def update(self, qid: int, question: str, qtype: str, use_in_charts: bool, points: int):
        with self.db.cursor() as cur:
            cur.execute(
                "UPDATE questionnaires SET question=%s, qtype=%s, use_in_charts=%s, points=%s WHERE id=%s",
                (question, qtype, use_in_charts, points, qid),
            )

    def delete(self, qid: int) -> bool:
        with self.db.cursor() as cur:
            cur.execute("DELETE FROM questionnaires WHERE id=%s", (qid,))
            return cur.rowcount > 0

    def get(self, qid: int):
        with self.db.cursor() as cur:
            cur.execute("SELECT * FROM questionnaires WHERE id=%s", (qid,))
            return cur.fetchone()

    def list_latest(self, limit: int = 50):
        with self.db.cursor() as cur:
            cur.execute("SELECT * FROM questionnaires ORDER BY id DESC LIMIT %s", (limit,))
            return cur.fetchall()

    def get_latest_by_qtype(self, qtype: str):
        with self.db.cursor() as cur:
            cur.execute(
                "SELECT * FROM questionnaires WHERE qtype=%s ORDER BY id DESC LIMIT 1",
                (qtype,),
            )
            return cur.fetchone()
