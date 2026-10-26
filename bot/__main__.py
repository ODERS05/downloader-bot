"""Entry point: `python -m bot`."""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from bot.config import ConfigError, Settings
from bot.handlers import build_router
from bot.i18n import TEXTS, t
from bot.middlewares import AccessMiddleware, LanguageMiddleware
from bot.services.downloader import Downloader
from bot.services.job_limiter import UserJobLimiter
from bot.services.request_store import RequestStore

logger = logging.getLogger("bot")


def create_bot(settings: Settings) -> Bot:
    session = None
    if settings.telegram_api_url:
        session = AiohttpSession(api=TelegramAPIServer.from_base(settings.telegram_api_url))
    return Bot(
        token=settings.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )


def create_dispatcher(settings: Settings, downloader: Downloader) -> Dispatcher:
    # Keyword arguments become available to every handler by name (dependency injection).
    dispatcher = Dispatcher(
        settings=settings,
        downloader=downloader,
        store=RequestStore(),
        jobs=UserJobLimiter(),
    )
    for observer in (dispatcher.message, dispatcher.callback_query):
        # Language first, so the "access denied" reply is in the user's language.
        observer.outer_middleware(LanguageMiddleware())
        observer.outer_middleware(AccessMiddleware(settings.allowed_user_ids))
    dispatcher.include_router(build_router())
    return dispatcher


async def set_commands(bot: Bot) -> None:
    """Show /start and /help in Telegram's menu, translated per app language."""
    for lang in TEXTS:
        commands = [
            BotCommand(command="start", description=t(lang, "cmd_start")),
            BotCommand(command="help", description=t(lang, "cmd_help")),
        ]
        await bot.set_my_commands(commands, language_code=None if lang == "en" else lang)


async def run(settings: Settings) -> None:
    downloader = Downloader(
        download_dir=settings.download_dir,
        max_file_size=settings.max_file_size_bytes,
        max_concurrent=settings.max_concurrent_downloads,
        cookies_file=settings.cookies_file,
    )
    downloader.prepare()

    bot = create_bot(settings)
    dispatcher = create_dispatcher(settings, downloader)
    logger.info(
        "Starting bot: api=%s, file limit=%d MB, allowed users=%d",
        settings.telegram_api_url or "cloud",
        settings.max_file_size_mb,
        len(settings.allowed_user_ids),
    )
    try:
        await set_commands(bot)
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        await bot.session.close()


def main() -> None:
    try:
        settings = Settings.from_env()
    except ConfigError as err:
        print(f"Configuration error: {err}", file=sys.stderr)
        sys.exit(1)

    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    asyncio.run(run(settings))


if __name__ == "__main__":
    main()
