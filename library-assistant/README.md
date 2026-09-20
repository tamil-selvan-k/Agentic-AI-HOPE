# Campus Library Assistant: a sample end-to-end agent project

SoDak EduTech, Agentic AI Track, Day 4. This is the worked example for the weekend project: a
small, complete agent service in a **different domain** from the Placement Assistant, so you copy
the patterns, not the code.

A member asks a question in plain English. A **supervisor** agent delegates to two **specialist**
agents, a catalogue specialist that can only look and a desk specialist that can reserve books and
send texts. The run is a job on a queue, and a worker that dies halfway through doesn't reserve the
book twice.

```
member ─▶ queue (agent.db) ─▶ worker ─▶ supervisor ──ask_catalogue──▶ catalogue agent ─▶ search_books, get_book
                                                   └─ask_desk───────▶ desk agent ─────▶ get_member, check_can_borrow,
                                                                                         reserve_book*, notify_member*
                                                                          * side effects: run once per key
```

## Run it (no API key needed)

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m scripts.demo            # two questions, scripted models, every step printed
python -m scripts.demo --crash    # the worker dies right after reserving; a second worker finishes: PASS
pytest                            # 21 tests, under a second
```

With Gemini (`export GEMINI_API_KEY=...`):

```bash
python -m scripts.demo --real                                      # same questions, real models
python -m scripts.worker                                           # terminal 1
python -m scripts.ask --student 22CS045 "Do you have anything on operating systems?"   # terminal 2
```

One question costs about 5–7 model calls with three agents, so the free tier runs out quickly.
Use the scripted models for everything except a final check.

## Where each day shows up

| Day | Idea | Where to look |
|---|---|---|
| 1 | The agent loop, self-healing tool errors | `app/agents.py` `run_specialist` |
| 2 | Tool descriptions are prompts; rules live in data; schema | `app/tools/library_tools.py`, `schema/library.sql` (`policy` table) |
| 2 | Agent memory apart from business data | `agent.db` vs `library.db` |
| 3 | A run is a job: queue, lease, heartbeat, reaper | `app/memory.py`, `app/worker.py`, `app/runner.py` |
| 3 | Idempotency keys; safe writes | `LibraryDb.once`, `LibraryDb.reserve`, `record_notification` |
| 4 | Supervisor and specialists ("agent as tool") | `app/agents.py` `SupervisorTools` |
| 4 | Least privilege per agent | catalogue has no write tools; `DeskTools` is bound to one roll number |
| 4 | Keys passed down to specialists | `run_tool` hands the delegation's key to `run_specialist` |

## Seed data

| Member | Fine | Max reservations | What happens |
|---|---|---|---|
| 22CS045 Priya Raman | Rs 0 | 3 | Can reserve |
| 22IT017 Arjun Kumar | Rs 150 | 3 | Refused: fine above the Rs 100 policy |
| 22EC031 Divya Sekar | Rs 0 | 1 | Refused: already holds one reservation |

Books: 1 Clean Code (2 copies), 2 Designing Data-Intensive Applications (1 copy), 3 Introduction to
Algorithms (2 of 3 on the shelf), 4 Operating System Concepts (0 on the shelf), 5 Computer Networking (2).

## Known limits (on purpose, for later days)

- A specialist's inner steps are not stored; only the delegation and its answer are. After a crash the
  specialist runs again, and keys keep its side effects single. Storing them is checkpointing (Day 5).
- Keys only match if the model repeats the same call. The scripted models always do; real models
  usually do at temperature 0. The reservation and text are also safe to repeat on their own, which
  covers the rest.
- No approval step before a side effect (Day 5), no guardrails or metrics (Day 6), no MCP (Day 7).
