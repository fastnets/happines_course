from entity.repositories.users_repo import UsersRepo
from entity.repositories.points_repo import PointsRepo
from entity.repositories.enrollment_repo import EnrollmentRepo
from entity.repositories.progress_repo import ProgressRepo

class AnalyticsService:
    def __init__(self, db, settings):
        self.users = UsersRepo(db)
        self.points = PointsRepo(db)
        self.enroll = EnrollmentRepo(db)
        self.progress = ProgressRepo(db)

    def profile(self, user_id: int):
        u = self.users.get_user(user_id)
        e = self.enroll.get(user_id)
        return {
            "display_name": (u.get("display_name") if u else None) or "Без имени",
            "enrolled": bool(e),
            "delivery_time": (e.get("delivery_time") if e else None),
            "points": self.points.total_points(user_id),
            "done_days": self.progress.count_done(user_id),
        }
