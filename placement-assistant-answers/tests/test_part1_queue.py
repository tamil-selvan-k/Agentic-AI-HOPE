"""Part 1 — the run queue: enqueue, claim, heartbeat, reap."""
import sqlite3

import pytest

from app.memory import RunStore
from app.placement_db import PlacementDb
from app.providers import ScriptedProvider
from app.worker import Worker
from tests.conftest import read_only_turns


def queued(store, text="hi", student="22CS045"):
    return store.enqueue(store.create_thread(student), text, "mock")


# ---------- enqueue

def test_enqueue_saves_message_and_queued_run(store):
    t = store.create_thread("22CS045")
    run_id = store.enqueue(t, "Am I eligible for Zoho?", "mock")
    run = store.get_run(run_id)
    assert run["status"] == "queued" and run["attempts"] == 0 and run["thread_id"] == t
    assert run["available_at"] == store.clock()
    assert store.load_history(t) == [{"seq": 1, "role": "user", "text": "Am I eligible for Zoho?"}]


def test_enqueue_is_all_or_nothing(store):
    with pytest.raises(sqlite3.IntegrityError):
        store.enqueue("no-such-thread", "hi", "mock")
    assert store.conn.execute("SELECT count(*) FROM run").fetchone()[0] == 0
    assert store.conn.execute("SELECT count(*) FROM message").fetchone()[0] == 0


# ---------- claim

def test_claim_takes_the_oldest_and_leases_it(store, clock):
    first = queued(store)
    clock.advance(1)
    queued(store)
    clock.advance(1)
    claimed = store.claim_next("w1", lease_seconds=30)
    assert claimed.run_id == first and claimed.attempts == 1
    run = store.get_run(first)
    assert run["status"] == "running" and run["lease_owner"] == "w1"
    assert run["lease_until"] == clock() + 30 and run["attempts"] == 1


def test_nothing_to_claim(store):
    assert store.claim_next("w1", 30) is None


def test_a_claimed_run_is_not_claimed_again(store):
    queued(store)
    assert store.claim_next("w1", 30) is not None
    assert store.claim_next("w2", 30) is None


def test_runs_that_are_not_available_yet_wait(store, clock):
    run_id = queued(store)
    store.conn.execute("UPDATE run SET available_at = ? WHERE id = ?", (clock() + 10, run_id))
    assert store.claim_next("w1", 30) is None
    clock.advance(10)
    assert store.claim_next("w1", 30).run_id == run_id


def test_two_workers_on_separate_connections_never_share_a_run(db_files, clock):
    agent, _ = db_files
    a, b = RunStore(agent, clock), RunStore(agent, clock)
    for _ in range(3):
        a.enqueue(a.create_thread("22CS045"), "hi", "mock")
    got = [a.claim_next("wa", 30), b.claim_next("wb", 30), a.claim_next("wa", 30), b.claim_next("wb", 30)]
    ids = [c.run_id for c in got if c]
    assert len(ids) == 3 and len(set(ids)) == 3


# ---------- heartbeat

def test_heartbeat_extends_the_lease(store, clock):
    run_id = queued(store)
    store.claim_next("w1", 30)
    clock.advance(20)
    assert store.heartbeat(run_id, "w1", 30) is True
    assert store.get_run(run_id)["lease_until"] == clock() + 30


def test_heartbeat_fails_for_a_worker_that_does_not_own_the_run(store):
    run_id = queued(store)
    store.claim_next("w1", 30)
    assert store.heartbeat(run_id, "w2", 30) is False


# ---------- reap

def test_expired_lease_goes_back_to_the_queue(store, clock):
    run_id = queued(store)
    store.claim_next("w1", 30)
    clock.advance(31)
    assert store.reap_expired() == [run_id]
    run = store.get_run(run_id)
    assert run["status"] == "queued" and run["lease_owner"] is None and run["error_code"] == "lease_expired"
    assert store.claim_next("w2", 30).attempts == 2


def test_live_leases_are_left_alone(store, clock):
    queued(store)
    store.claim_next("w1", 30)
    clock.advance(29)
    assert store.reap_expired() == []


def test_a_run_that_keeps_killing_workers_is_dead_lettered(store, clock):
    run_id = queued(store)
    for _ in range(3):                      # max_attempts defaults to 3
        store.claim_next("w", 30)
        clock.advance(31)
        store.reap_expired()
    run = store.get_run(run_id)
    assert run["status"] == "dead" and run["error_code"] == "lease_expired"


# ---------- a worker, end to end

def test_worker_runs_a_queued_question(store, placement):
    t = store.create_thread("22CS045")
    run_id = store.enqueue(t, "Am I eligible for Zoho?", "mock")
    worker = Worker(store, placement, ScriptedProvider(read_only_turns()), worker_id="w1")
    assert worker.run_until_idle() == [(run_id, "succeeded")]
    run = store.get_run(run_id)
    assert run["status"] == "succeeded" and run["lease_owner"] is None
    assert [s["kind"] for s in run["steps"]] == ["model", "tool", "model"]
    assert store.load_history(t)[-1] == {"seq": 2, "role": "model", "text": "Yes, you meet all four Zoho rules."}


def test_a_worker_that_lost_its_lease_writes_nothing_more(store, placement, clock):
    run_id = queued(store)
    claimed = store.claim_next("slow-worker", 30)
    clock.advance(31)
    store.reap_expired()
    store.claim_next("new-worker", 30)
    from app.runner import LeaseLost, execute_run
    from app.tools.placement_tools import PlacementTools

    with pytest.raises(LeaseLost):
        execute_run(claimed, store=store, placement=placement, tools=PlacementTools(placement),
                    provider=ScriptedProvider(read_only_turns()), worker_id="slow-worker", lease_seconds=30)
    assert store.get_run(run_id)["steps"] == []
