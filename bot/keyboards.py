"""Inline keyboards and the data their buttons carry."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.i18n import t
from bot.services.media import AUDIO_CHOICE, BEST_CHOICE, MediaInfo
from bot.utils.formatting import format_size

BUTTONS_PER_ROW = 2


class DownloadCallback(CallbackData, prefix="dl"):
    """Packed into the button as e.g. "dl:Ab3dE5fG:720" (Telegram allows up to 64 bytes)."""

    token: str  # key in RequestStore
    choice: str  # "mp3", "best" or a height like "720"


def fits(size: int | None, limit: int) -> bool:
    """Unknown sizes are allowed: the downloader re-checks the real file."""
    return size is None or size <= limit


def quality_keyboard(info: MediaInfo, token: str, lang: str, max_size: int) -> InlineKeyboardMarkup | None:
    """One button per quality that fits the size limit, plus MP3. None if nothing fits."""
    builder = InlineKeyboardBuilder()
    video_buttons = 0

    for quality in info.qualities:
        if not fits(quality.estimated_size, max_size):
            continue
        text = quality.label
        if quality.estimated_size:
            text += f" · ≈{format_size(quality.estimated_size)}"
        builder.button(text=text, callback_data=DownloadCallback(token=token, choice=str(quality.height)))
        video_buttons += 1

    if not info.qualities:
        # The site didn't list resolutions (common outside YouTube): offer a single "best".
        builder.button(text=t(lang, "best_button"), callback_data=DownloadCallback(token=token, choice=BEST_CHOICE))
        video_buttons += 1

    audio_fits = fits(info.audio_size, max_size)
    if audio_fits:
        builder.button(text=t(lang, "audio_button"), callback_data=DownloadCallback(token=token, choice=AUDIO_CHOICE))

    if video_buttons == 0 and not audio_fits:
        return None

    rows = [BUTTONS_PER_ROW] * (video_buttons // BUTTONS_PER_ROW)
    if video_buttons % BUTTONS_PER_ROW:
        rows.append(video_buttons % BUTTONS_PER_ROW)
    if audio_fits:
        rows.append(1)  # MP3 on its own row
    builder.adjust(*rows)
    return builder.as_markup()
