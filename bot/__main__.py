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
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand, BotCommandScopeChat

from bot.config import ConfigError, Settings
from bot.handlers import build_router
from bot.i18n import TEXTS, t
from bot.middlewares import AccessMiddleware, LanguageMiddleware
from bot.services.downloader import Downloader
from bot.services.job_limiter import UserJobLimiter
from bot.services.request_store import RequestStore
from bot.services.user_store import UserStore

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


def create_dispatcher(settings: Settings, downloader: Downloader, users: UserStore) -> Dispatcher:
    # Keyword arguments become available to every handler by name (dependency injection).
    dispatcher = Dispatcher(
        settings=settings,
        downloader=downloader,
        store=RequestStore(),
        jobs=UserJobLimiter(),
        users=users,
    )
    access = AccessMiddleware(users, settings.admin_user_id)
    for observer in (dispatcher.message, dispatcher.callback_query):
        # Language first, so the "access denied" reply is in the user's language.
        observer.outer_middleware(LanguageMiddleware())
        observer.outer_middleware(access)
    dispatcher.include_router(build_router())
    return dispatcher


async def set_commands(bot: Bot, admin_user_id: int) -> None:
    """Show /start and /help in Telegram's menu, translated per app language. The owner also sees /users."""
    for lang in TEXTS:
        commands = [
            BotCommand(command="start", description=t(lang, "cmd_start")),
            BotCommand(command="help", description=t(lang, "cmd_help")),
        ]
        language_code = None if lang == "en" else lang
        await bot.set_my_commands(commands, language_code=language_code)
        admin_commands = [*commands, BotCommand(command="users", description=t(lang, "cmd_users"))]
        try:
            await bot.set_my_commands(
                admin_commands, scope=BotCommandScopeChat(chat_id=admin_user_id), language_code=language_code
            )
        except TelegramAPIError as err:
            # The owner hasn't pressed Start in the bot yet. /users still works when typed.
            logger.warning("Couldn't set the owner's command menu: %s", err)


async def run(settings: Settings) -> None:
    downloader = Downloader(
        download_dir=settings.download_dir,
        max_file_size=settings.max_file_size_bytes,
        max_concurrent=settings.max_concurrent_downloads,
        cookies_file=settings.cookies_file,
        proxy_url=settings.proxy_url,
    )
    downloader.prepare()

    users = UserStore(settings.users_file, settings.allowed_user_ids)
    bot = create_bot(settings)
    dispatcher = create_dispatcher(settings, downloader, users)
    logger.info(
        "Starting bot: api=%s, file limit=%d MB, allowed users=%d (+%d approved in chat), owner=%d",
        settings.telegram_api_url or "cloud",
        settings.max_file_size_mb,
        len(settings.allowed_user_ids),
        len(users.approved()),
        settings.admin_user_id,
    )
    try:
        await set_commands(bot, settings.admin_user_id)
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
