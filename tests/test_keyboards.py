import pytest

from bot.keyboards import (
    AUTO_DOWNLOAD_MAX_SECONDS,
    DownloadCallback,
    audio_keyboard,
    auto_choice,
    fits,
    quality_keyboard,
)
from bot.services.media import Quality
from tests.conftest import MB, make_info


def button_rows(markup):
    return [[(b.text, DownloadCallback.unpack(b.callback_data).choice) for b in row] for row in markup.inline_keyboard]


def test_callback_data_fits_telegram_limit():
    packed = DownloadCallback(token="Ab3dE5fG", choice="2160").pack()

    assert packed == "dl:Ab3dE5fG:2160"
    assert len(packed.encode()) <= 64


def test_fits():
    assert fits(None, 10)
    assert fits(10, 10)
    assert not fits(11, 10)


def test_keyboard_skips_qualities_over_limit():
    markup = quality_keyboard(make_info(), "tok", "en", max_size=50 * MB)

    assert button_rows(markup) == [
        [("720p · ≈40.0 MB", "720"), ("360p", "360")],
        [("🎵 Audio (MP3)", "mp3")],
    ]


def test_keyboard_puts_two_qualities_per_row():
    qualities = tuple(Quality(h, f"{h}p", None) for h in (1080, 720, 480))
    markup = quality_keyboard(make_info(qualities=qualities), "tok", "ru", max_size=50 * MB)

    rows = button_rows(markup)
    assert [len(r) for r in rows] == [2, 1, 1]
    assert rows[-1] == [("🎵 Аудио (MP3)", "mp3")]


def test_keyboard_offers_best_when_site_lists_no_resolutions():
    markup = quality_keyboard(make_info(qualities=(), audio_size=None), "tok", "en", max_size=50 * MB)

    assert button_rows(markup) == [[("⬇️ Best quality", "best")], [("🎵 Audio (MP3)", "mp3")]]


def test_keyboard_without_audio_when_mp3_too_big():
    qualities = (Quality(360, "360p", 1 * MB),)
    markup = quality_keyboard(make_info(qualities=qualities, audio_size=60 * MB), "tok", "en", max_size=50 * MB)

    assert button_rows(markup) == [[("360p · ≈1.0 MB", "360")]]


def test_keyboard_is_none_when_nothing_fits():
    qualities = (Quality(360, "360p", 60 * MB),)

    assert quality_keyboard(make_info(qualities=qualities, audio_size=60 * MB), "tok", "en", 50 * MB) is None


SHORT_CLIP = 30


def test_auto_choice_sends_short_clip_with_few_qualities():
    qualities = (Quality(1280, "720p", 5 * MB), Quality(1024, "576p", 3 * MB))

    assert auto_choice(make_info(duration=SHORT_CLIP, qualities=qualities), 50 * MB) == "1280"


def test_auto_choice_skips_qualities_over_limit():
    qualities = (Quality(1280, "720p", 60 * MB), Quality(1024, "576p", 3 * MB))

    assert auto_choice(make_info(duration=SHORT_CLIP, qualities=qualities), 50 * MB) == "1024"


def test_auto_choice_uses_best_when_site_lists_no_resolutions():
    assert auto_choice(make_info(duration=SHORT_CLIP, qualities=()), 50 * MB) == "best"


@pytest.mark.parametrize(
    "info",
    [
        make_info(duration=SHORT_CLIP),  # three qualities: let the user choose
        make_info(duration=AUTO_DOWNLOAD_MAX_SECONDS + 1, qualities=()),
        make_info(duration=None, qualities=()),
        make_info(duration=SHORT_CLIP, qualities=(Quality(720, "720p", 60 * MB),)),
    ],
)
def test_auto_choice_shows_menu(info):
    assert auto_choice(info, 50 * MB) is None


def test_audio_keyboard():
    markup = audio_keyboard(make_info(), "tok", "en", 50 * MB)

    assert button_rows(markup) == [[("🎵 Audio (MP3)", "mp3")]]
    assert audio_keyboard(make_info(audio_size=60 * MB), "tok", "en", 50 * MB) is None
