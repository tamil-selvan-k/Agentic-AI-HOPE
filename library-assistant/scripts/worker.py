"""Run a worker.   python -m scripts.worker [--mock] [--slow 2] [--once]"""
import argparse
import logging
import time

from app.config import make_providers, open_stores
from app.worker import Worker
from scripts._term import CYAN, DIM, GREEN, RED, RESET, print_step


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mock", action="store_true")
    p.add_argument("--slow", type=float, default=0.0)
    p.add_argument("--once", action="store_true")
    a = p.parse_args()
    logging.basicConfig(level=logging.WARNING)
    store, db = open_stores()
    worker = Worker(store, db, make_providers(a.mock, a.slow), on_step=print_step)
    print(f"{CYAN}worker {worker.worker_id}{RESET} {DIM}Ctrl+C to stop.{RESET}")
    try:
        while True:
            item = worker.run_once()
            if item is None:
                if a.once:
                    break
                time.sleep(1.0)
                continue
            colour = GREEN if item[1] == "succeeded" else RED
            print(f"{colour}run {item[0][:8]} {item[1]}{RESET}\n")
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
