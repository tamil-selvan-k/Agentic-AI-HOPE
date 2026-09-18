-- agent.db: the agent's memory, now also its job queue. Business data is NOT in here (placement.db).
-- Day 3 changes to the Day 2 schema are marked "Day 3". SQLite can't change a CHECK in place, so
-- start from a fresh agent.db.

CREATE TABLE IF NOT EXISTS thread (
    id          TEXT PRIMARY KEY,
    student_id  TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS message (
    id          INTEGER PRIMARY KEY,
    thread_id   TEXT NOT NULL REFERENCES thread (id),
    seq         INTEGER NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('user', 'model')),
    text        TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (thread_id, seq)
);

CREATE TRIGGER IF NOT EXISTS message_no_update BEFORE UPDATE ON message
BEGIN SELECT RAISE(ABORT, 'message is append-only: UPDATE rejected'); END;

CREATE TRIGGER IF NOT EXISTS message_no_delete BEFORE DELETE ON message
BEGIN SELECT RAISE(ABORT, 'message is append-only: DELETE rejected'); END;

CREATE TABLE IF NOT EXISTS run (
    id                TEXT PRIMARY KEY,
    thread_id         TEXT NOT NULL REFERENCES thread (id),
    status            TEXT NOT NULL CHECK (status IN
                          ('queued', 'running', 'succeeded', 'failed', 'cancelled', 'dead')),   -- Day 3
    model             TEXT NOT NULL,
    tokens_in         INTEGER NOT NULL DEFAULT 0,
    tokens_out        INTEGER NOT NULL DEFAULT 0,
    attempts          INTEGER NOT NULL DEFAULT 0,                                -- Day 3
    max_attempts      INTEGER NOT NULL DEFAULT 3,                                -- Day 3
    available_at      REAL NOT NULL,              -- Day 3: unix time; not claimable before this
    lease_owner       TEXT,                       -- Day 3: worker id holding the run
    lease_until       REAL,                       -- Day 3: unix time the lease expires
    cancel_requested  INTEGER NOT NULL DEFAULT 0 CHECK (cancel_requested IN (0, 1)),   -- Day 3
    error_code        TEXT,
    created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    started_at        TEXT,
    finished_at       TEXT
);

CREATE INDEX IF NOT EXISTS run_claimable ON run (status, available_at);

CREATE TABLE IF NOT EXISTS run_step (
    id          INTEGER PRIMARY KEY,
    run_id      TEXT NOT NULL REFERENCES run (id),
    seq         INTEGER NOT NULL,
    kind        TEXT NOT NULL CHECK (kind IN ('model', 'tool')),
    tokens_in   INTEGER NOT NULL DEFAULT 0,
    tokens_out  INTEGER NOT NULL DEFAULT 0,
    text        TEXT,                             -- Day 3: model steps, what the model said
    tool_calls  TEXT,                             -- Day 3: model steps, JSON [{"name", "args"}]
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (run_id, seq)
);

CREATE TABLE IF NOT EXISTS tool_call (
    id           INTEGER PRIMARY KEY,
    run_step_id  INTEGER NOT NULL UNIQUE REFERENCES run_step (id),
    tool_name    TEXT NOT NULL,
    args         TEXT NOT NULL,
    result       TEXT NOT NULL,
    ok           INTEGER NOT NULL CHECK (ok IN (0, 1)),
    latency_ms   INTEGER NOT NULL,
    idempotency_key  TEXT,                        -- Day 3
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
