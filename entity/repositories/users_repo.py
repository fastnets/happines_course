from entity.db import Database

class UsersRepo:
    def __init__(self, db: Database):
        self.db = db

    def upsert_user(self, tg_id: int, username: str | None, display_name: str | None, timezone: str | None):
        with self.db.cursor() as cur:
            cur.execute(
                '''
                INSERT INTO users(id, username, display_name, timezone)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE
                  SET username = EXCLUDED.username,
                      -- Preserve a user-customized name: once display_name exists in DB,
                      -- don't overwrite it on each ensure_user(...) call.
                      display_name = COALESCE(users.display_name, EXCLUDED.display_name),
                      timezone = COALESCE(EXCLUDED.timezone, users.timezone)
                ''',
                (tg_id, username, display_name, timezone),
            )

    def get_user(self, tg_id: int):
        with self.db.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE id=%s", (tg_id,))
            return cur.fetchone()

    def get_timezone(self, tg_id: int) -> str | None:
        with self.db.cursor() as cur:
            cur.execute("SELECT timezone FROM users WHERE id=%s", (tg_id,))
            row = cur.fetchone()
            if not row:
                return None
            # psycopg2 returns dict rows in our DB wrapper
            return row.get("timezone")

    def set_timezone(self, tg_id: int, tz: str):
        with self.db.cursor() as cur:
            cur.execute("UPDATE users SET timezone=%s WHERE id=%s", (tz, tg_id))

    def update_display_name(self, tg_id: int, display_name: str):
        with self.db.cursor() as cur:
            cur.execute("UPDATE users SET display_name=%s WHERE id=%s", (display_name, tg_id))

    def set_pd_consent(self, tg_id: int, consent: bool):
        with self.db.cursor() as cur:
            if consent:
                cur.execute(
                    "UPDATE users SET pd_consent=TRUE, pd_consent_at=NOW() WHERE id=%s",
                    (tg_id,),
                )
            else:
                cur.execute(
                    "UPDATE users SET pd_consent=FALSE, pd_consent_at=NULL WHERE id=%s",
                    (tg_id,),
                )

    def list_user_ids(self, limit: int = 20000):
        with self.db.cursor() as cur:
            cur.execute("SELECT id FROM users ORDER BY created_at DESC LIMIT %s", (limit,))
            return [int(r['id']) for r in cur.fetchall()]
