import logging

from telegram.ext import CallbackQueryHandler, MessageHandler, filters


log = logging.getLogger("trace")


async def trace_update(update, context):
    u = update.effective_user
    uid = u.id if u else None
    if update.callback_query:
        log.info("[TRACE] uid=%s callback=%r", uid, update.callback_query.data)
    elif update.message:
        log.info("[TRACE] uid=%s text=%r", uid, update.message.text)


def register_trace(app):
    """Register a very-early handler that logs every update.

    This helps to understand the order of handlers and what is happening.
    """

    app.add_handler(CallbackQueryHandler(trace_update), group=-100)
    app.add_handler(MessageHandler(filters.ALL, trace_update), group=-100)
