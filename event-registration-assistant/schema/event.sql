-- event.db: student, event, registration data. The agent's memory is in agent.sql.

CREATE TABLE IF NOT EXISTS student (
    id                INTEGER PRIMARY KEY,
    reg_num           TEXT NOT NULL UNIQUE,
    name              TEXT NOT NULL,
    dept              TEXT NOT NULL,
    password          TEXT NOT NULL,
    max_registrations INTEGER NOT NULL DEFAULT 3
);

CREATE TABLE IF NOT EXISTS event (
    id               INTEGER PRIMARY KEY,
    title            TEXT NOT NULL,
    category         TEXT NOT NULL,
    organizer        TEXT NOT NULL,
    seats_total      INTEGER NOT NULL,
    seats_available  INTEGER NOT NULL CHECK (seats_available >= 0),
    version          INTEGER NOT NULL DEFAULT 0
);

-- Business rules live in data, not in prompts.
CREATE TABLE IF NOT EXISTS policy (
    name   TEXT PRIMARY KEY,
    value  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS registration (
    id          INTEGER PRIMARY KEY,
    student_id  INTEGER NOT NULL REFERENCES student (id),
    event_id    INTEGER NOT NULL REFERENCES event (id),
    created_at  REAL NOT NULL,
    UNIQUE (student_id, event_id)
);

CREATE TABLE IF NOT EXISTS notification (
    id          INTEGER PRIMARY KEY,
    reg_num     TEXT NOT NULL,
    message     TEXT NOT NULL,
    dedupe_key  TEXT NOT NULL UNIQUE,
    created_at  REAL NOT NULL
);

-- Keys live next to the side effects they guard.
CREATE TABLE IF NOT EXISTS idempotency (
    key         TEXT PRIMARY KEY,
    tool_name   TEXT NOT NULL,
    result      TEXT NOT NULL,
    created_at  REAL NOT NULL
);
