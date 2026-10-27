"""Allow each user only one download at a time (protects the server from button spam)."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager


class UserJobLimiter:
    def __init__(self) -> None:
        # One "cancel" switch per running job. A threading.Event, because the download thread checks it.
        self._busy: dict[int, threading.Event] = {}

    def is_busy(self, user_id: int) -> bool:
        return user_id in self._busy

    @contextmanager
    def acquire(self, user_id: int) -> Iterator[bool]:
        """Yield True if the user had no job running (and mark them busy), else False."""
        if user_id in self._busy:
            yield False
            return
        self._busy[user_id] = threading.Event()
        try:
            yield True
        finally:
            self._busy.pop(user_id, None)

    def cancel_event(self, user_id: int) -> threading.Event:
        """The switch for the user's running job; a fresh one if nothing is running."""
        return self._busy.get(user_id) or threading.Event()

    def cancel(self, user_id: int) -> bool:
        """Ask the user's running job to stop. False if nothing is running."""
        event = self._busy.get(user_id)
        if event is None:
            return False
        event.set()
        return True
