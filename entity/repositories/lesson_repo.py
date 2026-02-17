from entity.db import Database

class LessonRepo:
    def __init__(self, db: Database):
        self.db = db

    def upsert_lesson(self, day_index: int, title: str, description: str, video_url: str, points_viewed: int) -> int:
        with self.db.cursor() as cur:
            cur.execute(
                '''
                INSERT INTO lessons(day_index, title, description, video_url, points_viewed)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT(day_index) DO UPDATE
                  SET title=EXCLUDED.title,
                      description=EXCLUDED.description,
                      video_url=EXCLUDED.video_url,
                      points_viewed=EXCLUDED.points_viewed
                RETURNING id
                ''',
                (day_index, title, description, video_url, points_viewed),
            )
            return int(cur.fetchone()["id"])

    def get_by_day(self, day_index: int):
        with self.db.cursor() as cur:
            cur.execute("SELECT * FROM lessons WHERE day_index=%s", (day_index,))
            return cur.fetchone()

    def list_latest(self, limit: int = 30):
        with self.db.cursor() as cur:
            cur.execute("SELECT * FROM lessons ORDER BY day_index ASC LIMIT %s", (limit,))
            return cur.fetchall()

    def get_latest(self):
        """Returns the latest lesson by day_index (highest)."""
        with self.db.cursor() as cur:
            cur.execute("SELECT * FROM lessons ORDER BY day_index DESC LIMIT 1")
            return cur.fetchone()

    def delete_day(self, day_index: int) -> bool:
        with self.db.cursor() as cur:
            cur.execute("DELETE FROM lessons WHERE day_index=%s", (day_index,))
            return cur.rowcount > 0
