import json, re
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters, CommandHandler
from event_bus import callbacks as cb

def q_buttons(qid: int):
    row = [InlineKeyboardButton(str(i), callback_data=f"{cb.Q_SCORE_PREFIX}{qid}:{i}") for i in range(1, 6)]
    return InlineKeyboardMarkup([row])

def register_questionnaire_handlers(app, settings, services):
    qsvc = services["questionnaire"]
    user_svc = services.get("user")
    achievement_svc = services.get("achievement")

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

    async def qsend(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.effective_message.reply_text("Использование: /qsend <id анкеты>")
            return
        try:
            qid = int(context.args[0])
        except ValueError:
            await update.effective_message.reply_text("ID должен быть числом.")
            return
        item = qsvc.get(qid)
        if not item:
            await update.effective_message.reply_text("Анкета не найдена.")
            return
        await update.effective_message.reply_text(f"📋 Анкета\n\n{item['question']}", reply_markup=q_buttons(qid))

    async def on_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        await q.answer()
        m = re.match(r"^q:score:(\d+):(\d+)$", q.data or "")
        if not m:
            return
        qid = int(m.group(1)); score = int(m.group(2))
        item = qsvc.get(qid)
        if not item:
            await q.edit_message_reply_markup(reply_markup=None)
            return
        if qsvc.has_response(q.from_user.id, qid):
            await q.edit_message_reply_markup(reply_markup=None)
            await context.bot.send_message(chat_id=q.from_user.id, text="✅ Эта анкета уже заполнена.")
            return
        points = int(item["points"])
        is_optional = (item.get("qtype") == "broadcast_optional")
        if is_optional:
            created = qsvc.submit_score_only(q.from_user.id, qid, score, points)
        else:
            qsvc.start_comment_flow(q.from_user.id, qid, score, points)
        await q.edit_message_reply_markup(reply_markup=None)
        if is_optional:
            if created:
                await context.bot.send_message(chat_id=q.from_user.id, text=f"Спасибо! Оценка: {score}. +{points} баллов")
            else:
                await context.bot.send_message(chat_id=q.from_user.id, text="✅ Эта анкета уже заполнена.")
        else:
            await context.bot.send_message(
                chat_id=q.from_user.id,
                text=f"Спасибо! Оценка: {score}.\n\nТеперь напиши коротко: почему так?\nБаллы начислятся после комментария.",
            )
        await _notify_achievements(q.from_user.id, context)

    async def on_comment_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = (update.effective_message.text or "").strip()
        if not text or text.startswith("/"):
            return
        st = qsvc.state.get_state(update.effective_user.id)
        if not st or st.get("step") != "wait_q_comment":
            return
        payload = st["payload_json"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        qid = int(payload.get("questionnaire_id", 0))
        score = int(payload.get("score", 0))
        if qid <= 0 or score <= 0:
            return
        saved = qsvc.save_comment(update.effective_user.id, qid, score, text)
        if not saved:
            await update.effective_message.reply_text("✅ Ответ по этой анкете уже сохранён.")
            return
        item = qsvc.get(qid) or {}
        points = int(item.get("points") or 0)
        if points > 0:
            await update.effective_message.reply_text(f"✅ Комментарий сохранён! +{points} баллов")
        else:
            await update.effective_message.reply_text("✅ Комментарий сохранён!")
        await _notify_achievements(update.effective_user.id, context)

    app.add_handler(CommandHandler("qsend", qsend))
    app.add_handler(CallbackQueryHandler(on_score, pattern=r"^q:score:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_comment_text), group=2)
