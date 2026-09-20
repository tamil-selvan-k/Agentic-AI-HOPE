-- Combined Supabase PostgreSQL Schema: Agent Memory/Queue + Event Registration Tables
-- Execute this script directly in the Supabase SQL Editor.

-- ==============================================================================
-- 1. AGENT MEMORY & WORKER QUEUE TABLES (PostgreSQL / Supabase Syntax)
-- ==============================================================================

CREATE TABLE IF NOT EXISTS thread (
    id          TEXT PRIMARY KEY,
    student_id  TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS message (
    id          BIGSERIAL PRIMARY KEY,
    thread_id   TEXT NOT NULL REFERENCES thread (id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('user', 'model')),
    text        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (thread_id, seq)
);

-- Append-only trigger for message table in PostgreSQL
CREATE OR REPLACE FUNCTION message_prevent_update_delete()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'message table is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS message_no_update ON message;
CREATE TRIGGER message_no_update BEFORE UPDATE ON message
FOR EACH ROW EXECUTE FUNCTION message_prevent_update_delete();

DROP TRIGGER IF EXISTS message_no_delete ON message;
CREATE TRIGGER message_no_delete BEFORE DELETE ON message
FOR EACH ROW EXECUTE FUNCTION message_prevent_update_delete();

CREATE TABLE IF NOT EXISTS run (
    id                TEXT PRIMARY KEY,
    thread_id         TEXT NOT NULL REFERENCES thread (id) ON DELETE CASCADE,
    status            TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled', 'dead')),
    model             TEXT NOT NULL,
    tokens_in         INTEGER NOT NULL DEFAULT 0,
    tokens_out        INTEGER NOT NULL DEFAULT 0,
    attempts          INTEGER NOT NULL DEFAULT 0,
    max_attempts      INTEGER NOT NULL DEFAULT 3,
    available_at      DOUBLE PRECISION NOT NULL,
    lease_owner       TEXT,
    lease_until       DOUBLE PRECISION,
    cancel_requested  BOOLEAN NOT NULL DEFAULT FALSE,
    error_code        TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at        TIMESTAMPTZ,
    finished_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS run_claimable ON run (status, available_at);

CREATE TABLE IF NOT EXISTS run_step (
    id          BIGSERIAL PRIMARY KEY,
    run_id      TEXT NOT NULL REFERENCES run (id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,
    kind        TEXT NOT NULL CHECK (kind IN ('model', 'tool')),
    tokens_in   INTEGER NOT NULL DEFAULT 0,
    tokens_out  INTEGER NOT NULL DEFAULT 0,
    text        TEXT,
    tool_calls  JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, seq)
);

CREATE TABLE IF NOT EXISTS tool_call (
    id              BIGSERIAL PRIMARY KEY,
    run_step_id     BIGINT NOT NULL UNIQUE REFERENCES run_step (id) ON DELETE CASCADE,
    tool_name       TEXT NOT NULL,
    args            JSONB NOT NULL,
    result          JSONB NOT NULL,
    ok              BOOLEAN NOT NULL,
    latency_ms      INTEGER NOT NULL,
    idempotency_key TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ==============================================================================
-- 2. EVENT REGISTRATION DOMAIN TABLES (PostgreSQL / Supabase Syntax)
-- ==============================================================================

CREATE TABLE IF NOT EXISTS student (
    id                BIGSERIAL PRIMARY KEY,
    reg_num           TEXT NOT NULL UNIQUE,
    name              TEXT NOT NULL,
    dept              TEXT NOT NULL,
    password          TEXT NOT NULL,
    max_registrations INTEGER NOT NULL DEFAULT 3
);

CREATE TABLE IF NOT EXISTS event (
    id               BIGSERIAL PRIMARY KEY,
    title            TEXT NOT NULL,
    category         TEXT NOT NULL,
    organizer        TEXT NOT NULL,
    seats_total      INTEGER NOT NULL,
    seats_available  INTEGER NOT NULL CHECK (seats_available >= 0),
    version          INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS policy (
    name   TEXT PRIMARY KEY,
    value  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS registration (
    id          BIGSERIAL PRIMARY KEY,
    student_id  BIGINT NOT NULL REFERENCES student (id) ON DELETE CASCADE,
    event_id    BIGINT NOT NULL REFERENCES event (id) ON DELETE CASCADE,
    created_at  DOUBLE PRECISION NOT NULL,
    UNIQUE (student_id, event_id)
);

CREATE TABLE IF NOT EXISTS notification (
    id          BIGSERIAL PRIMARY KEY,
    reg_num     TEXT NOT NULL,
    message     TEXT NOT NULL,
    dedupe_key  TEXT NOT NULL UNIQUE,
    created_at  DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS idempotency (
    key         TEXT PRIMARY KEY,
    tool_name   TEXT NOT NULL,
    result      JSONB NOT NULL,
    created_at  DOUBLE PRECISION NOT NULL
);

-- ==============================================================================
-- 3. SEED DATA FOR SUPABASE
-- ==============================================================================

INSERT INTO student (id, reg_num, name, dept, password, max_registrations) VALUES
    (1, '22CS045', 'Priya Raman', 'CSE', 'pass123', 3),
    (2, '22IT017', 'Arjun Kumar', 'IT', 'pass123', 1),
    (3, '22EC031', 'Divya Sekar', 'ECE', 'pass123', 1)
ON CONFLICT (reg_num) DO NOTHING;

INSERT INTO event (id, title, category, organizer, seats_total, seats_available, version) VALUES
    (1, 'AI Hackathon 2026', 'hackathon', 'CSE Dept', 50, 50, 0),
    (2, 'Web3 & Cloud Symposium', 'symposium', 'IT Dept', 1, 1, 0),
    (3, 'Algorithmic Code Sprint', 'hackathon', 'Coding Club', 30, 29, 0),
    (4, 'Operating System Workshop', 'workshop', 'ECE Dept', 20, 0, 0),
    (5, 'Cyber Security Challenge', 'hackathon', 'IEEE', 25, 24, 0)
ON CONFLICT (id) DO NOTHING;

INSERT INTO policy (name, value) VALUES
    ('max_registrations_per_student', 3)
ON CONFLICT (name) DO NOTHING;

INSERT INTO registration (student_id, event_id, created_at) VALUES
    (2, 5, EXTRACT(EPOCH FROM NOW())),
    (3, 3, EXTRACT(EPOCH FROM NOW()))
ON CONFLICT (student_id, event_id) DO NOTHING;
