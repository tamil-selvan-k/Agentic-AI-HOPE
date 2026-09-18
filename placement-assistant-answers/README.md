# Placement Assistant: Day 3 answer kit (instructor only)

Do not share this folder with students.

| Path | What it is |
|---|---|
| `INSTRUCTOR.md` | Timings, what to demo, common mistakes, catch-up, sprint checking |
| `catchup/` | Checkpoints for a stuck student at the end of Part 1, 2 or 3. No lab answers. |
| `app/memory.py` | Part 1, lab 1 (`request_cancel`, `mark_cancelled`), lab 2 (`fail_attempt`) |
| `app/idempotency.py`, `app/placement_db.py` (`once`), `app/runner.py` (`call_tool`) | Part 2 |
| `app/placement_db.py` (safe writes), `app/idempotency.py` (`notification_dedupe_key`) | Part 3 |
| `app/runner.py` (`between_steps`) | Lab 1 |
| `tests/test_lab3_race.py` | Lab 3: the tests students write |
| `docs/lab4_crash.md`, `docs/design.md` | Written answer keys |

```bash
pip install -r requirements.txt
pytest            # 66 passed (about 20 s: the crash drill starts real processes)
```
