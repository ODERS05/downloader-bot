"""Application settings, loaded once from environment variables (or a .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Telegram's hard upload limits for bots.
CLOUD_API_LIMIT_MB = 50
LOCAL_API_LIMIT_MB = 2000


class ConfigError(ValueError):
    """Raised when a required setting is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    bot_token: str
    allowed_user_ids: frozenset[int]
    telegram_api_url: str | None
    max_file_size_mb: int
    download_dir: Path
    max_concurrent_downloads: int
    cookies_file: Path | None
    log_level: str

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def uses_local_api(self) -> bool:
        return self.telegram_api_url is not None

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        """Build settings from `env` (defaults to os.environ + .env file)."""
        if env is None:
            load_dotenv()
            env = dict(os.environ)

        bot_token = env.get("BOT_TOKEN", "").strip()
        if not bot_token:
            raise ConfigError("BOT_TOKEN is not set. Get one from @BotFather.")

        telegram_api_url = env.get("TELEGRAM_API_URL", "").strip().rstrip("/") or None
        telegram_limit = LOCAL_API_LIMIT_MB if telegram_api_url else CLOUD_API_LIMIT_MB
        max_file_size_mb = _parse_int(env, "MAX_FILE_SIZE_MB", telegram_limit, minimum=1)
        if max_file_size_mb > telegram_limit:
            raise ConfigError(
                f"MAX_FILE_SIZE_MB={max_file_size_mb} exceeds Telegram's limit of {telegram_limit} MB "
                + (
                    "for the local Bot API server."
                    if telegram_api_url
                    else "for the cloud Bot API. Set TELEGRAM_API_URL to use a local server (2000 MB)."
                )
            )

        cookies_raw = env.get("COOKIES_FILE", "").strip()
        cookies_file = Path(cookies_raw) if cookies_raw else None

        return cls(
            bot_token=bot_token,
            allowed_user_ids=_parse_user_ids(env.get("ALLOWED_USER_IDS", "")),
            telegram_api_url=telegram_api_url,
            max_file_size_mb=max_file_size_mb,
            download_dir=Path(env.get("DOWNLOAD_DIR", "").strip() or "downloads"),
            max_concurrent_downloads=_parse_int(env, "MAX_CONCURRENT_DOWNLOADS", 2, minimum=1),
            cookies_file=cookies_file,
            log_level=env.get("LOG_LEVEL", "INFO").strip().upper() or "INFO",
        )


def _parse_user_ids(raw: str) -> frozenset[int]:
    parts = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
    if not parts:
        raise ConfigError(
            "ALLOWED_USER_IDS is empty. Add your Telegram user ID "
            "(message @userinfobot to find it), e.g. ALLOWED_USER_IDS=123456789"
        )
    try:
        return frozenset(int(p) for p in parts)
    except ValueError as exc:
        raise ConfigError(f"ALLOWED_USER_IDS must be numbers separated by commas, got: {raw!r}") from exc


def _parse_int(env: dict[str, str], key: str, default: int, *, minimum: int) -> int:
    raw = env.get(key, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be a whole number, got: {raw!r}") from exc
    if value < minimum:
        raise ConfigError(f"{key} must be at least {minimum}, got: {value}")
    return value
