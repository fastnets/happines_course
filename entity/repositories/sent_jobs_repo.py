from __future__ import annotations

from datetime import date
from entity.db import Database

class SentJobsRepo:
    """Idempotency guard: records that a (user, content_type, day_index, local_date) was sent."""

    def __init__(self, db: Database):
        self.db = db

    def was_sent(self, user_id: int, content_type: str, day_index: int, for_date: date) -> bool:
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM sent_jobs
                WHERE user_id=%s AND content_type=%s AND day_index=%s AND for_date=%s
                """,
                (user_id, content_type, day_index, for_date),
            )
            return cur.fetchone() is not None

    def mark_sent(self, user_id: int, content_type: str, day_index: int, for_date: date) -> bool:
        """Returns True if inserted (i.e., first time), False if already existed."""
        with self.db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sent_jobs(user_id, content_type, day_index, for_date)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, content_type, day_index, for_date) DO NOTHING
                RETURNING 1
                """,
                (user_id, content_type, day_index, for_date),
            )
            return cur.fetchone() is not None
