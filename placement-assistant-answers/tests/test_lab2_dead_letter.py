"""Lab 2 — retry with backoff, and dead-letter a poison run instead of retrying forever."""
import pytest

from app.providers import AgentError, ModelTurn, ScriptedProvider
from app.worker import Worker


def claimed(store, max_attempts=3):
    run_id = store.enqueue(store.create_thread("22CS045"), "hi", "mock", max_attempts=max_attempts)
    store.claim_next("w", 30)
    return run_id


def test_retryable_failure_goes_back_to_the_queue_with_backoff(store, clock):
    run_id = claimed(store)
    assert store.fail_attempt(run_id, "w", "provider_rate_limited", retryable=True) == "queued"
    run = store.get_run(run_id)
    assert run["status"] == "queued" and run["lease_owner"] is None
    assert run["error_code"] == "provider_rate_limited" and run["available_at"] == clock() + 2.0


@pytest.mark.parametrize("attempt, delay", [(1, 2.0), (2, 4.0)])
def test_backoff_doubles(store, clock, attempt, delay):
    run_id = claimed(store, max_attempts=5)
    for _ in range(attempt - 1):
        store.fail_attempt(run_id, "w", "x", retryable=True)
        clock.advance(100)
        store.claim_next("w", 30)
    store.fail_attempt(run_id, "w", "x", retryable=True)
    assert store.get_run(run_id)["available_at"] == clock() + delay


def test_non_retryable_failure_is_final(store):
    run_id = claimed(store)
    assert store.fail_attempt(run_id, "w", "step_limit", retryable=False) == "failed"
    run = store.get_run(run_id)
    assert run["status"] == "failed" and run["finished_at"] is not None


def test_only_the_owner_can_fail_an_attempt(store):
    run_id = claimed(store)
    assert store.fail_attempt(run_id, "intruder", "x", retryable=True) is None
    assert store.get_run(run_id)["status"] == "running"


def test_a_poison_run_is_dead_lettered(store, placement, clock):
    run_id = store.enqueue(store.create_thread("22CS045"), "hi", "mock")
    always_down = ScriptedProvider([AgentError("provider_unavailable", "down", retryable=True)], loop=True)
    worker = Worker(store, placement, always_down, worker_id="w")
    outcomes = []
    for _ in range(10):
        item = worker.run_once()
        if item:
            outcomes.append(item[1])
        clock.advance(60)
    assert outcomes == ["queued", "queued", "dead"]
    assert len(always_down.calls) == 3
    assert store.get_run(run_id)["error_code"] == "provider_unavailable"


def test_a_healthy_run_after_a_blip_succeeds(store, placement, clock):
    run_id = store.enqueue(store.create_thread("22CS045"), "hi", "mock")
    flaky = ScriptedProvider([AgentError("provider_rate_limited", "quota", retryable=True), ModelTurn(text="hello")])
    worker = Worker(store, placement, flaky, worker_id="w")
    assert worker.run_once()[1] == "queued"
    clock.advance(2)
    assert worker.run_once() == (run_id, "succeeded")
