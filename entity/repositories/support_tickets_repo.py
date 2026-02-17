from __future__ import annotations

from entity.db import Database


class SupportTicketsRepo:
    def __init__(self, db: Database):
        self.db = db

    def create(self, user_id: int, question_text: str) -> dict | None:
        with self.db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO support_tickets(user_id, status, question_text)
                VALUES (%s, 'open', %s)
                RETURNING *
                """,
                (user_id, question_text),
            )
            return cur.fetchone()

    def get(self, ticket_id: int) -> dict | None:
        with self.db.cursor() as cur:
            cur.execute("SELECT * FROM support_tickets WHERE id=%s", (ticket_id,))
            return cur.fetchone()

    def list_tickets(self, status: str | None = "open", limit: int = 20) -> list[dict]:
        safe_limit = max(1, int(limit or 20))
        with self.db.cursor() as cur:
            if status:
                cur.execute(
                    """
                    SELECT *
                    FROM support_tickets
                    WHERE status=%s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (status, safe_limit),
                )
            else:
                cur.execute(
                    """
                    SELECT *
                    FROM support_tickets
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (safe_limit,),
                )
            return cur.fetchall() or []

    def close_with_reply(self, ticket_id: int, admin_id: int, admin_reply: str) -> dict | None:
        with self.db.cursor() as cur:
            cur.execute(
                """
                UPDATE support_tickets
                SET
                  status='closed',
                  admin_id=%s,
                  admin_reply=%s,
                  updated_at=NOW(),
                  closed_at=NOW()
                WHERE id=%s AND status='open'
                RETURNING *
                """,
                (admin_id, admin_reply, ticket_id),
            )
            return cur.fetchone()

    def close(self, ticket_id: int, admin_id: int) -> dict | None:
        with self.db.cursor() as cur:
            cur.execute(
                """
                UPDATE support_tickets
                SET
                  status='closed',
                  admin_id=%s,
                  updated_at=NOW(),
                  closed_at=NOW()
                WHERE id=%s AND status='open'
                RETURNING *
                """,
                (admin_id, ticket_id),
            )
            return cur.fetchone()

