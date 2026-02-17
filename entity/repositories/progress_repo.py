from entity.db import Database

class ProgressRepo:
    def __init__(self, db: Database):
        self.db = db

    def mark_sent(self, user_id: int, day_index: int):
        with self.db.cursor() as cur:
            cur.execute(
                "INSERT INTO progress(user_id, day_index, status) VALUES (%s,%s,'sent') ON CONFLICT(user_id, day_index) DO NOTHING",
                (user_id, day_index),
            )

    def mark_viewed(self, user_id: int, day_index: int):
        with self.db.cursor() as cur:
            cur.execute(
                "INSERT INTO progress(user_id, day_index, status) VALUES (%s,%s,'viewed') "
                "ON CONFLICT(user_id, day_index) DO UPDATE SET status='viewed'",
                (user_id, day_index),
            )

    def mark_done(self, user_id: int, day_index: int):
        with self.db.cursor() as cur:
            cur.execute(
                "INSERT INTO progress(user_id, day_index, status, done_at) VALUES (%s,%s,'done',NOW()) "
                "ON CONFLICT(user_id, day_index) DO UPDATE SET status='done', done_at=NOW()",
                (user_id, day_index),
            )

    def count_done(self, user_id: int) -> int:
        with self.db.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM progress WHERE user_id=%s AND status='done'", (user_id,))
            return int(cur.fetchone()["cnt"])

    def was_delivered(self, user_id: int, day_index: int) -> bool:
        """True if the user already received anything for this day.

        We treat any progress row (sent/viewed/done) as "delivered", because:
        - viewing implies the lesson was delivered,
        - answering implies the quest was delivered.
        """
        with self.db.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM progress WHERE user_id=%s AND day_index=%s LIMIT 1",
                (user_id, day_index),
            )
            return cur.fetchone() is not None
