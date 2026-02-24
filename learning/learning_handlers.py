import json
import logging
import asyncio
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from event_bus import callbacks as cb
from ui.keyboards.reply import kb_back_only

logger = logging.getLogger("happines_course")


def register_learning_handlers(app, settings, services):
    learning = services["learning"]
    schedule = services["schedule"]
    ai = services.get("ai")
    user_svc = services.get("user")
    achievement_svc = services.get("achievement")

    AI_STEP = "ai_quest_followup"
    AI_CHAT_STEP = "ai_chat"

    def _achievement_lines(rows: list[dict]) -> str | None:
        if not rows:
            return None
        header = "🏆 Новая ачивка!" if len(rows) == 1 else "🏆 Новые ачивки!"
        lines = [header]
        for row in rows:
            icon = (row.get("icon") or "🏅").strip() or "🏅"
            title = (row.get("title") or "Ачивка").strip()
            lines.append(f"• {icon} {title}")
        return "\n".join(lines)

    async def _notify_achievements(uid: int, context: ContextTypes.DEFAULT_TYPE):
        if not achievement_svc:
            return
        try:
            tz_name = user_svc.get_timezone(uid) if user_svc else None
            rows = achievement_svc.evaluate(uid, user_timezone=tz_name)
        except Exception:
            return
        text = _achievement_lines(rows)
        if text:
            await context.bot.send_message(chat_id=uid, text=text)

    # ----------------------------
    # Lesson viewed
    # ----------------------------
    async def on_viewed(update: Update, context: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        await q.answer()
        payload = schedule.parse_viewed_payload(q.data or "")
        if not payload:
            await q.edit_message_reply_markup(reply_markup=None)
            return

        day_index = int(payload["day_index"])
        points = int(payload["points"])

        if learning.has_viewed_lesson(q.from_user.id, day_index):
            await q.edit_message_reply_markup(reply_markup=None)
            await context.bot.send_message(chat_id=q.from_user.id, text="✅ Уже засчитано.")
            return

        learning.mark_viewed_today(q.from_user.id, day_index)
        learning.points.add_points(q.from_user.id, "lesson_viewed", f"day:{day_index}", points)
        await q.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(chat_id=q.from_user.id, text=f"✅ Просмотрено! +{points} баллов")
        await _notify_achievements(q.from_user.id, context)

    async def on_extra_viewed(update: Update, context: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        await q.answer()
        payload = schedule.parse_extra_viewed_payload(q.data or "")
        if not payload:
            await q.edit_message_reply_markup(reply_markup=None)
            return

        material_id = int(payload["material_id"])
        points = int(payload["points"])
        source_key = f"extra:{material_id}"

        if learning.points.has_entry(q.from_user.id, "extra_viewed", source_key):
            await q.edit_message_reply_markup(reply_markup=None)
            await context.bot.send_message(chat_id=q.from_user.id, text="✅ Уже засчитано.")
            return

        learning.points.add_points(q.from_user.id, "extra_viewed", source_key, points)
        await q.edit_message_reply_markup(reply_markup=None)
        if points > 0:
            await context.bot.send_message(chat_id=q.from_user.id, text=f"✅ Просмотрено! +{points} баллов")
            await _notify_achievements(q.from_user.id, context)
        else:
            await context.bot.send_message(chat_id=q.from_user.id, text="✅ Просмотрено.")

    # ----------------------------
    # Quest reply button
    # ----------------------------
    async def on_quest_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        await q.answer()
        data = q.data or ""
        if not data.startswith(cb.QUEST_REPLY_PREFIX):
            return

        try:
            day_index = int(data.split(":")[-1])
        except Exception:
            return

        if learning.has_quest_answer(q.from_user.id, day_index):
            try:
                await q.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
            await context.bot.send_message(chat_id=q.from_user.id, text="✅ Это задание уже отправлено.")
            return

        quest = schedule.quest.get_by_day(day_index)
        if not quest:
            await context.bot.send_message(chat_id=q.from_user.id, text="⚠️ Не нашёл задание для этого дня.")
            return

        learning.state.set_state(
            q.from_user.id,
            "last_quest",
            {
                "day_index": day_index,
                "points": int(quest.get("points") or 1),
                "prompt": quest.get("prompt"),
            },
        )

        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass

        await context.bot.send_message(
            chat_id=q.from_user.id,
            text="✍️ Напиши ответ одним сообщением в этот чат.",
        )

    # ----------------------------
    # /answer compatibility
    # ----------------------------
    async def answer_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = " ".join(context.args).strip() if context.args else ""
        if not text:
            await update.effective_message.reply_text("Просто напиши ответ сообщением в чат 🙂")
            return
        await _submit(update, context, text)

    # ----------------------------
    # Plain text handler
    # ----------------------------
    async def on_plain_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_message.text or update.effective_message.text.startswith("/"):
            return

        st = learning.state.get_state(update.effective_user.id)
        if st and st.get("step") in (AI_STEP, AI_CHAT_STEP):
            await _ai_chat(update, context, st)
            return

        await _submit(update, context, update.effective_message.text.strip())

    # ----------------------------
    # Submit quest answer
    # ----------------------------
    async def _submit(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
        st = learning.state.get_state(update.effective_user.id)
        if not st or not st.get("payload_json"):
            return

        payload = st["payload_json"]
        if isinstance(payload, str):
            payload = json.loads(payload)

        if st.get("step") != "last_quest":
            return

        day_index = int(payload.get("day_index", 0))
        points = int(payload.get("points", 1))
        if day_index <= 0:
            return

        learning.submit_answer(update.effective_user.id, day_index, points, text)
        await update.effective_message.reply_text(f"✅ Ответ принят! +{points} баллов")
        await _notify_achievements(update.effective_user.id, context)

        # ---------- AI FEEDBACK ----------
        try:
            if not ai:
                return

            enabled_fn = getattr(ai, "enabled", None)
            if callable(enabled_fn) and not enabled_fn():
                logger.info("AI disabled")
                return

            quest_text = (payload.get("prompt") or "").strip()
            user_name = update.effective_user.first_name or update.effective_user.full_name or ""

            fb = None

            # async API (future-proof)
            if hasattr(ai, "feedback_for_quest_answer"):
                fb = await ai.feedback_for_quest_answer(
                    user_name=user_name,
                    day_index=day_index,
                    quest_text=quest_text or "(задание не найдено)",
                    answer_text=text,
                )

            # sync API (current reality)
            elif hasattr(ai, "generate_followup_question"):
                def _call():
                    return ai.generate_followup_question(
                        quest_text=quest_text or "(задание не найдено)",
                        user_answer=text,
                    )

                fb = await asyncio.to_thread(_call)

            if not fb:
                return

            await update.effective_message.reply_text(fb)

            learning.state.set_state(
                update.effective_user.id,
                AI_CHAT_STEP,
                {
                    "day_index": day_index,
                    "quest_text": quest_text,
                    "first_answer": text,
                    "ai_message_1": fb,
                },
            )

            await update.effective_message.reply_text(
                "💬 Можешь продолжить общение с ассистентом.\n"
                "Чтобы выйти — нажми «⬅️ Назад».",
                reply_markup=kb_back_only(),
            )

        except Exception:
            logger.exception("AI follow-up failed")

    # ----------------------------
    # AI chat continuation
    # ----------------------------
    async def _ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE, st_row):
        try:
            payload = st_row.get("payload_json")
            if isinstance(payload, str):
                payload = json.loads(payload)

            user_msg = update.effective_message.text.strip()
            if not user_msg:
                return

            if not ai:
                learning.state.clear_state(update.effective_user.id)
                return

            enabled_fn = getattr(ai, "enabled", None)
            if callable(enabled_fn) and not enabled_fn():
                learning.state.clear_state(update.effective_user.id)
                return

            quest_text = payload.get("quest_text") or ""
            first_answer = payload.get("first_answer") or ""
            ai_message_1 = payload.get("ai_message_1") or ""

            if hasattr(ai, "followup_after_user_reply"):
                msg = await ai.followup_after_user_reply(
                    user_name=update.effective_user.first_name or "",
                    day_index=int(payload.get("day_index") or 0),
                    quest_text=quest_text,
                    first_answer=first_answer,
                    ai_message_1=ai_message_1,
                    user_followup=user_msg,
                )
            else:
                def _call():
                    return ai.generate_followup_question(
                        quest_text=quest_text,
                        user_answer=f"{first_answer}\n\nПользователь продолжает: {user_msg}",
                    )

                msg = await asyncio.to_thread(_call)

            if msg:
                await update.effective_message.reply_text(msg, reply_markup=kb_back_only())

        except Exception:
            logger.exception("AI chat failed")

    # ----------------------------
    # Handlers
    # ----------------------------
    app.add_handler(CallbackQueryHandler(on_viewed, pattern=f"^{cb.LESSON_VIEWED}"))
    app.add_handler(CallbackQueryHandler(on_extra_viewed, pattern=f"^{cb.EXTRA_VIEWED}"))
    app.add_handler(CallbackQueryHandler(on_quest_reply, pattern=f"^{cb.QUEST_REPLY_PREFIX}"))
    app.add_handler(CommandHandler("answer", answer_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_plain_text), group=5)
