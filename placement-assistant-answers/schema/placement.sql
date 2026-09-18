-- placement.db: the college's placement data. The agent's memory is NOT in here (that is agent.db).
-- Given. Run by PlacementDb.migrate(), which also loads the seed data once.

CREATE TABLE IF NOT EXISTS student (
    id         INTEGER PRIMARY KEY,
    roll_no    TEXT NOT NULL UNIQUE,
    name       TEXT NOT NULL,
    branch     TEXT NOT NULL,
    cgpa       REAL NOT NULL CHECK (cgpa BETWEEN 0 AND 10),
    backlogs   INTEGER NOT NULL DEFAULT 0 CHECK (backlogs >= 0),
    grad_year  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS company (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE,
    sector  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS drive (
    id          INTEGER PRIMARY KEY,
    company_id  INTEGER NOT NULL REFERENCES company (id),
    role        TEXT NOT NULL,
    ctc_lpa     REAL NOT NULL,
    deadline    REAL NOT NULL,                       -- unix time
    status      TEXT NOT NULL CHECK (status IN ('open', 'closed'))
);

CREATE TABLE IF NOT EXISTS eligibility_rule (
    id        INTEGER PRIMARY KEY,
    drive_id  INTEGER NOT NULL REFERENCES drive (id),
    field     TEXT NOT NULL CHECK (field IN ('cgpa', 'backlogs', 'branch', 'grad_year')),
    op        TEXT NOT NULL CHECK (op IN ('>=', '<=', '==', 'in')),
    value     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS application (
    id          INTEGER PRIMARY KEY,
    student_id  INTEGER NOT NULL REFERENCES student (id),
    drive_id    INTEGER NOT NULL REFERENCES drive (id),
    status      TEXT NOT NULL DEFAULT 'applied',
    created_at  REAL NOT NULL,
    UNIQUE (student_id, drive_id)
);

CREATE TABLE IF NOT EXISTS interview_slot (
    id          INTEGER PRIMARY KEY,
    drive_id    INTEGER NOT NULL REFERENCES drive (id),
    starts_at   REAL NOT NULL,
    student_id  INTEGER REFERENCES student (id),
    version     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS notification (
    id          INTEGER PRIMARY KEY,
    roll_no     TEXT NOT NULL,
    message     TEXT NOT NULL,
    dedupe_key  TEXT NOT NULL UNIQUE,
    created_at  REAL NOT NULL
);

-- Day 3: one row per side effect that has already happened. Lives next to the data it protects,
-- so the side effect and its key commit in the same transaction.
CREATE TABLE IF NOT EXISTS idempotency (
    key         TEXT PRIMARY KEY,
    tool_name   TEXT NOT NULL,
    result      TEXT NOT NULL,                       -- JSON
    created_at  REAL NOT NULL
);
