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
    assert settings.proxy_url is None
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
            "PROXY_URL": " socks5://user:pass@proxy.example:1080 ",
            "DOWNLOAD_DIR": "/downloads",
            "LOG_LEVEL": "debug",
        }
    )

    assert settings.allowed_user_ids == frozenset({1, 2, 3})
    assert settings.max_file_size_mb == 20
    assert settings.max_concurrent_downloads == 4
    assert settings.cookies_file == Path("/app/data/cookies.txt")
    assert settings.proxy_url == "socks5://user:pass@proxy.example:1080"
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
        ({**BASE_ENV, "PROXY_URL": "ftp://proxy:21"}, "PROXY_URL"),
        ({**BASE_ENV, "PROXY_URL": "proxy.example:1080"}, "PROXY_URL"),
        ({**BASE_ENV, "PROXY_URL": "http://proxy:port"}, "PROXY_URL"),
    ],
)
def test_invalid_env_raises_clear_error(env, message):
    with pytest.raises(ConfigError, match=message):
        Settings.from_env(env)


def test_proxy_error_does_not_leak_password():
    with pytest.raises(ConfigError) as err:
        Settings.from_env({**BASE_ENV, "PROXY_URL": "ftp://user:secret@proxy:21"})

    assert "secret" not in str(err.value)


def test_proxy_is_hidden_from_repr():
    settings = Settings.from_env({**BASE_ENV, "PROXY_URL": "http://user:secret@proxy:8080"})

    assert "secret" not in repr(settings)


def test_reads_os_environ_when_no_env_given(monkeypatch):
    monkeypatch.setattr("bot.config.load_dotenv", lambda: None)
    monkeypatch.setenv("BOT_TOKEN", "999:zzz")
    monkeypatch.setenv("ALLOWED_USER_IDS", "5")

    assert Settings.from_env().bot_token == "999:zzz"


def test_first_allowed_id_is_the_owner():
    settings = Settings.from_env({**BASE_ENV, "ALLOWED_USER_IDS": "333, 111,222"})

    assert settings.admin_user_id == 333
    assert settings.users_file == Path("state/users.json")


def test_users_file_can_be_set():
    settings = Settings.from_env({**BASE_ENV, "USERS_FILE": "/app/state/u.json"})

    assert settings.users_file == Path("/app/state/u.json")
