from contextlib import contextmanager

import pytest
from sqlalchemy.exc import OperationalError

from remoteops.config import Settings
from remoteops.worker import run_worker


class StopAfterOneWait:
    def __init__(self, waits_before_stop: int = 1) -> None:
        self.waits: list[float] = []
        self.waits_before_stop = waits_before_stop

    def is_set(self) -> bool:
        return False

    def wait(self, timeout: float) -> bool:
        self.waits.append(timeout)
        return len(self.waits) >= self.waits_before_stop


def test_worker_uses_a_fresh_session_and_interruptible_wait() -> None:
    sessions: list[object] = []

    @contextmanager
    def session_factory():
        session = object()
        sessions.append(session)
        yield session

    stop = StopAfterOneWait(waits_before_stop=2)
    processed: list[object] = []

    run_worker(
        stop_event=stop,
        poll_seconds=2.5,
        session_factory=session_factory,
        processor=lambda session: processed.append(session) or 0,
    )

    assert processed == sessions
    assert len({id(session) for session in sessions}) == 2
    assert stop.waits == [2.5, 2.5]


def test_worker_retries_database_failures(caplog: pytest.LogCaptureFixture) -> None:
    @contextmanager
    def session_factory():
        yield object()

    stop = StopAfterOneWait()

    def unavailable(_session: object) -> int:
        raise OperationalError("SELECT 1", {}, ConnectionError("offline"))

    run_worker(
        stop_event=stop,
        poll_seconds=1,
        session_factory=session_factory,
        processor=unavailable,
    )

    assert "database operation failed" in caplog.text
    assert stop.waits == [1]


def test_worker_does_not_hide_programming_errors() -> None:
    @contextmanager
    def session_factory():
        yield object()

    def broken(_session: object) -> int:
        raise RuntimeError("bug")

    with pytest.raises(RuntimeError, match="bug"):
        run_worker(
            stop_event=StopAfterOneWait(),
            poll_seconds=1,
            session_factory=session_factory,
            processor=broken,
        )


def test_worker_poll_interval_must_be_positive() -> None:
    with pytest.raises(ValueError):
        Settings(
            database_url="postgresql+psycopg://localhost/remoteops",
            jwt_secret="test-only-secret-at-least-32-characters",
            webhook_worker_poll_seconds=0,
        )
