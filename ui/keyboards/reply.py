"""Backward-compatible re-exports.

The project historically used `ui.keyboards.reply.*`. New code should use
`ui.keyboards.menus.*`.
"""

from ui.keyboards.menus import (  # noqa: F401
    kb_main,
    kb_day,
    kb_settings,
    kb_progress,
    kb_back_only,
)
