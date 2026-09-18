# Day 3 instructor notes: durable execution

No Docker, no database server. Two SQLite files. `pip install -r requirements.txt`.

## Opening demo (block A, 5 of the 20 minutes)

Ask for the answer to Day 2's homework: "kill the chat mid-run; what does the run say?" It says
`running`, forever. Nothing will ever finish it or tell you it failed. That is today's problem.

## Plan

| Block | Min | You | Students |
|---|---|---|---|
| B concept | 50 | A run is a job: status machine, lease, heartbeat, reaper. Why BEGIN IMMEDIATE (Day 2 deadlock, applied). | Whiteboard |
| C build | 70 | Live-code `enqueue` and `claim_next`. Show two workers never share a run. | `heartbeat`, `reap_expired`, then two terminals: worker + ask |
| D concept + build | 40 | **Run the crash drill on the Part 1 checkpoint: it FAILS with two notifications.** Then idempotency keys: hashing from Day 2, applied. | `canonical_json`, `idempotency_key`, `once`, `call_tool`; drill passes |
| E build | 60 | "A new key doesn't help if the user asks twice." | Safe writes: ON CONFLICT, optimistic version, dedupe key |
| F lab | 90 | Circulate | L1 cancel, L2 retry and dead-letter, L3 write the race test, L4 drill |
| G | 30 | **Issue the sprint** (`SPRINT.md`). Name the channel and response window. | |

The drill failing before Part 2 is the moment the day turns. To show it: copy `catchup/after-part1/` over a
starter copy, run `python -m scripts.crash_drill`, and read out "notifications 2".

## Common mistakes

| Where | Mistake |
|---|---|
| `claim_next` | SELECT then UPDATE in two autocommit statements: two workers can claim one run. Both must be inside `self.transaction()`. |
| `reap_expired` | Requeueing without clearing `lease_owner`, so the old worker's heartbeat still succeeds |
| `heartbeat` | Not checking `lease_owner`: a worker that lost its lease keeps writing |
| `canonical_json` | Forgetting nested values, or `12.0` vs `12` (Gemini sends floats for integers) |
| `once` | Catching the tool's exception inside the transaction: a half-written effect commits and its key is stored |
| `call_tool` | Wrapping read-only tools in `once` too: harmless but fills the table; ask why it's unnecessary |
| `claim_slot` | Bumping the version in a second statement; checking the version in Python instead of the WHERE clause |
| Lab 2 | Backoff from attempts instead of attempts - 1 (first retry after 4 s instead of 2 s) |

## Catch-up

At the end of each part, copy the matching `catchup/` folder over the student's kit (see
`catchup/README.md`). None contains a lab answer. Students who fall behind in the sprint get the
next checkpoint from you on request.

## Checking the sprint (night before Day 4)

```bash
pytest -q
for i in 1 2 3; do python -m scripts.crash_drill | tail -1; done
```

Then read `docs/design.md` against `docs/design.md` in this kit.
