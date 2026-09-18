"""Part 3.2 and 3.3 — the ConversationStore, and an agent that remembers."""
import json
import sqlite3

import pytest

from app.agent import Agent
from app.memory import ConversationStore
from app.providers import AgentError, ModelTurn, ScriptedProvider, ToolCall


# ---------- 3.2 the store

def test_append_message_numbers_each_thread_from_one(store):
    a, b = store.create_thread("22CS045"), store.create_thread("22IT017")
    assert [store.append_message(a, "user", "1"), store.append_message(a, "model", "2")] == [1, 2]
    assert store.append_message(b, "user", "x") == 1


def test_load_history_in_order(store):
    t = store.create_thread("22CS045")
    for role, text in [("user", "hi"), ("model", "hello"), ("user", "bye")]:
        store.append_message(t, role, text)
    assert store.load_history(t) == [{"seq": 1, "role": "user", "text": "hi"},
                                     {"seq": 2, "role": "model", "text": "hello"},
                                     {"seq": 3, "role": "user", "text": "bye"}]


def test_run_lifecycle_and_token_totals(store):
    t = store.create_thread("22CS045")
    run = store.start_run(t, "mock")
    assert store.get_run(run)["status"] == "running"
    store.record_model_step(run, 1, 100, 10)
    store.record_tool_call(run, 2, "get_student", {"student_id": "22CS045"}, {"name": "Priya"}, True, 4)
    store.record_model_step(run, 3, 150, 20)
    store.finish_run(run, "succeeded")
    r = store.get_run(run)
    assert r["status"] == "succeeded" and r["finished_at"] is not None
    assert (r["tokens_in"], r["tokens_out"]) == (250, 30)
    assert [s["kind"] for s in r["steps"]] == ["model", "tool", "model"]
    tool = r["steps"][1]
    assert tool["tool_name"] == "get_student" and tool["ok"] == 1
    assert json.loads(tool["args"]) == {"student_id": "22CS045"}
    assert json.loads(tool["result"]) == {"name": "Priya"}


def test_failed_run_keeps_its_error_code(store):
    run = store.start_run(store.create_thread("22CS045"), "mock")
    store.finish_run(run, "failed", "step_limit")
    assert store.get_run(run)["error_code"] == "step_limit"


def test_step_and_tool_call_commit_together(store):
    run = store.start_run(store.create_thread("22CS045"), "mock")
    with pytest.raises(sqlite3.IntegrityError):
        # tool_name NOT NULL makes the SECOND insert fail; the first must be rolled back with it.
        store.record_tool_call(run, 1, None, {}, {}, True, 1)
    assert store.conn.execute("SELECT count(*) FROM run_step").fetchone()[0] == 0


# ---------- 3.3 an agent that remembers

def check_turns():
    return [ModelTurn(text=None, tool_calls=[ToolCall("check_eligibility", {"student_id": "22CS045", "drive_id": 1})],
                      tokens_in=100, tokens_out=10),
            ModelTurn(text="Yes, eligible.", tokens_in=150, tokens_out=12)]


def test_agent_saves_messages_and_steps(tools, store):
    t = store.create_thread("22CS045")
    agent = Agent(ScriptedProvider(check_turns()), tools, "22CS045", memory=store, thread_id=t)
    agent.ask("Am I eligible for Zoho?")
    assert [(m["role"], m["text"]) for m in store.load_history(t)] == [
        ("user", "Am I eligible for Zoho?"), ("model", "Yes, eligible.")]
    run_id = store.conn.execute("SELECT id FROM run").fetchone()["id"]
    run = store.get_run(run_id)
    assert run["status"] == "succeeded" and run["model"] == "mock"
    assert [s["kind"] for s in run["steps"]] == ["model", "tool", "model"]
    assert (run["tokens_in"], run["tokens_out"]) == (250, 22)


def test_a_new_agent_continues_the_saved_conversation(tools, tmp_path):
    path = str(tmp_path / "agent.db")
    first = ConversationStore(path)
    first.migrate()
    t = first.create_thread("22CS045")
    Agent(ScriptedProvider([ModelTurn(text="first answer")]), tools, "22CS045", memory=first, thread_id=t).ask("one")

    again = ConversationStore(path)            # a new process would open the file like this
    provider = ScriptedProvider([ModelTurn(text="second answer")])
    Agent(provider, tools, "22CS045", memory=again, thread_id=t).ask("two")
    assert [c["text"] for c in provider.calls[0]] == ["one", "first answer", "two"]


def test_agent_crash_mid_run_keeps_what_already_happened(tools, store, repo):
    t = store.create_thread("22CS045")
    provider = ScriptedProvider([
        ModelTurn(text=None, tool_calls=[ToolCall("apply_to_drive", {"student_id": "22CS045", "drive_id": 1})]),
        AgentError("provider_unavailable", "Model provider failed.", retryable=True),
    ])
    agent = Agent(provider, tools, "22CS045", memory=store, thread_id=t)
    with pytest.raises(AgentError):
        agent.ask("Apply me to Zoho")
    run = store.get_run(store.conn.execute("SELECT id FROM run").fetchone()["id"])
    assert run["status"] == "failed" and run["error_code"] == "provider_unavailable"
    assert [s["kind"] for s in run["steps"]] == ["model", "tool"]
    assert repo.has_application(1, 1)                      # the side effect happened...
    assert [m["role"] for m in store.load_history(t)] == ["user"]   # ...and the record explains it
