"""Handlers and middlewares, with Telegram objects replaced by mocks."""

import asyncio
from contextlib import asynccontextmanager, nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Message

from bot.handlers import admin as admin_handlers
from bot.handlers import build_router
from bot.handlers import download as download_handlers
from bot.handlers.download import (
    _Job,
    _show_progress,
    error_text,
    handle_cancel,
    handle_choice,
    handle_link,
    progress_text,
)
from bot.handlers.start import cmd_help, cmd_start
from bot.i18n import TEXTS
from bot.keyboards import AccessCallback, CancelCallback, DownloadCallback
from bot.middlewares import AccessMiddleware, LanguageMiddleware
from bot.services.job_limiter import UserJobLimiter
from bot.services.media import DownloadedFile, MediaError, Quality
from bot.services.progress import DownloadProgress
from bot.services.request_store import RequestStore
from bot.services.user_store import UserStore
from bot.utils.urls import is_public_url
from tests.conftest import MB, make_info


def make_message(text: str = "", chat_id: int = 10, message_id: int = 5) -> MagicMock:
    message = MagicMock(spec=Message)
    message.text = text
    message.chat = SimpleNamespace(id=chat_id)
    message.message_id = message_id
    message.from_user = SimpleNamespace(id=1, first_name="Ann <3")
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
        self.progress: list[DownloadProgress | None] = []

    @asynccontextmanager
    async def download(self, url, choice, extracted=None, progress=None):
        self.downloads.append((url, choice))
        self.extracted.append(extracted)
        self.progress.append(progress)
        if self._download_error:
            raise self._download_error
        yield self._file


@pytest.fixture(autouse=True)
def no_chat_actions(monkeypatch):
    fake = SimpleNamespace(upload_document=lambda **_: nullcontext(), upload_voice=lambda **_: nullcontext())
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

    assert message.answer.await_args_list[0].args[0].startswith("👋 Hi, <b>Ann &lt;3</b>!")
    assert "50.0 MB" in message.answer.await_args_list[1].args[0]


def test_build_router_includes_all_handlers():
    assert [r.name for r in build_router().sub_routers] == ["start", "admin", "download"]


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
    cancel = status.edit_text.await_args_list[0].kwargs["reply_markup"].inline_keyboard[0][0]
    assert CancelCallback.unpack(cancel.callback_data).user_id == 1
    kwargs = bot.send_document.await_args.kwargs
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
    bot.send_document.assert_not_awaited()
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
    assert menu.reply.await_args.kwargs["reply_markup"] is not None  # the Cancel button
    assert downloader.progress[0] is not None
    kwargs = bot.send_document.await_args.kwargs
    # Sent as a file, so Telegram keeps the original quality.
    assert kwargs["document"].filename == "My Clip.mp4"
    assert kwargs["disable_content_type_detection"] is True
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
    bot.send_document.assert_not_awaited()


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
        (MediaError("cancelled"), TEXTS["en"]["cancelled"]),
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


def make_users(tmp_path, owners=frozenset({1})) -> UserStore:
    return UserStore(tmp_path / "users.json", owners)


def stranger(user_id=77, username="friend"):
    return SimpleNamespace(id=user_id, language_code="ru", username=username, first_name="Bob", last_name=None)


async def run_access(users, event, from_user, lang="en", admin_id=1, bot=None):
    middleware = AccessMiddleware(users, admin_id)
    handler = AsyncMock(return_value="ok")
    bot = bot or AsyncMock()
    result = await middleware(handler, event, {"event_from_user": from_user, "lang": lang, "bot": bot})
    return result, handler, bot


async def test_access_allows_owner_from_env(tmp_path):
    result, _, _ = await run_access(make_users(tmp_path), MagicMock(), user(1))

    assert result == "ok"


async def test_access_allows_user_approved_in_chat(tmp_path):
    users = make_users(tmp_path)
    users.approve(77, "Bob")

    result, _, _ = await run_access(users, MagicMock(), stranger())

    assert result == "ok"


async def test_stranger_triggers_one_request_to_the_owner(tmp_path):
    users = make_users(tmp_path)
    message = make_message()

    _, handler, bot = await run_access(users, message, stranger(), lang="ru")
    await run_access(users, message, stranger(), lang="ru", bot=bot)

    handler.assert_not_awaited()
    bot.send_message.assert_awaited_once()
    chat_id, text = bot.send_message.await_args.args
    assert chat_id == 1
    assert "Bob (@friend)" in text and "77" in text
    approve = bot.send_message.await_args.kwargs["reply_markup"].inline_keyboard[0][0]
    assert AccessCallback.unpack(approve.callback_data) == AccessCallback(action="approve", user_id=77, lang="ru")
    replies = [call.args[0] for call in message.answer.await_args_list]
    assert replies == [TEXTS["ru"]["access_requested"], TEXTS["ru"]["access_pending"]]


