"""The main flow: link → quality buttons → download → send the file."""

from __future__ import annotations

import asyncio
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, FSInputFile, Message, ReplyParameters
from aiogram.utils.chat_action import ChatActionSender

from bot.config import Settings
from bot.i18n import t
from bot.keyboards import DownloadCallback, quality_keyboard
from bot.services.downloader import Downloader
from bot.services.job_limiter import UserJobLimiter
from bot.services.media import AUDIO_CHOICE, DownloadedFile, MediaError, MediaInfo
from bot.services.request_store import RequestStore
from bot.utils.formatting import format_duration, format_size, safe_filename
from bot.utils.urls import extract_url, is_public_url

logger = logging.getLogger(__name__)
router = Router(name="download")

# Uploading 2 GB to the local Bot API server can take a while.
UPLOAD_TIMEOUT_SECONDS = 60 * 60
MAX_CAPTION_TITLE_LENGTH = 200


@router.message(F.text)
async def handle_link(
    message: Message, lang: str, settings: Settings, downloader: Downloader, store: RequestStore
) -> None:
    url = extract_url(message.text)
    if url is None:
        await message.answer(t(lang, "no_link"))
        return
    if not await asyncio.to_thread(is_public_url, url):
        await message.answer(t(lang, "bad_link"))
        return

    status = await message.reply(t(lang, "fetching"))
    try:
        info = await downloader.probe(url)
    except MediaError as err:
        await status.edit_text(error_text(err, lang, settings))
        return
    except Exception:
        logger.exception("Failed to look up %s", url)
        await status.edit_text(t(lang, "error_generic"))
        return

    token = store.put(info)
    keyboard = quality_keyboard(info, token, lang, settings.max_file_size_bytes)
    if keyboard is None:
        await status.edit_text(t(lang, "nothing_fits", limit=format_size(settings.max_file_size_bytes)))
        return
    await status.edit_text(
        t(lang, "choose", title=escape(info.title), details=_details_line(info)),
        reply_markup=keyboard,
    )


@router.callback_query(DownloadCallback.filter())
async def handle_choice(
    callback: CallbackQuery,
    callback_data: DownloadCallback,
    bot: Bot,
    lang: str,
    settings: Settings,
    downloader: Downloader,
    store: RequestStore,
    jobs: UserJobLimiter,
) -> None:
    info = store.get(callback_data.token)
    menu = callback.message
    if info is None or not isinstance(menu, Message):
        await callback.answer(t(lang, "expired"), show_alert=True)
        return

    with jobs.acquire(callback.from_user.id) as acquired:
        if not acquired:
            await callback.answer(t(lang, "busy"), show_alert=True)
            return
        await callback.answer()

        quality = _choice_label(info, callback_data.choice, lang)
        status = await menu.reply(t(lang, "downloading", quality=quality))
        try:
            async with downloader.download(info.url, callback_data.choice) as file:
                await status.edit_text(t(lang, "uploading"))
                await _send_file(bot, menu, file, info.url)
        except MediaError as err:
            await status.edit_text(error_text(err, lang, settings))
            return
        except Exception:
            logger.exception("Failed to download/send %s as %s", info.url, callback_data.choice)
            await status.edit_text(t(lang, "error_generic"))
            return
        await status.delete()


async def _send_file(bot: Bot, menu: Message, file: DownloadedFile, source_url: str) -> None:
    chat_id = menu.chat.id
    extension = file.path.suffix.lstrip(".") or ("mp3" if file.kind == "audio" else "mp4")
    upload = FSInputFile(file.path, filename=safe_filename(file.title, extension))
    title = file.title[:MAX_CAPTION_TITLE_LENGTH]
    caption = f'<a href="{escape(source_url, quote=True)}">{escape(title)}</a>'
    reply_to = ReplyParameters(message_id=menu.message_id, allow_sending_without_reply=True)

    if file.kind == "audio":
        async with ChatActionSender.upload_voice(chat_id=chat_id, bot=bot):
            await bot.send_audio(
                chat_id,
                audio=upload,
                caption=caption,
                title=title,
                performer=file.uploader,
                duration=file.duration,
                reply_parameters=reply_to,
                request_timeout=UPLOAD_TIMEOUT_SECONDS,
            )
        return

    async with ChatActionSender.upload_video(chat_id=chat_id, bot=bot):
        await bot.send_video(
            chat_id,
            video=upload,
            caption=caption,
            duration=file.duration,
            width=file.width,
            height=file.height,
            supports_streaming=True,
            reply_parameters=reply_to,
            request_timeout=UPLOAD_TIMEOUT_SECONDS,
        )


def error_text(err: MediaError, lang: str, settings: Settings) -> str:
    params = {**err.params, "limit": format_size(settings.max_file_size_bytes)}
    if "size" in params:
        params["size"] = format_size(params["size"])
    return t(lang, err.code, **params)


def _details_line(info: MediaInfo) -> str:
    parts = []
    if info.uploader:
        parts.append(f"👤 {escape(info.uploader)}")
    if duration := format_duration(info.duration):
        parts.append(f"⏱ {duration}")
    return " · ".join(parts)


def _choice_label(info: MediaInfo, choice: str, lang: str) -> str:
    if choice == AUDIO_CHOICE:
        return "MP3"
    for quality in info.qualities:
        if str(quality.height) == choice:
            return quality.label
    return t(lang, "best_button")
