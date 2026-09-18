"""Part 2 — idempotency keys, and a side effect that runs at most once per key."""
import pytest

from app.idempotency import canonical_json, idempotency_key
from app.providers import booking_mock
from app.worker import Worker
from tests.conftest import SimulatedCrash


# ---------- canonical JSON and keys

def test_key_order_does_not_matter():
    assert canonical_json({"a": 1, "b": 2}) == canonical_json({"b": 2, "a": 1})


def test_whole_floats_are_integers():
    assert canonical_json({"drive_id": 1.0}) == canonical_json({"drive_id": 1})
    assert canonical_json({"cgpa": 7.5}) != canonical_json({"cgpa": 7})


def test_nested_values_are_normalised_too():
    assert canonical_json({"x": [{"b": 2.0, "a": 1}]}) == canonical_json({"x": [{"a": 1, "b": 2}]})


def test_same_call_same_key():
    k1 = idempotency_key("run-1", 4, "apply_to_drive", {"student_id": "22CS045", "drive_id": 1})
    k2 = idempotency_key("run-1", 4, "apply_to_drive", {"drive_id": 1.0, "student_id": "22CS045"})
    assert k1 == k2 and len(k1) == 64 and int(k1, 16) >= 0


@pytest.mark.parametrize("change", [
    ("run-2", 4, "apply_to_drive", {"student_id": "22CS045", "drive_id": 1}),
    ("run-1", 5, "apply_to_drive", {"student_id": "22CS045", "drive_id": 1}),
    ("run-1", 4, "book_interview_slot", {"student_id": "22CS045", "drive_id": 1}),
    ("run-1", 4, "apply_to_drive", {"student_id": "22CS045", "drive_id": 2}),
])
def test_any_difference_changes_the_key(change):
    assert idempotency_key(*change) != idempotency_key("run-1", 4, "apply_to_drive", {"student_id": "22CS045", "drive_id": 1})


# ---------- once

def test_once_runs_the_effect_once(placement):
    calls = []

    def effect():
        calls.append(1)
        return {"n": len(calls)}

    assert placement.once("k1", "t", effect) == ({"n": 1}, True)
    assert placement.once("k1", "t", effect) == ({"n": 1}, False)
    assert calls == [1]
    assert placement.count("idempotency") == 1


def test_a_failed_effect_leaves_no_trace(placement):
    def effect():
        placement.create_application(1, 1)
        raise RuntimeError("crashed halfway")

    with pytest.raises(RuntimeError):
        placement.once("k1", "apply_to_drive", effect)
    assert placement.count("application") == 0 and placement.count("idempotency") == 0
    assert placement.once("k1", "apply_to_drive", lambda: {"ok": True}) == ({"ok": True}, True)


# ---------- the point of it all: a crash between the side effect and its record

def test_replay_after_a_crash_does_not_repeat_the_side_effect(store, placement, clock):
    run_id = store.enqueue(store.create_thread("22CS045"), "Apply me to Zoho", "mock")
    real_record = store.record_tool_call
    crashed = []

    def crash_after_apply(run, seq, name, *args, **kw):
        if name == "apply_to_drive" and not crashed:
            crashed.append(seq)
            raise SimulatedCrash()          # the application IS committed; its record is not
        return real_record(run, seq, name, *args, **kw)

    store.record_tool_call = crash_after_apply
    with pytest.raises(SimulatedCrash):
        Worker(store, placement, booking_mock(), worker_id="A").run_once()
    store.record_tool_call = real_record
    assert placement.count("application") == 1
    assert store.get_run(run_id)["status"] == "running"

    clock.advance(31)                       # worker A's lease runs out
    assert Worker(store, placement, booking_mock(), worker_id="B").run_until_idle() == [(run_id, "succeeded")]

    run = store.get_run(run_id)
    assert run["attempts"] == 2
    assert placement.count("application") == 1
    applies = [s for s in run["steps"] if s["kind"] == "tool" and s["tool_name"] == "apply_to_drive"]
    assert len(applies) == 1 and applies[0]["result"]["already_applied"] is False   # the stored first result
    booked = placement.conn.execute("SELECT count(*) FROM interview_slot WHERE student_id IS NOT NULL").fetchone()[0]
    assert booked == 1 and placement.count("notification") == 1


def test_recorded_calls_match_stored_idempotency_rows(store, placement):
    run_id = store.enqueue(store.create_thread("22CS045"), "Apply me", "mock")
    Worker(store, placement, booking_mock(), worker_id="A").run_until_idle()
    keys = [r[0] for r in store.conn.execute("SELECT idempotency_key FROM tool_call")]
    assert all(k and len(k) == 64 for k in keys) and len(set(keys)) == len(keys)
    stored = {r[0] for r in placement.conn.execute("SELECT key FROM idempotency")}
    side_effect_keys = {r[0] for r in store.conn.execute(
        "SELECT idempotency_key FROM tool_call WHERE tool_name IN ('apply_to_drive', 'book_interview_slot', 'notify_student')")}
    assert side_effect_keys == stored
    assert run_id
