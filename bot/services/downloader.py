"""yt-dlp wrapper: look up a link's formats and download the one the user picked.

yt-dlp is blocking, so every call runs in a worker thread to keep the bot responsive.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import shutil
import tempfile
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from bot.services.media import (
    AUDIO_CHOICE,
    BEST_CHOICE,
    FORMAT_SORT,
    MP3_BITRATE_KBPS,
    DownloadedFile,
    MediaError,
    MediaInfo,
    estimate_mp3_size,
    estimate_size,
    extract_qualities,
    video_format_selector,
)

logger = logging.getLogger(__name__)

SOCKET_TIMEOUT_SECONDS = 30
RETRIES = 3
JOB_DIR_PREFIX = "job-"
COOKIES_COPY_NAME = "cookies.txt"
# Big parts of the lookup result the download never needs; dropped to keep saved lookups small.
UNUSED_INFO_KEYS = ("automatic_captions", "subtitles", "thumbnails", "heatmap", "description")

# Substrings of yt-dlp error messages, checked in order, mapped to i18n keys.
_ERROR_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("error_blocked", ("not a bot", "http error 429", "too many requests", "rate-limit")),
    (
        "error_restricted",
        (
            "private video",
            "sign in",
            "age-restricted",
            "confirm your age",
            "members-only",
            "login required",
            "log in",
            "logged-in",
            "logged in",
            "account credentials",
            "requires authentication",
        ),
    ),
    (
        "error_unsupported",
        ("unsupported url", "is not a valid url", "video unavailable", "no video formats found", "404"),
    ),
)


class _YtDlpLogger:
    """Route yt-dlp's console output into Python logging."""

    def debug(self, msg: str) -> None:
        logger.debug(msg)

    def info(self, msg: str) -> None:
        logger.debug(msg)

    def warning(self, msg: str) -> None:
        logger.warning(msg)

    def error(self, msg: str) -> None:
        logger.error(msg)


class Downloader:
    def __init__(
        self,
        download_dir: Path,
        max_file_size: int,
        max_concurrent: int,
        cookies_file: Path | None = None,
    ) -> None:
        self._download_dir = download_dir
        self._max_file_size = max_file_size
        self._cookies_file = cookies_file
        self._semaphore = asyncio.Semaphore(max_concurrent)

    def prepare(self) -> None:
        """Create the download folder, remove job folders left over from a crash, check cookies."""
        self._download_dir.mkdir(parents=True, exist_ok=True)
        for leftover in self._download_dir.glob(f"{JOB_DIR_PREFIX}*"):
            shutil.rmtree(leftover, ignore_errors=True)

        if self._cookies_file is None:
            return
        try:
            with self._cookies_file.open("rb"):
                pass
        except OSError as err:
            logger.warning("Can't read COOKIES_FILE (%s), continuing without cookies", err)
            self._cookies_file = None
            return
        logger.info("Using cookies from %s", self._cookies_file)

    async def probe(self, url: str) -> MediaInfo:
        """Fetch title, duration and available qualities without downloading."""
        with self._job_dir() as workdir:
            return await asyncio.to_thread(self._probe_sync, url, workdir)

    @asynccontextmanager
    async def download(
        self, url: str, choice: str, extracted: dict[str, Any] | None = None
    ) -> AsyncIterator[DownloadedFile]:
        """Download `url` as `choice` ("mp3", "best" or a height like "720").

        `extracted` is the saved lookup from `probe`; reusing it skips a second lookup.
        The file is deleted when the `async with` block ends.
        """
        with self._job_dir() as workdir:
            async with self._semaphore:
                result = await asyncio.to_thread(self._download_with_fallback, url, choice, workdir, extracted)
            yield result

    @contextmanager
    def _job_dir(self) -> Iterator[Path]:
        """A private temporary folder per job, deleted afterwards."""
        workdir = Path(tempfile.mkdtemp(prefix=JOB_DIR_PREFIX, dir=self._download_dir))
        try:
            yield workdir
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    # --- blocking parts, run in worker threads ---

    def _base_options(self, workdir: Path) -> dict[str, Any]:
        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": False,
            "noprogress": True,
            "noplaylist": True,
            "socket_timeout": SOCKET_TIMEOUT_SECONDS,
            "retries": RETRIES,
            "fragment_retries": RETRIES,
            "logger": _YtDlpLogger(),
            # YouTube's HLS list costs an extra request, and its streams download in many small
            # fragments; the plain HTTPS formats cover the same qualities.
            "extractor_args": {"youtube": {"skip": ["hls"]}},
        }
        if self._cookies_file:
            # yt-dlp rewrites the cookie file when it finishes. Each job gets its own copy, so
            # parallel jobs can't corrupt each other's cookies and the original stays read-only.
            job_cookies = workdir / COOKIES_COPY_NAME
            shutil.copyfile(self._cookies_file, job_cookies)
            options["cookiefile"] = str(job_cookies)
        return options

    def _probe_sync(self, url: str, workdir: Path) -> MediaInfo:
        options = {**self._base_options(workdir), "skip_download": True, "extract_flat": "in_playlist"}
        info = _run_ytdlp(options, url, download=False)

        if info.get("_type") in ("playlist", "multi_video"):
            raise MediaError("playlist")
        if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming"):
            raise MediaError("live")

        duration = info.get("duration")
        return MediaInfo(
            url=info.get("webpage_url") or url,
            title=info.get("title") or "video",
            duration=duration,
            uploader=info.get("uploader") or info.get("channel"),
            qualities=extract_qualities(info.get("formats") or [], duration),
            audio_size=estimate_mp3_size(duration),
            extracted=_reusable_info(info),
        )

    def _download_with_fallback(
        self, url: str, choice: str, workdir: Path, extracted: dict[str, Any] | None
    ) -> DownloadedFile:
        if extracted is None:
            return self._download_sync(url, choice, workdir, None)
        try:
            return self._download_sync(url, choice, workdir, extracted)
        except MediaError as err:
            if err.code == "too_large":
                raise
            # The saved links may have expired; a fresh lookup gets new ones.
            logger.info("Saved lookup for %s failed (%s), looking it up again", url, err.code)
        _empty_dir(workdir)
        return self._download_sync(url, choice, workdir, None)

    def _download_sync(self, url: str, choice: str, workdir: Path, extracted: dict[str, Any] | None) -> DownloadedFile:
        options = {
            **self._base_options(workdir),
            "paths": {"home": str(workdir), "temp": str(workdir)},
            "outtmpl": "%(id).60B.%(ext)s",
            "max_filesize": self._max_file_size,
            **_format_options(choice),
        }
        info = _run_ytdlp(options, url, download=True, saved_info=extracted)

        path = _find_output_file(workdir)
        if path is None:
            # yt-dlp silently skips files over max_filesize.
            raise MediaError("too_large", size=_selected_size(info))
        size = path.stat().st_size
        if size > self._max_file_size:
            # Streams (HLS/DASH) don't always report their size in advance.
            raise MediaError("too_large", size=size)

        is_audio = choice == AUDIO_CHOICE
        return DownloadedFile(
            path=path,
            kind="audio" if is_audio else "video",
            title=info.get("title") or "video",
            duration=int(info["duration"]) if info.get("duration") else None,
            width=None if is_audio else info.get("width"),
            height=None if is_audio else info.get("height"),
            uploader=info.get("uploader") or info.get("channel"),
        )


