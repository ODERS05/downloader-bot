"""Data models and pure helpers for working with yt-dlp's format lists.

Nothing in this module touches the network, so it is easy to unit test.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

# Values stored in the button's callback data.
AUDIO_CHOICE = "mp3"
BEST_CHOICE = "best"

MP3_BITRATE_KBPS = 192
MAX_QUALITY_BUTTONS = 8

# Among formats with the same resolution, prefer H.264 video + AAC audio in MP4:
# it plays inline on every Telegram client (VP9/AV1 doesn't on some older phones).
FORMAT_SORT = ("res", "vcodec:h264", "ext:mp4:m4a")


@dataclass(frozen=True)
class Quality:
    height: int  # used to select the format; for vertical videos this is the long side
    label: str  # what the user sees, e.g. "1080p"
    estimated_size: int | None  # bytes, video + audio; None if the site doesn't say


@dataclass(frozen=True)
class MediaInfo:
    url: str
    title: str
    duration: float | None
    uploader: str | None
    qualities: tuple[Quality, ...]  # best first
    audio_size: int | None  # estimated MP3 size in bytes


@dataclass(frozen=True)
class DownloadedFile:
    path: Path
    kind: Literal["video", "audio"]
    title: str
    duration: int | None
    width: int | None
    height: int | None
    uploader: str | None


class MediaError(Exception):
    """A download problem we can explain to the user.

    `code` is an i18n key (see bot/i18n.py); `params` fill the placeholders.
    """

    def __init__(self, code: str, **params: Any) -> None:
        super().__init__(code)
        self.code = code
        self.params = params


def is_video_choice(choice: str) -> bool:
    return choice == BEST_CHOICE or choice.isdigit()


def video_format_selector(height: int | None) -> str:
    """yt-dlp format string: best video up to `height` + best audio, or a single combined file."""
    if height is None:
        return "bv*+ba/b"
    limit = f"[height<=?{height}]"
    return f"bv*{limit}+ba/b{limit}"


def extract_qualities(formats: list[dict[str, Any]], duration: float | None) -> tuple[Quality, ...]:
    """Group video formats by resolution and estimate each one's download size."""
    audio_size = _best_audio_size(formats, duration)
    by_height: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for fmt in formats:
        if _has_video(fmt) and fmt.get("height"):
            by_height[int(fmt["height"])].append(fmt)

    qualities = []
    for height, group in by_height.items():
        chosen = _preferred_video_format(group)
        size = estimate_size(chosen, duration)
        if size is not None and not _has_audio(chosen) and audio_size is not None:
            size += audio_size
        qualities.append(Quality(height=height, label=_quality_label(chosen, height), estimated_size=size))

    qualities.sort(key=lambda q: q.height, reverse=True)
    return tuple(_dedupe_labels(qualities)[:MAX_QUALITY_BUTTONS])


def estimate_mp3_size(duration: float | None) -> int | None:
    if not duration:
        return None
    return int(duration * MP3_BITRATE_KBPS * 1000 / 8)


def estimate_size(fmt: dict[str, Any], duration: float | None) -> int | None:
    """Exact size if the site reports it, otherwise bitrate × duration."""
    size = fmt.get("filesize") or fmt.get("filesize_approx")
    if size:
        return int(size)
    bitrate_kbps = fmt.get("tbr")
    if bitrate_kbps and duration:
        return int(bitrate_kbps * 1000 / 8 * duration)
    return None


def _has_video(fmt: dict[str, Any]) -> bool:
    vcodec = fmt.get("vcodec")
    # Storyboards (thumbnail strips) have no codec but an "mhtml" extension.
    return vcodec not in (None, "none") and fmt.get("ext") != "mhtml"


def _has_audio(fmt: dict[str, Any]) -> bool:
    return fmt.get("acodec") not in (None, "none")


def _is_h264(fmt: dict[str, Any]) -> bool:
    return str(fmt.get("vcodec", "")).startswith(("avc1", "h264"))


def _preferred_video_format(group: list[dict[str, Any]]) -> dict[str, Any]:
    """Mirror FORMAT_SORT: H.264 first, then the highest bitrate."""
    return max(group, key=lambda f: (_is_h264(f), f.get("tbr") or 0))


def _best_audio_size(formats: list[dict[str, Any]], duration: float | None) -> int | None:
    audio_only = [f for f in formats if _has_audio(f) and not _has_video(f)]
    if not audio_only:
        return None
    best = max(audio_only, key=lambda f: (f.get("ext") == "m4a", f.get("abr") or 0))
    return estimate_size(best, duration)


def _quality_label(fmt: dict[str, Any], height: int) -> str:
    # Vertical videos (Shorts, TikTok) are 1080x1920: people call that "1080p", not "1920p".
    width = fmt.get("width")
    short_side = min(height, int(width)) if width else height
    return f"{short_side}p"


def _dedupe_labels(qualities: list[Quality]) -> list[Quality]:
    seen: set[str] = set()
    unique = []
    for quality in qualities:
        if quality.label not in seen:
            seen.add(quality.label)
            unique.append(quality)
    return unique
