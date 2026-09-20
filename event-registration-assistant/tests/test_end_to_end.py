"""The whole thing: queue, worker, supervisor, specialists, crash, replay."""
import pytest

from app.providers import demo_providers
from app.worker import Worker
from tests.conftest import SimulatedCrash

PRIYA = "Is AI Hackathon 2026 available? If it is, register me for it and send me a text."


def ask(store, roll_no, text):
    thread = store.create_thread(roll_no)
    return thread, store.enqueue(thread, text, "mock")


def test_a_question_goes_all_the_way_through(store, db):
    thread, run_id = ask(store, "22CS045", PRIYA)
    assert Worker(store, db, demo_providers(), worker_id="w").run_until_idle() == [(run_id, "succeeded")]
    run = store.get_run(run_id)
    assert [s["tool_name"] for s in run["steps"] if s["kind"] == "tool"] == ["ask_catalogue", "ask_desk"]
    assert "registered" in store.load_history(thread)[-1]["text"]
    assert db.count("registration") == 3 and db.count("notification") == 1


def test_policy_refusal_is_a_normal_answer(store, db):
    thread, run_id = ask(store, "22IT017", "Can I register for Web3 & Cloud Symposium?")
    Worker(store, db, demo_providers(), worker_id="w").run_until_idle()
    assert store.get_run(run_id)["status"] == "succeeded"
    assert "max registration" in store.load_history(thread)[-1]["text"] or "limit" in store.load_history(thread)[-1]["text"]
    assert db.count("registration") == 2 and db.count("notification") == 0


def test_crash_inside_a_specialist_after_the_registration_does_not_duplicate_it(store, db, clock):
    _, run_id = ask(store, "22CS045", PRIYA)
    real_once = db.once

    def once_then_die(key, tool_name, effect):
        result = real_once(key, tool_name, effect)
        if tool_name == "register_event":
            raise SimulatedCrash()
        return result

    db.once = once_then_die
    with pytest.raises(SimulatedCrash):
        Worker(store, db, demo_providers(), worker_id="A", lease_seconds=30).run_once()
    db.once = real_once
    assert db.count("registration") == 3 and store.get_run(run_id)["status"] == "running"

    clock.advance(31)
    assert Worker(store, db, demo_providers(), worker_id="B", lease_seconds=30).run_until_idle() == [(run_id, "succeeded")]
    assert db.count("registration") == 3 and db.count("notification") == 1
    assert store.get_run(run_id)["attempts"] == 2


def test_asking_twice_still_one_registration(store, db):
    for _ in range(2):
        ask(store, "22CS045", PRIYA)
    Worker(store, db, demo_providers(), worker_id="w").run_until_idle()
    assert db.count("registration") == 3 and db.count("notification") == 1
