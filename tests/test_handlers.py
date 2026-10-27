"""Handlers and middlewares, with Telegram objects replaced by mocks."""

from contextlib import asynccontextmanager, nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Message

from bot.handlers import build_router
from bot.handlers import download as download_handlers
from bot.handlers.download import error_text, handle_choice, handle_link
from bot.handlers.start import cmd_help, cmd_start
from bot.i18n import TEXTS
from bot.keyboards import DownloadCallback
from bot.middlewares import AccessMiddleware, LanguageMiddleware
from bot.services.job_limiter import UserJobLimiter
from bot.services.media import DownloadedFile, MediaError, Quality
from bot.services.request_store import RequestStore
from bot.utils.urls import is_public_url
from tests.conftest import MB, make_info


def make_message(text: str = "", chat_id: int = 10, message_id: int = 5) -> MagicMock:
    message = MagicMock(spec=Message)
    message.text = text
    message.chat = SimpleNamespace(id=chat_id)
    message.message_id = message_id
    message.from_user = SimpleNamespace(id=1)
    message.answer = AsyncMock()
    status = MagicMock()
    status.edit_text = AsyncMock()
    status.delete = AsyncMock()
    message.reply = AsyncMock(return_value=status)
    return message


class FakeDownloader:
    def __init__(self, info=None, probe_error=None, file=None, download_error=None):
        self.probe = AsyncMock(return_value=info, side_effect=probe_error)
        self._file = file
        self._download_error = download_error
        self.downloads: list[tuple[str, str]] = []
        self.extracted: list[dict | None] = []

    @asynccontextmanager
    async def download(self, url, choice, extracted=None):
        self.downloads.append((url, choice))
        self.extracted.append(extracted)
        if self._download_error:
            raise self._download_error
        yield self._file


@pytest.fixture(autouse=True)
def no_chat_actions(monkeypatch):
    fake = SimpleNamespace(upload_video=lambda **_: nullcontext(), upload_voice=lambda **_: nullcontext())
    monkeypatch.setattr(download_handlers, "ChatActionSender", fake)


@pytest.fixture(autouse=True)
def no_dns(monkeypatch):
    """Pretend every hostname resolves to a public address, so tests don't need the internet."""
    public = [(None, None, None, "", ("142.250.74.46", 0))]
    monkeypatch.setattr(
        download_handlers, "is_public_url", lambda url: is_public_url(url, resolve=lambda host, port: public)
    )


# --- /start and /help ---


async def test_start_and_help(settings):
    message = make_message()

    await cmd_start(message, lang="en")
    await cmd_help(message, lang="ru", settings=settings)

    assert message.answer.await_args_list[0].args[0] == TEXTS["en"]["start"]
    assert "50.0 MB" in message.answer.await_args_list[1].args[0]


def test_build_router_includes_all_handlers():
    assert [r.name for r in build_router().sub_routers] == ["start", "download"]


# --- sending a link ---


async def send_link(settings, message, downloader, store=None, jobs=None):
    bot = AsyncMock()
    store = store if store is not None else RequestStore()
    await handle_link(message, "en", settings, downloader, store, jobs or UserJobLimiter(), bot)
    return bot


async def test_message_without_link(settings):
    message = make_message("hello")

    await send_link(settings, message, FakeDownloader())

    message.answer.assert_awaited_once_with(TEXTS["en"]["no_link"])


async def test_private_network_link_is_rejected(settings):
    message = make_message("http://localhost:8081/")
    downloader = FakeDownloader()

    await send_link(settings, message, downloader)

    message.answer.assert_awaited_once_with(TEXTS["en"]["bad_link"])
    downloader.probe.assert_not_awaited()


async def test_link_shows_quality_buttons(settings):
    message = make_message("https://youtu.be/abc")
    store = RequestStore()

    await send_link(settings, message, FakeDownloader(info=make_info()), store)

    status = message.reply.return_value
    text = status.edit_text.await_args.args[0]
    assert "Test &lt;Video&gt;" in text  # title is HTML-escaped
    assert "👤 Channel · ⏱ 2:05" in text
    assert status.edit_text.await_args.kwargs["reply_markup"] is not None
    assert len(store) == 1


async def test_link_when_nothing_fits(settings):
    message = make_message("https://youtu.be/abc")
    info = make_info(qualities=(Quality(720, "720p", 999 * MB),), audio_size=999 * MB)

    await send_link(settings, message, FakeDownloader(info=info))

    assert "50.0 MB" in message.reply.return_value.edit_text.await_args.args[0]


