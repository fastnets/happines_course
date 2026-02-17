from entity.repositories.state_repo import StateRepo
from entity.repositories.progress_repo import ProgressRepo
from entity.repositories.points_repo import PointsRepo
from entity.repositories.answers_repo import AnswersRepo

class LearningService:
    def __init__(self, db, settings):
        self.state = StateRepo(db)
        self.progress = ProgressRepo(db)
        self.points = PointsRepo(db)
        self.answers = AnswersRepo(db)

    def mark_viewed_today(self, user_id: int, day_index: int):
        self.progress.mark_viewed(user_id, day_index)

    def submit_answer(self, user_id: int, day_index: int, points: int, answer_text: str):
        self.answers.save(user_id, day_index, answer_text)
        self.points.add_points(user_id, "quest", f"day:{day_index}", points)
        self.progress.mark_done(user_id, day_index)
        self.state.clear_state(user_id)

    def has_quest_answer(self, user_id: int, day_index: int) -> bool:
        return bool(getattr(self.answers, "exists_for_day", None) and self.answers.exists_for_day(user_id, day_index))

    def has_viewed_lesson(self, user_id: int, day_index: int) -> bool:
        # lesson viewed points are written with source_type='lesson_viewed' and source_key='day:<n>'
        return bool(getattr(self.points, "has_entry", None) and self.points.has_entry(user_id, "lesson_viewed", f"day:{day_index}"))
