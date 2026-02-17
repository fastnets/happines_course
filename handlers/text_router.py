from telegram.ext import MessageHandler, filters
from ui.keyboards.reply import kb_main, kb_day, kb_settings, kb_progress, kb_back_only
from core.screen import set_screen
from services.auth import is_admin

async def on_text(update, context):
    text = (update.message.text or "").strip()

    if text == "⬅️ Назад":
        set_screen(context, "main")
        await update.message.reply_text(
            "Главное меню 👇",
            reply_markup=kb_main(is_admin(update.effective_user.id))
        )
        return

    if text == "🗓 Мой день":
        set_screen(context, "day")
        await update.message.reply_text("Твой день 👇", reply_markup=kb_day())
        return

    if text == "⚙️ Настройки":
        set_screen(context, "settings")
        await update.message.reply_text("Настройки 👇", reply_markup=kb_settings())
        return

    if text == "📊 Мой прогресс":
        set_screen(context, "progress")
        await update.message.reply_text("Твой прогресс 👇", reply_markup=kb_progress())
        return

    if text == "❓ Помощь":
        set_screen(context, "help")
        await update.message.reply_text("Помощь 👇", reply_markup=kb_back_only())
        return

    if text == "Получить раньше поставленного времени":
        from services.learning import send_day_materials
        await send_day_materials(update, context)
        return

    if text == "⏰ Изменить время":
        from services.profile import start_change_time
        await start_change_time(update, context)
        return

    if text == "✏️ Изменить имя":
        from services.profile import start_change_name
        await start_change_name(update, context)
        return

    if text == "🔄 Обновить":
        from services.analytics import show_progress
        await show_progress(update, context)
        return

    await update.message.reply_text(
        "Выбери пункт меню 👇",
        reply_markup=kb_main(is_admin(update.effective_user.id))
    )

def setup(application):
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
