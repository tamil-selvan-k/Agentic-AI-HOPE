"""A worker: claim a run, execute it, record how it ended. (Same as Day 3.)"""
import logging
import os
import socket
import time
import uuid

from app.library_db import LibraryDb
from app.memory import RunStore
from app.providers import AgentError
from app.runner import LeaseLost, execute_run

log = logging.getLogger("worker")


class Worker:
    def __init__(self, store: RunStore, db: LibraryDb, providers: dict, worker_id: str | None = None,
                 lease_seconds: float = 60.0, on_step=None, record_delay: float = 0.0):
        self.store, self.db, self.providers = store, db, providers
        self.worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:4]}"
        self.lease_seconds, self.on_step, self.record_delay = lease_seconds, on_step, record_delay

    def run_once(self) -> tuple[str, str] | None:
        self.store.reap_expired()
        claimed = self.store.claim_next(self.worker_id, self.lease_seconds)
        if claimed is None:
            return None
        try:
            outcome = execute_run(claimed, store=self.store, db=self.db, providers=self.providers,
                                  worker_id=self.worker_id, lease_seconds=self.lease_seconds,
                                  on_step=self.on_step, record_delay=self.record_delay)
        except LeaseLost:
            outcome = "lease_lost"
        except AgentError as e:
            outcome = self.store.fail_attempt(claimed.run_id, self.worker_id, e.code, e.retryable) or "lease_lost"
        except Exception:
            log.exception("run %s crashed", claimed.run_id)
            outcome = self.store.fail_attempt(claimed.run_id, self.worker_id, "internal_error", False) or "lease_lost"
        return claimed.run_id, outcome

    def run_until_idle(self) -> list[tuple[str, str]]:
        done = []
        while (item := self.run_once()) is not None:
            done.append(item)
        return done

    def run_forever(self, poll_seconds: float = 1.0) -> None:
        while True:
            if self.run_once() is None:
                time.sleep(poll_seconds)
