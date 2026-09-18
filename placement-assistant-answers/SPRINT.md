# Sprint: three days, on your own

Issued at the end of Day 3. **Submit by 21:00 the evening before Day 4.**

## Scope

One domain, one codebase, and `tests/` is the contract. You choose how; the tests say what.

1. **Every test passes**, including the lab 3 race tests you write yourself: `pytest`.
2. **The crash drill passes three times in a row**: `python -m scripts.crash_drill`.
3. **Real model, real workers**: start two workers with Gemini, queue five questions from at least three different students, and show zero duplicate applications, bookings or notifications with `python -m scripts.status`. Paste the output into `docs/lab4_crash.md` under a new heading.
4. **Design notes**: answer the five questions in `docs/design.md`.

## Rules

- Use `--mock` for everything except task 3. Three days on the free tier runs out by mid-afternoon; the scripted model costs nothing.
- Stuck for more than an hour? Ask your instructor for the matching catch-up files, then keep going.
- Questions go to the course channel. Replies within 4 hours, 09:00–21:00.

## Submit

Zip the project folder **without** `.venv`, `agent.db` and `placement.db`, name it `day3-<your-roll-no>.zip`, and upload it to the course drive.

## How it is checked

The instructor runs `pytest` and the crash drill on your code the night before Day 4, and reads `docs/design.md`. Day 4 starts from this codebase.
