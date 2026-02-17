from entity.repositories.users_repo import UsersRepo
from entity.repositories.state_repo import StateRepo
from entity.repositories.enrollment_repo import EnrollmentRepo

class UserService:
    def __init__(self, db, settings):
        self.settings = settings
        self.users = UsersRepo(db)
        self.state = StateRepo(db)
        self.enroll = EnrollmentRepo(db)

    def ensure_user(self, tg_id: int, username: str | None, display_name: str | None):
        # IMPORTANT:
        # We do NOT auto-fill timezone with default_timezone on first contact.
        # Onboarding must explicitly ask the user to confirm/select timezone.
        # This prevents the classic bug where everyone silently gets Europe/Moscow.
        self.users.upsert_user(tg_id, username, display_name, None)

    def set_step(self, user_id: int, step: str | None, payload: dict | None = None):
        if step is None:
            self.state.clear_state(user_id)
        else:
            self.state.set_state(user_id, step, payload or {})

    def get_step(self, user_id: int):
        return self.state.get_state(user_id)

    def update_display_name(self, user_id: int, name: str):
        self.users.update_display_name(user_id, name)

    def enroll_user(self, user_id: int, delivery_time: str):
        self.enroll.upsert(user_id, delivery_time)

    def update_delivery_time(self, user_id: int, delivery_time: str):
        self.enroll.upsert(user_id, delivery_time)

    def has_pd_consent(self, user_id: int) -> bool:
        u = self.users.get_user(user_id)
        return bool(u and u.get("pd_consent"))

    def set_pd_consent(self, user_id: int, consent: bool):
        self.users.set_pd_consent(user_id, consent)

    def get_timezone(self, user_id: int) -> str | None:
        u = self.users.get_user(user_id)
        if not u:
            return None
        return u.get("timezone")

    def set_timezone(self, user_id: int, tz_name: str):
        self.users.set_timezone(user_id, tz_name)
