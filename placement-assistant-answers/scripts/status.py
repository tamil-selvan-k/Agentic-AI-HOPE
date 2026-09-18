"""Inspect runs and side effects.

    python -m scripts.status              # recent runs, and counts of applications, bookings, notifications
    python -m scripts.status <run_id>     # one run, every step
"""
import sys

from app.config import open_stores
from scripts._term import DIM, RESET, print_step


def main() -> None:
    store, placement = open_stores()
    if len(sys.argv) > 1:
        run = store.conn.execute("SELECT id FROM run WHERE id LIKE ?", (sys.argv[1] + "%",)).fetchone()
        if run is None:
            raise SystemExit("no such run")
        r = store.get_run(run["id"])
        print(f"run {r['id']}  {r['status']}  attempts {r['attempts']}/{r['max_attempts']}"
              f"  owner {r['lease_owner']}  error {r['error_code']}  tokens {r['tokens_in']}/{r['tokens_out']}")
        for step in r["steps"]:
            print_step(step)
        return
    for r in store.conn.execute("SELECT id, status, attempts, error_code, created_at FROM run"
                                " ORDER BY created_at DESC LIMIT 10"):
        print(f"{r['id'][:8]}  {r['status']:<10} attempts {r['attempts']}  {r['error_code'] or '':<16} {DIM}{r['created_at']}{RESET}")
    booked = placement.conn.execute("SELECT count(*) FROM interview_slot WHERE student_id IS NOT NULL").fetchone()[0]
    print(f"\napplications {placement.count('application')}   booked slots {booked}"
          f"   notifications {placement.count('notification')}   idempotency keys {placement.count('idempotency')}")


if __name__ == "__main__":
    main()
