-- The agent's memory. Business data (students, drives, applications) is NOT in here.
-- Run by ConversationStore.migrate(). SQLite: foreign keys are switched on per connection.

-- Given, as the pattern to follow.
CREATE TABLE IF NOT EXISTS thread (
    id          TEXT PRIMARY KEY,
    student_id  TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS message (
    id          INTEGER PRIMARY KEY,
    thread_id   TEXT NOT NULL REFERENCES thread(id),
    seq         INTEGER NOT NULL,
    role        TEXT NOT NULL,
    text        TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (thread_id, seq),
    CHECK (role IN ('user', 'model'))
);

CREATE TABLE IF NOT EXISTS run (
    id          TEXT PRIMARY KEY,
    thread_id   TEXT NOT NULL REFERENCES thread(id),
    status      TEXT NOT NULL,
    model       TEXT NOT NULL,
    tokens_in   INTEGER NOT NULL DEFAULT 0,
    tokens_out  INTEGER NOT NULL DEFAULT 0,
    error_code  TEXT,
    started_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    finished_at TEXT,
    CHECK (status IN ('running', 'succeeded', 'failed'))
);

CREATE TABLE IF NOT EXISTS run_step (
    id          INTEGER PRIMARY KEY,
    run_id      TEXT NOT NULL REFERENCES run(id),
    seq         INTEGER NOT NULL,
    kind        TEXT NOT NULL,
    tokens_in   INTEGER NOT NULL DEFAULT 0,
    tokens_out  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (run_id, seq),
    CHECK (kind IN ('model', 'tool'))
);

CREATE TABLE IF NOT EXISTS tool_call (
    id          INTEGER PRIMARY KEY,
    run_step_id INTEGER NOT NULL UNIQUE REFERENCES run_step(id),
    tool_name   TEXT NOT NULL,
    args        TEXT NOT NULL,
    result      TEXT NOT NULL,
    ok          INTEGER NOT NULL,
    latency_ms  INTEGER NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK (ok IN (0, 1))
);
