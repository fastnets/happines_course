from entity.db import Database


class AdminsRepo:
    """Repository for bot admins.

    An admin is a user_id present in the `admins` table.
    """

    def __init__(self, db: Database):
        self.db = db

    def is_admin(self, user_id: int) -> bool:
        with self.db.cursor() as cur:
            cur.execute("SELECT 1 FROM admins WHERE user_id=%s", (user_id,))
            return cur.fetchone() is not None

    def add(self, user_id: int):
        with self.db.cursor() as cur:
            cur.execute(
                "INSERT INTO admins(user_id) VALUES(%s) ON CONFLICT(user_id) DO NOTHING",
                (user_id,),
            )

    def upsert(self, user_id: int, role: str = "admin"):
        safe_role = "owner" if str(role).strip().lower() == "owner" else "admin"
        with self.db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO admins(user_id, role)
                VALUES(%s, %s)
                ON CONFLICT(user_id) DO UPDATE SET role = EXCLUDED.role
                """,
                (user_id, safe_role),
            )

    def remove(self, user_id: int):
        with self.db.cursor() as cur:
            cur.execute("DELETE FROM admins WHERE user_id=%s", (user_id,))

    def is_owner(self, user_id: int) -> bool:
        with self.db.cursor() as cur:
            cur.execute("SELECT 1 FROM admins WHERE user_id=%s AND role='owner'", (user_id,))
            return cur.fetchone() is not None

    def count_owners(self) -> int:
        with self.db.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM admins WHERE role='owner'")
            row = cur.fetchone() or {}
            return int(row.get("cnt") or 0)

    def list_admins(self) -> list[dict]:
        with self.db.cursor() as cur:
            cur.execute("SELECT user_id, role, created_at FROM admins ORDER BY created_at DESC")
            return cur.fetchall() or []

    def list_user_ids(self) -> list[int]:
        with self.db.cursor() as cur:
            cur.execute("SELECT user_id FROM admins ORDER BY created_at DESC")
            rows = cur.fetchall() or []
            return [int(r["user_id"]) for r in rows]