def _format_options(choice: str) -> dict[str, Any]:
    if choice == AUDIO_CHOICE:
        return {
            "format": "ba/b",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": str(MP3_BITRATE_KBPS),
                }
            ],
        }
    height = None if choice == BEST_CHOICE else int(choice)
    return {
        "format": video_format_selector(height),
        "format_sort": list(FORMAT_SORT),
        "merge_output_format": "mp4",
    }


def _run_ytdlp(
    options: dict[str, Any], url: str, *, download: bool, saved_info: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Look up `url`, or with `saved_info` reuse an earlier lookup (like yt-dlp's --load-info-json)."""
    try:
        with YoutubeDL(options) as ydl:
            if saved_info is None:
                info = ydl.extract_info(url, download=download)
            else:
                # yt-dlp fills in the dict as it works; keep the saved one untouched for retries.
                info = ydl.process_ie_result(copy.deepcopy(saved_info), download=download)
    except DownloadError as exc:
        raise MediaError(classify_error(str(exc))) from exc
    if not info:
        raise MediaError("error_unsupported")
    return info


def _reusable_info(info: dict[str, Any]) -> dict[str, Any]:
    clean = YoutubeDL.sanitize_info(info, remove_private_keys=True)
    return {key: value for key, value in clean.items() if key not in UNUSED_INFO_KEYS}


def _empty_dir(workdir: Path) -> None:
    for path in workdir.iterdir():
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)


def classify_error(message: str) -> str:
    """Turn a yt-dlp error message into an i18n key the user will understand."""
    lowered = message.lower()
    for code, needles in _ERROR_PATTERNS:
        if any(needle in lowered for needle in needles):
            return code
    return "error_generic"


def _find_output_file(workdir: Path) -> Path | None:
    """The finished file is the largest one left (yt-dlp removes its partial/fragment files)."""
    files = [
        p
        for p in workdir.iterdir()
        if p.is_file() and p.name != COOKIES_COPY_NAME and not p.name.endswith((".part", ".ytdl"))
    ]
    return max(files, key=lambda p: p.stat().st_size, default=None)


def _selected_size(info: dict[str, Any]) -> int | None:
    formats = info.get("requested_formats") or [info]
    sizes = [estimate_size(f, info.get("duration")) for f in formats]
    return None if any(s is None for s in sizes) else sum(sizes)  # type: ignore[arg-type]
