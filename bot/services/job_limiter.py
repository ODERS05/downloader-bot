"""Allow each user only one download at a time (protects the server from button spam)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager


class UserJobLimiter:
    def __init__(self) -> None:
        self._busy: set[int] = set()

    def is_busy(self, user_id: int) -> bool:
        return user_id in self._busy

    @contextmanager
    def acquire(self, user_id: int) -> Iterator[bool]:
        """Yield True if the user had no job running (and mark them busy), else False."""
        if user_id in self._busy:
            yield False
            return
        self._busy.add(user_id)
        try:
            yield True
        finally:
            self._busy.discard(user_id)
