"""UserStore, DownloadProgress and the cancel switch in UserJobLimiter."""

import json

import pytest
from yt_dlp.utils import DownloadCancelled

from bot.services.job_limiter import UserJobLimiter
from bot.services.progress import DownloadProgress
from bot.services.user_store import UserStore


def store(tmp_path, owners=frozenset({1})) -> UserStore:
    return UserStore(tmp_path / "state" / "users.json", owners)


def test_owners_are_always_allowed(tmp_path):
    users = store(tmp_path)

    assert users.is_allowed(1)
    assert not users.is_allowed(2)
    assert not users.remove(1)


def test_approved_users_are_saved_and_loaded(tmp_path):
    users = store(tmp_path)
    users.add_request(5, "Zed")
    users.approve(5, "Zed")
    users.approve(6, "amy")
    users.deny(7)

    reloaded = store(tmp_path)

    assert reloaded.is_allowed(5) and reloaded.is_allowed(6)
    assert reloaded.is_denied(7)
    assert reloaded.approved() == [(6, "amy"), (5, "Zed")]
    assert not reloaded.has_request(5)
    assert not (tmp_path / "state" / "users.tmp").exists()


def test_requests_are_remembered_until_answered(tmp_path):
    users = store(tmp_path)

    users.add_request(5, "Bob")

    assert users.has_request(5)
    assert users.request_name(5) == "Bob"
    users.deny(5)
    assert not users.has_request(5)
    assert users.request_name(5) == "5"


def test_approving_a_denied_user_and_denying_an_approved_one(tmp_path):
    users = store(tmp_path)
    users.deny(5)
    users.approve(5, "Bob")
    assert users.is_allowed(5) and not users.is_denied(5)

    users.deny(5)

    assert not users.is_allowed(5) and users.is_denied(5)


def test_removed_user_can_ask_again(tmp_path):
    users = store(tmp_path)
    users.approve(5, "Bob")

    assert users.remove(5)

    assert not users.is_allowed(5)
    assert not users.is_denied(5)
    assert not users.remove(5)


@pytest.mark.parametrize("content", ["{not json", "[1, 2]", '{"approved": {"x": "Bob"}}'])
def test_broken_file_is_kept_aside(tmp_path, content):
    path = tmp_path / "users.json"
    path.write_text(content, encoding="utf-8")

    users = UserStore(path, frozenset({1}))
    users.approve(5, "Bob")

    assert (tmp_path / "users.broken").read_text(encoding="utf-8") == content
    assert users.approved() == [(5, "Bob")]


def test_requests_survive_a_restart(tmp_path):
    store(tmp_path).add_request(5, "Bob")

    reloaded = store(tmp_path)

    assert reloaded.has_request(5)
    assert reloaded.request_name(5) == "Bob"
    reloaded.forget_request(5)
    reloaded.forget_request(5)
    assert not store(tmp_path).has_request(5)


def test_file_format(tmp_path):
    users = store(tmp_path)
    users.approve(5, "Боб")
    users.deny(9)

    data = json.loads((tmp_path / "state" / "users.json").read_text(encoding="utf-8"))

    assert data == {"approved": {"5": "Боб"}, "denied": [9], "requests": {}}


# --- DownloadProgress ---


def test_progress_is_unknown_without_sizes():
    progress = DownloadProgress()

    progress.on_download({"filename": "a", "downloaded_bytes": 10})

    assert progress.percent is None


def test_progress_across_video_and_audio_never_goes_back():
    progress = DownloadProgress()

    # Field names as yt-dlp sends them: "finished" has no tmpfilename.
    progress.on_download({"filename": "v.mp4", "tmpfilename": "v.mp4.part", "downloaded_bytes": 60, "total_bytes": 90})
    assert progress.percent == 66
    progress.on_download({"filename": "v.mp4", "status": "finished", "downloaded_bytes": 90, "total_bytes": 90})
    assert progress.percent == 100
    progress.on_download({"filename": "a.m4a", "tmpfilename": "a.m4a.part", "downloaded_bytes": 0, "total_bytes": 10})
    assert progress.percent == 100  # 90/100 would be 90%: never goes back
    progress.on_download({"filename": "a.m4a", "status": "finished", "downloaded_bytes": 10, "total_bytes": 10})

    assert progress.percent == 100


def test_progress_counts_video_and_audio_together():
    progress = DownloadProgress()

    progress.on_download({"filename": "v.mp4", "downloaded_bytes": 10, "total_bytes": 90})
    progress.on_download({"filename": "a.m4a", "downloaded_bytes": 0, "total_bytes": 10})

    assert progress.percent == 11  # 10/90 before the audio was known; it never goes back


@pytest.mark.parametrize("hook", ["on_download", "on_postprocess"])
def test_cancelled_progress_stops_ytdlp(hook):
    progress = DownloadProgress()
    progress.cancelled.set()

    with pytest.raises(DownloadCancelled):
        getattr(progress, hook)({"filename": "a"})


# --- cancel switch ---


def test_cancel_reaches_the_running_job():
    jobs = UserJobLimiter()

    assert not jobs.cancel(1)
    with jobs.acquire(1):
        event = jobs.cancel_event(1)
        assert jobs.cancel(1)
        assert event.is_set()

    assert not jobs.is_busy(1)
    assert not jobs.cancel_event(1).is_set()  # the next job starts fresh
