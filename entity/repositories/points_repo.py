from entity.db import Database

class PointsRepo:
    def __init__(self, db: Database):
        self.db = db

    def add_points(self, user_id: int, source_type: str, source_key: str | None, points: int):
        with self.db.cursor() as cur:
            cur.execute(
                "INSERT INTO points_ledger(user_id, source_type, source_key, points) VALUES (%s,%s,%s,%s)",
                (user_id, source_type, source_key, points),
            )

    def total_points(self, user_id: int) -> int:
        with self.db.cursor() as cur:
            cur.execute("SELECT COALESCE(SUM(points),0) AS s FROM points_ledger WHERE user_id=%s", (user_id,))
            return int(cur.fetchone()["s"])

    def has_entry(self, user_id: int, source_type: str, source_key: str | None) -> bool:
        with self.db.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM points_ledger WHERE user_id=%s AND source_type=%s AND source_key=%s LIMIT 1",
                (user_id, source_type, source_key),
            )
            return cur.fetchone() is not None
