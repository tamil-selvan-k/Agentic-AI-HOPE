"""Lab 1 — cancel: a queued run stops at once; a running run stops after its current step, never mid-tool."""
from app.providers import booking_mock
from app.tools.placement_tools import PlacementTools
from app.worker import Worker


def queued(store):
    return store.enqueue(store.create_thread("22CS045"), "Apply me to Zoho", "mock")


def test_cancelling_a_queued_run_is_immediate(store, placement):
    run_id = queued(store)
    assert store.request_cancel(run_id) == "cancelled"
    assert store.get_run(run_id)["finished_at"] is not None
    assert Worker(store, placement, booking_mock(), worker_id="w").run_once() is None


def test_unknown_and_finished_runs(store, placement):
    assert store.request_cancel("nope") is None
    run_id = queued(store)
    Worker(store, placement, booking_mock(), worker_id="w").run_until_idle()
    assert store.request_cancel(run_id) == "succeeded"
    assert store.get_run(run_id)["cancel_requested"] == 0


def test_a_running_run_finishes_its_current_tool_then_stops(store, placement):
    run_id = queued(store)

    class CancelDuringApply(PlacementTools):
        def apply_to_drive(self, student_id: str, drive_id: int) -> dict:
            assert store.request_cancel(run_id) == "running"      # the user cancels while this tool runs
            return super().apply_to_drive(student_id, drive_id)

    worker = Worker(store, placement, booking_mock(), worker_id="w")
    worker.tools = CancelDuringApply(placement)
    assert worker.run_until_idle() == [(run_id, "cancelled")]

    run = store.get_run(run_id)
    assert run["status"] == "cancelled" and run["lease_owner"] is None and run["finished_at"] is not None
    tools_run = [s["tool_name"] for s in run["steps"] if s["kind"] == "tool"]
    assert tools_run == ["check_eligibility", "apply_to_drive"]        # apply finished and was recorded
    assert placement.count("application") == 1                          # its side effect stands
    assert placement.conn.execute("SELECT count(*) FROM interview_slot WHERE student_id IS NOT NULL").fetchone()[0] == 0


def test_mark_cancelled_only_for_the_owner(store):
    run_id = queued(store)
    store.claim_next("w1", 30)
    assert store.mark_cancelled(run_id, "someone-else") is False
    assert store.mark_cancelled(run_id, "w1") is True
