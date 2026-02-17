from entity.db import Database

class EnrollmentRepo:
    def __init__(self, db: Database):
        self.db = db

    def upsert(self, user_id: int, delivery_time: str):
        with self.db.cursor() as cur:
            cur.execute(
                '''
                INSERT INTO enrollments(user_id, delivery_time, is_active)
                VALUES (%s, %s, TRUE)
                ON CONFLICT(user_id) DO UPDATE
                  SET delivery_time=EXCLUDED.delivery_time,
                      is_active=TRUE
                ''',
                (user_id, delivery_time),
            )

    def get(self, user_id: int):
        with self.db.cursor() as cur:
            cur.execute("SELECT * FROM enrollments WHERE user_id=%s AND is_active=TRUE", (user_id,))
            return cur.fetchone()

    def list_active(self):
        with self.db.cursor() as cur:
            cur.execute("SELECT * FROM enrollments WHERE is_active=TRUE")
            return cur.fetchall()
