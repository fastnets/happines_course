from datetime import datetime, timezone
import json
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from event_bus import callbacks as cb
from questionnaires.questionnaire_handlers import q_buttons


async def _get_bot_username(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    """Best-effort bot username for deep links."""
    # python-telegram-bot caches Bot.get_me() internally, so this is cheap after first call
    try:
        me = await context.bot.get_me()
        if me and getattr(me, "username", None):
            return me.username
    except Exception:
        pass
    return None


async def _deep_link(context: ContextTypes.DEFAULT_TYPE, payload: str) -> str | None:
    uname = await _get_bot_username(context)
    if not uname:
        return None
    return f"https://t.me/{uname}?start={payload}"


def _collect_pending_backlog(schedule, learning, qsvc, user_id: int, day_index: int):
    """Collect unfinished items from day 1..day_index for cumulative reminders."""

    pending = []
    first_lesson_day = None
    first_quest_day = None

    for d in range(1, day_index + 1):
        lesson = schedule.lesson.get_by_day(d)
        if lesson and (not learning.has_viewed_lesson(user_id, d)):
            pending.append(f"• 📚 День {d}: лекция — не отмечена «Просмотрено»")
            if first_lesson_day is None:
                first_lesson_day = d

        quest = schedule.quest.get_by_day(d)
        if quest and (not learning.has_quest_answer(user_id, d)):
            pending.append(f"• 📝 День {d}: задание — нет ответа")
            if first_quest_day is None:
                first_quest_day = d

        day_questionnaires = qsvc.list_for_day(d, qtypes=("manual", "daily"))
        has_pending_questionnaire = any(
            not qsvc.has_response(user_id, int(row["id"])) for row in day_questionnaires
        )
        if has_pending_questionnaire:
            pending.append(f"• 📋 День {d}: анкета — нет ответа")

    return pending, first_lesson_day, first_quest_day


async def tick(context: ContextTypes.DEFAULT_TYPE, services: dict):
    # Create new outbox jobs (lessons/quests + daily reminder) and then deliver due ones
    services["schedule"].schedule_due_jobs()
    # Create habit reminder jobs (occurrences + outbox)
    if services.get("habit_schedule"):
        services["habit_schedule"].schedule_due_jobs()
    # Create personal reminder jobs (outbox)
    if services.get("personal_reminder_schedule"):
        services["personal_reminder_schedule"].schedule_due_jobs()
    await _process_outbox(context, services)


async def _process_outbox(context: ContextTypes.DEFAULT_TYPE, services: dict):
    outbox = services["schedule"].outbox
    learning = services["learning"]
    qsvc = services["questionnaire"]
    schedule = services["schedule"]
    habit_svc = services.get("habit")
    habit_occ = getattr(habit_svc, "occ", None) if habit_svc else None

    jobs = outbox.fetch_due_pending(limit=50)
    for j in jobs:
        job_id = int(j["id"])
        user_id = int(j["user_id"])
        try:
            payload = j["payload_json"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            kind = payload.get("kind")

            # Backward compatible handler: combined day content (older versions)
            if kind == "day_content":
                day_index = int(payload["day_index"])
                lesson = payload.get("lesson")
                quest = payload.get("quest")

                if lesson:
                    pts = int(lesson.get("points_viewed") or 0)
                    viewed_cb = schedule.make_viewed_cb(day_index, pts)
                    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Просмотрено", callback_data=viewed_cb)]])

                    title = lesson.get("title") or f"День {day_index}"
                    desc = lesson.get("description") or ""
                    video = lesson.get("video_url") or ""
                    text = f"📚 Лекция дня {day_index}\n*{title}*\n\n{desc}"
                    if video:
                        text += f"\n\n🎥 {video}"
                    await context.bot.send_message(chat_id=user_id, text=text, parse_mode="Markdown", reply_markup=kb)

                    user_tz = schedule._user_tz(user_id)
                    for_date = datetime.now(timezone.utc).astimezone(user_tz).date()
                    schedule.sent_jobs.mark_sent(user_id, "lesson", day_index, for_date)
                    schedule.deliveries.mark_sent(user_id, day_index, "lesson")

                if quest:
                    qtext = (
                        f"📝 Задание дня {day_index}:\n{quest['prompt']}\n\n"
                        "Нажми кнопку ниже, чтобы продолжить, или просто ответь сообщением в чат."
                    )
                    reply_cb = f"{cb.QUEST_REPLY_PREFIX}{day_index}"
                    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✍️ Ответить на задание", callback_data=reply_cb)]])
                    await context.bot.send_message(chat_id=user_id, text=qtext, reply_markup=kb)
                    learning.state.set_state(
                        user_id,
                        "last_quest",
                        {"day_index": day_index, "points": int(quest["points"]), "prompt": quest.get("prompt")},
                    )

                    user_tz = schedule._user_tz(user_id)
                    for_date = datetime.now(timezone.utc).astimezone(user_tz).date()
                    schedule.sent_jobs.mark_sent(user_id, "quest", day_index, for_date)
                    schedule.deliveries.mark_sent(user_id, day_index, "quest")

                outbox.mark_sent(job_id)
                continue

            # Split handlers: lecture and quest are scheduled independently
            if kind == "day_lesson":
                day_index = int(payload["day_index"])
                for_date_s = payload.get("for_date")
                lesson = payload.get("lesson")
                if lesson:
                    pts = int(lesson.get("points_viewed") or 0)
                    viewed_cb = schedule.make_viewed_cb(day_index, pts)
                    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Просмотрено", callback_data=viewed_cb)]])

                    title = lesson.get("title") or f"День {day_index}"
                    desc = lesson.get("description") or ""
                    video = lesson.get("video_url") or ""
                    text = f"📚 Лекция дня {day_index}\n*{title}*\n\n{desc}"
                    if video:
                        text += f"\n\n🎥 {video}"
                    await context.bot.send_message(chat_id=user_id, text=text, parse_mode="Markdown", reply_markup=kb)

                    if for_date_s:
                        for_date = datetime.fromisoformat(for_date_s).date()
                    else:
                        user_tz = schedule._user_tz(user_id)
                        for_date = datetime.now(timezone.utc).astimezone(user_tz).date()
                    schedule.sent_jobs.mark_sent(user_id, "lesson", day_index, for_date)
                    schedule.deliveries.mark_sent(user_id, day_index, "lesson")
                outbox.mark_sent(job_id)
                continue

            if kind == "day_quest":
                day_index = int(payload["day_index"])
                for_date_s = payload.get("for_date")
                quest = payload.get("quest")
                if quest:
                    qtext = (
                        f"📝 Задание дня {day_index}:\n{quest['prompt']}\n\n"
                        "Нажми кнопку ниже, чтобы продолжить, или просто ответь сообщением в чат."
                    )
                    reply_cb = f"{cb.QUEST_REPLY_PREFIX}{day_index}"
                    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✍️ Ответить на задание", callback_data=reply_cb)]])
                    await context.bot.send_message(chat_id=user_id, text=qtext, reply_markup=kb)
                    learning.state.set_state(
                        user_id,
                        "last_quest",
                        {"day_index": day_index, "points": int(quest["points"]), "prompt": quest.get("prompt")},
                    )
                    learning.progress.mark_sent(user_id, day_index)

                    if for_date_s:
                        for_date = datetime.fromisoformat(for_date_s).date()
                    else:
                        user_tz = schedule._user_tz(user_id)
                        for_date = datetime.now(timezone.utc).astimezone(user_tz).date()
                    schedule.sent_jobs.mark_sent(user_id, "quest", day_index, for_date)
                    schedule.deliveries.mark_sent(user_id, day_index, "quest")
                outbox.mark_sent(job_id)
                continue

            if kind == "daily_reminder":
                day_index = int(payload.get("day_index") or 0)
                for_date_s = payload.get("for_date")
                for_date = datetime.fromisoformat(for_date_s).date() if for_date_s else None
                if day_index <= 0:
                    outbox.mark_sent(job_id)
                    continue

                pending, first_lesson_day, first_quest_day = _collect_pending_backlog(
                    schedule,
                    learning,
                    qsvc,
                    user_id,
                    day_index,
                )

                if not pending:
                    if for_date:
                        schedule.sent_jobs.mark_sent(user_id, "daily_reminder", day_index, for_date)
                    outbox.mark_sent(job_id)
                    continue

                text = (
                    "🔔 Напоминание про твой день\n\n"
                    "У тебя есть незавершенные материалы:\n"
                    + "\n".join(pending)
                    + "\n\nНажми кнопку ниже, чтобы вернуться к нужному материалу ✅"
                )

                buttons = []
                # Deep links back into the exact unfinished content
                if first_lesson_day is not None:
                    url = await _deep_link(context, f"gol_{first_lesson_day}")
                    if url:
                        buttons.append([InlineKeyboardButton("📚 Открыть первую незавершенную лекцию", url=url)])
                if first_quest_day is not None:
                    url = await _deep_link(context, f"goq_{first_quest_day}")
                    if url:
                        buttons.append([InlineKeyboardButton("📝 Открыть первое незавершенное задание", url=url)])

                reply_markup = InlineKeyboardMarkup(buttons) if buttons else None
                await context.bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup)
                if for_date:
                    schedule.sent_jobs.mark_sent(user_id, "daily_reminder", day_index, for_date)
                outbox.mark_sent(job_id)
                continue

            if kind == "questionnaire_broadcast":
                qid = int(payload["questionnaire_id"])
                day_index = int(payload.get("day_index") or 0)
                for_date_s = payload.get("for_date")
                for_date = datetime.fromisoformat(for_date_s).date() if for_date_s else None
                is_optional = bool(payload.get("optional"))
                item = qsvc.get(qid)
                if not item:
                    outbox.mark_sent(job_id)
                    continue
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"📋 Анкета\n\n{item['question']}",
                    reply_markup=q_buttons(qid),
                )
                if (not is_optional) and day_index and for_date:
                    q_content_type = schedule.questionnaire_content_type(qid)
                    schedule.sent_jobs.mark_sent(user_id, q_content_type, day_index, for_date)
                outbox.mark_sent(job_id)
                continue

            if kind == "habit_reminder":
                occurrence_id = int(payload.get("occurrence_id") or 0)
                title = payload.get("title") or "Привычка"
                if occurrence_id <= 0:
                    outbox.mark_sent(job_id)
                    continue

                # Mark as sent (best-effort) so we can audit delivery status.
                try:
                    if habit_occ:
                        habit_occ.mark_sent(occurrence_id)
                except Exception:
                    pass

                done_cb = f"habit:done:{occurrence_id}"
                skip_cb = f"habit:skip:{occurrence_id}"
                kb = InlineKeyboardMarkup(
                    [[
                        InlineKeyboardButton("✅ Выполнено", callback_data=done_cb),
                        InlineKeyboardButton("➖ Пропустить", callback_data=skip_cb),
                    ]]
                )
                text = f"🔔 Привычка\n\n*{title}*\n\nОтметь результат:"
                await context.bot.send_message(chat_id=user_id, text=text, parse_mode="Markdown", reply_markup=kb)
                outbox.mark_sent(job_id)
                continue

            if kind == "personal_reminder":
                text = (payload.get("text") or "").strip() or "Напоминание"
                msg = f"🔔 Персональное напоминание\n\n{text}"
                await context.bot.send_message(chat_id=user_id, text=msg)
                outbox.mark_sent(job_id)
                continue

            outbox.mark_sent(job_id)

        except Exception as e:
            outbox.mark_failed(job_id, str(e))