@pytest.mark.parametrize(
    ("error", "expected_key"),
    [(MediaError("playlist"), "playlist"), (RuntimeError("boom"), "error_generic")],
)
async def test_link_lookup_errors(settings, error, expected_key):
    message = make_message("https://youtu.be/abc")

    await send_link(settings, message, FakeDownloader(probe_error=error))

    message.reply.return_value.edit_text.assert_awaited_once_with(TEXTS["en"][expected_key])


def short_clip(**overrides):
    return make_info(
        url="https://www.tiktok.com/@me/video/1", duration=15, qualities=(Quality(1280, "720p", 5 * MB),), **overrides
    )


async def test_short_clip_is_sent_without_menu(settings, tmp_path):
    message = make_message("https://vm.tiktok.com/xyz/")
    store = RequestStore()
    downloader = FakeDownloader(info=short_clip(extracted={"id": "1"}), file=make_file(tmp_path))

    bot = await send_link(settings, message, downloader, store)

    assert downloader.downloads == [("https://www.tiktok.com/@me/video/1", "1280")]
    assert downloader.extracted == [{"id": "1"}]
    status = message.reply.return_value
    assert "720p" in status.edit_text.await_args_list[0].args[0]
    kwargs = bot.send_video.await_args.kwargs
    assert kwargs["reply_parameters"].message_id == message.message_id
    # MP3 is still available, as a button under the video.
    (button,) = kwargs["reply_markup"].inline_keyboard[0]
    callback = DownloadCallback.unpack(button.callback_data)
    assert callback.choice == "mp3"
    assert store.get(callback.token) is not None
    status.delete.assert_awaited_once()


async def test_short_clip_shows_menu_while_user_is_busy(settings):
    message = make_message("https://vm.tiktok.com/xyz/")
    downloader = FakeDownloader(info=short_clip())
    jobs = UserJobLimiter()

    with jobs.acquire(1):
        await send_link(settings, message, downloader, jobs=jobs)

    assert downloader.downloads == []
    assert message.reply.return_value.edit_text.await_args.kwargs["reply_markup"] is not None


async def test_short_clip_download_error_is_shown(settings):
    message = make_message("https://vm.tiktok.com/xyz/")
    jobs = UserJobLimiter()
    downloader = FakeDownloader(info=short_clip(), download_error=MediaError("error_blocked"))

    bot = await send_link(settings, message, downloader, jobs=jobs)

    message.reply.return_value.edit_text.assert_awaited_with(TEXTS["en"]["error_blocked"])
    bot.send_video.assert_not_awaited()
    assert not jobs.is_busy(1)


# --- pressing a quality button ---


def make_callback(menu, user_id=1) -> MagicMock:
    callback = MagicMock(spec=CallbackQuery)
    callback.message = menu
    callback.from_user = SimpleNamespace(id=user_id)
    callback.answer = AsyncMock()
    return callback


def make_file(tmp_path, kind="video") -> DownloadedFile:
    path = tmp_path / ("abc.mp4" if kind == "video" else "abc.mp3")
    path.write_bytes(b"data")
    return DownloadedFile(
        path=path,
        kind=kind,
        title="My <Clip>",
        duration=12,
        width=1280 if kind == "video" else None,
        height=720 if kind == "video" else None,
        uploader="Me",
    )


async def press(settings, choice, downloader, store=None, jobs=None, menu=None, token=None):
    store = store or RequestStore()
    token = token or store.put(make_info())
    menu = menu if menu is not None else make_message()
    callback = make_callback(menu)
    bot = AsyncMock()
    await handle_choice(
        callback,
        DownloadCallback(token=token, choice=choice),
        bot,
        "en",
        settings,
        downloader,
        store,
        jobs or UserJobLimiter(),
    )
    return callback, menu, bot


async def test_choice_downloads_and_sends_video(settings, tmp_path):
    downloader = FakeDownloader(file=make_file(tmp_path))

    callback, menu, bot = await press(settings, "720", downloader)

    callback.answer.assert_awaited_once_with()
    assert downloader.downloads == [("https://www.youtube.com/watch?v=abc", "720")]
    assert "720p" in menu.reply.await_args.args[0]
    kwargs = bot.send_video.await_args.kwargs
    assert kwargs["video"].filename == "My Clip.mp4"
    assert (kwargs["width"], kwargs["height"], kwargs["duration"]) == (1280, 720, 12)
    assert kwargs["caption"] == '<a href="https://www.youtube.com/watch?v=abc">My &lt;Clip&gt;</a>'
    menu.reply.return_value.delete.assert_awaited_once()


