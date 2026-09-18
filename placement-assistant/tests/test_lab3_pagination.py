"""Lab 3 — read a long conversation page by page: ConversationStore.page_messages."""
import pytest


def seeded(store, n):
    t = store.create_thread("22CS045")
    for i in range(1, n + 1):
        store.conn.execute("INSERT INTO message (thread_id, seq, role, text) VALUES (?, ?, ?, ?)",
                           (t, i, "user" if i % 2 else "model", f"m{i}"))
    return t


def test_pages_walk_the_whole_thread(store):
    t = seeded(store, 7)
    seen, after, pages = [], 0, 0
    while True:
        items, after = store.page_messages(t, after_seq=after, limit=3)
        seen += [m["seq"] for m in items]
        pages += 1
        if after is None:
            break
    assert seen == [1, 2, 3, 4, 5, 6, 7] and pages == 3


def test_page_items_have_the_expected_fields(store):
    items, _ = store.page_messages(seeded(store, 2), limit=5)
    assert set(items[0]) == {"seq", "role", "text", "created_at"}


def test_exact_multiple_has_no_empty_last_page(store):
    t = seeded(store, 6)
    _, after = store.page_messages(t, limit=3)
    items, after = store.page_messages(t, after_seq=after, limit=3)
    assert [m["seq"] for m in items] == [4, 5, 6] and after is None


def test_stable_while_messages_arrive(store):
    t = seeded(store, 4)
    _, after = store.page_messages(t, limit=2)
    store.conn.execute("INSERT INTO message (thread_id, seq, role, text) VALUES (?, 5, 'user', 'late')", (t,))
    items, _ = store.page_messages(t, after_seq=after, limit=10)
    assert [m["seq"] for m in items] == [3, 4, 5]


def test_other_threads_do_not_leak_in(store):
    t = seeded(store, 2)
    seeded(store, 3)
    items, _ = store.page_messages(t, limit=10)
    assert [m["text"] for m in items] == ["m1", "m2"]


def test_limit_must_be_positive(store):
    with pytest.raises(ValueError):
        store.page_messages(seeded(store, 1), limit=0)
