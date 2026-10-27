"""Friends the owner approved from the chat, saved to a JSON file so they survive restarts.

Users listed in ALLOWED_USER_IDS are always allowed and can't be removed from the chat.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class UserStore:
    def __init__(self, path: Path, owner_ids: frozenset[int]) -> None:
        self._path = path
        self._owner_ids = owner_ids
        self._approved: dict[int, str] = {}  # user ID → name shown in /users
        self._denied: set[int] = set()
        self._requests: dict[int, str] = {}  # waiting for the owner's answer
        self._load()

    def is_allowed(self, user_id: int) -> bool:
        return user_id in self._owner_ids or user_id in self._approved

    def is_denied(self, user_id: int) -> bool:
        return user_id in self._denied

    def has_request(self, user_id: int) -> bool:
        """True if the owner was already asked about this user (so they're asked only once)."""
        return user_id in self._requests

    def add_request(self, user_id: int, name: str) -> None:
        self._requests[user_id] = name
        self._save()

    def forget_request(self, user_id: int) -> None:
        """The owner couldn't be asked: let the user try again later."""
        if self._requests.pop(user_id, None) is not None:
            self._save()

    def request_name(self, user_id: int) -> str:
        return self._requests.get(user_id) or self._approved.get(user_id) or str(user_id)

    def approve(self, user_id: int, name: str) -> None:
        self._requests.pop(user_id, None)
        self._denied.discard(user_id)
        self._approved[user_id] = name
        self._save()

    def deny(self, user_id: int) -> None:
        self._requests.pop(user_id, None)
        self._approved.pop(user_id, None)
        self._denied.add(user_id)
        self._save()

    def remove(self, user_id: int) -> bool:
        """Take away access. The user can ask again. False if they weren't approved from the chat."""
        if self._approved.pop(user_id, None) is None:
            return False
        self._save()
        return True

    def approved(self) -> list[tuple[int, str]]:
        return sorted(self._approved.items(), key=lambda item: item[1].lower())

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            approved = {int(user_id): str(name) for user_id, name in data.get("approved", {}).items()}
            denied = {int(user_id) for user_id in data.get("denied", [])}
            requests = {int(user_id): str(name) for user_id, name in data.get("requests", {}).items()}
        except FileNotFoundError:
            return
        except (OSError, ValueError, TypeError, AttributeError) as err:
            # Keep the broken file for a human to look at, instead of overwriting it on the next save.
            broken = self._path.with_suffix(".broken")
            logger.error("Can't read %s (%s). Moved it to %s, starting with no approved users", self._path, err, broken)
            os.replace(self._path, broken)
            return
        self._approved, self._denied, self._requests = approved, denied, requests
        logger.info("Loaded %d approved users from %s", len(self._approved), self._path)

    def _save(self) -> None:
        data = {
            "approved": {str(user_id): name for user_id, name in self._approved.items()},
            "denied": sorted(self._denied),
            "requests": {str(user_id): name for user_id, name in self._requests.items()},
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Write a temporary file and swap it in, so a crash never leaves a half-written file.
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self._path)
