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

    def seed_admins_from_settings(self):
        """Ensure that admins from env are present in DB.

        This makes development easier: you can keep ADMIN_TG_IDS in .env and
        still migrate towards DB-based access.
        """
        for uid in getattr(self.settings, "admin_tg_ids", []) or []:
            try:
                self.admins.add(int(uid))
            except Exception:
                # Don't crash startup due to a single bad id.
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
        if uid in ids:
            try:
                self.admins.add(uid)
            except Exception:
                # If insert fails (e.g., user not in `users` yet), treat as not admin.
                return False
            return True

        return False

    # Existing feature used by old inline admin panel
    def list_questionnaires(self, limit: int = 50):
        return self.q.list_latest(limit)
