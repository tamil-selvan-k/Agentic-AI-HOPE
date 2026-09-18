"""Execute one claimed run, step by step, so that it can be resumed after a crash."""
import time
from collections.abc import Callable

from app.idempotency import idempotency_key
from app.memory import Claimed, RunStore
from app.placement_db import PlacementDb
from app.providers import AgentError
from app.tools.placement_tools import PlacementTools

MAX_STEPS = 12

SYSTEM = """You are the Placement Assistant for an engineering college's placement cell.
You are talking to the student with roll number {student_id}. Act only for this student.
Use the tools for every fact about drives, eligibility, applications and slots; never guess.
Eligibility is decided by check_eligibility, not by you. Keep replies short and concrete."""


class LeaseLost(Exception):
    """Another worker owns this run now. Stop without writing anything else."""


def rebuild(store: RunStore, thread_id: str, run_id: str):
    """Rebuild what the model had seen from the database. (Given.)

    Returns (contents, seq, pending, final_text):
      contents    history plus every recorded step of this run
      seq         the last step number used
      pending     [(seq, {"name", "args"})] tool calls the model asked for that have no recorded result
      final_text  the model's final answer if it was recorded but the run was never completed, else None
    """
    contents = [{"role": m["role"], "text": m["text"]} for m in store.load_history(thread_id)]
    seq, pending, final_text = 0, [], None
    for step in store.load_steps(run_id):
        if step["kind"] == "model":
            calls = step["tool_calls"] or []
            if not calls:
                final_text = step["text"] or ""
                seq = step["seq"]
                continue
            contents.append({"role": "model", "text": step["text"], "tool_calls": calls})
            pending = [(step["seq"] + i + 1, call) for i, call in enumerate(calls)]
            seq = step["seq"] + len(calls)
        else:
            contents.append({"role": "tool", "name": step["tool_name"], "result": step["result"]})
            pending = [p for p in pending if p[0] != step["seq"]]
    return contents, seq, pending, final_text


def call_tool(tools: PlacementTools, placement: PlacementDb, key: str, name: str, args: dict) -> dict:
    """Run one tool. Side-effect tools run at most once per idempotency key. Never raises."""
    try:
        if name in tools.SIDE_EFFECTS:
            result, _fresh = placement.once(key, name, lambda: tools.call(name, args))
            return result
        return tools.call(name, args)
    except NotImplementedError:
        return {"error": "not_implemented", "hint": f"{name} is not available yet. Tell the user."}
    except Exception as e:     # the effect's transaction was rolled back, and no key was stored
        return {"error": "tool_failed", "hint": f"{name} failed ({type(e).__name__}). Try another way or tell the user."}


def execute_run(claimed: Claimed, *, store: RunStore, placement: PlacementDb, tools: PlacementTools, provider,
                worker_id: str, lease_seconds: float, on_step: Callable[[dict], None] | None = None,
                record_delay: float = 0.0) -> str:
    """Drive a run to an end. Returns 'succeeded' or 'cancelled'. Raises AgentError or LeaseLost.

    record_delay widens the gap between a tool's side effect and its record, for the crash drill only."""
    run_id = claimed.run_id
    thread = store.get_thread(claimed.thread_id)
    system = SYSTEM.format(student_id=thread["student_id"])
    functions = list(tools.functions().values())
    contents, seq, pending, final_text = rebuild(store, claimed.thread_id, run_id)

    def between_steps() -> str | None:
        # TODO (lab 1): if store.cancel_requested(run_id), mark the run cancelled (raise LeaseLost if that
        # fails: someone else owns it) and return "cancelled". This is the only place a run may stop early.
        if not store.heartbeat(run_id, worker_id, lease_seconds):
            raise LeaseLost()
        return None

    if final_text is not None:                  # crashed after the answer, before completing
        if not store.complete(run_id, worker_id, final_text):
            raise LeaseLost()
        return "succeeded"

    while True:
        for step_seq, call in pending:
            if stop := between_steps():
                return stop
            key = idempotency_key(run_id, step_seq, call["name"], call["args"])
            started = time.perf_counter()
            result = call_tool(tools, placement, key, call["name"], call["args"])
            ms = round((time.perf_counter() - started) * 1000)
            ok = "error" not in result
            if record_delay:
                time.sleep(record_delay)        # crash drill: the side effect is done, its record is not
            store.record_tool_call(run_id, step_seq, call["name"], call["args"], result, ok, ms, key)
            contents.append({"role": "tool", "name": call["name"], "result": result})
            if on_step:
                on_step({"run_id": run_id, "step": step_seq, "kind": "tool", "tool": call["name"],
                         "args": call["args"], "result": result, "ok": ok, "ms": ms})
        pending = []

        if seq >= MAX_STEPS:
            raise AgentError("step_limit", f"Stopped after {MAX_STEPS} steps without an answer.", retryable=False)
        if stop := between_steps():
            return stop

        turn = provider.generate(system, contents, functions)
        seq += 1
        calls = [{"name": c.name, "args": c.args} for c in turn.tool_calls]
        store.record_model_step(run_id, seq, turn.tokens_in, turn.tokens_out, turn.text, calls)
        if on_step:
            on_step({"run_id": run_id, "step": seq, "kind": "model", "text": turn.text, "tool_calls": calls})

        if not calls:
            if not store.complete(run_id, worker_id, turn.text or ""):
                raise LeaseLost()
            return "succeeded"

        contents.append({"role": "model", "text": turn.text, "raw": turn.raw, "tool_calls": calls})
        pending = [(seq + i + 1, call) for i, call in enumerate(calls)]
        seq += len(calls)
