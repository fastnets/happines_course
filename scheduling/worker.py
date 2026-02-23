from datetime import datetime, timezone
import json
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from event_bus import callbacks as cb
from questionnaires.questionnaire_handlers import q_buttons


def _save_material_message(
    schedule,
    user_id: int,
    day_index: int,
    kind: str,
    message_id: int,
    content_id: int = 0,
):
    """Best-effort save of sent message id for reminder navigation."""

    if day_index <= 0 or message_id <= 0:
        return
    try:
        repo = getattr(schedule, "material_messages", None)
        if not repo:
            return
        repo.upsert(
            user_id=user_id,
            day_index=day_index,
            kind=kind,
            message_id=message_id,
            content_id=content_id,
        )
    except Exception:
        pass


def _collect_pending_backlog(schedule, learning, qsvc, user_id: int, day_index: int):
    """Collect unfinished items from day 1..day_index for cumulative reminders."""

    pending = []
    first_lesson_day = None
    first_quest_day = None
    first_questionnaire = None

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
        first_unanswered_qid = None
        for row in day_questionnaires:
            qid = int(row["id"])
            if not qsvc.has_response(user_id, qid):
                first_unanswered_qid = qid
                break
        if first_unanswered_qid is not None:
            if first_questionnaire is None:
                first_questionnaire = (d, first_unanswered_qid)
            pending.append(f"• 📋 День {d}: анкета — нет ответа")

    return pending, first_lesson_day, first_quest_day, first_questionnaire


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
                    text = f"📚 Лекция дня {day_index}\n{title}\n\n{desc}"
                    if video:
                        text += f"\n\n🎥 {video}"
                    msg = await context.bot.send_message(chat_id=user_id, text=text, reply_markup=kb)
                    _save_material_message(
                        schedule,
                        user_id=user_id,
                        day_index=day_index,
                        kind="lesson",
                        message_id=int(msg.message_id),
                    )

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
                    msg = await context.bot.send_message(chat_id=user_id, text=qtext, reply_markup=kb)
                    _save_material_message(
                        schedule,
                        user_id=user_id,
                        day_index=day_index,
                        kind="quest",
                        message_id=int(msg.message_id),
                    )
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
                    text = f"📚 Лекция дня {day_index}\n{title}\n\n{desc}"
                    if video:
                        text += f"\n\n🎥 {video}"
                    msg = await context.bot.send_message(chat_id=user_id, text=text, reply_markup=kb)
                    _save_material_message(
                        schedule,
                        user_id=user_id,
                        day_index=day_index,
                        kind="lesson",
                        message_id=int(msg.message_id),
                    )

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
                    msg = await context.bot.send_message(chat_id=user_id, text=qtext, reply_markup=kb)
                    _save_material_message(
                        schedule,
                        user_id=user_id,
                        day_index=day_index,
                        kind="quest",
                        message_id=int(msg.message_id),
                    )
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

                pending, first_lesson_day, first_quest_day, first_questionnaire = _collect_pending_backlog(
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
                if first_lesson_day is not None:
                    buttons.append(
                        [
                            InlineKeyboardButton(
                                f"📚 Открыть незавершенную лекцию (день {first_lesson_day})",
                                callback_data=f"{cb.REMINDER_NAV_PREFIX}lesson:{first_lesson_day}",
                            )
                        ]
                    )
                if first_quest_day is not None:
                    buttons.append(
                        [
                            InlineKeyboardButton(
                                f"📝 Открыть незавершенное задание (день {first_quest_day})",
                                callback_data=f"{cb.REMINDER_NAV_PREFIX}quest:{first_quest_day}",
                            )
                        ]
                    )
                if first_questionnaire is not None:
                    q_day, qid = first_questionnaire
                    buttons.append(
                        [
                            InlineKeyboardButton(
                                f"📋 Открыть незавершенную анкету (день {q_day})",
                                callback_data=f"{cb.REMINDER_NAV_PREFIX}questionnaire:{q_day}:{qid}",
                            )
                        ]
                    )
                buttons.append(
                    [
                        InlineKeyboardButton(
                            "➡️ Продолжить по порядку",
                            callback_data=cb.REMINDER_NAV_NEXT,
                        )
                    ]
                )

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
                msg = await context.bot.send_message(
                    chat_id=user_id,
                    text=f"📋 Анкета\n\n{item['question']}",
                    reply_markup=q_buttons(qid),
                )
                _save_material_message(
                    schedule,
                    user_id=user_id,
                    day_index=day_index,
                    kind="questionnaire",
                    content_id=qid,
                    message_id=int(msg.message_id),
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
