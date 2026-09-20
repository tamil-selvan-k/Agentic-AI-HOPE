import os


def _load_env():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(base_dir, ".env")
    if not os.path.exists(env_path):
        env_path = ".env"
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip("'\"")
                    if key and key not in os.environ:
                        os.environ[key] = value


_load_env()

from app.event_db import EventDb
from app.memory import RunStore

AGENT_DB = os.environ.get("AGENT_DB", "agent.db")
EVENT_DB = os.environ.get("EVENT_DB", os.environ.get("LIBRARY_DB", "event.db"))
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GEMINI_MODEL = GROQ_MODEL
GEMINI_API_KEY = GROQ_API_KEY


def open_stores() -> tuple[RunStore, EventDb]:
    store, db = RunStore(AGENT_DB), EventDb(EVENT_DB)
    store.migrate()
    db.migrate()
    return store, db


def make_providers(mock: bool, slow: float = 0.0) -> dict:
    """One provider per agent. With Groq all three share one client; each keeps its own prompt and tools."""
    if mock:
        from app.providers import demo_providers

        return demo_providers(slow)
    from app.providers import GroqProvider

    groq = GroqProvider(GROQ_MODEL)
    return {"supervisor": groq, "catalogue": groq, "desk": groq}
