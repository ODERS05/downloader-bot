"""/start and /help."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.config import Settings
from bot.i18n import t
from bot.utils.formatting import format_size

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, lang: str) -> None:
    await message.answer(t(lang, "start"))


@router.message(Command("help"))
async def cmd_help(message: Message, lang: str, settings: Settings) -> None:
    await message.answer(t(lang, "help", limit=format_size(settings.max_file_size_bytes)))
