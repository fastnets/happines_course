from entity.db import Database

class QuestionnaireRepo:
    def __init__(self, db: Database):
        self.db = db

    def create(
        self,
        question: str,
        qtype: str,
        use_in_charts: bool,
        points: int,
        created_by: int | None,
        day_index: int | None = None,
    ):
        with self.db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO questionnaires(question, qtype, day_index, use_in_charts, points, created_by)
                VALUES (%s,%s,%s,%s,%s,%s)
                RETURNING id
                """,
                (question, qtype, day_index, use_in_charts, points, created_by),
            )
            return int(cur.fetchone()["id"])

    def update(
        self,
        qid: int,
        question: str,
        qtype: str,
        use_in_charts: bool,
        points: int,
        day_index: int | None = None,
    ):
        with self.db.cursor() as cur:
            cur.execute(
                """
                UPDATE questionnaires
                SET question=%s, qtype=%s, day_index=%s, use_in_charts=%s, points=%s
                WHERE id=%s
                """,
                (question, qtype, day_index, use_in_charts, points, qid),
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

    def list_by_day(self, day_index: int, qtypes: tuple[str, ...] = ("manual",)):
        with self.db.cursor() as cur:
            qtypes_list = list(qtypes)
            if "daily" in qtypes_list:
                # Backward compatibility: old daily questionnaires were created
                # without day_index and should still broadcast each day.
                cur.execute(
                    """
                    SELECT *
                    FROM questionnaires
                    WHERE (day_index=%s AND qtype = ANY(%s))
                       OR (qtype='daily' AND day_index IS NULL)
                    ORDER BY id ASC
                    """,
                    (day_index, qtypes_list),
                )
            else:
                cur.execute(
                    """
                    SELECT *
                    FROM questionnaires
                    WHERE day_index=%s
                      AND qtype = ANY(%s)
                    ORDER BY id ASC
                    """,
                    (day_index, qtypes_list),
                )
            return cur.fetchall()

    def has_user_response(self, user_id: int, questionnaire_id: int) -> bool:
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM questionnaire_responses
                WHERE user_id=%s AND questionnaire_id=%s
                LIMIT 1
                """,
                (user_id, questionnaire_id),
            )
            return cur.fetchone() is not None