async def test_request_uses_the_owners_language(tmp_path):
    users = make_users(tmp_path)
    middleware = AccessMiddleware(users, 1)
    bot = AsyncMock()
    await middleware(AsyncMock(), MagicMock(), {"event_from_user": user(1), "lang": "ru", "bot": bot})

    await middleware(AsyncMock(), make_message(), {"event_from_user": stranger(), "lang": "en", "bot": bot})

    assert "Запрос доступа" in bot.send_message.await_args.args[1]


async def test_request_is_retried_when_the_owner_cannot_be_reached(tmp_path):
    from aiogram.exceptions import TelegramForbiddenError

    users = make_users(tmp_path)
    bot = AsyncMock()
    bot.send_message.side_effect = TelegramForbiddenError(method=MagicMock(), message="blocked")
    message = make_message()

    await run_access(users, message, stranger(), bot=bot)

    assert "77" in message.answer.await_args.args[0]
    assert not users.has_request(77)


async def test_denied_user_only_sees_their_id(tmp_path):
    users = make_users(tmp_path)
    users.deny(77)
    message = make_message()

    _, _, bot = await run_access(users, message, stranger())

    bot.send_message.assert_not_awaited()
    assert "77" in message.answer.await_args.args[0]


async def test_access_blocks_callback_with_alert(tmp_path):
    callback = make_callback(make_message(), user_id=77)

    await run_access(make_users(tmp_path), callback, stranger(), lang="ru")

    callback.answer.assert_awaited_once_with(TEXTS["ru"]["not_allowed_alert"], show_alert=True)


async def test_access_blocks_event_without_user(tmp_path):
    result, handler, _ = await run_access(make_users(tmp_path), make_message(), None)

    assert result is None
    handler.assert_not_awaited()


# --- owner: access requests and /users ---


def admin_message(text="🔔 request"):
    message = make_message()
    message.html_text = text
    message.edit_text = AsyncMock()
    return message


async def answer_request(settings, users, action, user_id=77, bot=None):
    message = admin_message()
    callback = make_callback(message, user_id=1)
    bot = bot or AsyncMock()
    await admin_handlers.handle_access(
        callback, AccessCallback(action=action, user_id=user_id, lang="ru"), bot, "en", settings, users
    )
    return callback, message, bot


async def test_owner_approves_request(settings, tmp_path):
    users = make_users(tmp_path)
    users.add_request(77, "Bob")

    _, message, bot = await answer_request(settings, users, "approve")

    assert users.is_allowed(77)
    bot.send_message.assert_awaited_once_with(77, TEXTS["ru"]["access_granted"])
    assert message.edit_text.await_args.args[0] == f"🔔 request\n\n<b>{TEXTS['en']['approved']}</b>"
    assert UserStore(tmp_path / "users.json", frozenset({1})).approved() == [(77, "Bob")]


async def test_approval_survives_an_unreachable_user(settings, tmp_path):
    from aiogram.exceptions import TelegramForbiddenError

    users = make_users(tmp_path)
    bot = AsyncMock()
    bot.send_message.side_effect = TelegramForbiddenError(method=MagicMock(), message="blocked")

    await answer_request(settings, users, "approve", bot=bot)

    assert users.is_allowed(77)


async def test_owner_denies_request(settings, tmp_path):
    users = make_users(tmp_path)
    users.add_request(77, "Bob")

    _, message, bot = await answer_request(settings, users, "deny")

    assert users.is_denied(77)
    assert not users.is_allowed(77)
    bot.send_message.assert_not_awaited()
    assert TEXTS["en"]["denied"] in message.edit_text.await_args.args[0]


async def test_users_command_lists_people(settings, tmp_path):
    users = make_users(tmp_path)
    users.approve(77, "Bob <b>")
    message = make_message()

    await admin_handlers.cmd_users(message, "en", settings, users)

    text = message.answer.await_args.args[0]
    assert "<code>1</code>, <code>2</code>" in text
    assert "• Bob &lt;b&gt;" in text
    (button,) = message.answer.await_args.kwargs["reply_markup"].inline_keyboard[0]
    assert AccessCallback.unpack(button.callback_data).action == "remove"


