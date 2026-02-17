from __future__ import annotations

from entity.repositories.admin_analytics_repo import AdminAnalyticsRepo


class AdminAnalyticsService:
    def __init__(self, db, settings):
        self.settings = settings
        self.repo = AdminAnalyticsRepo(db)

    @staticmethod
    def _period_label(days: int) -> str:
        if int(days) <= 1:
            return "сегодня"
        return f"последние {int(days)} дн."

    @staticmethod
    def _pct(num: int, den: int) -> str:
        if den <= 0:
            return "0%"
        return f"{(100.0 * float(num) / float(den)):.1f}%"

    @staticmethod
    def _safe_int(v) -> int:
        try:
            return int(v or 0)
        except Exception:
            return 0

    @staticmethod
    def _day_from_source_key(key: str | None) -> int | None:
        s = (key or "").strip()
        if not s.startswith("day:"):
            return None
        n = s[4:]
        if not n.isdigit():
            return None
        return int(n)

    def summary_report(self, days: int) -> str:
        d = self.repo.summary(days)
        users_total = self._safe_int(d.get("users_total"))
        consent_total = self._safe_int(d.get("consent_total"))
        timezone_total = self._safe_int(d.get("timezone_total"))
        enrolled_total = self._safe_int(d.get("enrolled_total"))
        active_users = self._safe_int(d.get("active_users"))
        avg_points = float(d.get("avg_points") or 0.0)

        return (
            f"📊 Сводка ({self._period_label(days)})\n\n"
            f"• Пользователей всего: {users_total}\n"
            f"• Согласие ПД: {consent_total} ({self._pct(consent_total, users_total)})\n"
            f"• Часовой пояс заполнен: {timezone_total} ({self._pct(timezone_total, users_total)})\n"
            f"• Записаны на курс: {enrolled_total}\n"
            f"• Активных за период: {active_users}\n"
            f"• Средние баллы/пользователь: {avg_points:.1f}"
        )

    def funnel_report(self, days: int) -> str:
        d = self.repo.funnel(days)
        total = self._safe_int(d.get("users_total"))
        consent = self._safe_int(d.get("consent_total"))
        timezone = self._safe_int(d.get("timezone_total"))
        enrolled = self._safe_int(d.get("enrolled_total"))
        day1_done = self._safe_int(d.get("day1_done_total"))

        return (
            f"🧭 Воронка ({self._period_label(days)}, по новым пользователям)\n\n"
            f"• Старт: {total}\n"
            f"• Согласие ПД: {consent} ({self._pct(consent, total)})\n"
            f"• Часовой пояс: {timezone} ({self._pct(timezone, total)})\n"
            f"• Записаны: {enrolled} ({self._pct(enrolled, total)})\n"
            f"• День 1 завершён: {day1_done} ({self._pct(day1_done, total)})"
        )

    def delivery_report(self, days: int) -> str:
        d = self.repo.delivery(days)
        s = d.get("status") or {}
        pending = self._safe_int(s.get("pending"))
        sent = self._safe_int(s.get("sent"))
        failed = self._safe_int(s.get("failed"))
        cancelled = self._safe_int(s.get("cancelled"))
        total = pending + sent + failed + cancelled

        lines = [
            f"📬 Доставка ({self._period_label(days)})",
            "",
            f"• Всего jobs: {total}",
            f"• Sent: {sent}",
            f"• Pending: {pending}",
            f"• Failed: {failed}",
            f"• Cancelled: {cancelled}",
        ]
        kinds = d.get("kinds") or []
        if kinds:
            lines.append("")
            lines.append("По типам:")
            for k in kinds:
                kind = (k.get("kind") or "-").strip()
                k_total = self._safe_int(k.get("total"))
                k_sent = self._safe_int(k.get("sent"))
                k_failed = self._safe_int(k.get("failed"))
                k_pending = self._safe_int(k.get("pending"))
                lines.append(
                    f"• {kind}: {k_sent}/{k_total} sent, failed={k_failed}, pending={k_pending}"
                )
        return "\n".join(lines)

    def content_report(self, days: int) -> str:
        d = self.repo.content(days)
        sent_rows = d.get("sent_rows") or []
        lesson_rows = d.get("lesson_rows") or []
        quest_rows = d.get("quest_rows") or []

        viewed_by_day: dict[int, int] = {}
        for r in lesson_rows:
            day = self._day_from_source_key(r.get("source_key"))
            if day is None:
                continue
            viewed_by_day[day] = self._safe_int(r.get("viewed"))

        answered_by_day: dict[int, int] = {}
        for r in quest_rows:
            day = self._safe_int(r.get("day_index"))
            answered_by_day[day] = self._safe_int(r.get("answered"))

        if not sent_rows:
            return f"📚 Контент ({self._period_label(days)})\n\nЗа период отправок нет."

        lines = [f"📚 Контент ({self._period_label(days)})", ""]
        for row in sent_rows[:15]:
            day = self._safe_int(row.get("day_index"))
            lesson_sent = self._safe_int(row.get("lesson_sent"))
            quest_sent = self._safe_int(row.get("quest_sent"))
            lesson_viewed = viewed_by_day.get(day, 0)
            quest_answered = answered_by_day.get(day, 0)
            lines.append(
                f"• День {day}: лекции {lesson_viewed}/{lesson_sent} ({self._pct(lesson_viewed, lesson_sent)}), "
                f"задания {quest_answered}/{quest_sent} ({self._pct(quest_answered, quest_sent)})"
            )
        return "\n".join(lines)

    def questionnaires_report(self, days: int) -> str:
        d = self.repo.questionnaires(days)
        s = d.get("summary") or {}
        responses_total = self._safe_int(s.get("responses_total"))
        users_total = self._safe_int(s.get("users_total"))
        avg_score = float(s.get("avg_score") or 0.0)

        lines = [
            f"📋 Анкеты ({self._period_label(days)})",
            "",
            f"• Ответов: {responses_total}",
            f"• Уникальных пользователей: {users_total}",
            f"• Средний score: {avg_score:.2f}",
        ]

        top_rows = d.get("top_rows") or []
        if top_rows:
            lines.append("")
            lines.append("Топ анкет:")
            for r in top_rows[:10]:
                qid = self._safe_int(r.get("id"))
                responses = self._safe_int(r.get("responses"))
                avg = float(r.get("avg_score") or 0.0)
                qtext = (r.get("question") or "").replace("\n", " ").strip()
                if len(qtext) > 54:
                    qtext = qtext[:51] + "..."
                lines.append(f"• #{qid}: ответов={responses}, avg={avg:.2f} — {qtext}")
        return "\n".join(lines)

    def reminders_report(self, days: int) -> str:
        d = self.repo.reminders(days)
        personal_created = self._safe_int(d.get("personal_created"))
        personal_sent = self._safe_int(d.get("personal_sent"))
        personal_pending = self._safe_int(d.get("personal_pending"))
        personal_cancelled = self._safe_int(d.get("personal_cancelled"))
        habits_created = self._safe_int(d.get("habits_created"))
        habit_sent = self._safe_int(d.get("habit_sent"))
        habit_done = self._safe_int(d.get("habit_done"))
        habit_skipped = self._safe_int(d.get("habit_skipped"))
        daily_sent = self._safe_int(d.get("daily_sent"))

        return (
            f"⏰ Ремайндеры ({self._period_label(days)})\n\n"
            f"• Personal reminders: created={personal_created}, sent={personal_sent}, pending={personal_pending}, cancelled={personal_cancelled}\n"
            f"• Habits: created={habits_created}, sent={habit_sent}, done={habit_done}, skipped={habit_skipped}\n"
            f"• Daily reminders sent: {daily_sent}"
        )
