"""Part 3.1 — the agent's memory schema (schema/agent.sql)."""
import sqlite3

import pytest

REQUIRED = {
    "thread": {"id", "student_id", "created_at"},
    "message": {"id", "thread_id", "seq", "role", "text", "created_at"},
    "run": {"id", "thread_id", "status", "model", "tokens_in", "tokens_out", "error_code", "started_at", "finished_at"},
    "run_step": {"id", "run_id", "seq", "kind", "tokens_in", "tokens_out", "created_at"},
    "tool_call": {"id", "run_step_id", "tool_name", "args", "result", "ok", "latency_ms", "created_at"},
}


@pytest.mark.parametrize("table", REQUIRED)
def test_table_has_required_columns(store, table):
    cols = {r["name"] for r in store.conn.execute(f"PRAGMA table_info({table})")}
    missing = REQUIRED[table] - cols
    assert not missing, f"{table} is missing {sorted(missing)}"


def test_no_business_tables_in_agent_memory(store):
    names = {r["name"] for r in store.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert not names & {"student", "drive", "application", "interview_slot", "company", "eligibility_rule"}


def thread(store):
    return store.create_thread("22CS045")


def test_message_seq_is_unique_per_thread(store):
    t = thread(store)
    sql = "INSERT INTO message (thread_id, seq, role, text) VALUES (?, 1, 'user', 'hi')"
    store.conn.execute(sql, (t,))
    with pytest.raises(sqlite3.IntegrityError):
        store.conn.execute(sql, (t,))


def test_message_role_is_constrained(store):
    with pytest.raises(sqlite3.IntegrityError):
        store.conn.execute("INSERT INTO message (thread_id, seq, role, text) VALUES (?, 1, 'wizard', 'hi')",
                           (thread(store),))


def test_message_needs_a_real_thread(store):
    with pytest.raises(sqlite3.IntegrityError):
        store.conn.execute("INSERT INTO message (thread_id, seq, role, text) VALUES ('nope', 1, 'user', 'hi')")


def test_run_status_is_constrained(store):
    with pytest.raises(sqlite3.IntegrityError):
        store.conn.execute("INSERT INTO run (id, thread_id, status, model) VALUES ('r1', ?, 'banana', 'm')",
                           (thread(store),))


def test_step_kind_is_constrained(store):
    store.conn.execute("INSERT INTO run (id, thread_id, status, model) VALUES ('r1', ?, 'running', 'm')", (thread(store),))
    with pytest.raises(sqlite3.IntegrityError):
        store.conn.execute("INSERT INTO run_step (run_id, seq, kind) VALUES ('r1', 1, 'dance')")


def test_one_tool_call_per_step(store):
    store.conn.execute("INSERT INTO run (id, thread_id, status, model) VALUES ('r1', ?, 'running', 'm')", (thread(store),))
    step = store.conn.execute("INSERT INTO run_step (run_id, seq, kind) VALUES ('r1', 1, 'tool')").lastrowid
    sql = ("INSERT INTO tool_call (run_step_id, tool_name, args, result, ok, latency_ms)"
           " VALUES (?, 'get_student', '{}', '{}', 1, 5)")
    store.conn.execute(sql, (step,))
    with pytest.raises(sqlite3.IntegrityError):
        store.conn.execute(sql, (step,))
