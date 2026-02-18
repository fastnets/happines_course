import re
import json
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, MessageHandler, filters, CommandHandler, ApplicationHandlerStop

from entity.settings import Settings
from ui import texts
from ui.keyboards import menus

log = logging.getLogger("happines_course")

# State steps
ADMIN_MENU_STEP = "admin_menu"
ADMIN_WIZARD_STEP = "admin_wizard"

# Reply buttons (admin UI)
BTN_LIST = "📋 Список"
BTN_CREATE = "➕ Создать"
BTN_EDIT = "✏️ Редактировать"
BTN_DELETE = "🗑 Удалить"
BTN_RANDOM_Q = "🎲 Рандомная анкета всем"

BTN_YES = "Да"
BTN_NO = "Нет"

# Analytics submenu
BTN_PERIOD_TODAY = "Сегодня"
BTN_PERIOD_7 = "7 дней"
BTN_PERIOD_30 = "30 дней"
BTN_A_SUMMARY = "📊 Сводка"
BTN_A_FUNNEL = "🧭 Воронка"
BTN_A_DELIVERY = "📬 Доставка"
BTN_A_CONTENT = "📚 Контент"
BTN_A_QUESTIONNAIRES = "📋 Анкеты"
BTN_A_REMINDERS = "⏰ Ремайндеры"

# Tickets submenu
BTN_T_OPEN = "🟡 Open"
BTN_T_ALL = "📚 Все"
BTN_T_VIEW = "🔎 Открыть по ID"
BTN_T_REPLY = "💬 Ответить"
BTN_T_CLOSE = "✅ Закрыть"


def _extract_quest_points(item: dict) -> int:
    """Return quest points from current or legacy field names."""
    try:
        return int(item.get("points") or item.get("points_reply") or 0)
    except Exception:
        return 0


def kb(rows):
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def kb_yes_no():
    return kb([[KeyboardButton(BTN_YES), KeyboardButton(BTN_NO)], [KeyboardButton(texts.BTN_BACK)]])


def kb_admin_home():
    return kb(
        [
            [KeyboardButton(texts.ADMIN_LESSONS), KeyboardButton(texts.ADMIN_QUESTS)],
            [KeyboardButton(texts.ADMIN_QUESTIONNAIRES), KeyboardButton(texts.ADMIN_ANALYTICS)],
            [KeyboardButton(texts.ADMIN_TICKETS)],
            [KeyboardButton(texts.BTN_BACK)],
        ]
    )

def kb_admin_actions(include_random: bool = False):
    rows = [
        [KeyboardButton(BTN_LIST), KeyboardButton(BTN_CREATE)],
        [KeyboardButton(BTN_EDIT), KeyboardButton(BTN_DELETE)],
    ]
    if include_random:
        rows.append([KeyboardButton(BTN_RANDOM_Q)])
    rows.append([KeyboardButton(texts.BTN_BACK)])
    return kb(rows)


def kb_admin_analytics():
    return kb(
        [
            [KeyboardButton(BTN_PERIOD_TODAY), KeyboardButton(BTN_PERIOD_7), KeyboardButton(BTN_PERIOD_30)],
            [KeyboardButton(BTN_A_SUMMARY), KeyboardButton(BTN_A_FUNNEL)],
            [KeyboardButton(BTN_A_DELIVERY), KeyboardButton(BTN_A_CONTENT)],
            [KeyboardButton(BTN_A_QUESTIONNAIRES), KeyboardButton(BTN_A_REMINDERS)],
            [KeyboardButton(texts.BTN_BACK)],
        ]
    )


def kb_admin_tickets():
    return kb(
        [
            [KeyboardButton(BTN_T_OPEN), KeyboardButton(BTN_T_ALL)],
            [KeyboardButton(BTN_T_VIEW), KeyboardButton(BTN_T_REPLY)],
            [KeyboardButton(BTN_T_CLOSE)],
            [KeyboardButton(texts.BTN_BACK)],
        ]
    )


