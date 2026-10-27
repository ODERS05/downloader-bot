"""/start and /help."""

from __future__ import annotations

from html import escape

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.config import Settings
from bot.i18n import t
from bot.utils.formatting import format_size

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, lang: str) -> None:
    name = message.from_user.first_name if message.from_user else ""
    await message.answer(t(lang, "start", name=escape(name or "👋")))


@router.message(Command("help"))
async def cmd_help(message: Message, lang: str, settings: Settings) -> None:
    await message.answer(t(lang, "help", limit=format_size(settings.max_file_size_bytes)))
