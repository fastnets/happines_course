from __future__ import annotations

from entity.db import Database


class MaterialMessagesRepo:
    """Stores last sent message ids for course materials per user/day."""

    def __init__(self, db: Database):
        self.db = db

    def upsert(
        self,
        user_id: int,
        day_index: int,
        kind: str,
        message_id: int,
        content_id: int = 0,
    ) -> None:
        with self.db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_material_messages(user_id, day_index, kind, content_id, message_id, sent_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (user_id, day_index, kind, content_id)
                DO UPDATE
                   SET message_id = EXCLUDED.message_id,
                       sent_at = NOW()
                """,
                (user_id, day_index, kind, content_id, message_id),
            )

    def get_message(
        self,
        user_id: int,
        day_index: int,
        kind: str,
        content_id: int = 0,
    ) -> dict | None:
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM user_material_messages
                WHERE user_id=%s AND day_index=%s AND kind=%s AND content_id=%s
                """,
                (user_id, day_index, kind, content_id),
            )
            return cur.fetchone()

    def get_latest_message(self, user_id: int, day_index: int, kind: str) -> dict | None:
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM user_material_messages
                WHERE user_id=%s AND day_index=%s AND kind=%s
                ORDER BY sent_at DESC
                LIMIT 1
                """,
                (user_id, day_index, kind),
            )
            return cur.fetchone()