async def test_users_command_when_nobody_was_added(settings, tmp_path):
    message = make_message()

    await admin_handlers.cmd_users(message, "en", settings, make_users(tmp_path))

    assert TEXTS["en"]["users_none"] in message.answer.await_args.args[0]
    assert message.answer.await_args.kwargs["reply_markup"] is None


async def test_owner_removes_user(settings, tmp_path):
    users = make_users(tmp_path)
    users.approve(77, "Bob")

    callback, message, _ = await answer_request(settings, users, "remove")

    assert not users.is_allowed(77)
    callback.answer.assert_awaited_once_with("Removed Bob.")
    assert TEXTS["en"]["users_none"] in message.edit_text.await_args.args[0]


async def test_double_tap_on_remove_does_not_edit_again(settings, tmp_path):
    users = make_users(tmp_path)

    _, message, _ = await answer_request(settings, users, "remove")

    message.edit_text.assert_not_awaited()


async def test_stale_request_message_is_ignored(settings, tmp_path):
    from aiogram.exceptions import TelegramBadRequest

    users = make_users(tmp_path)
    message = admin_message()
    message.edit_text.side_effect = TelegramBadRequest(method=MagicMock(), message="message is not modified")

    await admin_handlers.handle_access(
        make_callback(message, user_id=1),
        AccessCallback(action="deny", user_id=77, lang="en"),
        AsyncMock(),
        "en",
        settings,
        users,
    )

    assert users.is_denied(77)


@pytest.mark.parametrize(("user_id", "expected"), [(1, True), (2, False)])
async def test_admin_filter(settings, user_id, expected):
    event = SimpleNamespace(from_user=SimpleNamespace(id=user_id))

    assert await admin_handlers.IsAdmin()(event, settings) is expected


# --- cancel and progress ---


async def test_cancel_stops_the_running_download():
    jobs = UserJobLimiter()
    callback = make_callback(make_message())

    with jobs.acquire(1):
        event = jobs.cancel_event(1)
        await handle_cancel(callback, CancelCallback(user_id=1), "en", jobs)

    assert event.is_set()
    callback.answer.assert_awaited_once_with(TEXTS["en"]["cancelling"])


@pytest.mark.parametrize("presser", [1, 2])
async def test_cancel_when_nothing_runs_or_someone_else_presses(presser):
    jobs = UserJobLimiter()
    callback = make_callback(make_message(), user_id=presser)

    with jobs.acquire(2 if presser == 2 else 3):
        await handle_cancel(callback, CancelCallback(user_id=1), "en", jobs)

    callback.answer.assert_awaited_once_with(TEXTS["en"]["cancel_too_late"])


def make_job(progress=None, choice="720"):
    return _Job(make_info(), choice, "en", 1, progress or DownloadProgress())


def test_progress_text_stages():
    progress = DownloadProgress()
    job = make_job(progress)

    assert progress_text(job) == "⬇️ Downloading <b>720p</b>…"
    progress.queued = True
    assert "waiting in line" in progress_text(job)
    progress.queued = False
    progress.on_download({"filename": "a", "downloaded_bytes": 45, "total_bytes": 100})
    assert progress_text(job).endswith("\n▰▰▰▰▱▱▱▱▱▱ 45%")
    progress.on_download({"filename": "a", "status": "finished", "total_bytes": 100})
    assert "almost done" in progress_text(job)


async def test_show_progress_edits_only_when_text_changes(monkeypatch):
    from aiogram.exceptions import TelegramRetryAfter

    progress = DownloadProgress()
    status = make_message().reply.return_value
    ticks = 0
    edits: list[str] = []

    async def fake_sleep(_seconds):
        nonlocal ticks
        ticks += 1
        if ticks == 1:
            progress.queued = True
        elif ticks == 3:
            progress.queued = False
        elif ticks == 5:
            raise asyncio.CancelledError

    async def edit(text, reply_markup):
        edits.append(text)
        if len(edits) == 1:
            raise TelegramRetryAfter(method=MagicMock(), message="slow down", retry_after=1)

    monkeypatch.setattr(download_handlers.asyncio, "sleep", fake_sleep)
    status.edit_text = edit

    with pytest.raises(asyncio.CancelledError):
        await _show_progress(status, make_job(progress))

    # Tick 1: queued, the edit fails. Tick 2: retried. Tick 3: back to downloading. Tick 4: no change.
    assert [("waiting" in text) for text in edits] == [True, True, False]
