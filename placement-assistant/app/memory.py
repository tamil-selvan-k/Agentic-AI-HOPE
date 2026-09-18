import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"


class ConversationStore:
    """The agent's memory in SQLite. All SQL for threads, messages, runs and steps lives here."""

    def __init__(self, path: str = ":memory:"):
        self.conn = sqlite3.connect(path, isolation_level=None)   # autocommit; transactions are explicit
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    # ------------------------------------------------------------------ given

    def migrate(self) -> None:
        for name in ("agent.sql", "append_only.sql"):
            sql = (SCHEMA_DIR / name).read_text()
            if sql.strip():
                self.conn.executescript(sql)

    @contextmanager
    def transaction(self):
        """Everything inside commits together, or nothing does."""
        self.conn.execute("BEGIN")
        try:
            yield self.conn
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")

    def create_thread(self, student_id: str) -> str:
        thread_id = str(uuid.uuid4())
        self.conn.execute("INSERT INTO thread (id, student_id) VALUES (?, ?)", (thread_id, student_id))
        return thread_id

    def get_thread(self, thread_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM thread WHERE id = ?", (thread_id,)).fetchone()
        return dict(row) if row else None

    def get_run(self, run_id: str) -> dict | None:
        run = self.conn.execute("SELECT * FROM run WHERE id = ?", (run_id,)).fetchone()
        if run is None:
            return None
        steps = self.conn.execute(
            """SELECT s.seq, s.kind, s.tokens_in, s.tokens_out,
                      t.tool_name, t.args, t.result, t.ok, t.latency_ms
                 FROM run_step s LEFT JOIN tool_call t ON t.run_step_id = s.id
                WHERE s.run_id = ? ORDER BY s.seq""", (run_id,)).fetchall()
        return {**dict(run), "steps": [dict(s) for s in steps]}

    # ------------------------------------------------------------------ Part 3.2: your SQL

    def append_message(self, thread_id: str, role: str, text: str) -> int:
        """Insert with seq = this thread's highest seq + 1 (computed in the same INSERT). Return the seq."""
        row = self.conn.execute(
            """INSERT INTO message (thread_id, seq, role, text)
               VALUES (?, (SELECT COALESCE(MAX(seq), 0) + 1 FROM message WHERE thread_id = ?), ?, ?)
               RETURNING seq""",
            (thread_id, thread_id, role, text)
        ).fetchone()
        return row[0]

    def load_history(self, thread_id: str) -> list[dict]:
        """[{"seq", "role", "text"}, ...] in seq order."""
        rows = self.conn.execute(
            "SELECT seq, role, text FROM message WHERE thread_id = ? ORDER BY seq",
            (thread_id,)
        ).fetchall()
        return [{"seq": r["seq"], "role": r["role"], "text": r["text"]} for r in rows]

    def start_run(self, thread_id: str, model: str) -> str:
        """New run with a uuid4 id and status 'running'. Return the id."""
        run_id = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO run (id, thread_id, status, model) VALUES (?, ?, 'running', ?)",
            (run_id, thread_id, model)
        )
        return run_id

    def record_model_step(self, run_id: str, seq: int, tokens_in: int, tokens_out: int) -> int:
        """Insert a 'model' run_step AND add its tokens to the run, in ONE transaction. Return the step id."""
        with self.transaction() as conn:
            step_id = conn.execute(
                "INSERT INTO run_step (run_id, seq, kind, tokens_in, tokens_out) VALUES (?, ?, 'model', ?, ?)",
                (run_id, seq, tokens_in, tokens_out)
            ).lastrowid
            conn.execute(
                "UPDATE run SET tokens_in = tokens_in + ?, tokens_out = tokens_out + ? WHERE id = ?",
                (tokens_in, tokens_out, run_id)
            )
            return step_id

    def record_tool_call(self, run_id: str, seq: int, name: str, args: dict, result: dict,
                         ok: bool, latency_ms: int) -> int:
        """Insert a 'tool' run_step and its tool_call (args and result as JSON) in ONE transaction.
        Return the step id."""
        with self.transaction() as conn:
            step_id = conn.execute(
                "INSERT INTO run_step (run_id, seq, kind) VALUES (?, ?, 'tool')",
                (run_id, seq)
            ).lastrowid
            conn.execute(
                "INSERT INTO tool_call (run_step_id, tool_name, args, result, ok, latency_ms)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (step_id, name, json.dumps(args), json.dumps(result), int(ok), latency_ms)
            )
            return step_id

    def finish_run(self, run_id: str, status: str, error_code: str | None = None) -> None:
        """Set status, error_code and finished_at."""
        self.conn.execute(
            "UPDATE run SET status = ?, error_code = ?,"
            " finished_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
            (status, error_code, run_id)
        )

    # ------------------------------------------------------------------ Lab 3

    def page_messages(self, thread_id: str, after_seq: int = 0, limit: int = 20) -> tuple[list[dict], int | None]:
        """Up to `limit` messages with seq > after_seq, as {"seq", "role", "text", "created_at"}.
        Also return the after_seq for the next page, or None if this is the last page.
        No OFFSET. limit below 1 raises ValueError."""
        if limit < 1:
            raise ValueError("limit must be at least 1")
        rows = self.conn.execute(
            "SELECT seq, role, text, created_at FROM message"
            " WHERE thread_id = ? AND seq > ? ORDER BY seq LIMIT ?",
            (thread_id, after_seq, limit + 1)
        ).fetchall()
        if len(rows) > limit:
            items = [{"seq": r["seq"], "role": r["role"], "text": r["text"], "created_at": r["created_at"]}
                     for r in rows[:limit]]
            next_after = items[-1]["seq"]
        else:
            items = [{"seq": r["seq"], "role": r["role"], "text": r["text"], "created_at": r["created_at"]}
                     for r in rows]
            next_after = None
        return items, next_after
