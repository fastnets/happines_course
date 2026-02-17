from entity.db import Database

class QuestRepo:
    def __init__(self, db: Database):
        self.db = db

    def upsert_quest(self, day_index: int, points: int, prompt: str, photo_file_id: str | None = None) -> int:
        with self.db.cursor() as cur:
            cur.execute(
                '''
                INSERT INTO quests(day_index, points, prompt, photo_file_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT(day_index) DO UPDATE
                  SET points=EXCLUDED.points,
                      prompt=EXCLUDED.prompt,
                      photo_file_id=EXCLUDED.photo_file_id
                RETURNING id
                ''',
                (day_index, points, prompt, photo_file_id),
            )
            return int(cur.fetchone()["id"])

    def get_by_day(self, day_index: int):
        with self.db.cursor() as cur:
            cur.execute("SELECT * FROM quests WHERE day_index=%s", (day_index,))
            return cur.fetchone()

    def list_latest(self, limit: int = 30):
        with self.db.cursor() as cur:
            cur.execute("SELECT * FROM quests ORDER BY day_index ASC LIMIT %s", (limit,))
            return cur.fetchall()

    def delete_day(self, day_index: int) -> bool:
        with self.db.cursor() as cur:
            cur.execute("DELETE FROM quests WHERE day_index=%s", (day_index,))
            return cur.rowcount > 0
