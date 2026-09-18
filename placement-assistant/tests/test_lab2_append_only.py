"""Lab 2 — the database, not your Python code, refuses to rewrite history (schema/append_only.sql)."""
import sqlite3

import pytest


def one_message(store):
    t = store.create_thread("22CS045")
    store.conn.execute("INSERT INTO message (thread_id, seq, role, text) VALUES (?, 1, 'user', 'original')", (t,))
    return t


def test_update_is_rejected(store):
    t = one_message(store)
    with pytest.raises(sqlite3.DatabaseError):
        store.conn.execute("UPDATE message SET text = 'edited' WHERE thread_id = ?", (t,))
    assert store.conn.execute("SELECT text FROM message WHERE thread_id = ?", (t,)).fetchone()[0] == "original"


def test_delete_is_rejected(store):
    t = one_message(store)
    with pytest.raises(sqlite3.DatabaseError):
        store.conn.execute("DELETE FROM message WHERE thread_id = ?", (t,))


def test_appending_still_works(store):
    t = one_message(store)
    store.conn.execute("INSERT INTO message (thread_id, seq, role, text) VALUES (?, 2, 'model', 'reply')", (t,))
    assert store.conn.execute("SELECT count(*) FROM message WHERE thread_id = ?", (t,)).fetchone()[0] == 2
