import json
from entity.db import Database

class StateRepo:
    def __init__(self, db: Database):
        self.db = db

    def set_state(self, user_id: int, step: str, payload: dict | None = None):
        with self.db.cursor() as cur:
            cur.execute(
                '''
                INSERT INTO user_state(user_id, step, payload_json, updated_at)
                VALUES (%s, %s, %s::jsonb, NOW())
                ON CONFLICT(user_id) DO UPDATE
                  SET step=EXCLUDED.step,
                      payload_json=EXCLUDED.payload_json,
                      updated_at=NOW()
                ''',
                (user_id, step, json.dumps(payload or {})),
            )

    def clear_state(self, user_id: int):
        with self.db.cursor() as cur:
            cur.execute("DELETE FROM user_state WHERE user_id=%s", (user_id,))

    def get_state(self, user_id: int):
        with self.db.cursor() as cur:
            cur.execute("SELECT * FROM user_state WHERE user_id=%s", (user_id,))
            return cur.fetchone()
