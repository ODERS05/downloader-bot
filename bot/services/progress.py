"""Download progress, shared between the yt-dlp thread (writes) and the bot (reads every few seconds)."""

from __future__ import annotations

import threading
from typing import Any

from yt_dlp.utils import DownloadCancelled


class DownloadProgress:
    def __init__(self, cancelled: threading.Event | None = None) -> None:
        self.cancelled = cancelled or threading.Event()
        self.queued = False  # waiting for a free download slot
        self._percent: int | None = None
        # file name → (bytes downloaded, total bytes). A video is often two files: video + audio.
        self._files: dict[str, tuple[int, int | None]] = {}

    @property
    def percent(self) -> int | None:
        """0–100 across all files, never going down. None while the size is unknown."""
        return self._percent

    def on_download(self, status: dict[str, Any]) -> None:
        """yt-dlp progress hook. Raising DownloadCancelled from here stops the download."""
        self.check_cancelled()
        # The final name, not tmpfilename: yt-dlp's "finished" event only carries the final name.
        name = status.get("filename") or ""
        total = status.get("total_bytes") or status.get("total_bytes_estimate")
        done = status.get("downloaded_bytes") or 0
        if status.get("status") == "finished":
            done = total = total or done
        self._files[name] = (done, total)

        if any(t is None for _, t in self._files.values()):
            return
        downloaded = sum(d for d, _ in self._files.values())
        total = sum(t or 0 for _, t in self._files.values())
        percent = min(100, downloaded * 100 // max(total, 1))
        # Starting the audio file adds to the total, which would make the bar jump back.
        self._percent = max(self._percent or 0, percent)

    def on_postprocess(self, _status: dict[str, Any]) -> None:
        """yt-dlp postprocessor hook (merging, MP3 conversion)."""
        self.check_cancelled()

    def check_cancelled(self) -> None:
        if self.cancelled.is_set():
            raise DownloadCancelled()
