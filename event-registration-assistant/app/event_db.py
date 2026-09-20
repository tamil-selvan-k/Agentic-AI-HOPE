"""event.db: students, events, registrations. Every SQL statement for event management lives here."""
import json
import time
from collections.abc import Callable
from pathlib import Path

from app.db import connect, transaction

SCHEMA = Path(__file__).resolve().parent.parent / "schema" / "event.sql"


class EventDb:
    def __init__(self, path: str = ":memory:", clock: Callable[[], float] = time.time):
        self.conn = connect(path)
        self.clock = clock

    def transaction(self):
        return transaction(self.conn)

    def migrate(self) -> None:
        self.conn.executescript(SCHEMA.read_text())
        if self.conn.execute("SELECT count(*) FROM student").fetchone()[0]:
            return
        with self.transaction() as c:
            c.executemany("INSERT INTO student VALUES (?, ?, ?, ?, ?, ?)", [
                (1, "22CS045", "Priya Raman", "CSE", "pass123", 3),
                (2, "22IT017", "Arjun Kumar", "IT", "pass123", 1),
                (3, "22EC031", "Divya Sekar", "ECE", "pass123", 1), 
                (4, "24IT1444", "Sam Raj", "IT", "12345678", 50)])
            c.executemany("INSERT INTO event VALUES (?, ?, ?, ?, ?, ?, 0)", [
                (1, "AI Hackathon 2026", "hackathon", "CSE Dept", 50, 50),
                (2, "Web3 & Cloud Symposium", "symposium", "IT Dept", 1, 1),
                (3, "Algorithmic Code Sprint", "hackathon", "Coding Club", 30, 29),
                (4, "Operating System Workshop", "workshop", "ECE Dept", 20, 0),
                (5, "Cyber Security Challenge", "hackathon", "IEEE", 25, 24)])
            c.executemany("INSERT INTO policy VALUES (?, ?)", [("max_registrations_per_student", 3)])
            c.executemany("INSERT INTO registration (student_id, event_id, created_at) VALUES (?, ?, ?)", [
                (2, 5, self.clock()),
                (3, 3, self.clock())
            ])

    # ------------------------------------------------------------------ reads

    def authenticate_student(self, reg_num: str, password: str) -> bool:
        r = self.conn.execute("SELECT 1 FROM student WHERE reg_num = ? AND password = ?", (reg_num, password)).fetchone()
        return r is not None

    def get_student(self, reg_num: str) -> dict | None:
        r = self.conn.execute("SELECT * FROM student WHERE reg_num = ?", (reg_num,)).fetchone()
        return dict(r) if r else None

    def policy(self, name: str) -> int:
        r = self.conn.execute("SELECT value FROM policy WHERE name = ?", (name,)).fetchone()
        return r[0] if r else 0

    def active_registrations(self, student_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT r.event_id, e.title, e.category FROM registration r JOIN event e ON e.id = r.event_id"
            " WHERE r.student_id = ? ORDER BY r.id", (student_id,)).fetchall()
        return [dict(r) for r in rows]

    def search_events(self, text: str, limit: int = 5) -> list[dict]:
        like = f"%{text.strip()}%"
        rows = self.conn.execute(
            "SELECT id, title, category, organizer, seats_available FROM event"
            " WHERE title LIKE ? OR category LIKE ? OR organizer LIKE ? ORDER BY title LIMIT ?",
            (like, like, like, limit)).fetchall()
        return [dict(r) for r in rows]

    def get_event(self, event_id: int) -> dict | None:
        r = self.conn.execute("SELECT * FROM event WHERE id = ?", (event_id,)).fetchone()
        return dict(r) if r else None

    def count(self, table: str) -> int:
        assert table.isidentifier()
        return self.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

    # ------------------------------------------------------------------ safe writes (Day 3)

    def register(self, student_id: int, event_id: int) -> str:
        """Returns 'registered', 'already_registered' or 'no_seats'. Safe to repeat."""
        with self.transaction() as c:
            if c.execute("SELECT 1 FROM registration WHERE student_id = ? AND event_id = ?",
                         (student_id, event_id)).fetchone():
                return "already_registered"                        # a repeat is a success
            version = c.execute("SELECT version FROM event WHERE id = ?", (event_id,)).fetchone()[0]
            took = c.execute(
                "UPDATE event SET seats_available = seats_available - 1, version = version + 1"
                " WHERE id = ? AND seats_available > 0 AND version = ?", (event_id, version)).rowcount
            if not took:
                return "no_seats"                               # a lost race is a normal outcome
            c.execute("INSERT INTO registration (student_id, event_id, created_at) VALUES (?, ?, ?)",
                      (student_id, event_id, self.clock()))
            return "registered"

    def unregister(self, student_id: int, event_id: int = 0, event_title: str = "") -> tuple[str, dict | None]:
        """Cancel/unregister an event registration. Safe to repeat and resolves unknown event_id for 1 registration."""
        with self.transaction() as c:
            active = self.active_registrations(student_id)
            if not active:
                return "not_registered", None

            target_event_id = None
            if event_id > 0:
                target_event_id = event_id
            elif event_title.strip():
                match = [a for a in active if event_title.strip().lower() in a["title"].lower()]
                if len(match) == 1:
                    target_event_id = match[0]["event_id"]
                elif len(match) > 1:
                    return "multiple_registrations", {"active": match}
            elif len(active) == 1:
                target_event_id = active[0]["event_id"]
            else:
                return "multiple_registrations", {"active": active}

            if not target_event_id:
                return "not_registered", None

            reg = c.execute("SELECT 1 FROM registration WHERE student_id = ? AND event_id = ?",
                            (student_id, target_event_id)).fetchone()
            if not reg:
                event_info = self.get_event(target_event_id)
                return "already_unregistered", event_info

            c.execute("DELETE FROM registration WHERE student_id = ? AND event_id = ?",
                      (student_id, target_event_id))
            c.execute("UPDATE event SET seats_available = seats_available + 1, version = version + 1 WHERE id = ?",
                      (target_event_id,))
            event_info = self.get_event(target_event_id)
            return "unregistered", event_info

    def record_notification(self, reg_num: str, message: str, dedupe_key: str) -> tuple[int, bool]:
        cur = self.conn.execute(
            "INSERT INTO notification (reg_num, message, dedupe_key, created_at) VALUES (?, ?, ?, ?)"
            " ON CONFLICT (dedupe_key) DO NOTHING", (reg_num, message, dedupe_key, self.clock()))
        if cur.rowcount == 1:
            return cur.lastrowid, True
        return self.conn.execute("SELECT id FROM notification WHERE dedupe_key = ?", (dedupe_key,)).fetchone()[0], False

    def once(self, key: str, tool_name: str, effect: Callable[[], dict]) -> tuple[dict, bool]:
        """Run a side effect at most once per idempotency key; the effect and its key commit together."""
        with self.transaction() as c:
            row = c.execute("SELECT result FROM idempotency WHERE key = ?", (key,)).fetchone()
            if row is not None:
                return json.loads(row["result"]), False
            result = effect()
            c.execute("INSERT INTO idempotency (key, tool_name, result, created_at) VALUES (?, ?, ?, ?)",
                      (key, tool_name, json.dumps(result, default=str), self.clock()))
            return result, True
