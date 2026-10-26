"""Human-friendly formatting helpers."""

from __future__ import annotations

import re

_UNITS = ("B", "KB", "MB", "GB", "TB")
_UNSAFE_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
MAX_FILENAME_LENGTH = 100


def format_size(num_bytes: int | None) -> str:
    """1536 -> '1.5 KB'. Returns '?' when the size is unknown."""
    if num_bytes is None or num_bytes < 0:
        return "?"
    size = float(num_bytes)
    unit_index = 0
    while size >= 1024 and unit_index < len(_UNITS) - 1:
        size /= 1024
        unit_index += 1
    unit = _UNITS[unit_index]
    return f"{size:.0f} {unit}" if unit in ("B", "KB") else f"{size:.1f} {unit}"


def format_duration(seconds: float | None) -> str:
    """75 -> '1:15', 3725 -> '1:02:05'. Returns '' when unknown."""
    if not seconds or seconds < 0:
        return ""
    total = int(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def safe_filename(title: str, extension: str) -> str:
    """Turn a video title into a filename that works on every OS."""
    cleaned = _UNSAFE_FILENAME_CHARS.sub(" ", title)
    cleaned = " ".join(cleaned.split()).strip(" .")[:MAX_FILENAME_LENGTH].rstrip(" .")
    return f"{cleaned or 'video'}.{extension}"
