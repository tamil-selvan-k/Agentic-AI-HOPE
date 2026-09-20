import pytest

from app.event_db import EventDb
from app.memory import RunStore


class FakeClock:
    def __init__(self, start: float = 1_790_000_000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class SimulatedCrash(BaseException):
    """Like kill -9: nothing in the worker catches it."""


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def db():
    d = EventDb(":memory:")
    d.migrate()
    return d


@pytest.fixture
def store(clock):
    s = RunStore(":memory:", clock)
    s.migrate()
    return s
