from __future__ import annotations

from entity.db import Database


class DeliveriesRepo:
    """Tracks delivered day items (lesson / quest) per user."""

    def __init__(self, db: Database):
        self.db = db

    def was_sent(self, user_id: int, day_index: int, item_type: str) -> bool:
        with self.db.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM deliveries WHERE user_id=%s AND day_index=%s AND item_type=%s",
                (user_id, day_index, item_type),
            )
            return cur.fetchone() is not None

    def mark_sent(self, user_id: int, day_index: int, item_type: str) -> None:
        with self.db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO deliveries(user_id, day_index, item_type)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, day_index, item_type) DO NOTHING
                """,
                (user_id, day_index, item_type),
            )
