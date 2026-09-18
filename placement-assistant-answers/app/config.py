"""Where the two databases live, and the model to use. (Given.)"""
import os

from app.memory import RunStore
from app.placement_db import PlacementDb

AGENT_DB = os.environ.get("AGENT_DB", "agent.db")
PLACEMENT_DB = os.environ.get("PLACEMENT_DB", "placement.db")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def open_stores() -> tuple[RunStore, PlacementDb]:
    store, placement = RunStore(AGENT_DB), PlacementDb(PLACEMENT_DB)
    store.migrate()
    placement.migrate()
    return store, placement


def make_provider(mock: bool, slow: float = 0.0):
    if mock:
        from app.providers import booking_mock

        return booking_mock(slow)
    from app.providers import GeminiProvider

    return GeminiProvider(GEMINI_MODEL)
