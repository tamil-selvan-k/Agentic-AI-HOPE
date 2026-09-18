"""Run a worker. Leave it running in one terminal; send questions from another with scripts.ask.

    python -m scripts.worker --mock               # scripted model: check, apply, book + notify, answer
    python -m scripts.worker --mock --slow 3      # 3 s per model call: time to kill it mid-run
    python -m scripts.worker                      # real Gemini (needs GEMINI_API_KEY)
    python -m scripts.worker --once               # handle what is queued, then exit
"""
import argparse
import logging

from app.config import make_provider, open_stores
from app.worker import Worker
from scripts._term import CYAN, DIM, GREEN, RED, RESET, print_step


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mock", action="store_true")
    p.add_argument("--slow", type=float, default=0.0)
    p.add_argument("--id")
    p.add_argument("--lease", type=float, default=30.0)
    p.add_argument("--once", action="store_true")
    p.add_argument("--gap", type=float, default=0.0, help="crash drill: seconds between a side effect and its record")
    a = p.parse_args()
    logging.basicConfig(level=logging.WARNING)

    store, placement = open_stores()
    worker = Worker(store, placement, make_provider(a.mock, a.slow), worker_id=a.id, lease_seconds=a.lease,
                    on_step=print_step, record_delay=a.gap)
    print(f"{CYAN}worker {worker.worker_id}{RESET} {DIM}on {worker.provider.model}, lease {a.lease:.0f} s. Ctrl+C to stop.{RESET}")
    try:
        while True:
            item = worker.run_once()
            if item is None:
                if a.once:
                    break
                import time

                time.sleep(1.0)
                continue
            run_id, outcome = item
            colour = GREEN if outcome == "succeeded" else RED
            print(f"{colour}run {run_id[:8]} {outcome}{RESET}\n")
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
