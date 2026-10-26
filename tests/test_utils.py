import pytest

from bot.utils.formatting import format_duration, format_size, safe_filename
from bot.utils.urls import extract_url, is_public_url


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("https://youtu.be/abc", "https://youtu.be/abc"),
        ("look: https://www.youtube.com/watch?v=abc&t=10s nice", "https://www.youtube.com/watch?v=abc&t=10s"),
        ("(https://vimeo.com/123).", "https://vimeo.com/123"),
        ("HTTP://EXAMPLE.COM/x", "HTTP://EXAMPLE.COM/x"),
        ("no link here", None),
        ("ftp://example.com/file", None),
        ("", None),
        (None, None),
    ],
)
def test_extract_url(text, expected):
    assert extract_url(text) == expected


FAKE_DNS = {
    "www.youtube.com": ["142.250.74.46", "2a00:1450:4001:82b::200e"],
    "youtu.be": ["142.250.74.46"],
    "127.0.0.1.nip.io": ["127.0.0.1"],
    "mixed.example.com": ["142.250.74.46", "10.0.0.1"],
    "linklocal.example.com": ["fe80::1%eth0"],
}


def fake_resolve(host, port):
    if host not in FAKE_DNS:
        raise OSError("Name or service not known")
    return [(None, None, None, "", (address, 0)) for address in FAKE_DNS[host]]


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.youtube.com/watch?v=abc", True),
        ("https://youtu.be/abc", True),
        ("http://8.8.8.8/video", True),
        # Hostnames that resolve to private addresses
        ("http://127.0.0.1.nip.io/", False),
        ("http://mixed.example.com/", False),
        ("http://linklocal.example.com/", False),
        ("http://does-not-exist.example.com/", False),
        # Unusual IPv4 spellings that Linux still treats as addresses
        ("http://127.1:8081/", False),
        ("http://0x7f.0.0.1/", False),
        ("http://0177.0.0.1/", False),
        ("http://10.1/", False),
        ("http://localhost:8081/bot", False),
        ("http://telegram-bot-api:8081/", False),
        ("http://router.local/", False),
        ("http://foo.localhost/", False),
        ("http://127.0.0.1/", False),
        ("http://10.0.0.5/", False),
        ("http://192.168.1.1/", False),
        ("http://169.254.169.254/latest/meta-data", False),
        ("http://[::1]/", False),
        ("http://[2001:4860:4860::8888]/", True),
        ("http://[::1/", False),
        ("ftp://example.com/", False),
        ("https://", False),
    ],
)
def test_is_public_url(url, expected):
    assert is_public_url(url, resolve=fake_resolve) is expected


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (None, "?"),
        (-1, "?"),
        (0, "0 B"),
        (512, "512 B"),
        (1536, "2 KB"),
        (5 * 1024**2, "5.0 MB"),
        (int(1.5 * 1024**3), "1.5 GB"),
        (3 * 1024**5, "3072.0 TB"),
    ],
)
def test_format_size(size, expected):
    assert format_size(size) == expected


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(None, ""), (0, ""), (-5, ""), (9, "0:09"), (75, "1:15"), (3725, "1:02:05"), (59.9, "0:59")],
)
def test_format_duration(seconds, expected):
    assert format_duration(seconds) == expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("My Video", "My Video.mp4"),
        ('a/b\\c:d*e?f"g<h>i|j', "a b c d e f g h i j.mp4"),
        ("  dots...  ", "dots.mp4"),
        ("???", "video.mp4"),
        ("x" * 300, "x" * 100 + ".mp4"),
    ],
)
def test_safe_filename(title, expected):
    assert safe_filename(title, "mp4") == expected
