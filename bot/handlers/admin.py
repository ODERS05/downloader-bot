"""Owner-only: answer access requests and manage who can use the bot (/users)."""

from __future__ import annotations

import logging
from html import escape

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, Filter
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot.config import Settings
from bot.i18n import t
from bot.keyboards import AccessCallback, users_keyboard
from bot.services.user_store import UserStore

logger = logging.getLogger(__name__)
router = Router(name="admin")


class IsAdmin(Filter):
    async def __call__(self, event: Message | CallbackQuery, settings: Settings) -> bool:
        return event.from_user is not None and event.from_user.id == settings.admin_user_id


router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


@router.message(Command("users"))
async def cmd_users(message: Message, lang: str, settings: Settings, users: UserStore) -> None:
    text, keyboard = users_view(settings, users, lang)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(AccessCallback.filter())
async def handle_access(
    callback: CallbackQuery,
    callback_data: AccessCallback,
    bot: Bot,
    lang: str,
    settings: Settings,
    users: UserStore,
) -> None:
    user_id = callback_data.user_id
    name = users.request_name(user_id)
    message = callback.message if isinstance(callback.message, Message) else None

    if callback_data.action == "remove":
        removed = users.remove(user_id)
        await callback.answer(t(lang, "user_removed", name=name))
        if message is not None and removed:  # a second tap would edit to the same text, which Telegram rejects
            text, keyboard = users_view(settings, users, lang)
            await message.edit_text(text, reply_markup=keyboard)
        return

    if callback_data.action == "approve":
        users.approve(user_id, name)
        result = t(lang, "approved")
        try:
            await bot.send_message(user_id, t(callback_data.lang, "access_granted"))
        except TelegramAPIError:
            logger.warning("Couldn't tell user %s they were let in", user_id)
    else:
        users.deny(user_id)
        result = t(lang, "denied")

    await callback.answer(result)
    if message is not None:
        # Keep the request text, swap the buttons for the answer.
        try:
            await message.edit_text(f"{message.html_text}\n\n<b>{result}</b>")
        except TelegramAPIError as err:
            logger.debug("Couldn't update the request message: %s", err)  # e.g. a quick double tap


def users_view(settings: Settings, users: UserStore, lang: str) -> tuple[str, InlineKeyboardMarkup | None]:
    approved = users.approved()
    env_ids = ", ".join(f"<code>{user_id}</code>" for user_id in sorted(settings.allowed_user_ids))
    lines = [t(lang, "users_title"), "", t(lang, "users_from_env", ids=env_ids), ""]
    if approved:
        lines += [f"• {escape(name)}" for _, name in approved]
        lines += ["", t(lang, "users_hint")]
    else:
        lines.append(t(lang, "users_none"))
    return "\n".join(lines), users_keyboard(approved, lang)
