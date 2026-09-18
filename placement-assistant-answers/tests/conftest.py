"""Shared fixtures. (Given.) No network, no database server: SQLite in memory or in a temp folder."""
import pytest

from app.memory import RunStore
from app.placement_db import PlacementDb
from app.providers import ModelTurn, ToolCall
from app.tools.placement_tools import PlacementTools


class FakeClock:
    """Time that only moves when a test says so."""

    def __init__(self, start: float = 1_790_000_000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class SimulatedCrash(BaseException):
    """Like kill -9: not an Exception, so nothing in the worker catches it and nothing is cleaned up."""


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def store(clock):
    s = RunStore(":memory:", clock)
    s.migrate()
    return s


@pytest.fixture
def placement():
    p = PlacementDb(":memory:")
    p.migrate()
    return p


@pytest.fixture
def tools(placement):
    return PlacementTools(placement)


@pytest.fixture
def db_files(tmp_path, clock):
    """Two connections' worth of the same database files, for tests that need two workers."""
    agent, place = str(tmp_path / "agent.db"), str(tmp_path / "placement.db")
    RunStore(agent, clock).migrate()
    PlacementDb(place).migrate()
    return agent, place


def read_only_turns():
    return [ModelTurn(text=None, tool_calls=[ToolCall("check_eligibility", {"student_id": "22CS045", "drive_id": 1})],
                      tokens_in=100, tokens_out=10),
            ModelTurn(text="Yes, you meet all four Zoho rules.", tokens_in=150, tokens_out=12)]
