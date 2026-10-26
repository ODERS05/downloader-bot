"""Middlewares run before every handler.

- LanguageMiddleware puts `lang` ("en"/"ru") into the handler arguments.
- AccessMiddleware stops anyone who isn't in ALLOWED_USER_IDS.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User

from bot.i18n import resolve_lang, t

logger = logging.getLogger(__name__)

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class LanguageMiddleware(BaseMiddleware):
    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        user: User | None = data.get("event_from_user")
        data["lang"] = resolve_lang(user.language_code if user else None)
        return await handler(event, data)


class AccessMiddleware(BaseMiddleware):
    def __init__(self, allowed_user_ids: frozenset[int]) -> None:
        self._allowed = allowed_user_ids

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        user: User | None = data.get("event_from_user")
        if user is not None and user.id in self._allowed:
            return await handler(event, data)

        user_id = user.id if user else "unknown"
        logger.info("Blocked user %s (@%s)", user_id, user.username if user else None)
        lang = data.get("lang", "en")
        if isinstance(event, Message):
            await event.answer(t(lang, "not_allowed", user_id=user_id))
        elif isinstance(event, CallbackQuery):
            await event.answer(t(lang, "not_allowed_alert"), show_alert=True)
        return None
