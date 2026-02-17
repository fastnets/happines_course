from __future__ import annotations

import json

from entity.db import Database


class AchievementsRepo:
    def __init__(self, db: Database):
        self.db = db

    def grant(
        self,
        user_id: int,
        code: str,
        title: str,
        description: str,
        icon: str,
        payload: dict | None = None,
    ) -> dict | None:
        with self.db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_achievements(user_id, code, title, description, icon, payload_json)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (user_id, code) DO NOTHING
                RETURNING user_id, code, title, description, icon, payload_json, awarded_at
                """,
                (user_id, code, title, description, icon, json.dumps(payload or {})),
            )
            return cur.fetchone()

    def list_for_user(self, user_id: int, limit: int = 20) -> list[dict]:
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT code, title, description, icon, payload_json, awarded_at
                FROM user_achievements
                WHERE user_id=%s
                ORDER BY awarded_at DESC
                LIMIT %s
                """,
                (user_id, max(1, int(limit or 20))),
            )
            return cur.fetchall() or []

    def count_for_user(self, user_id: int) -> int:
        with self.db.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM user_achievements WHERE user_id=%s", (user_id,))
            row = cur.fetchone() or {}
            return int(row.get("cnt") or 0)

