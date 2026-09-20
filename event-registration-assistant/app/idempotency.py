"""Stable fingerprints for side effects. Hashing, used for exactly-once."""
import hashlib
import json
from datetime import date


def _normalise(value):
    """Make equal things look equal: 12.0 and 12 are the same drive id."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {str(k): _normalise(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalise(v) for v in value]
    return value


def canonical_json(value) -> str:
    """One spelling per meaning: sorted keys, no spaces, integers for whole floats."""
    return json.dumps(_normalise(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def idempotency_key(run_id: str, step_seq: int, tool_name: str, args: dict) -> str:
    """The same tool call at the same step of the same run always gets the same key."""
    return _sha256(canonical_json([run_id, step_seq, tool_name, args]))


def notification_dedupe_key(roll_no: str, message: str, day: date) -> str:
    """The same message to the same student on the same day is one notification."""
    return _sha256(canonical_json([roll_no, " ".join(message.split()), day.isoformat()]))
