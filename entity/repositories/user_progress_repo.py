from __future__ import annotations

from datetime import datetime, timezone

from entity.db import Database


class UserProgressRepo:
    def __init__(self, db: Database):
        self.db = db

    def delivery_counts(self, user_id: int) -> dict:
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT
                  COALESCE(SUM(CASE WHEN item_type='lesson' THEN 1 ELSE 0 END), 0) AS lessons_sent,
                  COALESCE(SUM(CASE WHEN item_type='quest' THEN 1 ELSE 0 END), 0) AS quests_sent
                FROM deliveries
                WHERE user_id=%s
                """,
                (user_id,),
            )
            return cur.fetchone() or {}

    def lesson_viewed_count(self, user_id: int) -> int:
        with self.db.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM points_ledger WHERE user_id=%s AND source_type='lesson_viewed'",
                (user_id,),
            )
            row = cur.fetchone() or {}
            return int(row.get("cnt") or 0)

    def quest_answered_count(self, user_id: int) -> int:
        with self.db.cursor() as cur:
            cur.execute(
                "SELECT COUNT(DISTINCT day_index) AS cnt FROM quest_answers WHERE user_id=%s",
                (user_id,),
            )
            row = cur.fetchone() or {}
            return int(row.get("cnt") or 0)

    def habit_done_skipped_counts(self, user_id: int) -> dict:
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT
                  COALESCE(SUM(CASE WHEN status='done' THEN 1 ELSE 0 END), 0) AS done,
                  COALESCE(SUM(CASE WHEN status='skipped' THEN 1 ELSE 0 END), 0) AS skipped
                FROM habit_occurrences
                WHERE user_id=%s
                """,
                (user_id,),
            )
            return cur.fetchone() or {}

    def done_timestamps(self, user_id: int) -> list[datetime]:
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT done_at
                FROM progress
                WHERE user_id=%s AND status='done' AND done_at IS NOT NULL
                ORDER BY done_at DESC
                """,
                (user_id,),
            )
            rows = cur.fetchall() or []
            out: list[datetime] = []
            for row in rows:
                dt = row.get("done_at")
                if not dt:
                    continue
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                out.append(dt)
            return out

    def questionnaire_count(self, user_id: int) -> int:
        with self.db.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM questionnaire_responses WHERE user_id=%s",
                (user_id,),
            )
            row = cur.fetchone() or {}
            return int(row.get("cnt") or 0)

    def points_events_since(self, user_id: int, since_utc: datetime) -> list[dict]:
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT created_at, points
                FROM points_ledger
                WHERE user_id=%s AND created_at >= %s
                ORDER BY created_at ASC
                """,
                (user_id, since_utc),
            )
            return cur.fetchall() or []

    def done_events_since(self, user_id: int, since_utc: datetime) -> list[dict]:
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT done_at
                FROM progress
                WHERE user_id=%s AND status='done' AND done_at IS NOT NULL AND done_at >= %s
                ORDER BY done_at ASC
                """,
                (user_id, since_utc),
            )
            return cur.fetchall() or []

    def questionnaire_events_since(self, user_id: int, since_utc: datetime) -> list[dict]:
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT created_at, score
                FROM questionnaire_responses
                WHERE user_id=%s AND created_at >= %s
                ORDER BY created_at ASC
                """,
                (user_id, since_utc),
            )
            return cur.fetchall() or []

