import pytest

from bot.i18n import TEXTS, resolve_lang, t


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("ru", "ru"),
        ("ru-RU", "ru"),
        ("ky", "ru"),
        ("KK", "ru"),
        ("en", "en"),
        ("en-US", "en"),
        ("de", "en"),
        (None, "en"),
        ("", "en"),
    ],
)
def test_resolve_lang(code, expected):
    assert resolve_lang(code) == expected


def test_all_languages_have_the_same_keys():
    english_keys = set(TEXTS["en"])
    for lang, texts in TEXTS.items():
        assert set(texts) == english_keys, f"{lang} is missing or has extra keys"


def test_formats_placeholders():
    assert "42" in t("en", "not_allowed", user_id=42)
    assert "42" in t("ru", "not_allowed", user_id=42)


def test_unknown_language_falls_back_to_english():
    assert t("xx", "no_link") == TEXTS["en"]["no_link"]


def test_extra_params_are_ignored():
    assert t("en", "busy", limit="50 MB") == TEXTS["en"]["busy"]
