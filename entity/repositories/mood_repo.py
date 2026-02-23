from __future__ import annotations

from datetime import date

from entity.db import Database


class MoodRepo:
    def __init__(self, db: Database):
        self.db = db

    def upsert_daily(self, user_id: int, local_date: date, score: int, comment: str = "") -> dict | None:
        with self.db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO mood_entries(user_id, local_date, score, comment)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, local_date) DO UPDATE
                  SET score=EXCLUDED.score,
                      comment=EXCLUDED.comment,
                      updated_at=NOW()
                RETURNING *
                """,
                (user_id, local_date, score, comment),
            )
            return cur.fetchone()

    def list_recent(self, user_id: int, days: int = 7) -> list[dict]:
        safe_days = max(1, int(days or 7))
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM mood_entries
                WHERE user_id=%s
                ORDER BY local_date DESC
                LIMIT %s
                """,
                (user_id, safe_days),
            )
            return cur.fetchall() or []

