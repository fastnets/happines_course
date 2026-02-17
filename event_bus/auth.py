from telegram import Update
from entity.settings import Settings

def is_admin(settings: Settings, update: Update) -> bool:
    uid = update.effective_user.id if update.effective_user else None
    return bool(uid and uid in settings.admin_tg_ids)
