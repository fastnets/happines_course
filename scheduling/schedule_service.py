from __future__ import annotations

import logging
from datetime import datetime, time, timezone, timedelta, date
from zoneinfo import ZoneInfo

from entity.repositories.enrollment_repo import EnrollmentRepo
from entity.repositories.lesson_repo import LessonRepo
from entity.repositories.quest_repo import QuestRepo
from entity.repositories.outbox_repo import OutboxRepo
from entity.repositories.users_repo import UsersRepo
from entity.repositories.progress_repo import ProgressRepo
from entity.repositories.deliveries_repo import DeliveriesRepo
from entity.repositories.sent_jobs_repo import SentJobsRepo
from entity.repositories.questionnaire_repo import QuestionnaireRepo

log = logging.getLogger("schedule")


class ScheduleService:
    """Responsible for planning deliveries into outbox_jobs.

    Notes:
    - All calculations are done in the user's IANA timezone.
    - Idempotency is ensured by outbox job_key + sent_jobs guard.
    """

    def __init__(self, db, settings):
        self.settings = settings
        self.enroll = EnrollmentRepo(db)
        self.lesson = LessonRepo(db)
        self.quest = QuestRepo(db)
        self.outbox = OutboxRepo(db)
        self.users = UsersRepo(db)
        self.progress = ProgressRepo(db)
        self.deliveries = DeliveriesRepo(db)
        self.sent_jobs = SentJobsRepo(db)
        self.questionnaires = QuestionnaireRepo(db)

    # ----------------------------
    # Helpers
    # ----------------------------
    @staticmethod
    def _job_key(day_index: int, lesson_id: int | None, quest_id: int | None, content_version: int) -> str:
        """Stable idempotency key for a (user, day, content-version, specific lesson/quest)."""

        l_part = f"l{lesson_id}" if lesson_id else "l0"
        q_part = f"q{quest_id}" if quest_id else "q0"
        return f"day:{day_index}:{l_part}:q:{q_part}:v:{content_version}"

    def _user_tz(self, user_id: int) -> ZoneInfo:
        tz_name = self.users.get_timezone(user_id) or self.settings.default_timezone
        try:
            return ZoneInfo(tz_name)
        except Exception:
            return ZoneInfo(self.settings.default_timezone)

    @staticmethod
    def _parse_hhmm(v: str, default: str = "09:30") -> time:
        s = (v or "").strip() or default
        try:
            hh, mm = [int(x) for x in s.split(":")]
            hh = max(0, min(23, hh))
            mm = max(0, min(59, mm))
            return time(hh, mm)
        except Exception:
            hh, mm = [int(x) for x in default.split(":")]
            return time(hh, mm)

    def _compute_run_at_utc(self, user_tz: ZoneInfo, for_date: date, delivery_time_hhmm: str) -> tuple[datetime, str]:
        """Return (run_at_utc, local_target_string).

        local_target_string is useful for logs/debugging.
        """

        t = self._parse_hhmm(delivery_time_hhmm or "21:00", "21:00")
        local_target = datetime.combine(for_date, t, tzinfo=user_tz)
        run_at_utc = local_target.astimezone(timezone.utc)
        local_str = f"{for_date.isoformat()} {t.strftime('%H:%M')} {user_tz.key}"
        return run_at_utc, local_str

    def _day_index_for_local_date(self, user_id: int, local_date: date) -> int:
        """1-based day index based on user's local enrollment date."""

        e = self.enroll.get(user_id)
        if not e:
            return 1
        tz = self._user_tz(user_id)
        enrolled_local_date = e["enrolled_at"].astimezone(tz).date()
        delta = (local_date - enrolled_local_date).days
        return max(1, delta + 1)

    # Backward-compatible public names used elsewhere in the project
    def day_index_for_local_date(self, user_id: int, local_date: date) -> int:
        return self._day_index_for_local_date(user_id, local_date)

    def compute_run_at_utc(self, user_tz: ZoneInfo, for_date: date, delivery_time_hhmm: str) -> datetime:
        run_at_utc, _ = self._compute_run_at_utc(user_tz, for_date, delivery_time_hhmm)
        return run_at_utc

    def _log_job(
        self,
        user_id: int,
        kind: str,
        job_key: str,
        user_tz: ZoneInfo,
        for_date: date,
        delivery_hhmm: str,
        run_at_utc: datetime,
    ):
        _, local_target_str = self._compute_run_at_utc(user_tz, for_date, delivery_hhmm)
        log.info(
            "plan job user_id=%s kind=%s job_key=%s for_date=%s tz=%s local_target=%s utc_run_at=%s",
            user_id,
            kind,
            job_key,
            for_date.isoformat(),
            user_tz.key,
            local_target_str,
            run_at_utc.isoformat(),
        )

    def reschedule_user(self, user_id: int) -> int:
        """Cancel future pending jobs for the user and schedule again (today+tomorrow)."""

        now_utc = datetime.now(timezone.utc)
        # Cancel only daily pipeline kinds.
        cancelled = self.outbox.cancel_future_jobs(
            user_id,
            kinds=["day_lesson", "day_quest", "daily_reminder"],
            from_utc_iso=now_utc.isoformat(),
        )
        # Regular questionnaires use kind=questionnaire_broadcast as well,
        # so cancel only job_key that belongs to day planning.
        cancelled += self.outbox.cancel_future_day_questionnaire_jobs(
            user_id=user_id,
            from_utc_iso=now_utc.isoformat(),
        )
        created = self._schedule_for_user(user_id, now_utc)
        log.info("reschedule user_id=%s cancelled=%s created=%s", user_id, cancelled, created)
        return created

    def _is_quiet_time(self, t_local: time) -> bool:
        start_t = self._parse_hhmm(getattr(self.settings, "quiet_hours_start", "22:00"), "22:00")
        end_t = self._parse_hhmm(getattr(self.settings, "quiet_hours_end", "09:00"), "09:00")
        # Quiet window may cross midnight (e.g. 22:00–09:00)
        if start_t < end_t:
            return start_t <= t_local < end_t
        return (t_local >= start_t) or (t_local < end_t)

    def _compute_daily_reminder_run_local(self, delivery_local_dt: datetime, tz: ZoneInfo) -> datetime:
        after_h = int(getattr(self.settings, "remind_after_hours", 12) or 12)
        fallback_t = self._parse_hhmm(getattr(self.settings, "reminder_fallback_time", "09:30"), "09:30")

        candidate = delivery_local_dt + timedelta(hours=after_h)
        if not self._is_quiet_time(candidate.timetz().replace(tzinfo=None)):
            return candidate

        # If candidate is in quiet hours, move to fallback time (usually morning).
        fallback = datetime.combine(candidate.date(), fallback_t, tzinfo=tz)
        # If fallback is not after candidate (e.g. candidate 23:00 same day), push to next day.
        if fallback <= candidate:
            fallback = fallback + timedelta(days=1)
        return fallback

    def _row_version_ts(self, row) -> int:
        """Return an integer content version for a DB row (updated_at fallback created_at)."""

        if not row:
            return 0
        dt = row.get("updated_at") or row.get("created_at")
        if dt is None:
            return 0
        try:
            if isinstance(dt, str):
                dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            return int(dt.timestamp())
        except Exception:
            return 0

    @staticmethod
    def questionnaire_content_type(questionnaire_id: int) -> str:
        return f"questionnaire:{int(questionnaire_id)}"

    # ----------------------------
    # Public API
    # ----------------------------
    def current_day_index(self, user_id: int, now_user: datetime | None = None) -> int:
        """1-based day index based on user's local dates."""

        e = self.enroll.get(user_id)
        if not e:
            return 1
        tz = self._user_tz(user_id)
        enrolled_local = e["enrolled_at"].astimezone(tz)
        now_local = (now_user or datetime.now(tz)).astimezone(tz)
        days = (now_local.date() - enrolled_local.date()).days
        return max(1, days + 1)

    def make_viewed_cb(self, day_index: int, points: int) -> str:
        return f"lesson:viewed:day={day_index}:p={points}"

    def parse_viewed_payload(self, data: str):
        if not data.startswith("lesson:viewed:"):
            return None
        try:
            parts = data.split(":")
            day = int(parts[2].split("=")[1])
            pts = int(parts[3].split("=")[1])
            return {"day_index": day, "points": pts}
        except Exception:
            return None

    def schedule_due_jobs(self) -> int:
        """Plan deliveries into outbox_jobs.

        v1.1 behavior:
        - Schedule jobs at exact run_at (UTC) derived from user's timezone + delivery_time.
        - Plan for today and tomorrow (lookahead) to avoid late deliveries.
        - Keep the existing grace window: if user is far past delivery time, we don't auto-send lesson/quest.
        """

        created = 0
        now_utc = datetime.now(timezone.utc)

        for e in self.enroll.list_active():
            user_id = int(e["user_id"])
            created += self._schedule_for_user(user_id, now_utc, enrollment_row=e)

        return created

    def _schedule_for_user(self, user_id: int, now_utc: datetime, enrollment_row=None) -> int:
        created = 0
        e = enrollment_row or self.enroll.get(user_id)
        if not e:
            return 0

        user_tz = self._user_tz(user_id)
        now_user = now_utc.astimezone(user_tz)
        delivery_hhmm = e.get("delivery_time") or "21:00"
        grace_min = int(getattr(self.settings, "delivery_grace_minutes", 15) or 15)

        # Plan for today and tomorrow.
        for offset_days in (0, 1):
            for_date = (now_user.date() + timedelta(days=offset_days))
            day_index = self.day_index_for_local_date(user_id, for_date)
            run_at_utc = self.compute_run_at_utc(user_tz, for_date, delivery_hhmm)
            delivery_local = run_at_utc.astimezone(user_tz)

            lesson = self.lesson.get_by_day(day_index)
            q = self.quest.get_by_day(day_index)
            day_questionnaires = self.questionnaires.list_by_day(day_index, qtypes=("manual", "daily"))

            if not lesson and not q and not day_questionnaires:
                continue

            # Auto-delivery guardrail for lessons/quests: if we're too late for today's window, skip.
            too_late = (now_user > (delivery_local + timedelta(minutes=grace_min)))
            can_autosend = (not too_late) or (offset_days == 1)

            if can_autosend:
                # Lesson
                if lesson and not self.sent_jobs.was_sent(user_id, "lesson", day_index, for_date):
                    lesson_id = int(lesson["id"])
                    l_ver = self._row_version_ts(lesson)
                    lesson_key = self._job_key(day_index, lesson_id, None, l_ver)
                    if not self.outbox.exists_job_for(user_id, lesson_key):
                        payload = {
                            "kind": "day_lesson",
                            "job_key": lesson_key,
                            "day_index": day_index,
                            "for_date": for_date.isoformat(),
                            "lesson": {
                                "title": lesson["title"],
                                "description": lesson["description"],
                                "video_url": lesson["video_url"],
                                "points_viewed": int(lesson["points_viewed"]),
                            },
                        }
                        self._log_job(user_id, "day_lesson", lesson_key, user_tz, for_date, delivery_hhmm, run_at_utc)
                        self.outbox.create_job(user_id, run_at_utc.isoformat(), payload)
                        created += 1

                # Quest
                if q and not self.sent_jobs.was_sent(user_id, "quest", day_index, for_date):
                    quest_id = int(q["id"])
                    q_ver = self._row_version_ts(q)
                    quest_key = self._job_key(day_index, None, quest_id, q_ver)
                    if not self.outbox.exists_job_for(user_id, quest_key):
                        payload = {
                            "kind": "day_quest",
                            "job_key": quest_key,
                            "day_index": day_index,
                            "for_date": for_date.isoformat(),
                            "quest": {
                                "prompt": q["prompt"],
                                "points": q["points"],
                                "photo_file_id": q.get("photo_file_id"),
                            },
                        }
                        self._log_job(user_id, "day_quest", quest_key, user_tz, for_date, delivery_hhmm, run_at_utc)
                        self.outbox.create_job(user_id, run_at_utc.isoformat(), payload)
                        created += 1

                # Day questionnaires: multiple questionnaires per day are supported.
                for qrow in day_questionnaires:
                    qid = int(qrow["id"])
                    q_content_type = self.questionnaire_content_type(qid)
                    if self.sent_jobs.was_sent(user_id, q_content_type, day_index, for_date):
                        continue
                    q_key = f"questionnaire:{qid}:day={day_index}:date={for_date.isoformat()}"
                    if self.outbox.exists_job_for(user_id, q_key):
                        continue
                    payload = {
                        "kind": "questionnaire_broadcast",
                        "job_key": q_key,
                        "day_index": day_index,
                        "for_date": for_date.isoformat(),
                        "questionnaire_id": qid,
                        "optional": False,
                    }
                    self._log_job(user_id, "questionnaire_broadcast", q_key, user_tz, for_date, delivery_hhmm, run_at_utc)
                    self.outbox.create_job(user_id, run_at_utc.isoformat(), payload)
                    created += 1

            # Daily reminder: schedule regardless of grace window (can still remind if delivery missed)
            if not self.sent_jobs.was_sent(user_id, "daily_reminder", day_index, for_date):
                reminder_local = self._compute_daily_reminder_run_local(delivery_local, user_tz)
                run_utc = reminder_local.astimezone(timezone.utc)
                job_key = f"daily_reminder:day={day_index}:date={for_date.isoformat()}"
                if not self.outbox.exists_job_for(user_id, job_key):
                    payload = {
                        "kind": "daily_reminder",
                        "job_key": job_key,
                        "day_index": day_index,
                        "for_date": for_date.isoformat(),
                    }
                    # reminder_local is based on delivery_local, so log with that reference
                    log.info(
                        "plan reminder user_id=%s day=%s for_date=%s tz=%s delivery_local=%s reminder_local=%s utc_run_at=%s",
                        user_id,
                        day_index,
                        for_date.isoformat(),
                        str(user_tz),
                        delivery_local.isoformat(),
                        reminder_local.isoformat(),
                        run_utc.isoformat(),
                    )
                    self.outbox.create_job(user_id, run_utc.isoformat(), payload)
                    created += 1

        return created

    def enqueue_day_now(self, user_id: int, day_index: int) -> int:
        """Manually enqueue today's content immediately."""

        lesson = self.lesson.get_by_day(day_index)
        q = self.quest.get_by_day(day_index)
        day_questionnaires = self.questionnaires.list_by_day(day_index, qtypes=("manual", "daily"))
        if not lesson and not q and not day_questionnaires:
            return 0

        created = 0
        now_utc = datetime.now(timezone.utc)
        run_utc = now_utc.isoformat()
        user_tz = self._user_tz(user_id)
        for_date = now_utc.astimezone(user_tz).date()

        if lesson:
            lesson_id = int(lesson["id"])
            l_ver = self._row_version_ts(lesson)
            lesson_key = self._job_key(day_index, lesson_id, None, l_ver)
            if not self.outbox.exists_job_for(user_id, lesson_key):
                payload = {
                    "kind": "day_lesson",
                    "job_key": lesson_key,
                    "day_index": day_index,
                    "lesson": {
                        "title": lesson["title"],
                        "description": lesson["description"],
                        "video_url": lesson["video_url"],
                        "points_viewed": int(lesson["points_viewed"]),
                    },
                }
                self.outbox.create_job(user_id, run_utc, payload)
                created += 1

        if q:
            quest_id = int(q["id"])
            q_ver = self._row_version_ts(q)
            quest_key = self._job_key(day_index, None, quest_id, q_ver)
            if not self.outbox.exists_job_for(user_id, quest_key):
                payload = {
                    "kind": "day_quest",
                    "job_key": quest_key,
                    "day_index": day_index,
                    "quest": {
                        "prompt": q["prompt"],
                        "points": q["points"],
                        "photo_file_id": q.get("photo_file_id"),
                    },
                }
                self.outbox.create_job(user_id, run_utc, payload)
                created += 1

        for qrow in day_questionnaires:
            qid = int(qrow["id"])
            q_key = f"questionnaire:{qid}:day={day_index}:date={for_date.isoformat()}"
            if self.outbox.exists_job_for(user_id, q_key):
                continue
            payload = {
                "kind": "questionnaire_broadcast",
                "job_key": q_key,
                "day_index": day_index,
                "for_date": for_date.isoformat(),
                "questionnaire_id": qid,
                "optional": False,
            }
            self.outbox.create_job(user_id, run_utc, payload)
            created += 1

        return created

    def schedule_questionnaire_broadcast(self, questionnaire_id: int, hhmm: str, optional: bool = False) -> int:
        """Schedule a questionnaire for each user at their local HH:MM."""

        hh, mm = [int(x) for x in hhmm.split(":")]
        user_ids = self.users.list_user_ids()
        created = 0

        now_utc = datetime.now(timezone.utc)
        for uid in user_ids:
            user_tz = self._user_tz(int(uid))
            now_local = now_utc.astimezone(user_tz)
            target_local = datetime.combine(now_local.date(), time(hh, mm), tzinfo=user_tz)
            # if already passed in user's local time — send almost immediately
            if target_local < now_local:
                target_local = now_local + timedelta(seconds=5)
            run_utc = target_local.astimezone(timezone.utc).isoformat()

            # Make key unique per-user + local date to avoid cross-TZ collisions
            job_key = f"qcast:{questionnaire_id}:{target_local.date().isoformat()}:{hhmm}"
            if self.outbox.exists_job_for(int(uid), job_key):
                continue
            payload = {
                "kind": "questionnaire_broadcast",
                "job_key": job_key,
                "questionnaire_id": questionnaire_id,
                "optional": bool(optional),
            }
            self.outbox.create_job(int(uid), run_utc, payload)
            created += 1
        return created
