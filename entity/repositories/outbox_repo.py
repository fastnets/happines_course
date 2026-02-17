import json
from entity.db import Database

class OutboxRepo:
    def __init__(self, db: Database):
        self.db = db

    def create_job(self, user_id: int, run_at_iso: str, payload: dict):
        with self.db.cursor() as cur:
            cur.execute(
                "INSERT INTO outbox_jobs(user_id, run_at, payload_json, status) VALUES (%s,%s,%s::jsonb,'pending')",
                (user_id, run_at_iso, json.dumps(payload)),
            )

    def fetch_due_pending(self, limit: int = 50):
        with self.db.cursor() as cur:
            cur.execute(
                "SELECT * FROM outbox_jobs WHERE status='pending' AND run_at<=NOW() ORDER BY run_at ASC LIMIT %s",
                (limit,),
            )
            return cur.fetchall()

    def exists_job_for(self, user_id: int, key: str):
        with self.db.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM outbox_jobs WHERE user_id=%s AND payload_json->>'job_key'=%s AND status IN ('pending','sent') LIMIT 1",
                (user_id, key),
            )
            return cur.fetchone() is not None

    def mark_sent(self, job_id: int):
        with self.db.cursor() as cur:
            cur.execute("UPDATE outbox_jobs SET status='sent' WHERE id=%s", (job_id,))

    def mark_failed(self, job_id: int, err: str):
        with self.db.cursor() as cur:
            cur.execute(
                "UPDATE outbox_jobs SET status='failed', attempts=attempts+1, last_error=%s WHERE id=%s",
                (err[:1000], job_id),
            )

    def cancel_future_jobs(self, user_id: int, kinds: list[str], from_utc_iso: str):
        """Cancel future pending jobs for the user.

        We keep rows for debugging/statistics but prevent delivery.
        """

        if not kinds:
            return 0
        with self.db.cursor() as cur:
            cur.execute(
                """
                UPDATE outbox_jobs
                   SET status='cancelled'
                 WHERE user_id=%s
                   AND status='pending'
                   AND run_at >= %s
                   AND (payload_json->>'kind') = ANY(%s)
                """,
                (user_id, from_utc_iso, kinds),
            )
            return cur.rowcount

    def cancel_future_habit_jobs(self, habit_id: int, from_utc_iso: str) -> int:
        """Cancel future pending habit_reminder jobs for a specific habit."""

        with self.db.cursor() as cur:
            cur.execute(
                """
                UPDATE outbox_jobs
                   SET status='cancelled'
                 WHERE status='pending'
                   AND run_at >= %s
                   AND payload_json->>'kind'='habit_reminder'
                   AND (payload_json->>'habit_id')::int = %s
                """,
                (from_utc_iso, habit_id),
            )
            return cur.rowcount
