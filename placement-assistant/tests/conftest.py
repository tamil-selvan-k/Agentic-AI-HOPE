"""Shared fixtures. (Given.) Nothing here needs a network or a database server."""
import pytest

from app.data import InMemoryPlacementRepo
from app.memory import ConversationStore
from app.notify import OutboxNotifier
from app.tools.placement_tools import PlacementTools


@pytest.fixture
def repo():
    return InMemoryPlacementRepo()


@pytest.fixture
def notifier():
    return OutboxNotifier()


@pytest.fixture
def tools(repo, notifier):
    return PlacementTools(repo, notifier)


@pytest.fixture
def store():
    s = ConversationStore(":memory:")
    s.migrate()
    return s