def register_admin_handlers(app, settings: Settings, services: dict):
    admin_svc = services.get("admin")
    admin_analytics = services.get("admin_analytics")
    support_svc = services.get("support")

    def _is_admin(update: Update) -> bool:
        try:
            uid = update.effective_user.id if update.effective_user else None
            return bool(uid and admin_svc and admin_svc.is_admin(uid))
        except Exception:
            return False

    state = services["user"].state
    qsvc = services["questionnaire"]
    schedule = services["schedule"]
    lesson_repo = schedule.lesson
    quest_repo = schedule.quest

    # ----------------------------
    # Navigation helpers
    # ----------------------------
    def _set_menu(uid: int, screen: str, extra: dict | None = None):
        payload = {"screen": screen}
        if extra:
            payload.update(extra)
        state.set_state(uid, ADMIN_MENU_STEP, payload)

    async def _show_main_menu(update: Update):
        uid = update.effective_user.id
        await update.effective_message.reply_text(
            "Главное меню 👇",
            reply_markup=menus.kb_main(bool(admin_svc and admin_svc.is_admin(uid))),
        )

    async def _show_admin_home(update: Update):
        uid = update.effective_user.id
        _set_menu(uid, "home")
        await update.effective_message.reply_text("🛠 Админка", reply_markup=kb_admin_home())

    async def _show_lessons_menu(update: Update):
        uid = update.effective_user.id
        _set_menu(uid, "lessons")
        await update.effective_message.reply_text("📚 Лекции", reply_markup=kb_admin_actions(False))

    async def _show_quests_menu(update: Update):
        uid = update.effective_user.id
        _set_menu(uid, "quests")
        await update.effective_message.reply_text("📝 Задания", reply_markup=kb_admin_actions(False))

    async def _show_q_menu(update: Update):
        uid = update.effective_user.id
        _set_menu(uid, "questionnaires")
        await update.effective_message.reply_text("📋 Анкеты", reply_markup=kb_admin_actions(True))

    async def _show_analytics_menu(update: Update, days: int = 7):
        uid = update.effective_user.id
        safe_days = 7
        try:
            safe_days = int(days)
        except Exception:
            safe_days = 7
        if safe_days not in (1, 7, 30):
            safe_days = 7
        _set_menu(uid, "analytics", {"days": safe_days})
        label = "Сегодня" if safe_days == 1 else f"Последние {safe_days} дней"
        await update.effective_message.reply_text(
            f"📈 Аналитика\nПериод: {label}\n\nВыбери отчёт:",
            reply_markup=kb_admin_analytics(),
        )

    def _safe_tickets_mode(value: str | None) -> str:
        return "all" if (value or "").strip().lower() == "all" else "open"

    def _safe_tickets_limit(value) -> int:
        try:
            n = int(value)
        except Exception:
            n = 20
        return max(1, min(100, n))

    def _tickets_list_text(rows: list[dict], mode: str, limit: int, include_commands: bool) -> str:
        mode_label = "только open" if mode == "open" else "все"
        if not rows:
            return f"🆘 Тикеты ({mode_label}, limit={limit})\n\nТикетов не найдено."

        lines = [f"🆘 Тикеты ({mode_label}, limit={limit})", ""]
        lines.extend(_ticket_preview(r) for r in rows)
        if include_commands:
            lines.extend(
                [
                    "",
                    "Команды:",
                    "/ticket <id>",
                    "/reply_ticket <id> <текст>",
                ]
            )
        return "\n".join(lines)

    async def _send_tickets_list(
        update: Update,
        mode: str = "open",
        limit: int = 20,
        include_commands: bool = False,
        reply_markup=None,
    ):
        if not support_svc:
            await update.effective_message.reply_text("⚠️ Сервис поддержки не подключён.", reply_markup=reply_markup)
            return
        safe_mode = _safe_tickets_mode(mode)
        safe_limit = _safe_tickets_limit(limit)
        rows = support_svc.list_open(limit=safe_limit) if safe_mode == "open" else support_svc.list_all(limit=safe_limit)
        text = _tickets_list_text(rows, safe_mode, safe_limit, include_commands)
        await update.effective_message.reply_text(text, reply_markup=reply_markup)

    async def _show_tickets_menu(update: Update, mode: str = "open", limit: int = 20):
        uid = update.effective_user.id
        safe_mode = _safe_tickets_mode(mode)
        safe_limit = _safe_tickets_limit(limit)
        _set_menu(uid, "tickets", {"mode": safe_mode, "limit": safe_limit})
        await _send_tickets_list(
            update,
            mode=safe_mode,
            limit=safe_limit,
            include_commands=False,
            reply_markup=kb_admin_tickets(),
        )

    def _ticket_status_label(status: str | None) -> str:
        s = (status or "").strip().lower()
        if s == "open":
            return "🟡 open"
        if s == "closed":
            return "✅ closed"
        return s or "-"

    def _ticket_preview(row: dict) -> str:
        txt = (row.get("question_text") or "").replace("\n", " ").strip()
        if len(txt) > 70:
            txt = txt[:67] + "..."
        return (
            f"• #{row.get('id')} [{_ticket_status_label(row.get('status'))}] "
            f"user={row.get('user_id')} — {txt}"
        )

    def _ticket_details(row: dict) -> str:
        base = [
            f"🆘 Тикет #{row.get('id')}",
            f"Статус: {_ticket_status_label(row.get('status'))}",
            f"user_id: {row.get('user_id')}",
            f"Создан: {row.get('created_at')}",
            "",
            "Сообщение:",
            str(row.get("question_text") or "-"),
        ]
        reply = (row.get("admin_reply") or "").strip()
        if reply:
            base.extend(
                [
                    "",
                    f"Ответ админа ({row.get('admin_id')}):",
                    reply,
                ]
            )
        return "\n".join(base)

    # ----------------------------
    # Entry points
    # ----------------------------
    async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            await update.effective_message.reply_text("⛔️ У вас нет прав для доступа к этой команде.")
            return
        await _show_admin_home(update)

    async def open_admin_from_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            await update.effective_message.reply_text("⛔️ Только для админов.")
            return
        await _show_admin_home(update)
        raise ApplicationHandlerStop

    async def cmd_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            await update.effective_message.reply_text("⛔️ Только для админов.")
            return
        mode = "open"
        limit = 20
        for arg in context.args or []:
            a = (arg or "").strip().lower()
            if a in ("open", "all"):
                mode = a
                continue
            if a.isdigit():
                try:
                    limit = max(1, min(100, int(a)))
                except Exception:
                    pass
        await _send_tickets_list(update, mode=mode, limit=limit, include_commands=True)

    async def cmd_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            await update.effective_message.reply_text("⛔️ Только для админов.")
            return
        if not support_svc:
            await update.effective_message.reply_text("⚠️ Сервис поддержки не подключён.")
            return
        if not context.args:
            await update.effective_message.reply_text("Использование: /ticket <id>")
            return
        raw_id = (context.args[0] or "").strip()
        if not raw_id.isdigit():
            await update.effective_message.reply_text("ID должен быть числом.")
            return
        row = support_svc.get(int(raw_id))
        if not row:
            await update.effective_message.reply_text("Тикет не найден.")
            return
        await update.effective_message.reply_text(_ticket_details(row))

    async def _reply_ticket_and_notify(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        ticket_id: int,
        reply_text: str,
        *,
        reply_markup=None,
    ) -> bool:
        row = support_svc.reply_and_close(
            ticket_id=int(ticket_id),
            admin_id=update.effective_user.id,
            reply_text=reply_text,
        )
        if not row:
            await update.effective_message.reply_text(
                "Не смог закрыть тикет. Возможно, он уже закрыт или не существует.",
                reply_markup=reply_markup,
            )
            return False

        user_id = int(row.get("user_id") or 0)
        user_msg = f"💬 Ответ поддержки по тикету #{int(ticket_id)}:\n{reply_text}"
        sent_ok = True
        try:
            await context.bot.send_message(chat_id=user_id, text=user_msg)
        except Exception:
            sent_ok = False

        tail = "" if sent_ok else "\n⚠️ Пользователю отправить не удалось (проверь chat доступность)."
        await update.effective_message.reply_text(
            f"✅ Тикет #{int(ticket_id)} закрыт и обработан.{tail}",
            reply_markup=reply_markup,
        )
        return True

    async def cmd_reply_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            await update.effective_message.reply_text("⛔️ Только для админов.")
            return
        if not support_svc:
            await update.effective_message.reply_text("⚠️ Сервис поддержки не подключён.")
            return
        if not context.args or len(context.args) < 2:
            await update.effective_message.reply_text("Использование: /reply_ticket <id> <текст ответа>")
            return

        raw_id = (context.args[0] or "").strip()
        if not raw_id.isdigit():
            await update.effective_message.reply_text("ID должен быть числом.")
            return
        tid = int(raw_id)
        reply_text = " ".join(context.args[1:]).strip()
        if not reply_text:
            await update.effective_message.reply_text("Ответ не должен быть пустым.")
            return
        await _reply_ticket_and_notify(update, context, tid, reply_text)

    # ----------------------------
    # Actions (reply-based)
    # ----------------------------
    async def lessons_list(update: Update):
        items = lesson_repo.list_latest(200)
        if not items:
            await update.effective_message.reply_text("📚 Лекции: пока пусто.", reply_markup=kb_admin_actions(False))
            return
        lines = ["📚 *Лекции* (день → баллы)"]
        for it in items:
            lines.append(f"• день *{it['day_index']}* — +{it['points_viewed']} балл(ов) — {it['title']}")
        await update.effective_message.reply_text(
            "\n".join(lines), parse_mode="Markdown", reply_markup=kb_admin_actions(False)
        )

    async def lessons_create(update: Update):
        uid = update.effective_user.id
        state.set_state(uid, ADMIN_WIZARD_STEP, {"mode": "l_create_day"})
        await update.effective_message.reply_text("➕ Создание лекции\n\nВведи номер дня (целое число), например: 1")

    async def lessons_edit(update: Update):
        uid = update.effective_user.id
        state.set_state(uid, ADMIN_WIZARD_STEP, {"mode": "l_edit_day"})
        await update.effective_message.reply_text("✏️ Редактирование лекции\n\nВведи номер дня (целое число), например: 1")

    async def lessons_delete(update: Update):
        uid = update.effective_user.id
        state.set_state(uid, ADMIN_WIZARD_STEP, {"mode": "l_delete_day"})
        await update.effective_message.reply_text("🗑 Удаление лекции\n\nВведи номер дня (целое число), например: 1")

    async def quests_list(update: Update):
        items = quest_repo.list_latest(200)
        if not items:
            await update.effective_message.reply_text("📝 Задания: пока пусто.", reply_markup=kb_admin_actions(False))
            return
        lines = ["📝 *Задания* (день → баллы)"]
        for it in items:
            pts = _extract_quest_points(it)
            prompt = (it.get("prompt") or "").replace("\n", " ")
            if len(prompt) > 60:
                prompt = prompt[:57] + "..."
            lines.append(f"• день *{it['day_index']}* — +{pts} балл(ов) — {prompt}")
        await update.effective_message.reply_text(
            "\n".join(lines), parse_mode="Markdown", reply_markup=kb_admin_actions(False)
        )

    async def quests_create(update: Update):
        uid = update.effective_user.id
        state.set_state(uid, ADMIN_WIZARD_STEP, {"mode": "qst_create_day"})
        await update.effective_message.reply_text("➕ Создание задания\n\nВведи номер дня (целое число), например: 1")

    async def quests_edit(update: Update):
        uid = update.effective_user.id
        state.set_state(uid, ADMIN_WIZARD_STEP, {"mode": "qst_edit_day"})
        await update.effective_message.reply_text("✏️ Редактирование задания\n\nВведи номер дня (целое число), например: 1")

    async def quests_delete(update: Update):
        uid = update.effective_user.id
        state.set_state(uid, ADMIN_WIZARD_STEP, {"mode": "qst_delete_day"})
        await update.effective_message.reply_text("🗑 Удаление задания\n\nВведи номер дня (целое число), например: 1")

    async def q_list(update: Update):
        items = qsvc.list_latest(50)
        if not items:
            await update.effective_message.reply_text("📋 Анкеты: пока пусто.", reply_markup=kb_admin_actions(True))
            return
        lines = ["📋 *Анкеты* (id → баллы, диаграммы)"]
        for it in items:
            qid = it["id"]
            pts = int(it.get("points") or 0)
            charts = "да" if it.get("use_in_charts") else "нет"
            q = it.get("question") or ""
            if len(q) > 70:
                q = q[:67] + "..."
            lines.append(f"• *{qid}* — +{pts} — charts={charts} — {q}")
        await update.effective_message.reply_text(
            "\n".join(lines), parse_mode="Markdown", reply_markup=kb_admin_actions(True)
        )

    async def q_create(update: Update):
        uid = update.effective_user.id
        state.set_state(uid, ADMIN_WIZARD_STEP, {"mode": "q_create_question"})
        await update.effective_message.reply_text("➕ Создание анкеты\n\nВведи вопрос анкеты одним сообщением.")

    async def q_edit(update: Update):
        uid = update.effective_user.id
        state.set_state(uid, ADMIN_WIZARD_STEP, {"mode": "q_edit_id"})
        await update.effective_message.reply_text("✏️ Редактирование анкеты\n\nВведи ID анкеты (число).")

    async def q_delete(update: Update):
        uid = update.effective_user.id
        state.set_state(uid, ADMIN_WIZARD_STEP, {"mode": "q_delete_id"})
        await update.effective_message.reply_text("🗑 Удаление анкеты\n\nВведи ID анкеты (число).")

    async def q_random(update: Update):
        uid = update.effective_user.id
        state.set_state(uid, ADMIN_WIZARD_STEP, {"mode": "qcast_question"})
        await update.effective_message.reply_text("🎲 Рандомная анкета всем\n\nВведи вопрос анкеты одним сообщением.")

    # ----------------------------
    # Reply-based menu router
    # ----------------------------
    async def admin_menu_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            return

        text = (update.effective_message.text or "").strip()
        if not text or text.startswith("/"):
            return

        uid = update.effective_user.id
        st = state.get_state(uid) or {}

        # If we're in wizard, don't handle anything here.
        # wizard_text (group=-10) will handle Back and input.
        if st.get("step") == ADMIN_WIZARD_STEP:
            return

        # This handler should be active only while admin menu state is active.
        # If state is not admin_menu, let other routers handle the message.
        if st.get("step") != ADMIN_MENU_STEP:
            return

        # Allow re-opening admin home from the main menu button while state is active.
        if text == texts.MENU_ADMIN:
            await _show_admin_home(update)
            raise ApplicationHandlerStop

        # If user clicks a MAIN menu button while still in admin state, exit admin
        # and let the main router handle it.
        if text in (texts.MENU_DAY, texts.MENU_PROGRESS, texts.MENU_SETTINGS, texts.MENU_HELP):
            state.clear_state(uid)
            return
        payload = st.get("payload_json") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        screen = payload.get("screen")

        # Back inside admin menu:
        #   lessons/quests/questionnaires/analytics -> admin home
        #   home -> main menu
        # (Wizard has its own Back in wizard_text.)
        if text == texts.BTN_BACK:
            screen0 = (screen or "home").lower()

            if screen0 in ("lessons", "quests", "questionnaires", "analytics", "tickets"):
                await _show_admin_home(update)
                raise ApplicationHandlerStop

            # home (or unknown) -> exit to main menu
            state.clear_state(uid)
            await _show_main_menu(update)
            raise ApplicationHandlerStop

        if screen in ("home", "library"):
            if text == texts.ADMIN_LESSONS:
                await _show_lessons_menu(update); raise ApplicationHandlerStop
            if text == texts.ADMIN_QUESTS:
                await _show_quests_menu(update); raise ApplicationHandlerStop
            if text == texts.ADMIN_QUESTIONNAIRES:
                await _show_q_menu(update); raise ApplicationHandlerStop
            if text == texts.ADMIN_ANALYTICS:
                await _show_analytics_menu(update, 7); raise ApplicationHandlerStop
            if text == texts.ADMIN_TICKETS:
                await _show_tickets_menu(update, "open", 20); raise ApplicationHandlerStop

        if screen == "analytics":
            payload0 = payload or {}
            days = 7
            try:
                days = int(payload0.get("days") or 7)
            except Exception:
                days = 7
            if text == BTN_PERIOD_TODAY:
                await _show_analytics_menu(update, 1); raise ApplicationHandlerStop
            if text == BTN_PERIOD_7:
                await _show_analytics_menu(update, 7); raise ApplicationHandlerStop
            if text == BTN_PERIOD_30:
                await _show_analytics_menu(update, 30); raise ApplicationHandlerStop

            if not admin_analytics:
                await update.effective_message.reply_text("⚠️ Сервис аналитики не подключён.", reply_markup=kb_admin_analytics())
                raise ApplicationHandlerStop

            if text == BTN_A_SUMMARY:
                await update.effective_message.reply_text(admin_analytics.summary_report(days), reply_markup=kb_admin_analytics())
                raise ApplicationHandlerStop
            if text == BTN_A_FUNNEL:
                await update.effective_message.reply_text(admin_analytics.funnel_report(days), reply_markup=kb_admin_analytics())
                raise ApplicationHandlerStop
            if text == BTN_A_DELIVERY:
                await update.effective_message.reply_text(admin_analytics.delivery_report(days), reply_markup=kb_admin_analytics())
                raise ApplicationHandlerStop
            if text == BTN_A_CONTENT:
                await update.effective_message.reply_text(admin_analytics.content_report(days), reply_markup=kb_admin_analytics())
                raise ApplicationHandlerStop
            if text == BTN_A_QUESTIONNAIRES:
                await update.effective_message.reply_text(admin_analytics.questionnaires_report(days), reply_markup=kb_admin_analytics())
                raise ApplicationHandlerStop
            if text == BTN_A_REMINDERS:
                await update.effective_message.reply_text(admin_analytics.reminders_report(days), reply_markup=kb_admin_analytics())
                raise ApplicationHandlerStop

        if screen == "lessons":
            if text == BTN_LIST: await lessons_list(update); raise ApplicationHandlerStop
            if text == BTN_CREATE: await lessons_create(update); raise ApplicationHandlerStop
            if text == BTN_EDIT: await lessons_edit(update); raise ApplicationHandlerStop
            if text == BTN_DELETE: await lessons_delete(update); raise ApplicationHandlerStop

        if screen == "quests":
            if text == BTN_LIST: await quests_list(update); raise ApplicationHandlerStop
            if text == BTN_CREATE: await quests_create(update); raise ApplicationHandlerStop
            if text == BTN_EDIT: await quests_edit(update); raise ApplicationHandlerStop
            if text == BTN_DELETE: await quests_delete(update); raise ApplicationHandlerStop

        if screen == "questionnaires":
            if text == BTN_LIST: await q_list(update); raise ApplicationHandlerStop
            if text == BTN_CREATE: await q_create(update); raise ApplicationHandlerStop
            if text == BTN_EDIT: await q_edit(update); raise ApplicationHandlerStop
            if text == BTN_DELETE: await q_delete(update); raise ApplicationHandlerStop
            if text == BTN_RANDOM_Q: await q_random(update); raise ApplicationHandlerStop

        if screen == "tickets":
            payload0 = payload or {}
            mode = _safe_tickets_mode(payload0.get("mode"))
            limit = _safe_tickets_limit(payload0.get("limit"))

            if text == BTN_T_OPEN:
                await _show_tickets_menu(update, "open", limit); raise ApplicationHandlerStop
            if text == BTN_T_ALL:
                await _show_tickets_menu(update, "all", limit); raise ApplicationHandlerStop
            if text == BTN_T_VIEW:
                state.set_state(
                    uid,
                    ADMIN_WIZARD_STEP,
                    {"mode": "t_view_id", "return_mode": mode, "return_limit": limit},
                )
                await update.effective_message.reply_text("Введи ID тикета (число).")
                raise ApplicationHandlerStop
            if text == BTN_T_REPLY:
                state.set_state(
                    uid,
                    ADMIN_WIZARD_STEP,
                    {"mode": "t_reply_id", "return_mode": mode, "return_limit": limit},
                )
                await update.effective_message.reply_text("Введи ID тикета, на который нужно ответить.")
                raise ApplicationHandlerStop
            if text == BTN_T_CLOSE:
                state.set_state(
                    uid,
                    ADMIN_WIZARD_STEP,
                    {"mode": "t_close_id", "return_mode": mode, "return_limit": limit},
                )
                await update.effective_message.reply_text("Введи ID тикета, который нужно закрыть.")
                raise ApplicationHandlerStop

        # Stop further handlers while admin menu is active.
        raise ApplicationHandlerStop

    # ----------------------------
    # Wizard text (adapted from previous implementation; reply keyboards only)
    # ----------------------------
    async def wizard_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            return
        text = (update.effective_message.text or "").strip()
        if not text or text.startswith("/"):
            return
        uid = update.effective_user.id
        st = state.get_state(uid)

        # ✅ Wizard handler must only run when we are really inside the wizard.
        if not st or st.get("step") != ADMIN_WIZARD_STEP:
            return

        # Allow leaving wizard with Back
        if text == texts.BTN_BACK:
            payload0 = st.get("payload_json") or {}
            if isinstance(payload0, str):
                try:
                    payload0 = json.loads(payload0)
                except Exception:
                    payload0 = {}
            mode0 = (payload0.get("mode") or "").lower()

            state.clear_state(uid)

            # Return to the appropriate admin menu
            if mode0.startswith("l_"):
                await _show_lessons_menu(update)
            elif mode0.startswith("qst_"):
                await _show_quests_menu(update)
            elif mode0.startswith("q_") or mode0.startswith("qcast_"):
                await _show_q_menu(update)
            elif mode0.startswith("t_"):
                back_mode = _safe_tickets_mode(payload0.get("return_mode"))
                back_limit = _safe_tickets_limit(payload0.get("return_limit"))
                await _show_tickets_menu(update, back_mode, back_limit)
            else:
                await _show_admin_home(update)
            raise ApplicationHandlerStop
        payload = st["payload_json"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        mode = payload.get("mode")

        # --- Lessons wizard ---
        if mode in ("l_create_day", "l_edit_day", "l_delete_day"):
            if not re.match(r"^\d+$", text):
                await update.effective_message.reply_text("Нужен номер дня (число)."); raise ApplicationHandlerStop
            day = int(text)
            if mode == "l_delete_day":
                ok = lesson_repo.delete_day(day)
                state.clear_state(update.effective_user.id)
                await _show_lessons_menu(update)
                await update.effective_message.reply_text("✅ Удалено" if ok else "⚠️ Не найдено")
                return
            existing = lesson_repo.get_by_day(day)
            payload = {"mode": "l_title", "day_index": day}
            state.set_state(update.effective_user.id, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text(
                f"День {day}. Введи название лекции." + (f"\nТекущее: {existing['title']}" if existing else ""))
            return

        if mode == "l_title":
            payload["title"] = text
            payload["mode"] = "l_desc"
            state.set_state(update.effective_user.id, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text("Введи описание лекции (текст).")
            return

        if mode == "l_desc":
            payload["description"] = text
            payload["mode"] = "l_video"
            state.set_state(update.effective_user.id, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text("Вставь ссылку на видео (Rutube/YouTube и т.п.).")
            return

        if mode == "l_video":
            if not (text.startswith("http://") or text.startswith("https://")):
                await update.effective_message.reply_text("Нужна ссылка, которая начинается с http:// или https://"); raise ApplicationHandlerStop
            payload["video_url"] = text
            payload["mode"] = "l_points"
            state.set_state(update.effective_user.id, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text("Сколько баллов за кнопку «Просмотрено»? (целое число)")
            return

        if mode == "l_points":
            if not re.match(r"^\d+$", text):
                await update.effective_message.reply_text("Нужно целое число, например: 1"); raise ApplicationHandlerStop
            day = int(payload["day_index"])
            lesson_repo.upsert_lesson(day, payload["title"], payload["description"], payload["video_url"], int(text))
            state.clear_state(update.effective_user.id)
            await _show_lessons_menu(update)
            await update.effective_message.reply_text("✅ Сохранено.")
            return

        # --- Quests wizard ---
        if mode in ("qst_create_day", "qst_edit_day", "qst_delete_day"):
            if not re.match(r"^\d+$", text):
                await update.effective_message.reply_text("Нужен номер дня (число)."); raise ApplicationHandlerStop
            day = int(text)
            if mode == "qst_delete_day":
                ok = quest_repo.delete_day(day)
                state.clear_state(update.effective_user.id)
                await _show_quests_menu(update)
                await update.effective_message.reply_text("✅ Удалено" if ok else "⚠️ Не найдено")
                return
            existing = quest_repo.get_by_day(day)
            payload = {"mode": "qst_prompt", "day_index": day}
            state.set_state(update.effective_user.id, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text(
                f"День {day}. Введи текст задания." + (f"\nТекущее: {existing['prompt']}" if existing else ""))
            return

        if mode == "qst_prompt":
            payload["prompt"] = text
            payload["mode"] = "qst_points"
            state.set_state(update.effective_user.id, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text("Сколько баллов за ответ на задание? (целое число)")
            return

        if mode == "qst_points":
            if not re.match(r"^\d+$", text):
                await update.effective_message.reply_text("Нужно целое число, например: 1"); raise ApplicationHandlerStop
            day = int(payload["day_index"])
            try:
                quest_repo.upsert_quest(day, int(text), payload["prompt"], payload.get("photo_file_id"))
            except Exception:
                await update.effective_message.reply_text("⚠️ Упс, ошибка. Попробуй ещё раз.")
                raise ApplicationHandlerStop
            state.clear_state(update.effective_user.id)
            await _show_quests_menu(update)
            await update.effective_message.reply_text("✅ Сохранено.")
            return

        # --- Questionnaire wizard (create/edit/delete) ---
        if mode == "q_create_question":
            payload = {"mode": "q_create_charts", "question": text}
            state.set_state(update.effective_user.id, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text("Учитывать в диаграммах? (Да/Нет)", reply_markup=kb_yes_no())
            return

        if mode == "q_create_charts":
            t = text.lower()
            if t not in ("да", "нет"):
                await update.effective_message.reply_text("Нужно 'Да' или 'Нет'.", reply_markup=kb_yes_no()); raise ApplicationHandlerStop
            payload["use_in_charts"] = (t == "да")
            payload["mode"] = "q_create_points"
            state.set_state(update.effective_user.id, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text("Сколько баллов за прохождение? (целое число)")
            return

        if mode == "q_create_points":
            if not re.match(r"^\d+$", text):
                await update.effective_message.reply_text("Нужно целое число, например: 1"); raise ApplicationHandlerStop
            qid = qsvc.create(payload["question"], "manual", bool(payload["use_in_charts"]), int(text), update.effective_user.id)
            item = qsvc.get(qid)
            state.clear_state(update.effective_user.id)
            await _show_q_menu(update)
            await update.effective_message.reply_text(f"✅ Анкета создана. ID={qid}.\nВопрос: {item['question']}")
            return

        if mode == "q_edit_id":
            if not re.match(r"^\d+$", text):
                await update.effective_message.reply_text("Нужен ID анкеты (число)."); raise ApplicationHandlerStop
            qid = int(text)
            item = qsvc.get(qid)
            if not item:
                await update.effective_message.reply_text("⚠️ Анкета не найдена."); raise ApplicationHandlerStop
            payload = {"mode": "q_edit_question", "id": qid}
            state.set_state(update.effective_user.id, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text(f"Текущий вопрос:\n{item['question']}\n\nВведи новый вопрос.")
            return

        if mode == "q_edit_question":
            payload["question"] = text
            payload["mode"] = "q_edit_charts"
            state.set_state(update.effective_user.id, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text("Учитывать в диаграммах? (Да/Нет)", reply_markup=kb_yes_no())
            return

        if mode == "q_edit_charts":
            t = text.lower()
            if t not in ("да", "нет"):
                await update.effective_message.reply_text("Нужно 'Да' или 'Нет'.", reply_markup=kb_yes_no()); raise ApplicationHandlerStop
            payload["use_in_charts"] = (t == "да")
            payload["mode"] = "q_edit_points"
            state.set_state(update.effective_user.id, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text("Сколько баллов? (целое число)")
            return

        if mode == "q_edit_points":
            if not re.match(r"^\d+$", text):
                await update.effective_message.reply_text("Нужно целое число, например: 1"); raise ApplicationHandlerStop
            qid = int(payload["id"])
            qsvc.update(qid, payload["question"], "manual", bool(payload["use_in_charts"]), int(text))
            state.clear_state(update.effective_user.id)
            await _show_q_menu(update)
            await update.effective_message.reply_text("✅ Анкета обновлена.")
            return

        if mode == "q_delete_id":
            if not re.match(r"^\d+$", text):
                await update.effective_message.reply_text("Нужен ID анкеты (число)."); raise ApplicationHandlerStop
            ok = qsvc.delete(int(text))
            state.clear_state(update.effective_user.id)
            await _show_q_menu(update)
            await update.effective_message.reply_text("✅ Удалено" if ok else "⚠️ Не найдено")
            return

        # --- Tickets wizard ---
        if mode == "t_view_id":
            if not re.match(r"^\d+$", text):
                await update.effective_message.reply_text("ID должен быть числом."); raise ApplicationHandlerStop
            tid = int(text)
            return_mode = _safe_tickets_mode(payload.get("return_mode"))
            return_limit = _safe_tickets_limit(payload.get("return_limit"))
            _set_menu(uid, "tickets", {"mode": return_mode, "limit": return_limit})
            if not support_svc:
                await update.effective_message.reply_text("⚠️ Сервис поддержки не подключён.", reply_markup=kb_admin_tickets())
                return
            row = support_svc.get(tid)
            if not row:
                await update.effective_message.reply_text("Тикет не найден.", reply_markup=kb_admin_tickets())
                return
            await update.effective_message.reply_text(_ticket_details(row), reply_markup=kb_admin_tickets())
            return

        if mode == "t_reply_id":
            if not re.match(r"^\d+$", text):
                await update.effective_message.reply_text("ID должен быть числом."); raise ApplicationHandlerStop
            if not support_svc:
                _set_menu(uid, "tickets", {"mode": _safe_tickets_mode(payload.get("return_mode")), "limit": _safe_tickets_limit(payload.get("return_limit"))})
                await update.effective_message.reply_text("⚠️ Сервис поддержки не подключён.", reply_markup=kb_admin_tickets())
                return
            tid = int(text)
            row = support_svc.get(tid)
            if not row:
                await update.effective_message.reply_text("Тикет не найден."); raise ApplicationHandlerStop
            payload["ticket_id"] = tid
            payload["mode"] = "t_reply_text"
            state.set_state(uid, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text(f"Тикет #{tid}.\nВведи текст ответа пользователю.")
            return

        if mode == "t_reply_text":
            tid = int(payload.get("ticket_id") or 0)
            reply_text = text.strip()
            if tid <= 0:
                _set_menu(uid, "tickets", {"mode": _safe_tickets_mode(payload.get("return_mode")), "limit": _safe_tickets_limit(payload.get("return_limit"))})
                await update.effective_message.reply_text("⚠️ Потерян ID тикета. Открой действие заново.", reply_markup=kb_admin_tickets())
                return
            if not reply_text:
                await update.effective_message.reply_text("Ответ не должен быть пустым."); raise ApplicationHandlerStop
            return_mode = _safe_tickets_mode(payload.get("return_mode"))
            return_limit = _safe_tickets_limit(payload.get("return_limit"))
            _set_menu(uid, "tickets", {"mode": return_mode, "limit": return_limit})
            await _reply_ticket_and_notify(
                update,
                context,
                tid,
                reply_text,
                reply_markup=kb_admin_tickets(),
            )
            return

        if mode == "t_close_id":
            if not re.match(r"^\d+$", text):
                await update.effective_message.reply_text("ID должен быть числом."); raise ApplicationHandlerStop
            tid = int(text)
            return_mode = _safe_tickets_mode(payload.get("return_mode"))
            return_limit = _safe_tickets_limit(payload.get("return_limit"))
            _set_menu(uid, "tickets", {"mode": return_mode, "limit": return_limit})
            if not support_svc:
                await update.effective_message.reply_text("⚠️ Сервис поддержки не подключён.", reply_markup=kb_admin_tickets())
                return
            row = support_svc.close(tid, update.effective_user.id)
            if not row:
                await update.effective_message.reply_text(
                    "Не смог закрыть тикет. Возможно, он уже закрыт или не существует.",
                    reply_markup=kb_admin_tickets(),
                )
                return
            await update.effective_message.reply_text(f"✅ Тикет #{tid} закрыт.", reply_markup=kb_admin_tickets())
            return

        # --- Broadcast random questionnaire to all ---
        if mode == "qcast_question":
            payload = {"mode": "qcast_charts", "question": text}
            state.set_state(update.effective_user.id, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text("Учитывать в диаграммах? (Да/Нет)", reply_markup=kb_yes_no())
            return

        if mode == "qcast_charts":
            t = text.lower()
            if t not in ("да", "нет"):
                await update.effective_message.reply_text("Нужно 'Да' или 'Нет'.", reply_markup=kb_yes_no()); raise ApplicationHandlerStop
            payload["use_in_charts"] = (t == "да")
            payload["mode"] = "qcast_points"
            state.set_state(update.effective_user.id, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text("Сколько баллов за прохождение? (целое число)")
            return

        if mode == "qcast_points":
            if not re.match(r"^\d+$", text):
                await update.effective_message.reply_text("Нужно целое число, например: 1"); raise ApplicationHandlerStop
            payload["points"] = int(text)
            payload["mode"] = "qcast_time"
            state.set_state(update.effective_user.id, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text("Во сколько отправить всем? (ЧЧ:ММ)")
            return

        if mode == "qcast_time":
            if not re.match(r"^\d{1,2}:\d{2}$", text):
                await update.effective_message.reply_text("Формат времени: ЧЧ:ММ"); raise ApplicationHandlerStop
            hh_i, mm_i = [int(x) for x in text.split(":")]
            if not (0 <= hh_i <= 23 and 0 <= mm_i <= 59):
                await update.effective_message.reply_text("Некорректное время."); raise ApplicationHandlerStop
            hhmm = f"{hh_i:02d}:{mm_i:02d}"

            qid = qsvc.create(payload["question"], "manual", bool(payload["use_in_charts"]), int(payload["points"]), update.effective_user.id)
            created = schedule.schedule_questionnaire_broadcast(qid, hhmm)
            state.clear_state(update.effective_user.id)
            await _show_q_menu(update)
            await update.effective_message.reply_text(f"✅ Запланировано. Анкета ID={qid}. Получателей: {created}")
            return

        raise ApplicationHandlerStop

    # ----------------------------
    # Register handlers
    # ----------------------------
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("tickets", cmd_tickets))
    app.add_handler(CommandHandler("ticket", cmd_ticket))
    app.add_handler(CommandHandler("reply_ticket", cmd_reply_ticket))
    app.add_handler(MessageHandler(filters.Regex(rf"^{re.escape(texts.MENU_ADMIN)}$"), open_admin_from_menu))
    # Admin menu navigation (reply buttons)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_pick), group=-11)
    # Wizard input
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, wizard_text), group=-10)
