import re
import json
import logging
from datetime import datetime
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
BTN_A_STATS = "📊 Статистика"

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
            [KeyboardButton(texts.ADMIN_ACHIEVEMENTS), KeyboardButton(texts.ADMIN_TICKETS)],
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
            [KeyboardButton(BTN_A_STATS)],
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
    achievement_svc = services.get("achievement")

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

    async def _show_achievements_menu(update: Update):
        uid = update.effective_user.id
        _set_menu(uid, "achievements")
        await update.effective_message.reply_text("🏆 Ачивки", reply_markup=kb_admin_actions(False))

    ACH_METRIC_OPTIONS = [
        ("Баллы", "points"),
        ("Завершенные дни", "done_days"),
        ("Серия дней", "streak"),
        ("Привычки выполнено", "habit_done"),
        ("Привычки пропущено", "habit_skipped"),
        ("Анкет заполнено", "questionnaire_count"),
    ]
    ACH_OPERATOR_OPTIONS = [
        ("не меньше", ">="),
        ("больше", ">"),
        ("равно", "="),
        ("не больше", "<="),
        ("меньше", "<"),
    ]
    OPERATOR_TOKEN = {
        ">=": "ge",
        ">": "gt",
        "=": "eq",
        "<=": "le",
        "<": "lt",
    }

    def _achievement_metrics_hint() -> str:
        lines = ["Доступные метрики:"]
        for i, (label, key) in enumerate(ACH_METRIC_OPTIONS, 1):
            lines.append(f"{i}. {label} ({key})")
        lines.append("Введи номер или название.")
        return "\n".join(lines)

    def _achievement_operators_hint() -> str:
        lines = ["Доступные операторы:"]
        for i, (label, sym) in enumerate(ACH_OPERATOR_OPTIONS, 1):
            lines.append(f"{i}. {label} ({sym})")
        lines.append("Введи номер или оператор.")
        return "\n".join(lines)

    def _metric_label_by_key(metric_key: str) -> str:
        key = (metric_key or "").strip()
        for label, val in ACH_METRIC_OPTIONS:
            if val == key:
                return label
        return key or "-"

    def _operator_label_by_symbol(operator: str) -> str:
        op = (operator or "").strip()
        for label, val in ACH_OPERATOR_OPTIONS:
            if val == op:
                return label
        return op or "-"

    def _parse_metric_key(text: str) -> str | None:
        raw = (text or "").strip()
        if not raw:
            return None
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(ACH_METRIC_OPTIONS):
                return ACH_METRIC_OPTIONS[idx - 1][1]
        low = raw.lower()
        for label, key in ACH_METRIC_OPTIONS:
            if low in (label.lower(), key.lower()):
                return key
        return None

    def _parse_operator_symbol(text: str) -> str | None:
        raw = (text or "").strip()
        if not raw:
            return None
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(ACH_OPERATOR_OPTIONS):
                return ACH_OPERATOR_OPTIONS[idx - 1][1]
        low = raw.lower()
        for label, sym in ACH_OPERATOR_OPTIONS:
            if raw == sym or low == label.lower():
                return sym
        return None

    @staticmethod
    def _slugify_ascii(raw: str) -> str:
        s = (raw or "").strip().lower()
        s = re.sub(r"[^a-z0-9]+", "_", s)
        s = re.sub(r"_+", "_", s).strip("_")
        return s

    def _next_achievement_sort_order() -> int:
        if not achievement_svc:
            return 100
        try:
            rows = achievement_svc.list_rules(limit=500, active_only=None) or []
        except Exception:
            return 100
        max_sort = 0
        for row in rows:
            try:
                max_sort = max(max_sort, int(row.get("sort_order") or 0))
            except Exception:
                pass
        if max_sort <= 0:
            return 10
        return ((max_sort // 10) + 1) * 10

    def _generate_achievement_code(title: str, metric_key: str, operator: str, threshold: int) -> str:
        base_title = _slugify_ascii(title)[:24]
        op_token = OPERATOR_TOKEN.get(operator, "eq")
        tail = f"{metric_key}_{op_token}_{abs(int(threshold))}"
        if base_title:
            base = f"{base_title}_{tail}"
        else:
            base = f"ach_{tail}"
        base = re.sub(r"_+", "_", base).strip("_")
        if len(base) < 3:
            base = "ach_rule"
        base = base[:64].strip("_")

        if not achievement_svc:
            return base
        try:
            rows = achievement_svc.list_rules(limit=1000, active_only=None) or []
            existing = {str(r.get("code") or "").strip().lower() for r in rows}
        except Exception:
            existing = set()
        if base.lower() not in existing:
            return base
        for i in range(2, 1000):
            suffix = f"_{i}"
            cand = base
            if len(cand) + len(suffix) > 64:
                cand = cand[: 64 - len(suffix)].rstrip("_")
            cand = f"{cand}{suffix}"
            if cand.lower() not in existing:
                return cand
        return f"ach_{int(datetime.now().timestamp())}"

    def _parse_yes_no(text: str) -> bool | None:
        value = (text or "").strip().lower()
        if value in ("да", "yes", "y", "1", "true"):
            return True
        if value in ("нет", "no", "n", "0", "false"):
            return False
        return None

    def _achievement_row_line(row: dict, pos: int) -> str:
        state_label = "🟢" if bool(row.get("is_active")) else "⚪️"
        metric_label = _metric_label_by_key(str(row.get("metric_key") or ""))
        operator_label = _operator_label_by_symbol(str(row.get("operator") or ""))
        return (
            f"• №{int(pos)} {state_label} {row.get('code')} | "
            f"{metric_label} {operator_label} {row.get('threshold')} | "
            f"{row.get('icon')} {row.get('title')}"
        )

    def _find_achievement_rule(identifier: str) -> dict | None:
        if not achievement_svc:
            return None
        raw = (identifier or "").strip()
        if not raw:
            return None
        token = raw
        if token.startswith("№"):
            pos_token = token[1:].strip()
            if pos_token.isdigit():
                try:
                    rows = achievement_svc.list_rules(limit=500, active_only=None) or []
                except Exception:
                    return None
                pos = int(pos_token)
                if 1 <= pos <= len(rows):
                    return rows[pos - 1]
            return None
        if token.startswith("#"):
            token = token[1:]
        token = token.strip()
        if token.isdigit():
            try:
                row = achievement_svc.get_rule(int(token))
                if row:
                    return row
            except Exception:
                pass
            # Fallback: allow entering list position number (1..N).
            try:
                rows = achievement_svc.list_rules(limit=500, active_only=None) or []
            except Exception:
                return None
            pos = int(token)
            if 1 <= pos <= len(rows):
                return rows[pos - 1]
            return None
        code = token.lower()
        try:
            rows = achievement_svc.list_rules(limit=500, active_only=None)
        except Exception:
            return None
        for row in rows:
            if str(row.get("code") or "").strip().lower() == code:
                return row
        return None

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
            f"📈 Аналитика\nПериод: {label}\n\nНажми «{BTN_A_STATS}».",
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

    def _tickets_list_text(rows: list[dict], mode: str, limit: int) -> str:
        mode_label = "только open" if mode == "open" else "все"
        if not rows:
            return f"🆘 Тикеты ({mode_label}, limit={limit})\n\nТикетов не найдено."

        lines = [f"🆘 Тикеты ({mode_label}, limit={limit})", ""]
        lines.extend(_ticket_preview(r) for r in rows)
        return "\n".join(lines)

    async def _send_tickets_list(
        update: Update,
        mode: str = "open",
        limit: int = 20,
        reply_markup=None,
    ):
        if not support_svc:
            await update.effective_message.reply_text("⚠️ Сервис поддержки не подключён.", reply_markup=reply_markup)
            return
        safe_mode = _safe_tickets_mode(mode)
        safe_limit = _safe_tickets_limit(limit)
        rows = support_svc.list_open(limit=safe_limit) if safe_mode == "open" else support_svc.list_all(limit=safe_limit)
        text = _tickets_list_text(rows, safe_mode, safe_limit)
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
            reply_markup=kb_admin_tickets(),
        )

    def _ticket_status_label(status: str | None) -> str:
        s = (status or "").strip().lower()
        if s == "open":
            return "🟡 open"
        if s == "closed":
            return "✅ closed"
        return s or "-"

    def _ticket_number(row: dict) -> int:
        try:
            tid = int(row.get("id") or 0)
        except Exception:
            tid = 0
        try:
            num = int(row.get("number") or 0)
        except Exception:
            num = 0
        return num if num > 0 else tid

    def _ticket_preview(row: dict) -> str:
        txt = (row.get("question_text") or "").replace("\n", " ").strip()
        if len(txt) > 70:
            txt = txt[:67] + "..."
        tid = int(row.get("id") or 0)
        tnum = _ticket_number(row)
        return (
            f"• №{tnum} (id={tid}) [{_ticket_status_label(row.get('status'))}] "
            f"user={row.get('user_id')} — {txt}"
        )

    def _ticket_details(row: dict) -> str:
        tid = int(row.get("id") or 0)
        tnum = _ticket_number(row)
        base = [
            f"🆘 Тикет №{tnum} (id={tid})",
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

        ticket_id_internal = int(row.get("id") or ticket_id or 0)
        ticket_number = _ticket_number(row)
        user_id = int(row.get("user_id") or 0)
        user_msg = f"💬 Ответ поддержки по заявке №{ticket_number}:\n{reply_text}"
        sent_ok = True
        try:
            await context.bot.send_message(chat_id=user_id, text=user_msg)
        except Exception:
            sent_ok = False

        tail = "" if sent_ok else "\n⚠️ Пользователю отправить не удалось (проверь chat доступность)."
        await update.effective_message.reply_text(
            f"✅ Заявка №{ticket_number} (id={ticket_id_internal}) закрыта и обработана.{tail}",
            reply_markup=reply_markup,
        )
        return True

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

    async def achievements_list(update: Update):
        if not achievement_svc:
            await update.effective_message.reply_text(
                "⚠️ Сервис ачивок не подключён.",
                reply_markup=kb_admin_actions(False),
            )
            return
        rows = achievement_svc.list_rules(limit=200, active_only=None)
        if not rows:
            await update.effective_message.reply_text(
                "🏆 Правила ачивок: пока пусто.",
                reply_markup=kb_admin_actions(False),
            )
            return
        lines = ["🏆 Правила ачивок (№, code, условие):", ""]
        lines.extend(_achievement_row_line(r, i + 1) for i, r in enumerate(rows))
        await update.effective_message.reply_text(
            "\n".join(lines),
            reply_markup=kb_admin_actions(False),
        )

    async def achievements_create(update: Update):
        uid = update.effective_user.id
        state.set_state(uid, ADMIN_WIZARD_STEP, {"mode": "a_create_title"})
        await update.effective_message.reply_text(
            "➕ Создание ачивки\n\n"
            "Шаг 1/7. Введи название ачивки.",
        )

    async def achievements_edit(update: Update):
        uid = update.effective_user.id
        state.set_state(uid, ADMIN_WIZARD_STEP, {"mode": "a_edit_id"})
        await update.effective_message.reply_text(
            "✏️ Редактирование ачивки\n\nВведи code, ID или номер из списка (например №9)."
        )

    async def achievements_delete(update: Update):
        uid = update.effective_user.id
        state.set_state(uid, ADMIN_WIZARD_STEP, {"mode": "a_delete_id"})
        await update.effective_message.reply_text(
            "🗑 Удаление ачивки\n\nВведи code, ID или номер из списка (например №9)."
        )

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

            if screen0 in ("lessons", "quests", "questionnaires", "analytics", "achievements", "tickets"):
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
            if text == texts.ADMIN_ACHIEVEMENTS:
                await _show_achievements_menu(update); raise ApplicationHandlerStop
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

            if text == BTN_A_STATS:
                await update.effective_message.reply_text(
                    admin_analytics.statistics_report(days),
                    reply_markup=kb_admin_analytics(),
                )
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

        if screen == "achievements":
            if text == BTN_LIST: await achievements_list(update); raise ApplicationHandlerStop
            if text == BTN_CREATE: await achievements_create(update); raise ApplicationHandlerStop
            if text == BTN_EDIT: await achievements_edit(update); raise ApplicationHandlerStop
            if text == BTN_DELETE: await achievements_delete(update); raise ApplicationHandlerStop

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

        # Allow leaving admin wizard by pressing main menu sections.
        if text in (texts.MENU_DAY, texts.MENU_PROGRESS, texts.MENU_SETTINGS, texts.MENU_HELP):
            state.clear_state(uid)
            return

        # Quick jump inside admin while wizard is active.
        if text == texts.MENU_ADMIN:
            state.clear_state(uid)
            await _show_admin_home(update)
            raise ApplicationHandlerStop
        if text == texts.ADMIN_LESSONS:
            state.clear_state(uid)
            await _show_lessons_menu(update)
            raise ApplicationHandlerStop
        if text == texts.ADMIN_QUESTS:
            state.clear_state(uid)
            await _show_quests_menu(update)
            raise ApplicationHandlerStop
        if text == texts.ADMIN_QUESTIONNAIRES:
            state.clear_state(uid)
            await _show_q_menu(update)
            raise ApplicationHandlerStop
        if text == texts.ADMIN_ANALYTICS:
            state.clear_state(uid)
            await _show_analytics_menu(update, 7)
            raise ApplicationHandlerStop
        if text == texts.ADMIN_ACHIEVEMENTS:
            state.clear_state(uid)
            await _show_achievements_menu(update)
            raise ApplicationHandlerStop
        if text == texts.ADMIN_TICKETS:
            state.clear_state(uid)
            await _show_tickets_menu(update, "open", 20)
            raise ApplicationHandlerStop

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
            elif mode0.startswith("a_"):
                await _show_achievements_menu(update)
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
        mode_s = str(mode or "").lower()

        # Quick action buttons should switch wizard mode and never be treated as step input.
        if mode_s.startswith("l_"):
            if text == BTN_LIST:
                state.clear_state(uid); await _show_lessons_menu(update); await lessons_list(update); raise ApplicationHandlerStop
            if text == BTN_CREATE:
                await lessons_create(update); raise ApplicationHandlerStop
            if text == BTN_EDIT:
                await lessons_edit(update); raise ApplicationHandlerStop
            if text == BTN_DELETE:
                await lessons_delete(update); raise ApplicationHandlerStop

        if mode_s.startswith("qst_"):
            if text == BTN_LIST:
                state.clear_state(uid); await _show_quests_menu(update); await quests_list(update); raise ApplicationHandlerStop
            if text == BTN_CREATE:
                await quests_create(update); raise ApplicationHandlerStop
            if text == BTN_EDIT:
                await quests_edit(update); raise ApplicationHandlerStop
            if text == BTN_DELETE:
                await quests_delete(update); raise ApplicationHandlerStop

        if mode_s.startswith("q_") or mode_s.startswith("qcast_"):
            if text == BTN_LIST:
                state.clear_state(uid); await _show_q_menu(update); await q_list(update); raise ApplicationHandlerStop
            if text == BTN_CREATE:
                await q_create(update); raise ApplicationHandlerStop
            if text == BTN_EDIT:
                await q_edit(update); raise ApplicationHandlerStop
            if text == BTN_DELETE:
                await q_delete(update); raise ApplicationHandlerStop
            if text == BTN_RANDOM_Q:
                await q_random(update); raise ApplicationHandlerStop

        if mode_s.startswith("a_"):
            if text == BTN_LIST:
                state.clear_state(uid); await _show_achievements_menu(update); await achievements_list(update); raise ApplicationHandlerStop
            if text == BTN_CREATE:
                await achievements_create(update); raise ApplicationHandlerStop
            if text == BTN_EDIT:
                await achievements_edit(update); raise ApplicationHandlerStop
            if text == BTN_DELETE:
                await achievements_delete(update); raise ApplicationHandlerStop

        if mode_s.startswith("t_"):
            return_mode = _safe_tickets_mode(payload.get("return_mode"))
            return_limit = _safe_tickets_limit(payload.get("return_limit"))
            if text == BTN_T_OPEN:
                state.clear_state(uid); await _show_tickets_menu(update, "open", return_limit); raise ApplicationHandlerStop
            if text == BTN_T_ALL:
                state.clear_state(uid); await _show_tickets_menu(update, "all", return_limit); raise ApplicationHandlerStop
            if text == BTN_T_VIEW:
                state.set_state(uid, ADMIN_WIZARD_STEP, {"mode": "t_view_id", "return_mode": return_mode, "return_limit": return_limit})
                await update.effective_message.reply_text("Введи ID тикета (число).")
                raise ApplicationHandlerStop
            if text == BTN_T_REPLY:
                state.set_state(uid, ADMIN_WIZARD_STEP, {"mode": "t_reply_id", "return_mode": return_mode, "return_limit": return_limit})
                await update.effective_message.reply_text("Введи ID тикета, на который нужно ответить.")
                raise ApplicationHandlerStop
            if text == BTN_T_CLOSE:
                state.set_state(uid, ADMIN_WIZARD_STEP, {"mode": "t_close_id", "return_mode": return_mode, "return_limit": return_limit})
                await update.effective_message.reply_text("Введи ID тикета, который нужно закрыть.")
                raise ApplicationHandlerStop

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

        # --- Achievements wizard ---
        if mode == "a_create_code":
            # Backward compatibility for previously stored wizard states.
            payload = {"mode": "a_create_desc", "title": text.strip()}
            state.set_state(uid, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text("Шаг 2/7. Введи описание ачивки.")
            return

        if mode == "a_create_title":
            title = text.strip()
            if not title:
                await update.effective_message.reply_text("Название не должно быть пустым."); raise ApplicationHandlerStop
            payload["title"] = title
            payload["mode"] = "a_create_desc"
            state.set_state(uid, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text("Шаг 2/7. Введи описание ачивки.")
            return

        if mode == "a_create_desc":
            description = text.strip()
            if not description:
                await update.effective_message.reply_text("Описание не должно быть пустым."); raise ApplicationHandlerStop
            payload["description"] = description
            payload["mode"] = "a_create_icon"
            state.set_state(uid, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text(
                "Шаг 3/7. Введи иконку (emoji) или '-' для значения по умолчанию 🏅."
            )
            return

        if mode == "a_create_icon":
            payload["icon"] = "🏅" if text.strip() == "-" else (text.strip() or "🏅")
            payload["mode"] = "a_create_metric"
            state.set_state(uid, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text(
                f"Шаг 4/7. Выбери метрику.\n{_achievement_metrics_hint()}"
            )
            return

        if mode == "a_create_metric":
            metric_key = _parse_metric_key(text)
            if not metric_key:
                await update.effective_message.reply_text(
                    f"Не понял метрику.\n{_achievement_metrics_hint()}"
                )
                raise ApplicationHandlerStop
            payload["metric_key"] = metric_key
            payload["mode"] = "a_create_op"
            state.set_state(uid, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text(
                f"Шаг 5/7. Выбери оператор.\n{_achievement_operators_hint()}"
            )
            return

        if mode == "a_create_op":
            operator = _parse_operator_symbol(text)
            if not operator:
                await update.effective_message.reply_text(
                    f"Не понял оператор.\n{_achievement_operators_hint()}"
                )
                raise ApplicationHandlerStop
            payload["operator"] = operator
            payload["mode"] = "a_create_threshold"
            state.set_state(uid, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text("Шаг 6/7. Введи порог (целое число).")
            return

        if mode == "a_create_threshold":
            if not re.match(r"^-?\d+$", text.strip()):
                await update.effective_message.reply_text("Порог должен быть целым числом."); raise ApplicationHandlerStop
            payload["threshold"] = int(text.strip())
            payload["mode"] = "a_create_active"
            state.set_state(uid, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text("Шаг 7/7. Активна? (Да/Нет)")
            return

        if mode == "a_create_active":
            active = _parse_yes_no(text)
            if active is None:
                await update.effective_message.reply_text("Введи 'Да' или 'Нет'."); raise ApplicationHandlerStop
            payload["is_active"] = active
            if not achievement_svc:
                state.clear_state(uid)
                await _show_achievements_menu(update)
                await update.effective_message.reply_text("⚠️ Сервис ачивок не подключён.")
                return
            metric_key = str(payload.get("metric_key") or "").strip()
            operator = str(payload.get("operator") or "").strip()
            threshold = int(payload.get("threshold") or 0)
            code = _generate_achievement_code(
                title=str(payload.get("title") or ""),
                metric_key=metric_key,
                operator=operator,
                threshold=threshold,
            )
            sort_order = _next_achievement_sort_order()
            try:
                row = achievement_svc.create_rule(
                    code=code,
                    title=payload.get("title"),
                    description=payload.get("description"),
                    icon=payload.get("icon"),
                    metric_key=metric_key,
                    operator=operator,
                    threshold=threshold,
                    is_active=payload.get("is_active"),
                    sort_order=sort_order,
                )
            except Exception as e:
                await update.effective_message.reply_text(f"⚠️ Не удалось создать правило: {e}")
                raise ApplicationHandlerStop
            state.clear_state(uid)
            await _show_achievements_menu(update)
            if not row:
                await update.effective_message.reply_text("⚠️ Не удалось создать правило.")
                return
            await update.effective_message.reply_text(
                f"✅ Правило создано: code={str(row.get('code') or '').strip()}"
            )
            return

        if mode == "a_edit_id":
            if not achievement_svc:
                state.clear_state(uid)
                await _show_achievements_menu(update)
                await update.effective_message.reply_text("⚠️ Сервис ачивок не подключён.")
                return
            row = _find_achievement_rule(text)
            if not row:
                await update.effective_message.reply_text("⚠️ Правило не найдено. Введи code, ID или № из списка."); raise ApplicationHandlerStop
            rid = int(row.get("id") or 0)
            payload = {
                "mode": "a_edit_title",
                "id": rid,
                "code": row.get("code"),
                "title": row.get("title"),
                "description": row.get("description"),
                "icon": row.get("icon"),
                "metric_key": row.get("metric_key"),
                "operator": row.get("operator"),
                "threshold": int(row.get("threshold") or 0),
                "is_active": bool(row.get("is_active")),
                "sort_order": int(row.get("sort_order") or 100),
            }
            state.set_state(uid, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text(
                f"Редактируем правило code={payload['code']}.\n"
                f"Текущее название: {payload['title']}\n"
                "Введи новое название или '-' чтобы оставить."
            )
            return

        if mode == "a_edit_code":
            # Backward compatibility for previously stored wizard states.
            if text.strip() != "-":
                payload["code"] = text.strip().lower()
            payload["mode"] = "a_edit_title"
            state.set_state(uid, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text(
                f"Текущее название: {payload['title']}\nВведи новое название или '-' чтобы оставить."
            )
            return

        if mode == "a_edit_title":
            if text.strip() != "-":
                payload["title"] = text.strip()
            payload["mode"] = "a_edit_desc"
            state.set_state(uid, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text("Введи новое описание или '-' чтобы оставить текущее.")
            return

        if mode == "a_edit_desc":
            if text.strip() != "-":
                payload["description"] = text.strip()
            payload["mode"] = "a_edit_icon"
            state.set_state(uid, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text(
                f"Текущая иконка: {payload['icon']}\nВведи новую или '-' чтобы оставить."
            )
            return

        if mode == "a_edit_icon":
            if text.strip() != "-":
                payload["icon"] = text.strip() or payload.get("icon") or "🏅"
            payload["mode"] = "a_edit_metric"
            state.set_state(uid, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text(
                f"Текущая метрика: {_metric_label_by_key(str(payload.get('metric_key') or ''))} "
                f"({payload['metric_key']})\n"
                f"Введи новую или '-' чтобы оставить.\n{_achievement_metrics_hint()}"
            )
            return

        if mode == "a_edit_metric":
            if text.strip() != "-":
                metric_key = _parse_metric_key(text)
                if not metric_key:
                    await update.effective_message.reply_text(
                        f"Не понял метрику.\n{_achievement_metrics_hint()}"
                    )
                    raise ApplicationHandlerStop
                payload["metric_key"] = metric_key
            payload["mode"] = "a_edit_op"
            state.set_state(uid, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text(
                f"Текущий оператор: {_operator_label_by_symbol(payload['operator'])} ({payload['operator']})\n"
                f"Введи новый или '-' чтобы оставить.\n{_achievement_operators_hint()}"
            )
            return

        if mode == "a_edit_op":
            if text.strip() != "-":
                operator = _parse_operator_symbol(text)
                if not operator:
                    await update.effective_message.reply_text(
                        f"Не понял оператор.\n{_achievement_operators_hint()}"
                    )
                    raise ApplicationHandlerStop
                payload["operator"] = operator
            payload["mode"] = "a_edit_threshold"
            state.set_state(uid, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text(
                f"Текущий порог: {payload['threshold']}\nВведи новый или '-' чтобы оставить."
            )
            return

        if mode == "a_edit_threshold":
            if text.strip() != "-":
                if not re.match(r"^-?\d+$", text.strip()):
                    await update.effective_message.reply_text("Порог должен быть целым числом."); raise ApplicationHandlerStop
                payload["threshold"] = int(text.strip())
            payload["mode"] = "a_edit_active"
            state.set_state(uid, ADMIN_WIZARD_STEP, payload)
            active_label = "Да" if payload.get("is_active") else "Нет"
            await update.effective_message.reply_text(
                f"Сейчас активна: {active_label}\nВведи Да/Нет или '-' чтобы оставить."
            )
            return

        if mode == "a_edit_active":
            if text.strip() != "-":
                active = _parse_yes_no(text)
                if active is None:
                    await update.effective_message.reply_text("Введи 'Да', 'Нет' или '-'."); raise ApplicationHandlerStop
                payload["is_active"] = active
            payload["mode"] = "a_edit_sort"
            state.set_state(uid, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text(
                f"Текущий порядок показа: {payload['sort_order']}\n"
                "Введи новый порядок (например 10/20/30) или '-' чтобы оставить."
            )
            return

        if mode == "a_edit_sort":
            if text.strip() != "-":
                if not re.match(r"^-?\d+$", text.strip()):
                    await update.effective_message.reply_text("Порядок должен быть целым числом."); raise ApplicationHandlerStop
                payload["sort_order"] = int(text.strip())
            if not achievement_svc:
                state.clear_state(uid)
                await _show_achievements_menu(update)
                await update.effective_message.reply_text("⚠️ Сервис ачивок не подключён.")
                return
            try:
                row = achievement_svc.update_rule(
                    rule_id=int(payload.get("id")),
                    code=payload.get("code"),
                    title=payload.get("title"),
                    description=payload.get("description"),
                    icon=payload.get("icon"),
                    metric_key=payload.get("metric_key"),
                    operator=payload.get("operator"),
                    threshold=payload.get("threshold"),
                    is_active=payload.get("is_active"),
                    sort_order=payload.get("sort_order"),
                )
            except Exception as e:
                await update.effective_message.reply_text(f"⚠️ Не удалось обновить правило: {e}")
                raise ApplicationHandlerStop
            state.clear_state(uid)
            await _show_achievements_menu(update)
            if not row:
                await update.effective_message.reply_text("⚠️ Правило не найдено.")
                return
            await update.effective_message.reply_text(
                f"✅ Правило обновлено: code={str(row.get('code') or '').strip()}"
            )
            return

        if mode == "a_delete_id":
            if not achievement_svc:
                state.clear_state(uid)
                await _show_achievements_menu(update)
                await update.effective_message.reply_text("⚠️ Сервис ачивок не подключён.")
                return
            row = _find_achievement_rule(text)
            if not row:
                await update.effective_message.reply_text("⚠️ Правило не найдено. Введи code, ID или № из списка."); raise ApplicationHandlerStop
            rid = int(row.get("id") or 0)
            code = str(row.get("code") or "").strip()
            ok = achievement_svc.delete_rule(rid)
            state.clear_state(uid)
            await _show_achievements_menu(update)
            if ok:
                await update.effective_message.reply_text(f"✅ Правило удалено: code={code}")
            else:
                await update.effective_message.reply_text("⚠️ Не найдено")
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
            payload["ticket_number"] = _ticket_number(row)
            payload["mode"] = "t_reply_text"
            state.set_state(uid, ADMIN_WIZARD_STEP, payload)
            await update.effective_message.reply_text(
                f"Заявка №{payload['ticket_number']} (id={tid}).\nВведи текст ответа пользователю."
            )
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
            await update.effective_message.reply_text(
                f"✅ Заявка №{_ticket_number(row)} (id={int(row.get('id') or tid)}) закрыта.",
                reply_markup=kb_admin_tickets(),
            )
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
    app.add_handler(MessageHandler(filters.Regex(rf"^{re.escape(texts.MENU_ADMIN)}$"), open_admin_from_menu))
    # Admin menu navigation (reply buttons)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_pick), group=-11)
    # Wizard input
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, wizard_text), group=-10)
