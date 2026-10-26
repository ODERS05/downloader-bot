"""Finding and validating links in user messages."""

from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_TRAILING_PUNCTUATION = ".,;:!?)]}»"
# Hosts like "127.1", "0x7f.0.0.1" or "0177.0.0.1": not valid per `ipaddress`, but Linux
# still treats them as IP addresses.
_NUMERIC_LABEL_RE = re.compile(r"^(0x[0-9a-f]*|[0-9]+)$")
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal")

Resolver = Callable[..., list[tuple[Any, ...]]]


def extract_url(text: str | None) -> str | None:
    """Return the first http(s) link in `text`, or None."""
    if not text:
        return None
    match = _URL_RE.search(text)
    if not match:
        return None
    return match.group(0).rstrip(_TRAILING_PUNCTUATION)


def is_public_url(url: str, resolve: Resolver = socket.getaddrinfo) -> bool:
    """Reject links that point at the server itself or its private network.

    yt-dlp follows any link it's given, so without this check someone could make the
    server fetch internal addresses such as http://localhost or http://telegram-bot-api:8081.
    Hostnames are resolved, and every address they point to must be public.
    This does a DNS lookup: call it from a worker thread.
    """
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        return False
    if parts.scheme not in ("http", "https") or not host:
        return False

    host = host.lower().rstrip(".")
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        pass

    # Block "localhost", single-label names (Docker services, LAN hosts) and odd IP spellings.
    if "." not in host or host.endswith(_BLOCKED_SUFFIXES):
        return False
    if all(_NUMERIC_LABEL_RE.match(label) for label in host.split(".")):
        return False

    try:
        addresses = {info[4][0] for info in resolve(host, None)}
    except (OSError, UnicodeError):
        return False
    return bool(addresses) and all(_is_global_address(address) for address in addresses)


def _is_global_address(address: str) -> bool:
    try:
        # Strip an IPv6 zone like "fe80::1%eth0".
        return ipaddress.ip_address(address.split("%")[0]).is_global
    except ValueError:
        return False
