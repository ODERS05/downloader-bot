import pytest

from bot.config import Settings
from bot.services.media import MediaInfo, Quality

MB = 1024 * 1024


def make_info(**overrides) -> MediaInfo:
    defaults = {
        "url": "https://www.youtube.com/watch?v=abc",
        "title": "Test <Video>",
        "duration": 125,
        "uploader": "Channel",
        "qualities": (
            Quality(height=1080, label="1080p", estimated_size=120 * MB),
            Quality(height=720, label="720p", estimated_size=40 * MB),
            Quality(height=360, label="360p", estimated_size=None),
        ),
        "audio_size": 3 * MB,
    }
    return MediaInfo(**{**defaults, **overrides})


@pytest.fixture
def settings() -> Settings:
    return Settings.from_env({"BOT_TOKEN": "123:abc", "ALLOWED_USER_IDS": "1,2"})
