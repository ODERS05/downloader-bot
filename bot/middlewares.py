"""Middlewares run before every handler.

- LanguageMiddleware puts `lang` ("en"/"ru") into the handler arguments.
- AccessMiddleware stops anyone who isn't allowed, and asks the owner to let them in.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from html import escape
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message, TelegramObject, User

from bot.i18n import DEFAULT_LANG, resolve_lang, t
from bot.keyboards import access_request_keyboard
from bot.services.user_store import UserStore

logger = logging.getLogger(__name__)

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class LanguageMiddleware(BaseMiddleware):
    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        user: User | None = data.get("event_from_user")
        data["lang"] = resolve_lang(user.language_code if user else None)
        return await handler(event, data)


class AccessMiddleware(BaseMiddleware):
    def __init__(self, users: UserStore, admin_user_id: int) -> None:
        self._users = users
        self._admin_user_id = admin_user_id
        # The owner's app language, learned from their last message, for the requests they receive.
        self._admin_lang = DEFAULT_LANG

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        user: User | None = data.get("event_from_user")
        lang = data.get("lang", DEFAULT_LANG)
        if user is not None and user.id == self._admin_user_id:
            self._admin_lang = lang
        if user is not None and self._users.is_allowed(user.id):
            return await handler(event, data)

        logger.info("Blocked user %s (@%s)", user.id if user else "unknown", user.username if user else None)
        if isinstance(event, CallbackQuery):
            await event.answer(t(lang, "not_allowed_alert"), show_alert=True)
        elif isinstance(event, Message):
            await event.answer(await self._reply_to_stranger(user, lang, data.get("bot")))
        return None

    async def _reply_to_stranger(self, user: User | None, lang: str, bot: Bot | None) -> str:
        if user is None or bot is None or self._users.is_denied(user.id):
            return t(lang, "not_allowed", user_id=user.id if user else "unknown")
        if self._users.has_request(user.id):
            return t(lang, "access_pending")
        name = _display_name(user)
        # Remembered before sending: two quick messages must not ask the owner twice.
        self._users.add_request(user.id, name)
        try:
            await bot.send_message(
                self._admin_user_id,
                t(self._admin_lang, "access_request", name=escape(name), user_id=user.id),
                reply_markup=access_request_keyboard(user.id, lang, self._admin_lang),
            )
        except TelegramAPIError:
            # Usually: the owner never pressed Start in their own bot, so it can't message them.
            logger.exception("Couldn't send the access request for %s to the owner", user.id)
            self._users.forget_request(user.id)
            return t(lang, "not_allowed", user_id=user.id)
        return t(lang, "access_requested")


def _display_name(user: User) -> str:
    name = " ".join(part for part in (user.first_name, user.last_name) if part) or str(user.id)
    return f"{name} (@{user.username})" if user.username else name
