import asyncio
from pathlib import Path

import pytest
from yt_dlp.utils import DownloadCancelled, DownloadError

from bot.services import downloader as downloader_module
from bot.services.downloader import Downloader, _format_options, _run_ytdlp, classify_error
from bot.services.media import MediaError, video_format_selector
from bot.services.progress import DownloadProgress

MAX_SIZE = 1000


@pytest.fixture
def downloader(tmp_path: Path) -> Downloader:
    instance = Downloader(download_dir=tmp_path / "downloads", max_file_size=MAX_SIZE, max_concurrent=1)
    instance.prepare()
    return instance


def fake_ytdlp(monkeypatch, info: dict, files: dict[str, int] | None = None):
    """Replace the real yt-dlp call; optionally 'download' files of given sizes."""
    calls = []

    def run(options, url, *, download, saved_info=None):
        calls.append(options)
        if download and files:
            home = Path(options["paths"]["home"])
            for name, size in files.items():
                (home / name).write_bytes(b"x" * size)
        return info

    monkeypatch.setattr(downloader_module, "_run_ytdlp", run)
    return calls


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("ERROR: [youtube] abc: Sign in to confirm you're not a bot", "error_blocked"),
        ("HTTP Error 429: Too Many Requests", "error_blocked"),
        ("ERROR: [TikTok] 123: Your IP address is blocked from accessing this post", "error_blocked"),
        ("[Instagram] abc: Requested content is not available, rate-limit reached or login required", "error_blocked"),
        ("ERROR: The uploader has not made this video available in your country", "error_blocked"),
        ("ERROR: This video is not available from your location due to geo restriction", "error_blocked"),
        ("ERROR: [youtube] abc: Private video. Sign in if you've been granted access", "error_restricted"),
        ("Sign in to confirm your age", "error_restricted"),
        ("ERROR: [vimeo] 1: The web client only works when logged-in. Use --cookies", "error_restricted"),
        ("[Instagram] abc: Restricted Video: You must be 18 years old or over to see this video", "error_restricted"),
        ("ERROR: Unsupported URL: https://example.com", "error_unsupported"),
        ("ERROR: [youtube] abc: Video unavailable", "error_unsupported"),
        ("ERROR: something exploded", "error_generic"),
    ],
)
def test_classify_error(message, code):
    assert classify_error(message) == code


def test_prepare_cleans_only_leftover_job_folders(tmp_path):
    leftover = tmp_path / "downloads" / "job-old" / "file.mp4"
    leftover.parent.mkdir(parents=True)
    leftover.write_bytes(b"x")
    unrelated = tmp_path / "downloads" / "my-video.mp4"
    unrelated.write_bytes(b"keep me")

    Downloader(tmp_path / "downloads", MAX_SIZE, 1).prepare()

    assert not leftover.parent.exists()
    assert unrelated.exists()


