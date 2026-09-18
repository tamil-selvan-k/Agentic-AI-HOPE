"""Lab 4 drill: kill -9 a worker in the middle of a run, start another, count the side effects.

    python -m scripts.crash_drill

Uses its own throwaway databases in a temp folder, so your agent.db and placement.db are untouched.
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEASE = 4.0


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="crash-drill-")
    env = {**os.environ, "AGENT_DB": os.path.join(tmp, "agent.db"), "PLACEMENT_DB": os.path.join(tmp, "placement.db")}
    os.environ.update({k: env[k] for k in ("AGENT_DB", "PLACEMENT_DB")})
    from app.memory import RunStore
    from app.placement_db import PlacementDb

    store, placement = RunStore(env["AGENT_DB"]), PlacementDb(env["PLACEMENT_DB"])
    store.migrate()
    placement.migrate()
    run_id = store.enqueue(store.create_thread("22CS045"), "Apply me to Zoho, book slot 1 and text me.", "mock")
    print(f"1. queued run {run_id[:8]}")

    worker = [sys.executable, "-m", "scripts.worker", "--mock", "--slow", "0.5", "--lease", str(LEASE)]
    first = subprocess.Popen(worker + ["--id", "worker-A", "--gap", "1.5"], cwd=ROOT, env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    print("2. worker-A started")
    deadline = time.time() + 30
    while placement.count("notification") == 0:
        if time.time() > deadline or first.poll() is not None:
            first.kill()
            print("worker-A never sent the notification; is Part 1 finished?")
            return 1
        time.sleep(0.1)
    first.kill()                       # SIGKILL on Linux/macOS, TerminateProcess on Windows: no cleanup runs
    first.wait()
    run = store.get_run(run_id)
    print(f"3. killed worker-A after it sent the notification but before it recorded doing so: run is '{run['status']}',"
          f" leased to {run['lease_owner']}, {len(run['steps'])} steps recorded")

    print(f"4. waiting {LEASE:.0f} s for worker-A's lease to expire...")
    time.sleep(LEASE + 0.5)
    subprocess.run(worker + ["--id", "worker-B", "--once"], cwd=ROOT, env=env, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    run = store.get_run(run_id)
    booked = placement.conn.execute("SELECT count(*) FROM interview_slot WHERE student_id IS NOT NULL").fetchone()[0]
    counts = (placement.count("application"), booked, placement.count("notification"))
    print(f"5. worker-B finished the run: '{run['status']}' after {run['attempts']} attempts")
    print(f"\napplications {counts[0]}   booked slots {counts[1]}   notifications {counts[2]}")
    ok = run["status"] == "succeeded" and counts == (1, 1, 1)
    print("PASS: exactly one of each" if ok else "FAIL: expected exactly one of each and a succeeded run")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
