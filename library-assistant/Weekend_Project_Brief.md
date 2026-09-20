# Weekend project: your own end-to-end agent

Build a small agent service like the Campus Library Assistant, in a domain of your own.
Two days, on your own. **Submit by 21:00 on Sunday.**

## Pick a domain

Choose one, or propose your own. It must have at least one thing that can run out or clash
(a copy, a seat, a slot, a stock count) and at least one message to send.

| Domain | Read-only tools | Side-effect tools | The thing that can clash |
|---|---|---|---|
| Hostel complaints desk | find complaint, get room | raise complaint, assign warden, notify | one open complaint per room per issue |
| Canteen pre-orders | list menu, check wallet | place order, cancel order, notify | limited portions per item |
| Lab equipment booking | list equipment, check training | book slot, return item, notify | one kit per slot |
| Event registration | list events, check eligibility | register, join waitlist, notify | seat limit |
| Leave requests | leave balance, holiday calendar | apply leave, withdraw, notify HOD | balance can't go negative |

## Requirements

Every item is checked. Items 1–7 are required; 8 is for a higher grade.

1. **Two SQLite databases.** Your domain's data in one, the agent's memory and queue in the other. Seed data included.
2. **At least five tools**: at least two read-only and two with side effects. Every description says when to use it, when not to, and what it changes.
3. **A business rule in data**, not in a prompt (like the library's `policy` table), and a tool that enforces it even if the model skips the check.
4. **A queue and a worker.** A question is queued, a worker claims it with a lease, and a dead worker's run is picked up by another.
5. **Idempotency.** Every side effect runs through a key stored with the effect, and at least one side effect is also safe to repeat on its own.
6. **Two agents or more.** A supervisor that delegates to at least one specialist, and at least one specialist with **no** write tools.
7. **Proof, without an API key.** Scripted models so `python -m scripts.demo` runs end to end with no key, a crash demo that prints PASS, and `pytest` with at least 12 tests, including one crash-and-replay test.
8. **For a higher grade**, any one of: cancel from a second terminal; retry with backoff and dead-lettering; a race test with threads; a successful run on real Gemini recorded in your README.

## Start here

1. Copy the library project's structure. Keep `app/db.py`, `app/memory.py`, `app/worker.py`, `app/idempotency.py` and `app/tools/dispatch.py` as they are; they have nothing library-specific in them.
2. Replace `schema/library.sql`, `app/library_db.py` and `app/tools/library_tools.py` with your domain.
3. Rewrite the prompts and delegations in `app/agents.py`, then the scripted conversations in `app/providers.py`.
4. Write tests as you go. Get `scripts/demo.py` working with scripted models before touching Gemini.

## Rules

- Scripted models for everything except the final real-model check. Two days of free-tier calls run out by lunch.
- Work alone. Talking about designs is fine; sharing code is not.
- Questions go to the course channel. Replies within 4 hours, 09:00–21:00.

## Submit

A zip named `weekend-<your-roll-no>.zip` **without** `.venv` or `.db` files, uploaded to the course drive. Include a
README with your domain, an architecture sketch like the library's, how to run the demo, and anything you left out.

## How it is graded

| Part | Weight | Checked by |
|---|---|---|
| Runs: demo, crash demo and tests pass on a clean machine with no key | 30% | Running them |
| Tools and data: descriptions, rule in data, schema, safe writes | 25% | Reading the code |
| Durable execution: queue, lease, keys, crash replay | 20% | Crash demo and tests |
| Multi-agent: delegation, least privilege, keys passed down | 15% | Reading the code |
| README and design choices explained | 10% | Reading |

A project that doesn't run with `python -m scripts.demo` on a clean machine gets at most 30%, whatever else it has.
