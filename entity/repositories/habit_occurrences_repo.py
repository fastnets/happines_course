from __future__ import annotations

from datetime import datetime

from entity.db import Database


class HabitOccurrencesRepo:
    def __init__(self, db: Database):
        self.db = db

    def ensure_planned(self, habit_id: int, user_id: int, scheduled_at_iso: str) -> int | None:
        """Insert occurrence if not exists. Returns occurrence id if created or existing."""

        with self.db.cursor() as cur:
            # Try insert
            cur.execute(
                """
                INSERT INTO habit_occurrences(habit_id, user_id, scheduled_at, status)
                VALUES (%s,%s,%s,'planned')
                ON CONFLICT (habit_id, scheduled_at) DO UPDATE SET habit_id=EXCLUDED.habit_id
                RETURNING id
                """,
                (habit_id, user_id, scheduled_at_iso),
            )
            row = cur.fetchone()
            return int(row["id"]) if row else None

    def get(self, occurrence_id: int):
        with self.db.cursor() as cur:
            cur.execute("SELECT * FROM habit_occurrences WHERE id=%s", (occurrence_id,))
            return cur.fetchone()

    def mark_sent(self, occurrence_id: int):
        with self.db.cursor() as cur:
            cur.execute(
                """
                UPDATE habit_occurrences
                   SET status='sent'
                 WHERE id=%s AND status='planned'
                """,
                (occurrence_id,),
            )
            return cur.rowcount

    def mark_done(self, occurrence_id: int, user_id: int) -> bool:
        with self.db.cursor() as cur:
            cur.execute(
                """
                UPDATE habit_occurrences
                   SET status='done', action_at=NOW()
                 WHERE id=%s AND user_id=%s AND status IN ('planned','sent')
                """,
                (occurrence_id, user_id),
            )
            return cur.rowcount > 0

    def mark_skipped(self, occurrence_id: int, user_id: int) -> bool:
        with self.db.cursor() as cur:
            cur.execute(
                """
                UPDATE habit_occurrences
                   SET status='skipped', action_at=NOW()
                 WHERE id=%s AND user_id=%s AND status IN ('planned','sent')
                """,
                (occurrence_id, user_id),
            )
            return cur.rowcount > 0

    def cancel_future_for_habit(self, habit_id: int, from_utc_iso: str) -> int:
        with self.db.cursor() as cur:
            cur.execute(
                """
                UPDATE habit_occurrences
                   SET status='cancelled'
                 WHERE habit_id=%s
                   AND status IN ('planned','sent')
                   AND scheduled_at >= %s
                """,
                (habit_id, from_utc_iso),
            )
            return cur.rowcount
