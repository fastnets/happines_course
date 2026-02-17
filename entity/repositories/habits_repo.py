import json
from datetime import datetime

from entity.db import Database


class HabitsRepo:
    def __init__(self, db: Database):
        self.db = db

    def create(self, user_id: int, title: str, remind_time: str, frequency: str) -> int:
        with self.db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO habits(user_id, title, remind_time, frequency, is_active)
                VALUES (%s,%s,%s,%s,TRUE)
                RETURNING id
                """,
                (user_id, title, remind_time, frequency),
            )
            return int(cur.fetchone()["id"])

    def list_for_user(self, user_id: int):
        with self.db.cursor() as cur:
            cur.execute(
                "SELECT * FROM habits WHERE user_id=%s ORDER BY is_active DESC, id DESC",
                (user_id,),
            )
            return cur.fetchall()

    def get(self, habit_id: int):
        with self.db.cursor() as cur:
            cur.execute("SELECT * FROM habits WHERE id=%s", (habit_id,))
            return cur.fetchone()

    def set_active(self, habit_id: int, user_id: int, is_active: bool):
        with self.db.cursor() as cur:
            cur.execute(
                """
                UPDATE habits
                   SET is_active=%s, updated_at=NOW()
                 WHERE id=%s AND user_id=%s
                """,
                (is_active, habit_id, user_id),
            )
            return cur.rowcount

    def delete(self, habit_id: int, user_id: int):
        with self.db.cursor() as cur:
            cur.execute("DELETE FROM habits WHERE id=%s AND user_id=%s", (habit_id, user_id))
            return cur.rowcount

    def update_title(self, habit_id: int, user_id: int, title: str):
        with self.db.cursor() as cur:
            cur.execute(
                """
                UPDATE habits
                   SET title=%s, updated_at=NOW()
                 WHERE id=%s AND user_id=%s
                """,
                (title, habit_id, user_id),
            )
            return cur.rowcount

    def update_time(self, habit_id: int, user_id: int, remind_time: str):
        with self.db.cursor() as cur:
            cur.execute(
                """
                UPDATE habits
                   SET remind_time=%s, updated_at=NOW()
                 WHERE id=%s AND user_id=%s
                """,
                (remind_time, habit_id, user_id),
            )
            return cur.rowcount

    def update_frequency(self, habit_id: int, user_id: int, frequency: str):
        with self.db.cursor() as cur:
            cur.execute(
                """
                UPDATE habits
                   SET frequency=%s, updated_at=NOW()
                 WHERE id=%s AND user_id=%s
                """,
                (frequency, habit_id, user_id),
            )
            return cur.rowcount

    def list_active(self):
        with self.db.cursor() as cur:
            cur.execute(
                "SELECT * FROM habits WHERE is_active=TRUE ORDER BY user_id, id",
            )
            return cur.fetchall()