def test_each_job_gets_its_own_cookies_copy(tmp_path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n")
    instance = Downloader(tmp_path / "downloads", MAX_SIZE, 1, cookies_file=cookies)
    instance.prepare()
    first, second = tmp_path / "job-a", tmp_path / "job-b"
    first.mkdir()
    second.mkdir()

    first_options = instance._base_options(first)
    second_options = instance._base_options(second)

    assert first_options["cookiefile"] == str(first / "cookies.txt")
    assert second_options["cookiefile"] == str(second / "cookies.txt")
    assert Path(first_options["cookiefile"]).read_text() == cookies.read_text()


@pytest.mark.parametrize("make_unreadable", [lambda p: None, lambda p: p.mkdir()])
def test_prepare_ignores_missing_or_unreadable_cookies(tmp_path, make_unreadable):
    cookies = tmp_path / "cookies.txt"
    make_unreadable(cookies)  # missing file, or a folder where the file should be
    instance = Downloader(tmp_path / "downloads", MAX_SIZE, 1, cookies_file=cookies)

    instance.prepare()

    assert "cookiefile" not in instance._base_options(tmp_path)


async def test_download_ignores_cookies_copy_when_finding_output(tmp_path, monkeypatch):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("x" * 5000)  # bigger than the "video"
    instance = Downloader(tmp_path / "downloads", MAX_SIZE * 10, 1, cookies_file=cookies)
    instance.prepare()

    def run(options, url, *, download, saved_info=None):
        assert Path(options["cookiefile"]).exists()
        (Path(options["paths"]["home"]) / "abc.mp4").write_bytes(b"v" * 100)
        return {"title": "t"}

    monkeypatch.setattr(downloader_module, "_run_ytdlp", run)

    async with instance.download("https://youtu.be/abc", "best") as file:
        assert file.path.name == "abc.mp4"


async def test_probe_cleans_up_its_temp_folder(downloader, monkeypatch, tmp_path):
    fake_ytdlp(monkeypatch, {"title": "x"})

    await downloader.probe("https://youtu.be/abc")

    assert list((tmp_path / "downloads").iterdir()) == []


async def test_probe_builds_media_info(downloader, monkeypatch):
    fake_ytdlp(
        monkeypatch,
        {
            "webpage_url": "https://www.youtube.com/watch?v=abc",
            "title": "Hello",
            "duration": 60,
            "channel": "Chan",
            "formats": [{"vcodec": "avc1", "acodec": "none", "height": 720, "width": 1280, "filesize": 100}],
        },
    )

    info = await downloader.probe("https://youtu.be/abc")

    assert info.url == "https://www.youtube.com/watch?v=abc"
    assert info.title == "Hello"
    assert info.uploader == "Chan"
    assert [q.label for q in info.qualities] == ["720p"]
    assert info.audio_size == 1_440_000


@pytest.mark.parametrize(
    ("info", "code"),
    [
        ({"_type": "playlist"}, "playlist"),
        ({"is_live": True}, "live"),
        ({"live_status": "is_upcoming"}, "live"),
    ],
)
async def test_probe_rejects_playlists_and_live(downloader, monkeypatch, info, code):
    fake_ytdlp(monkeypatch, info)

    with pytest.raises(MediaError) as err:
        await downloader.probe("https://example.com/x")
    assert err.value.code == code


async def test_download_video_returns_file_and_cleans_up(downloader, monkeypatch):
    calls = fake_ytdlp(
        monkeypatch,
        {"title": "Hello", "duration": 12.7, "width": 1280, "height": 720, "uploader": "Me"},
        files={"abc.mp4": 500, "abc.f140.m4a.part": 900},
    )

    async with downloader.download("https://youtu.be/abc", "720") as file:
        assert file.path.name == "abc.mp4"
        assert file.kind == "video"
        assert (file.duration, file.width, file.height, file.uploader) == (12, 1280, 720, "Me")
        workdir = file.path.parent

    assert not workdir.exists()
    options = calls[0]
    assert options["format"] == video_format_selector(720)
    assert options["merge_output_format"] == "mp4"
    assert options["max_filesize"] == MAX_SIZE


async def test_download_audio(downloader, monkeypatch):
    calls = fake_ytdlp(
        monkeypatch, {"title": "Song", "duration": None, "width": 1, "height": 1}, files={"abc.mp3": 100}
    )

    async with downloader.download("https://youtu.be/abc", "mp3") as file:
        assert file.kind == "audio"
        assert file.width is None and file.height is None and file.duration is None

    assert calls[0]["postprocessors"][0]["preferredcodec"] == "mp3"


async def test_download_skipped_for_size_raises_too_large(downloader, monkeypatch):
    fake_ytdlp(monkeypatch, {"duration": 10, "requested_formats": [{"filesize": 800}, {"filesize": 700}]})

    with pytest.raises(MediaError) as err:
        async with downloader.download("https://youtu.be/abc", "best"):
            pass
    assert err.value.code == "too_large"
    assert err.value.params["size"] == 1500


async def test_download_unknown_size_reports_none(downloader, monkeypatch):
    fake_ytdlp(monkeypatch, {"duration": 10, "requested_formats": [{"filesize": 800}, {}]})

    with pytest.raises(MediaError) as err:
        async with downloader.download("https://youtu.be/abc", "best"):
            pass
    assert err.value.params["size"] is None


async def test_downloaded_file_over_limit_raises_too_large(downloader, monkeypatch):
    fake_ytdlp(monkeypatch, {"title": "Big"}, files={"abc.mp4": MAX_SIZE + 1})

    with pytest.raises(MediaError) as err:
        async with downloader.download("https://youtu.be/abc", "best"):
            pass
    assert err.value.params["size"] == MAX_SIZE + 1


def test_format_options_for_best():
    options = _format_options("best")

    assert options["format"].startswith("bv*[vcodec!~=")
    assert options["format"].endswith("/bv*+ba/b")
    assert options["format_sort"][0] == "res"


def fake_youtube_dl_class(extract_info, processed=None):
    class FakeYoutubeDL:
        def __init__(self, options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download):
            return extract_info()

        def process_ie_result(self, info, download):
            if processed is not None:
                processed.append(info)
            info["touched"] = True
            return info

    return FakeYoutubeDL


def test_run_ytdlp_translates_errors(monkeypatch):
    def fail():
        raise DownloadError("ERROR: Private video")

    monkeypatch.setattr(downloader_module, "YoutubeDL", fake_youtube_dl_class(fail))

    with pytest.raises(MediaError) as err:
        _run_ytdlp({}, "https://youtu.be/abc", download=False)
    assert err.value.code == "error_restricted"


def test_run_ytdlp_empty_result_is_unsupported(monkeypatch):
    monkeypatch.setattr(downloader_module, "YoutubeDL", fake_youtube_dl_class(lambda: None))

    with pytest.raises(MediaError) as err:
        _run_ytdlp({}, "https://youtu.be/abc", download=False)
    assert err.value.code == "error_unsupported"


def test_run_ytdlp_returns_info(monkeypatch):
    monkeypatch.setattr(downloader_module, "YoutubeDL", fake_youtube_dl_class(lambda: {"title": "ok"}))

    assert _run_ytdlp({}, "https://youtu.be/abc", download=False) == {"title": "ok"}


def test_run_ytdlp_reuses_saved_info_without_changing_it(monkeypatch):
    processed = []
    monkeypatch.setattr(
        downloader_module, "YoutubeDL", fake_youtube_dl_class(lambda: pytest.fail("looked up again"), processed)
    )
    saved = {"title": "ok", "formats": [{"format_id": "1"}]}

    result = _run_ytdlp({}, "https://youtu.be/abc", download=True, saved_info=saved)

    assert result["title"] == "ok"
    assert processed and processed[0] is not saved
    assert "touched" not in saved


async def test_probe_keeps_extracted_info_without_heavy_fields(downloader, monkeypatch):
    fake_ytdlp(
        monkeypatch,
        {
            "title": "Hello",
            "formats": [{"format_id": "18", "url": "https://x"}],
            "automatic_captions": {"en": [{"url": "https://captions"}]},
            "subtitles": {"en": []},
            "__private": "internal",
        },
    )

    info = await downloader.probe("https://youtu.be/abc")

    assert info.extracted["formats"] == [{"format_id": "18", "url": "https://x"}]
    for key in ("automatic_captions", "subtitles", "__private"):
        assert key not in info.extracted


def test_youtube_hls_formats_are_skipped(downloader, tmp_path):
    options = downloader._base_options(tmp_path)

    assert options["extractor_args"] == {"youtube": {"skip": ["hls"]}}


def test_proxy_is_passed_to_ytdlp(tmp_path):
    instance = Downloader(tmp_path / "downloads", MAX_SIZE, 1, proxy_url="socks5://user:pass@proxy:1080")

    assert instance._base_options(tmp_path)["proxy"] == "socks5://user:pass@proxy:1080"


def test_no_proxy_by_default(downloader, tmp_path):
    assert "proxy" not in downloader._base_options(tmp_path)


def record_ytdlp(monkeypatch, results):
    """Fake yt-dlp that returns/raises `results` in order and records whether saved info was used."""
    used_saved_info = []

    def run(options, url, *, download, saved_info=None):
        used_saved_info.append(saved_info is not None)
        result = results[len(used_saved_info) - 1]
        if isinstance(result, Exception):
            (Path(options["paths"]["home"]) / "stale.mp4.part").write_bytes(b"x")
            raise result
        (Path(options["paths"]["home"]) / "abc.mp4").write_bytes(b"v" * 10)
        return result

    monkeypatch.setattr(downloader_module, "_run_ytdlp", run)
    return used_saved_info


async def test_download_reuses_probe_result(downloader, monkeypatch):
    used_saved_info = record_ytdlp(monkeypatch, [{"title": "Hello"}])

    async with downloader.download("https://youtu.be/abc", "720", extracted={"title": "Hello"}) as file:
        assert file.title == "Hello"

    assert used_saved_info == [True]


async def test_download_looks_up_again_when_saved_info_fails(downloader, monkeypatch):
    used_saved_info = record_ytdlp(monkeypatch, [MediaError("error_generic"), {"title": "Fresh"}])

    async with downloader.download("https://youtu.be/abc", "720", extracted={"title": "Old"}) as file:
        assert file.title == "Fresh"
        assert sorted(p.name for p in file.path.parent.iterdir()) == ["abc.mp4"]

    assert used_saved_info == [True, False]


async def test_download_too_large_is_not_retried(downloader, monkeypatch):
    used_saved_info = record_ytdlp(monkeypatch, [MediaError("too_large", size=5)])

    with pytest.raises(MediaError) as err:
        async with downloader.download("https://youtu.be/abc", "720", extracted={"title": "x"}):
            pass

    assert err.value.code == "too_large"
    assert used_saved_info == [True]


@pytest.mark.parametrize("code", ["too_large", "cancelled"])
async def test_final_errors_are_not_retried(downloader, monkeypatch, code):
    used_saved_info = record_ytdlp(monkeypatch, [MediaError(code)])

    with pytest.raises(MediaError) as err:
        async with downloader.download("https://youtu.be/abc", "720", extracted={"title": "x"}):
            pass

    assert err.value.code == code
    assert used_saved_info == [True]


def test_run_ytdlp_translates_cancel(monkeypatch):
    def cancel():
        raise DownloadCancelled()

    monkeypatch.setattr(downloader_module, "YoutubeDL", fake_youtube_dl_class(cancel))

    with pytest.raises(MediaError) as err:
        _run_ytdlp({}, "https://youtu.be/abc", download=True)

    assert err.value.code == "cancelled"


async def test_download_passes_progress_hooks(downloader, monkeypatch):
    calls = fake_ytdlp(monkeypatch, {"title": "t"}, files={"abc.mp4": 10})
    progress = DownloadProgress()

    async with downloader.download("https://youtu.be/abc", "720", progress=progress):
        pass

    assert calls[0]["progress_hooks"] == [progress.on_download]
    assert calls[0]["postprocessor_hooks"] == [progress.on_postprocess]


async def test_cancel_pressed_after_the_last_hook_drops_the_file(downloader, monkeypatch):
    progress = DownloadProgress()

    def run(options, url, *, download, saved_info=None):
        (Path(options["paths"]["home"]) / "abc.mp4").write_bytes(b"v")
        progress.cancelled.set()
        return {"title": "t"}

    monkeypatch.setattr(downloader_module, "_run_ytdlp", run)

    with pytest.raises(MediaError) as err:
        async with downloader.download("https://youtu.be/abc", "720", progress=progress):
            pass

    assert err.value.code == "cancelled"


async def test_waits_in_line_and_can_be_cancelled_there(downloader, monkeypatch):
    monkeypatch.setattr(downloader_module, "QUEUE_POLL_SECONDS", 0.01)
    fake_ytdlp(monkeypatch, {"title": "t"}, files={"abc.mp4": 10})
    progress = DownloadProgress()
    await downloader._semaphore.acquire()  # someone else is downloading in the only slot

    waiting = asyncio.create_task(downloader.download("https://youtu.be/b", "720", progress=progress).__aenter__())
    await asyncio.sleep(0.05)
    assert progress.queued
    progress.cancelled.set()
    with pytest.raises(MediaError) as err:
        await waiting

    assert err.value.code == "cancelled"
    assert not progress.queued
    downloader._semaphore.release()
    async with downloader.download("https://youtu.be/abc", "720"):
        pass  # the cancelled job didn't keep a slot
