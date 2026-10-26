from pathlib import Path

import pytest

from bot.config import CLOUD_API_LIMIT_MB, LOCAL_API_LIMIT_MB, ConfigError, Settings

BASE_ENV = {"BOT_TOKEN": "123:abc", "ALLOWED_USER_IDS": "111, 222"}


def test_minimal_env_uses_cloud_defaults():
    settings = Settings.from_env(BASE_ENV)

    assert settings.bot_token == "123:abc"
    assert settings.allowed_user_ids == frozenset({111, 222})
    assert settings.telegram_api_url is None
    assert not settings.uses_local_api
    assert settings.max_file_size_mb == CLOUD_API_LIMIT_MB
    assert settings.max_file_size_bytes == CLOUD_API_LIMIT_MB * 1024 * 1024
    assert settings.download_dir == Path("downloads")
    assert settings.max_concurrent_downloads == 2
    assert settings.cookies_file is None
    assert settings.log_level == "INFO"


def test_local_api_raises_default_limit_and_strips_trailing_slash():
    settings = Settings.from_env({**BASE_ENV, "TELEGRAM_API_URL": "http://telegram-bot-api:8081/"})

    assert settings.telegram_api_url == "http://telegram-bot-api:8081"
    assert settings.uses_local_api
    assert settings.max_file_size_mb == LOCAL_API_LIMIT_MB


def test_optional_values_are_parsed():
    settings = Settings.from_env(
        {
            **BASE_ENV,
            "ALLOWED_USER_IDS": "1;2,3",
            "MAX_FILE_SIZE_MB": "20",
            "MAX_CONCURRENT_DOWNLOADS": "4",
            "COOKIES_FILE": "/app/data/cookies.txt",
            "DOWNLOAD_DIR": "/downloads",
            "LOG_LEVEL": "debug",
        }
    )

    assert settings.allowed_user_ids == frozenset({1, 2, 3})
    assert settings.max_file_size_mb == 20
    assert settings.max_concurrent_downloads == 4
    assert settings.cookies_file == Path("/app/data/cookies.txt")
    assert settings.download_dir == Path("/downloads")
    assert settings.log_level == "DEBUG"


@pytest.mark.parametrize(
    ("env", "message"),
    [
        ({"ALLOWED_USER_IDS": "1"}, "BOT_TOKEN"),
        ({"BOT_TOKEN": "x"}, "ALLOWED_USER_IDS is empty"),
        ({**BASE_ENV, "ALLOWED_USER_IDS": "me"}, "must be numbers"),
        ({**BASE_ENV, "MAX_FILE_SIZE_MB": "big"}, "whole number"),
        ({**BASE_ENV, "MAX_CONCURRENT_DOWNLOADS": "0"}, "at least 1"),
        ({**BASE_ENV, "MAX_FILE_SIZE_MB": "100"}, "cloud Bot API"),
        ({**BASE_ENV, "TELEGRAM_API_URL": "http://x:8081", "MAX_FILE_SIZE_MB": "3000"}, "local Bot API"),
    ],
)
def test_invalid_env_raises_clear_error(env, message):
    with pytest.raises(ConfigError, match=message):
        Settings.from_env(env)


def test_reads_os_environ_when_no_env_given(monkeypatch):
    monkeypatch.setattr("bot.config.load_dotenv", lambda: None)
    monkeypatch.setenv("BOT_TOKEN", "999:zzz")
    monkeypatch.setenv("ALLOWED_USER_IDS", "5")

    assert Settings.from_env().bot_token == "999:zzz"
