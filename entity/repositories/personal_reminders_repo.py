from entity.db import Database


class PersonalRemindersRepo:
    def __init__(self, db: Database):
        self.db = db

    def create(
        self,
        user_id: int,
        text: str,
        start_at_iso: str,
        remind_time: str,
    ) -> int:
        with self.db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO personal_reminders(user_id, text, start_at, remind_time, is_active)
                VALUES (%s,%s,%s,%s,TRUE)
                RETURNING id
                """,
                (user_id, text, start_at_iso, remind_time),
            )
            return int(cur.fetchone()["id"])

    def list_for_user(self, user_id: int):
        with self.db.cursor() as cur:
            cur.execute(
                "SELECT * FROM personal_reminders WHERE user_id=%s ORDER BY is_active DESC, id DESC",
                (user_id,),
            )
            return cur.fetchall()

    def get(self, reminder_id: int):
        with self.db.cursor() as cur:
            cur.execute("SELECT * FROM personal_reminders WHERE id=%s", (reminder_id,))
            return cur.fetchone()

    def update_text(self, reminder_id: int, user_id: int, text: str) -> int:
        with self.db.cursor() as cur:
            cur.execute(
                """
                UPDATE personal_reminders
                   SET text=%s, updated_at=NOW()
                 WHERE id=%s AND user_id=%s
                """,
                (text, reminder_id, user_id),
            )
            return cur.rowcount

    def update_datetime(self, reminder_id: int, user_id: int, start_at_iso: str, remind_time: str) -> int:
        with self.db.cursor() as cur:
            cur.execute(
                """
                UPDATE personal_reminders
                   SET start_at=%s, remind_time=%s, updated_at=NOW()
                 WHERE id=%s AND user_id=%s
                """,
                (start_at_iso, remind_time, reminder_id, user_id),
            )
            return cur.rowcount

    def delete(self, reminder_id: int, user_id: int) -> int:
        with self.db.cursor() as cur:
            cur.execute(
                "DELETE FROM personal_reminders WHERE id=%s AND user_id=%s",
                (reminder_id, user_id),
            )
            return cur.rowcount

    def list_active(self):
        with self.db.cursor() as cur:
            cur.execute(
                "SELECT * FROM personal_reminders WHERE is_active=TRUE ORDER BY user_id, id",
            )
            return cur.fetchall()