async def test_choice_passes_saved_lookup_to_download(settings, tmp_path):
    downloader = FakeDownloader(file=make_file(tmp_path))
    store = RequestStore()
    token = store.put(make_info(extracted={"title": "saved"}))

    await press(settings, "720", downloader, store=store, token=token)

    assert downloader.extracted == [{"title": "saved"}]


async def test_choice_sends_audio(settings, tmp_path):
    downloader = FakeDownloader(file=make_file(tmp_path, kind="audio"))

    _, menu, bot = await press(settings, "mp3", downloader)

    assert "MP3" in menu.reply.await_args.args[0]
    kwargs = bot.send_audio.await_args.kwargs
    assert kwargs["audio"].filename == "My Clip.mp3"
    assert kwargs["performer"] == "Me"
    bot.send_video.assert_not_awaited()


async def test_choice_best_label(settings, tmp_path):
    _, menu, _ = await press(settings, "best", FakeDownloader(file=make_file(tmp_path)))

    assert TEXTS["en"]["best_button"] in menu.reply.await_args.args[0]


async def test_expired_token(settings):
    callback, menu, _ = await press(settings, "720", FakeDownloader(), token="gone")

    callback.answer.assert_awaited_once_with(TEXTS["en"]["expired"], show_alert=True)
    menu.reply.assert_not_awaited()


async def test_inaccessible_message_is_treated_as_expired(settings):
    callback, _, _ = await press(settings, "720", FakeDownloader(), menu=object())

    callback.answer.assert_awaited_once_with(TEXTS["en"]["expired"], show_alert=True)


async def test_busy_user_cannot_start_second_download(settings):
    jobs = UserJobLimiter()
    downloader = FakeDownloader()

    with jobs.acquire(1):
        callback, _, _ = await press(settings, "720", downloader, jobs=jobs)

    callback.answer.assert_awaited_once_with(TEXTS["en"]["busy"], show_alert=True)
    assert downloader.downloads == []


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (MediaError("too_large", size=60 * MB), "📦 The file is 60.0 MB, larger than the 50.0 MB limit."),
        (RuntimeError("boom"), TEXTS["en"]["error_generic"]),
    ],
)
async def test_download_errors_are_shown(settings, error, expected):
    jobs = UserJobLimiter()
    _, menu, _ = await press(settings, "720", FakeDownloader(download_error=error), jobs=jobs)

    assert menu.reply.return_value.edit_text.await_args.args[0].startswith(expected)
    assert not jobs.is_busy(1)


def test_error_text_with_unknown_size(settings):
    assert "The file is ?," in error_text(MediaError("too_large", size=None), "en", settings)


# --- middlewares ---


def user(user_id=1, language_code="ru"):
    return SimpleNamespace(id=user_id, language_code=language_code, username="someone")


async def test_language_middleware_sets_lang():
    handler = AsyncMock(return_value="ok")
    data = {"event_from_user": user(language_code="ru-RU")}

    assert await LanguageMiddleware()(handler, MagicMock(), data) == "ok"
    assert data["lang"] == "ru"


async def test_language_middleware_without_user():
    data = {}

    await LanguageMiddleware()(AsyncMock(), MagicMock(), data)

    assert data["lang"] == "en"


async def test_access_allows_listed_user():
    handler = AsyncMock(return_value="ok")

    result = await AccessMiddleware(frozenset({1}))(handler, MagicMock(), {"event_from_user": user(1)})

    assert result == "ok"


async def test_access_blocks_message_and_shows_id():
    handler = AsyncMock()
    message = make_message()

    await AccessMiddleware(frozenset({1}))(handler, message, {"event_from_user": user(77), "lang": "en"})

    handler.assert_not_awaited()
    assert "77" in message.answer.await_args.args[0]


async def test_access_blocks_callback_with_alert():
    callback = make_callback(make_message(), user_id=77)

    await AccessMiddleware(frozenset({1}))(AsyncMock(), callback, {"event_from_user": user(77), "lang": "ru"})

    callback.answer.assert_awaited_once_with(TEXTS["ru"]["not_allowed_alert"], show_alert=True)


async def test_access_blocks_event_without_user():
    handler = AsyncMock()

    assert await AccessMiddleware(frozenset({1}))(handler, MagicMock(), {}) is None
    handler.assert_not_awaited()
