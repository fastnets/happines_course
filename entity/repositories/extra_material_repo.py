from entity.db import Database


class ExtraMaterialRepo:
    def __init__(self, db: Database):
        self.db = db

    def upsert(
        self,
        day_index: int,
        content_text: str,
        points: int = 0,
        link_url: str | None = None,
        photo_file_id: str | None = None,
        is_active: bool = True,
    ) -> int:
        with self.db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO extra_materials(day_index, content_text, points, link_url, photo_file_id, is_active)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT(day_index) DO UPDATE
                  SET content_text=EXCLUDED.content_text,
                      points=EXCLUDED.points,
                      link_url=EXCLUDED.link_url,
                      photo_file_id=EXCLUDED.photo_file_id,
                      is_active=EXCLUDED.is_active,
                      updated_at=NOW()
                RETURNING id
                """,
                (day_index, content_text, points, link_url, photo_file_id, bool(is_active)),
            )
            return int(cur.fetchone()["id"])

    def get_by_day(self, day_index: int):
        with self.db.cursor() as cur:
            cur.execute("SELECT * FROM extra_materials WHERE day_index=%s", (day_index,))
            return cur.fetchone()

    def list_latest(self, limit: int = 200):
        with self.db.cursor() as cur:
            cur.execute("SELECT * FROM extra_materials ORDER BY day_index ASC LIMIT %s", (limit,))
            return cur.fetchall()

    def delete_day(self, day_index: int) -> bool:
        with self.db.cursor() as cur:
            cur.execute("DELETE FROM extra_materials WHERE day_index=%s", (day_index,))
            return cur.rowcount > 0
