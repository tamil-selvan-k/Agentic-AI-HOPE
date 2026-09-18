"""Queue a question and watch the run from the database, step by step.

    python -m scripts.ask "Apply me to Zoho and book the first slot"
    python -m scripts.ask --student 22IT017 "Can I apply to Zoho?"
    python -m scripts.ask --thread <id> "And TCS?"          # same conversation
    python -m scripts.ask --no-follow "..."                  # queue it and return

Nothing happens until a worker is running (python -m scripts.worker --mock).
"""
import argparse
import time

from app.config import GEMINI_MODEL, open_stores
from scripts._term import CYAN, DIM, GREEN, RED, RESET, print_step


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("text")
    p.add_argument("--student", default="22CS045")
    p.add_argument("--thread")
    p.add_argument("--no-follow", action="store_true")
    a = p.parse_args()

    store, _ = open_stores()
    thread_id = a.thread or store.create_thread(a.student)
    run_id = store.enqueue(thread_id, a.text, GEMINI_MODEL)
    print(f"{DIM}thread {thread_id}{RESET}\n{CYAN}run {run_id}{RESET} queued")
    if a.no_follow:
        return

    shown, last_status = 0, None
    while True:
        run = store.get_run(run_id)
        for step in run["steps"][shown:]:
            print_step(step)
        shown = len(run["steps"])
        if run["status"] != last_status:
            if run["status"] not in ("queued",) or last_status is not None:
                owner = f" by {run['lease_owner']}" if run["lease_owner"] else ""
                note = f" ({run['error_code']})" if run["error_code"] else ""
                print(f"{DIM}status: {run['status']}{owner}{note}, attempt {run['attempts']}{RESET}")
            last_status = run["status"]
        if run["status"] in ("succeeded", "failed", "cancelled", "dead"):
            break
        time.sleep(0.5)
    if run["status"] == "succeeded":
        reply = store.load_history(thread_id)[-1]["text"]
        print(f"{GREEN}assistant>{RESET} {reply}")
    else:
        print(f"{RED}run ended: {run['status']}{RESET}")


if __name__ == "__main__":
    main()
