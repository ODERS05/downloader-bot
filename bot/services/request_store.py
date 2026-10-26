"""Short-lived memory of "link the user sent" → "qualities we offered".

Telegram button data is limited to 64 bytes, too small for a full URL, so each button
carries a short random token that points to an entry here. Entries expire after a while
and are lost on restart; the user then just sends the link again.
"""

from __future__ import annotations

import secrets
import time
from collections import OrderedDict
from collections.abc import Callable

from bot.services.media import MediaInfo

DEFAULT_TTL_SECONDS = 60 * 60
DEFAULT_MAX_ENTRIES = 1000
TOKEN_BYTES = 6  # 8 URL-safe characters


class RequestStore:
    def __init__(
        self,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[str, tuple[float, MediaInfo]] = OrderedDict()

    def put(self, info: MediaInfo) -> str:
        """Remember `info` and return the token that identifies it."""
        self._evict_expired()
        token = secrets.token_urlsafe(TOKEN_BYTES)
        self._entries[token] = (self._clock() + self._ttl, info)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)
        return token

    def get(self, token: str) -> MediaInfo | None:
        """Return the stored info, or None if the token is unknown or expired."""
        entry = self._entries.get(token)
        if entry is None:
            return None
        expires_at, info = entry
        if expires_at <= self._clock():
            del self._entries[token]
            return None
        return info

    def __len__(self) -> int:
        return len(self._entries)

    def _evict_expired(self) -> None:
        now = self._clock()
        expired = [token for token, (expires_at, _) in self._entries.items() if expires_at <= now]
        for token in expired:
            del self._entries[token]
