"""library.db: members, books, reservations. Every SQL statement for the library lives here."""
import json
import time
from collections.abc import Callable
from pathlib import Path

from app.db import connect, transaction

SCHEMA = Path(__file__).resolve().parent.parent / "schema" / "library.sql"


class LibraryDb:
    def __init__(self, path: str = ":memory:", clock: Callable[[], float] = time.time):
        self.conn = connect(path)
        self.clock = clock

    def transaction(self):
        return transaction(self.conn)

    def migrate(self) -> None:
        self.conn.executescript(SCHEMA.read_text())
        if self.conn.execute("SELECT count(*) FROM member").fetchone()[0]:
            return
        with self.transaction() as c:
            c.executemany("INSERT INTO member VALUES (?, ?, ?, ?, ?, ?)", [
                (1, "22CS045", "Priya Raman", "CSE", 3, 0),
                (2, "22IT017", "Arjun Kumar", "IT", 3, 150),
                (3, "22EC031", "Divya Sekar", "ECE", 1, 0)])
            c.executemany("INSERT INTO book VALUES (?, ?, ?, ?, ?, ?, 0)", [
                (1, "Clean Code", "Alexander Graham Bell", "software engineering", 2, 2),
                (2, "Designing Data-Intensive Applications", "Martin Kleppmann", "databases", 1, 1),
                (3, "Introduction to Algorithms", "Cormen, Leiserson, Rivest, Stein", "algorithms", 3, 3),
                (4, "Operating System Concepts", "Silberschatz, Galvin, Gagne", "operating systems", 2, 0),
                (5, "Computer Networking: A Top-Down Approach", "Kurose, Ross", "networks", 2, 2)])
            c.executemany("INSERT INTO policy VALUES (?, ?)", [("max_fine_to_borrow", 100)])
            c.execute("INSERT INTO reservation (member_id, book_id, created_at) VALUES (3, 3, ?)", (self.clock(),))
            c.execute("UPDATE book SET copies_available = copies_available - 1 WHERE id = 3")
    
    # ------------------------------------------------------------------ reads

    def get_member(self, roll_no: str) -> dict | None:
        r = self.conn.execute("SELECT * FROM member WHERE roll_no = ?", (roll_no,)).fetchone()
        return dict(r) if r else None

    def policy(self, name: str) -> int:
        return self.conn.execute("SELECT value FROM policy WHERE name = ?", (name,)).fetchone()[0]

    def active_reservations(self, member_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT r.book_id, b.title FROM reservation r JOIN book b ON b.id = r.book_id"
            " WHERE r.member_id = ? ORDER BY r.id", (member_id,)).fetchall()
        return [dict(r) for r in rows]

    def search_books(self, text: str, limit: int = 5) -> list[dict]:
        like = f"%{text.strip()}%"
        rows = self.conn.execute(
            "SELECT id, title, author, subject, copies_available FROM book"
            " WHERE title LIKE ? OR author LIKE ? OR subject LIKE ? ORDER BY title LIMIT ?",
            (like, like, like, limit)).fetchall()
        return [dict(r) for r in rows]

    def get_book(self, book_id: int) -> dict | None:
        r = self.conn.execute("SELECT * FROM book WHERE id = ?", (book_id,)).fetchone()
        return dict(r) if r else None

    def count(self, table: str) -> int:
        assert table.isidentifier()
        return self.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

    # ------------------------------------------------------------------ safe writes (Day 3)

    def reserve(self, member_id: int, book_id: int) -> str:
        """Returns 'reserved', 'already_reserved' or 'no_copies'. Safe to repeat."""
        with self.transaction() as c:
            if c.execute("SELECT 1 FROM reservation WHERE member_id = ? AND book_id = ?",
                         (member_id, book_id)).fetchone():
                return "already_reserved"                        # a repeat is a success
            version = c.execute("SELECT version FROM book WHERE id = ?", (book_id,)).fetchone()[0]
            took = c.execute(
                "UPDATE book SET copies_available = copies_available - 1, version = version + 1"
                " WHERE id = ? AND copies_available > 0 AND version = ?", (book_id, version)).rowcount
            if not took:
                return "no_copies"                               # a lost race is a normal outcome
            c.execute("INSERT INTO reservation (member_id, book_id, created_at) VALUES (?, ?, ?)",
                      (member_id, book_id, self.clock()))
            return "reserved"

    def record_notification(self, roll_no: str, message: str, dedupe_key: str) -> tuple[int, bool]:
        cur = self.conn.execute(
            "INSERT INTO notification (roll_no, message, dedupe_key, created_at) VALUES (?, ?, ?, ?)"
            " ON CONFLICT (dedupe_key) DO NOTHING", (roll_no, message, dedupe_key, self.clock()))
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
