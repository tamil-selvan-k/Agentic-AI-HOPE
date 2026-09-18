"""placement.db: the college's placement data in SQLite. (Given, except the Day 3 TODOs.)"""
import json
import sqlite3
import time
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from app.domain import Drive, Rule, Slot, Student

SCHEMA = Path(__file__).resolve().parent.parent / "schema" / "placement.sql"
DAY = 86400.0


def _dt(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, timezone.utc)


def connect(path: str) -> sqlite3.Connection:
    """Autocommit connection; transactions are explicit. Waits up to 5 s for another writer."""
    conn = sqlite3.connect(path, isolation_level=None, timeout=5.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


class PlacementDb:
    def __init__(self, path: str = ":memory:", clock: Callable[[], float] = time.time):
        self.conn = connect(path)
        self.clock = clock

    # ------------------------------------------------------------------ setup (given)

    def migrate(self, seed: bool = True) -> None:
        self.conn.executescript(SCHEMA.read_text())
        if seed and self.conn.execute("SELECT count(*) FROM student").fetchone()[0] == 0:
            self._seed()

    def _seed(self) -> None:
        now = self.clock()
        with self.transaction() as c:
            c.executemany("INSERT INTO student VALUES (?, ?, ?, ?, ?, ?, ?)", [
                (1, "22CS045", "Priya Raman", "CSE", 8.4, 0, 2026),
                (2, "22IT017", "Arjun Kumar", "IT", 6.8, 1, 2026),
                (3, "22EC031", "Divya Sekar", "ECE", 7.2, 2, 2026),
                (4, "22ME008", "Karthik Murugan", "MECH", 7.9, 0, 2026)])
            c.executemany("INSERT INTO company VALUES (?, ?, ?)",
                          [(1, "Zoho", "Product"), (2, "TCS", "IT services"), (3, "Freshworks", "SaaS")])
            c.executemany("INSERT INTO drive VALUES (?, ?, ?, ?, ?, ?)", [
                (1, 1, "Member Technical Staff", 8.4, now + 30 * DAY, "open"),
                (2, 2, "Ninja", 3.6, now + 21 * DAY, "open"),
                (3, 3, "Software Engineer I", 12.0, now - 2 * DAY, "closed")])
            c.executemany("INSERT INTO eligibility_rule VALUES (?, ?, ?, ?, ?)", [
                (1, 1, "cgpa", ">=", "7.0"), (2, 1, "backlogs", "<=", "0"), (3, 1, "branch", "in", "CSE,IT,ECE"),
                (4, 1, "grad_year", "==", "2026"), (5, 2, "cgpa", ">=", "6.0"), (6, 2, "backlogs", "<=", "1"),
                (7, 2, "grad_year", "==", "2026"), (8, 3, "cgpa", ">=", "8.0"), (9, 3, "backlogs", "<=", "0"),
                (10, 3, "branch", "in", "CSE,IT")])
            c.executemany("INSERT INTO interview_slot (id, drive_id, starts_at) VALUES (?, ?, ?)", [
                (1, 1, now + 35 * DAY), (2, 1, now + 35 * DAY + 3600), (3, 2, now + 25 * DAY)])

    @contextmanager
    def transaction(self):
        """BEGIN IMMEDIATE: take the write lock up front, so two writers queue instead of deadlocking."""
        if self.conn.in_transaction:          # already inside one: join it
            yield self.conn
            return
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield self.conn
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")

    # ------------------------------------------------------------------ reads (given)

    def get_student(self, roll_no: str) -> Student | None:
        r = self.conn.execute("SELECT * FROM student WHERE roll_no = ?", (roll_no,)).fetchone()
        return Student(r["id"], r["roll_no"], r["name"], r["branch"], r["cgpa"], r["backlogs"], r["grad_year"]) if r else None

    def _drive(self, r) -> Drive:
        return Drive(r["id"], r["company"], r["role"], r["ctc_lpa"], _dt(r["deadline"]), r["status"])

    _DRIVE_SQL = ("SELECT d.id, c.name AS company, d.role, d.ctc_lpa, d.deadline, d.status"
                  " FROM drive d JOIN company c ON c.id = d.company_id")

    def get_drive(self, drive_id: int) -> Drive | None:
        r = self.conn.execute(self._DRIVE_SQL + " WHERE d.id = ?", (drive_id,)).fetchone()
        return self._drive(r) if r else None

    def list_open_drives(self, now: datetime) -> list[Drive]:
        rows = self.conn.execute(self._DRIVE_SQL + " WHERE d.status = 'open' AND d.deadline > ? ORDER BY d.deadline",
                                 (now.timestamp(),)).fetchall()
        return [self._drive(r) for r in rows]

    def rules_for_drive(self, drive_id: int) -> list[Rule]:
        rows = self.conn.execute("SELECT * FROM eligibility_rule WHERE drive_id = ? ORDER BY id", (drive_id,)).fetchall()
        return [Rule(r["id"], r["drive_id"], r["field"], r["op"], r["value"]) for r in rows]

    def has_application(self, student_id: int, drive_id: int) -> bool:
        return self.conn.execute("SELECT 1 FROM application WHERE student_id = ? AND drive_id = ?",
                                 (student_id, drive_id)).fetchone() is not None

    def get_slot(self, slot_id: int) -> Slot | None:
        r = self.conn.execute("SELECT * FROM interview_slot WHERE id = ?", (slot_id,)).fetchone()
        return Slot(r["id"], r["drive_id"], _dt(r["starts_at"]), r["student_id"]) if r else None

    def slot_version(self, slot_id: int) -> int | None:
        r = self.conn.execute("SELECT version FROM interview_slot WHERE id = ?", (slot_id,)).fetchone()
        return r["version"] if r else None

    def free_slots(self, drive_id: int) -> list[Slot]:
        rows = self.conn.execute("SELECT * FROM interview_slot WHERE drive_id = ? AND student_id IS NULL"
                                 " ORDER BY starts_at", (drive_id,)).fetchall()
        return [Slot(r["id"], r["drive_id"], _dt(r["starts_at"]), None) for r in rows]

    def count(self, table: str) -> int:
        """For tests and scripts: rows in a table."""
        assert table.isidentifier()
        return self.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

    # ------------------------------------------------------------------ Part 3: safe writes (TODO)

    def create_application(self, student_id: int, drive_id: int) -> tuple[int, bool]:
        """Returns (application_id, created).

        TODO (Part 3.1): a duplicate application is a success, not an error. Today a second insert for the
        same (student_id, drive_id) raises IntegrityError. Use ON CONFLICT ... DO NOTHING, then return the
        existing row's id with created = False."""
        cur = self.conn.execute("INSERT INTO application (student_id, drive_id, created_at) VALUES (?, ?, ?)",
                                (student_id, drive_id, self.clock()))
        return cur.lastrowid, True

    def claim_slot(self, slot_id: int, student_id: int, expected_version: int) -> bool:
        """True if this call booked the slot.

        TODO (Part 3.2): optimistic locking. Book only if the slot is still free AND its version still equals
        expected_version, and bump the version when you book. Today the version is ignored."""
        cur = self.conn.execute("UPDATE interview_slot SET student_id = ? WHERE id = ? AND student_id IS NULL",
                                (student_id, slot_id))
        return cur.rowcount == 1

    def record_notification(self, roll_no: str, message: str, dedupe_key: str) -> tuple[int, bool]:
        """Returns (notification_id, created).

        TODO (Part 3.3): store it only if no notification has this dedupe_key; otherwise return the existing
        id with created = False. Today every call inserts (and a repeated key raises IntegrityError)."""
        cur = self.conn.execute(
            "INSERT INTO notification (roll_no, message, dedupe_key, created_at) VALUES (?, ?, ?, ?)",
            (roll_no, message, dedupe_key, self.clock()))
        return cur.lastrowid, True

    def list_applications(self, student_id: int) -> list[dict]:
        rows = self.conn.execute(
            """SELECT a.id AS application_id, a.drive_id, c.name AS company, d.role, a.status, a.created_at,
                      s.starts_at AS interview_at
                 FROM application a JOIN drive d ON d.id = a.drive_id JOIN company c ON c.id = d.company_id
                 LEFT JOIN interview_slot s ON s.drive_id = a.drive_id AND s.student_id = a.student_id
                WHERE a.student_id = ? ORDER BY a.id""", (student_id,)).fetchall()
        return [{**dict(r), "created_at": _dt(r["created_at"]),
                 "interview_at": _dt(r["interview_at"]) if r["interview_at"] else None} for r in rows]

    # ------------------------------------------------------------------ Part 2: idempotency (TODO)

    def once(self, key: str, tool_name: str, effect: Callable[[], dict]) -> tuple[dict, bool]:
        """Run `effect` at most once per key.

        In ONE transaction: if the key is already stored, return (stored result, False) without running
        the effect. Otherwise run it, store the key with its result, and return (result, True).
        If the effect raises, nothing is stored and nothing it wrote survives.
        """
        with self.transaction() as conn:
            row = conn.execute("SELECT result FROM idempotency WHERE key = ?", (key,)).fetchone()
            if row is not None:
                return json.loads(row["result"]), False
            result = effect()
            conn.execute("INSERT INTO idempotency (key, tool_name, result, created_at) VALUES (?, ?, ?, ?)",
                         (key, tool_name, json.dumps(result, default=str), self.clock()))
            return result, True
