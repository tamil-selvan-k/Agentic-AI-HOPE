"""Cancel a run.   python -m scripts.cancel <run_id>"""
import sys

from app.config import open_stores


def main() -> None:
    store, _ = open_stores()
    row = store.conn.execute("SELECT id FROM run WHERE id LIKE ?", (sys.argv[1] + "%",)).fetchone()
    if row is None:
        raise SystemExit("no such run")
    status = store.request_cancel(row["id"])
    print(f"run {row['id'][:8]}: {status}" + (" (the worker stops after its current step)" if status == "running" else ""))


if __name__ == "__main__":
    main()
