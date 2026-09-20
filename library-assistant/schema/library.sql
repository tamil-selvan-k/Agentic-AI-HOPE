-- library.db: the library's own data. The agent's memory is in agent.db.

CREATE TABLE IF NOT EXISTS member (
    id         INTEGER PRIMARY KEY,
    roll_no    TEXT NOT NULL UNIQUE,
    name       TEXT NOT NULL,
    dept       TEXT NOT NULL,
    max_loans  INTEGER NOT NULL DEFAULT 3,
    fine_due   INTEGER NOT NULL DEFAULT 0 CHECK (fine_due >= 0)      -- rupees
);

CREATE TABLE IF NOT EXISTS book (
    id                INTEGER PRIMARY KEY,
    title             TEXT NOT NULL,
    author            TEXT NOT NULL,
    subject           TEXT NOT NULL,
    copies_total      INTEGER NOT NULL,
    copies_available  INTEGER NOT NULL CHECK (copies_available >= 0),
    version           INTEGER NOT NULL DEFAULT 0
);

-- Business rules live in data, not in prompts (Day 2).
CREATE TABLE IF NOT EXISTS policy (
    name   TEXT PRIMARY KEY,
    value  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS reservation (
    id          INTEGER PRIMARY KEY,
    member_id   INTEGER NOT NULL REFERENCES member (id),
    book_id     INTEGER NOT NULL REFERENCES book (id),
    created_at  REAL NOT NULL,
    UNIQUE (member_id, book_id)
);

CREATE TABLE IF NOT EXISTS notification (
    id          INTEGER PRIMARY KEY,
    roll_no     TEXT NOT NULL,
    message     TEXT NOT NULL,
    dedupe_key  TEXT NOT NULL UNIQUE,
    created_at  REAL NOT NULL
);

-- Day 3: keys live next to the side effects they guard.
CREATE TABLE IF NOT EXISTS idempotency (
    key         TEXT PRIMARY KEY,
    tool_name   TEXT NOT NULL,
    result      TEXT NOT NULL,
    created_at  REAL NOT NULL
);
