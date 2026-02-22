from __future__ import annotations

from entity.repositories.admins_repo import AdminsRepo
from entity.repositories.questionnaire_repo import QuestionnaireRepo


class AdminService:
    """Admin operations.

    Admin access is stored in the DB (`admins` table). `settings.admin_tg_ids`
    is used only to seed the table on first run.
    """

    def __init__(self, db, settings):
        self.db = db
        self.settings = settings

        self.admins = AdminsRepo(db)
        self.q = QuestionnaireRepo(db)

    def _configured_owner_uid(self) -> int | None:
        try:
            val = getattr(self.settings, "owner_tg_id", None)
            if val is None:
                return None
            uid = int(val)
            return uid if uid > 0 else None
        except Exception:
            return None

    def seed_admins_from_settings(self):
        """Ensure that admins from env are present in DB.

        This makes development easier: you can keep ADMIN_TG_IDS in .env and
        still migrate towards DB-based access.
        """
        env_ids = list(getattr(self.settings, "admin_tg_ids", []) or [])
        owner_uid = self._configured_owner_uid()
        if owner_uid and owner_uid not in env_ids:
            env_ids.insert(0, owner_uid)
        for uid in env_ids:
            try:
                self.admins.add(int(uid))
            except Exception:
                # Don't crash startup due to a single bad id.
                pass
        if owner_uid:
            try:
                self.admins.upsert(owner_uid, role="owner")
            except Exception:
                pass
        self._ensure_owner_exists(preferred_uid=owner_uid or (int(env_ids[0]) if env_ids else None))

    def _ensure_owner_exists(self, preferred_uid: int | None = None):
        try:
            if int(self.admins.count_owners() or 0) > 0:
                return
        except Exception:
            return

        candidate: int | None = None
        if preferred_uid and self.admins.is_admin(int(preferred_uid)):
            candidate = int(preferred_uid)
        else:
            ids = self.admins.list_user_ids() or []
            if ids:
                candidate = int(ids[0])
        if candidate:
            try:
                self.admins.upsert(candidate, role="owner")
            except Exception:
                pass

    def is_admin(self, user_id: int) -> bool:
        """Check admin access.

        Source of truth is the DB table `admins`.

        Bootstrap behavior:
        - If a user_id is listed in settings.ADMIN_TG_IDS, we *lazily* add it to
          the DB on first check. This solves the common FK issue when seeding on
          startup (admins references users), because by the time we check admin
          status the user has already done /start and exists in `users`.
        """
        uid = int(user_id)

        # Fast path: already stored in DB.
        if self.admins.is_admin(uid):
            return True

        # Lazy seed: if uid is configured as admin in env, persist it in DB.
        ids = getattr(self.settings, "admin_tg_ids", []) or []
        owner_uid = self._configured_owner_uid()
        if owner_uid and uid == owner_uid:
            try:
                self.admins.upsert(uid, role="owner")
                self._ensure_owner_exists(preferred_uid=uid)
            except Exception:
                return False
            return True

        if uid in ids:
            try:
                self.admins.add(uid)
                self._ensure_owner_exists(preferred_uid=owner_uid or uid)
            except Exception:
                # If insert fails (e.g., user not in `users` yet), treat as not admin.
                return False
            return True

        return False

    def is_owner(self, user_id: int) -> bool:
        uid = int(user_id)
        if not self.is_admin(uid):
            return False
        self._ensure_owner_exists(preferred_uid=uid)
        return bool(self.admins.is_owner(uid))

    def list_admins(self) -> list[dict]:
        self._ensure_owner_exists()
        rows = self.admins.list_admins() or []
        out: list[dict] = []
        for row in rows:
            out.append(
                {
                    "user_id": int(row.get("user_id") or 0),
                    "role": str(row.get("role") or "admin"),
                    "created_at": row.get("created_at"),
                }
            )
        return out

    def grant_admin(self, actor_id: int, target_user_id: int) -> tuple[bool, str]:
        actor = int(actor_id)
        target = int(target_user_id)
        if target <= 0:
            return False, "Некорректный user_id."
        if not self.is_owner(actor):
            return False, "Только owner может управлять админами."
        if self.admins.is_owner(target):
            return False, "Пользователь уже owner. Сменить роль можно через распределение ролей."
        try:
            self.admins.upsert(target, role="admin")
        except Exception:
            return False, "Не удалось выдать роль admin. Убедись, что пользователь уже запускал бота."
        return True, f"user_id={target} теперь admin."

    def grant_owner(self, actor_id: int, target_user_id: int) -> tuple[bool, str]:
        actor = int(actor_id)
        target = int(target_user_id)
        if target <= 0:
            return False, "Некорректный user_id."
        if not self.is_owner(actor):
            return False, "Только owner может назначать owner."
        try:
            self.admins.upsert(target, role="owner")
        except Exception:
            return False, "Не удалось выдать роль owner. Убедись, что пользователь уже запускал бота."
        return True, f"user_id={target} теперь owner."

    def demote_owner_to_admin(self, actor_id: int, target_user_id: int) -> tuple[bool, str]:
        actor = int(actor_id)
        target = int(target_user_id)
        if target <= 0:
            return False, "Некорректный user_id."
        if not self.is_owner(actor):
            return False, "Только owner может менять роль owner."
        if not self.admins.is_admin(target):
            return False, "Пользователь не является админом."
        if self.admins.is_owner(target) and int(self.admins.count_owners() or 0) <= 1:
            return False, "Нельзя снять роль у последнего owner."
        try:
            self.admins.upsert(target, role="admin")
        except Exception:
            return False, "Не удалось изменить роль."
        return True, f"user_id={target} теперь admin."

    def remove_admin(self, actor_id: int, target_user_id: int) -> tuple[bool, str]:
        actor = int(actor_id)
        target = int(target_user_id)
        if target <= 0:
            return False, "Некорректный user_id."
        if not self.is_owner(actor):
            return False, "Только owner может удалять админов."
        if not self.admins.is_admin(target):
            return False, "Пользователь не является админом."
        if self.admins.is_owner(target) and int(self.admins.count_owners() or 0) <= 1:
            return False, "Нельзя удалить последнего owner."
        try:
            self.admins.remove(target)
        except Exception:
            return False, "Не удалось удалить админа."
        return True, f"user_id={target} удалён из админов."

    def set_role(self, actor_id: int, target_user_id: int, role: str) -> tuple[bool, str]:
        role_s = (role or "").strip().lower()
        if role_s == "owner":
            return self.grant_owner(actor_id, target_user_id)
        if role_s == "admin":
            target = int(target_user_id)
            if self.admins.is_owner(target):
                return self.demote_owner_to_admin(actor_id, target)
            return self.grant_admin(actor_id, target)
        return False, "Допустимые роли: owner, admin."

    # Existing feature used by old inline admin panel
    def list_questionnaires(self, limit: int = 50):
        return self.q.list_latest(limit)
