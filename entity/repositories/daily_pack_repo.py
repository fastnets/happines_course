import json
from typing import Any, Dict, Optional

from entity.db import Database


class DailyPackRepo:
    """DB access for daily generated content packs.

    A 'set' is one pack per UTC date. There can be multiple sets per date;
    the latest READY set is considered active. When a new set is created and
    marked READY, older READY sets for the same date are marked SUPERSEDED.
    """

    def __init__(self, db: Database):
        self.db = db

    def create_set(self, *, utc_date: str, lesson_day_index: Optional[int], topic: str, trigger: str) -> int:
        with self.db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO daily_sets(utc_date, lesson_day_index, topic, trigger, status)
                VALUES (%s, %s, %s, %s, 'pending')
                RETURNING id
                """,
                (utc_date, lesson_day_index, topic, trigger),
            )
            return int(cur.fetchone()["id"])

    def mark_ready(self, *, set_id: int):
        with self.db.cursor() as cur:
            cur.execute("UPDATE daily_sets SET status='ready' WHERE id=%s", (set_id,))

    def mark_failed(self, *, set_id: int, error: str | None = None):
        # keep error in payload_json? We don't have a column; for now only status.
        with self.db.cursor() as cur:
            cur.execute("UPDATE daily_sets SET status='failed' WHERE id=%s", (set_id,))

    def supersede_other_ready(self, *, utc_date: str, keep_set_id: int):
        with self.db.cursor() as cur:
            cur.execute(
                """
                UPDATE daily_sets
                   SET status='superseded'
                 WHERE utc_date=%s AND status='ready' AND id<>%s
                """,
                (utc_date, keep_set_id),
            )

    def upsert_item(self, *, set_id: int, kind: str, title: str | None, content_text: str, payload: Dict[str, Any] | None = None):
        payload_json = json.dumps(payload or {}, ensure_ascii=False)
        with self.db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO daily_items(set_id, kind, title, content_text, payload_json)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                ON CONFLICT(set_id, kind) DO UPDATE
                  SET title=EXCLUDED.title,
                      content_text=EXCLUDED.content_text,
                      payload_json=EXCLUDED.payload_json
                RETURNING id
                """,
                (set_id, kind, title, content_text, payload_json),
            )
            return int(cur.fetchone()["id"])

    def get_active_set(self, *, utc_date: str):
        """Latest ready set for the date."""
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM daily_sets
                 WHERE utc_date=%s AND status='ready'
                 ORDER BY created_at DESC, id DESC
                 LIMIT 1
                """,
                (utc_date,),
            )
            return cur.fetchone()

    def get_items_for_set(self, *, set_id: int):
        with self.db.cursor() as cur:
            cur.execute("SELECT * FROM daily_items WHERE set_id=%s ORDER BY kind ASC", (set_id,))
            return cur.fetchall()

    def has_any_set_for_date(self, *, utc_date: str) -> bool:
        with self.db.cursor() as cur:
            cur.execute("SELECT 1 FROM daily_sets WHERE utc_date=%s LIMIT 1", (utc_date,))
            return cur.fetchone() is not None

    def update_item_payload(self, *, item_id: int, payload: dict) -> None:
        """Replace payload_json for a daily_items row."""
        with self.db.cursor() as cur:
            cur.execute(
                "UPDATE daily_items SET payload_json=%s WHERE id=%s",
                (json.dumps(payload), item_id),
            )

    def set_item_photo_file_id(self, *, item_id: int, photo_file_id: str) -> None:
        """Merge/assign photo_file_id into payload_json for a daily_items row."""
        with self.db.cursor() as cur:
            cur.execute("SELECT payload_json FROM daily_items WHERE id=%s", (item_id,))
            row = cur.fetchone()
            payload = row[0] if row and row[0] else {}
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    payload = {}
            payload = dict(payload)
            payload["photo_file_id"] = photo_file_id
            cur.execute(
                "UPDATE daily_items SET payload_json=%s WHERE id=%s",
                (json.dumps(payload), item_id),
            )