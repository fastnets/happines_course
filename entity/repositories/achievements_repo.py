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

    def list_rules(self, active_only: bool | None = None, limit: int = 200) -> list[dict]:
        with self.db.cursor() as cur:
            safe_limit = max(1, int(limit or 200))
            if active_only is None:
                cur.execute(
                    """
                    SELECT *
                    FROM achievement_rules
                    ORDER BY sort_order ASC, id ASC
                    LIMIT %s
                    """,
                    (safe_limit,),
                )
            else:
                cur.execute(
                    """
                    SELECT *
                    FROM achievement_rules
                    WHERE is_active=%s
                    ORDER BY sort_order ASC, id ASC
                    LIMIT %s
                    """,
                    (bool(active_only), safe_limit),
                )
            return cur.fetchall() or []

    def get_rule(self, rule_id: int) -> dict | None:
        with self.db.cursor() as cur:
            cur.execute("SELECT * FROM achievement_rules WHERE id=%s", (int(rule_id),))
            return cur.fetchone()

    def create_rule(
        self,
        code: str,
        title: str,
        description: str,
        icon: str,
        metric_key: str,
        operator: str,
        threshold: int,
        is_active: bool,
        sort_order: int,
    ) -> dict | None:
        with self.db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO achievement_rules(
                    code, title, description, icon, metric_key, "operator", threshold, is_active, sort_order, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                RETURNING *
                """,
                (
                    str(code),
                    str(title),
                    str(description),
                    str(icon),
                    str(metric_key),
                    str(operator),
                    int(threshold),
                    bool(is_active),
                    int(sort_order),
                ),
            )
            return cur.fetchone()

    def update_rule(
        self,
        rule_id: int,
        code: str,
        title: str,
        description: str,
        icon: str,
        metric_key: str,
        operator: str,
        threshold: int,
        is_active: bool,
        sort_order: int,
    ) -> dict | None:
        with self.db.cursor() as cur:
            cur.execute(
                """
                UPDATE achievement_rules
                SET
                  code=%s,
                  title=%s,
                  description=%s,
                  icon=%s,
                  metric_key=%s,
                  "operator"=%s,
                  threshold=%s,
                  is_active=%s,
                  sort_order=%s,
                  updated_at=NOW()
                WHERE id=%s
                RETURNING *
                """,
                (
                    str(code),
                    str(title),
                    str(description),
                    str(icon),
                    str(metric_key),
                    str(operator),
                    int(threshold),
                    bool(is_active),
                    int(sort_order),
                    int(rule_id),
                ),
            )
            return cur.fetchone()

    def delete_rule(self, rule_id: int) -> bool:
        with self.db.cursor() as cur:
            cur.execute("DELETE FROM achievement_rules WHERE id=%s", (int(rule_id),))
            return cur.rowcount > 0
