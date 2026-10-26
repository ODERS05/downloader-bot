"""RequestStore and UserJobLimiter."""

from bot.services.job_limiter import UserJobLimiter
from bot.services.request_store import RequestStore
from tests.conftest import make_info


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_store_returns_saved_info():
    store = RequestStore()
    info = make_info()

    token = store.put(info)

    assert store.get(token) is info
    assert len(token) == 8


def test_store_unknown_token():
    assert RequestStore().get("nope") is None


def test_store_entries_expire():
    clock = FakeClock()
    store = RequestStore(ttl_seconds=10, clock=clock)
    token = store.put(make_info())

    clock.now = 10

    assert store.get(token) is None
    assert len(store) == 0


def test_store_evicts_expired_on_put():
    clock = FakeClock()
    store = RequestStore(ttl_seconds=10, clock=clock)
    store.put(make_info())
    clock.now = 11

    store.put(make_info())

    assert len(store) == 1


def test_store_drops_oldest_when_full():
    store = RequestStore(max_entries=2)
    first = store.put(make_info())
    second = store.put(make_info())
    third = store.put(make_info())

    assert store.get(first) is None
    assert store.get(second) is not None
    assert store.get(third) is not None


def test_limiter_allows_one_job_per_user():
    limiter = UserJobLimiter()

    with limiter.acquire(1) as first:
        assert first
        assert limiter.is_busy(1)
        with limiter.acquire(1) as second:
            assert not second
        with limiter.acquire(2) as other_user:
            assert other_user

    assert not limiter.is_busy(1)


def test_limiter_releases_on_error():
    limiter = UserJobLimiter()

    try:
        with limiter.acquire(1):
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    assert not limiter.is_busy(1)
