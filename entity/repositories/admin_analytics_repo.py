from __future__ import annotations

from datetime import datetime, timedelta, timezone

from entity.db import Database


class AdminAnalyticsRepo:
    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def _cutoff(days: int) -> datetime:
        d = max(1, int(days or 7))
        return datetime.now(timezone.utc) - timedelta(days=d)

    def summary(self, days: int) -> dict:
        cutoff = self._cutoff(days)
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT
                  (SELECT COUNT(*) FROM users) AS users_total,
                  (SELECT COUNT(*) FROM users WHERE pd_consent=TRUE) AS consent_total,
                  (SELECT COUNT(*) FROM users WHERE COALESCE(timezone,'') <> '') AS timezone_total,
                  (SELECT COUNT(*) FROM enrollments WHERE is_active=TRUE) AS enrolled_total
                """
            )
            base = cur.fetchone() or {}

            cur.execute(
                """
                SELECT COUNT(DISTINCT user_id) AS active_users
                FROM (
                  SELECT user_id FROM points_ledger WHERE created_at >= %s
                  UNION
                  SELECT user_id FROM quest_answers WHERE created_at >= %s
                  UNION
                  SELECT user_id FROM questionnaire_responses WHERE created_at >= %s
                  UNION
                  SELECT user_id FROM habit_occurrences WHERE COALESCE(action_at, scheduled_at) >= %s
                ) t
                """,
                (cutoff, cutoff, cutoff, cutoff),
            )
            act = cur.fetchone() or {}

            cur.execute(
                """
                SELECT COALESCE(AVG(total_points),0) AS avg_points
                FROM (
                  SELECT u.id AS user_id, COALESCE(SUM(pl.points),0) AS total_points
                  FROM users u
                  LEFT JOIN points_ledger pl ON pl.user_id=u.id
                  GROUP BY u.id
                ) s
                """
            )
            avg_row = cur.fetchone() or {}

        out = dict(base)
        out["active_users"] = int(act.get("active_users") or 0)
        out["avg_points"] = float(avg_row.get("avg_points") or 0.0)
        return out

    def funnel(self, days: int) -> dict:
        cutoff = self._cutoff(days)
        with self.db.cursor() as cur:
            cur.execute(
                """
                WITH cohort AS (
                  SELECT id FROM users WHERE created_at >= %s
                )
                SELECT
                  (SELECT COUNT(*) FROM cohort) AS users_total,
                  (SELECT COUNT(*) FROM cohort c JOIN users u ON u.id=c.id WHERE u.pd_consent=TRUE) AS consent_total,
                  (SELECT COUNT(*) FROM cohort c JOIN users u ON u.id=c.id WHERE COALESCE(u.timezone,'') <> '') AS timezone_total,
                  (SELECT COUNT(*) FROM cohort c WHERE EXISTS (
                     SELECT 1 FROM enrollments e WHERE e.user_id=c.id AND e.is_active=TRUE
                   )) AS enrolled_total,
                  (SELECT COUNT(*) FROM cohort c WHERE EXISTS (
                     SELECT 1 FROM progress p WHERE p.user_id=c.id AND p.day_index=1 AND p.status='done'
                   )) AS day1_done_total
                """,
                (cutoff,),
            )
            return cur.fetchone() or {}

    def delivery(self, days: int) -> dict:
        cutoff = self._cutoff(days)
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT
                  COALESCE(SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END),0) AS pending,
                  COALESCE(SUM(CASE WHEN status='sent' THEN 1 ELSE 0 END),0) AS sent,
                  COALESCE(SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END),0) AS failed,
                  COALESCE(SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END),0) AS cancelled
                FROM outbox_jobs
                WHERE created_at >= %s
                """,
                (cutoff,),
            )
            status_row = cur.fetchone() or {}

            cur.execute(
                """
                SELECT
                  payload_json->>'kind' AS kind,
                  COUNT(*) AS total,
                  COALESCE(SUM(CASE WHEN status='sent' THEN 1 ELSE 0 END),0) AS sent,
                  COALESCE(SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END),0) AS failed,
                  COALESCE(SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END),0) AS pending,
                  COALESCE(SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END),0) AS cancelled
                FROM outbox_jobs
                WHERE created_at >= %s
                GROUP BY payload_json->>'kind'
                ORDER BY total DESC, kind ASC
                LIMIT 12
                """,
                (cutoff,),
            )
            kinds = cur.fetchall() or []

        return {"status": status_row, "kinds": kinds}

    def content(self, days: int) -> dict:
        cutoff = self._cutoff(days)
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT
                  day_index,
                  COALESCE(SUM(CASE WHEN item_type='lesson' THEN 1 ELSE 0 END),0) AS lesson_sent,
                  COALESCE(SUM(CASE WHEN item_type='quest' THEN 1 ELSE 0 END),0) AS quest_sent
                FROM deliveries
                WHERE sent_at >= %s
                GROUP BY day_index
                ORDER BY day_index ASC
                """,
                (cutoff,),
            )
            sent_rows = cur.fetchall() or []

            cur.execute(
                """
                SELECT source_key, COUNT(*) AS viewed
                FROM points_ledger
                WHERE source_type='lesson_viewed' AND created_at >= %s
                GROUP BY source_key
                """,
                (cutoff,),
            )
            lesson_rows = cur.fetchall() or []

            cur.execute(
                """
                SELECT day_index, COUNT(*) AS answered
                FROM quest_answers
                WHERE created_at >= %s
                GROUP BY day_index
                """,
                (cutoff,),
            )
            quest_rows = cur.fetchall() or []

        return {
            "sent_rows": sent_rows,
            "lesson_rows": lesson_rows,
            "quest_rows": quest_rows,
        }

    def questionnaires(self, days: int) -> dict:
        cutoff = self._cutoff(days)
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT
                  COUNT(*) AS responses_total,
                  COUNT(DISTINCT user_id) AS users_total,
                  COALESCE(AVG(score),0) AS avg_score
                FROM questionnaire_responses
                WHERE created_at >= %s
                """,
                (cutoff,),
            )
            summary = cur.fetchone() or {}

            cur.execute(
                """
                SELECT
                  q.id,
                  q.question,
                  COUNT(r.id) AS responses,
                  COALESCE(AVG(r.score),0) AS avg_score
                FROM questionnaires q
                LEFT JOIN questionnaire_responses r
                  ON r.questionnaire_id=q.id
                 AND r.created_at >= %s
                GROUP BY q.id, q.question
                ORDER BY responses DESC, q.id DESC
                LIMIT 10
                """,
                (cutoff,),
            )
            top_rows = cur.fetchall() or []

        return {"summary": summary, "top_rows": top_rows}

    def reminders(self, days: int) -> dict:
        cutoff = self._cutoff(days)
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT
                  (SELECT COUNT(*) FROM personal_reminders WHERE created_at >= %s) AS personal_created,
                  (SELECT COUNT(*) FROM outbox_jobs WHERE created_at >= %s AND payload_json->>'kind'='personal_reminder' AND status='sent') AS personal_sent,
                  (SELECT COUNT(*) FROM outbox_jobs WHERE created_at >= %s AND payload_json->>'kind'='personal_reminder' AND status='pending') AS personal_pending,
                  (SELECT COUNT(*) FROM outbox_jobs WHERE created_at >= %s AND payload_json->>'kind'='personal_reminder' AND status='cancelled') AS personal_cancelled,
                  (SELECT COUNT(*) FROM habits WHERE created_at >= %s) AS habits_created,
                  (SELECT COUNT(*) FROM outbox_jobs WHERE created_at >= %s AND payload_json->>'kind'='habit_reminder' AND status='sent') AS habit_sent,
                  (SELECT COUNT(*) FROM habit_occurrences WHERE action_at >= %s AND status='done') AS habit_done,
                  (SELECT COUNT(*) FROM habit_occurrences WHERE action_at >= %s AND status='skipped') AS habit_skipped,
                  (SELECT COUNT(*) FROM outbox_jobs WHERE created_at >= %s AND payload_json->>'kind'='daily_reminder' AND status='sent') AS daily_sent
                """,
                (
                    cutoff,
                    cutoff,
                    cutoff,
                    cutoff,
                    cutoff,
                    cutoff,
                    cutoff,
                    cutoff,
                    cutoff,
                ),
            )
            return cur.fetchone() or {}
