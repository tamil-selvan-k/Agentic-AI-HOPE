# Campus Event Registration Assistant: End-to-End Multi-Agent Service

An agentic event registration platform for college students (hackathons, symposiums, workshops).

A student asks a question in plain English. A **supervisor** agent delegates to two **specialist**
agents: an event catalogue specialist that can only look up event details and a desk specialist that can authenticate students, register for events, and send notification texts. The run is a job on a queue, and a worker that dies halfway through doesn't register the student twice.

```
student ─▶ queue (agent.db) ─▶ worker ─▶ supervisor ──ask_catalogue──▶ catalogue agent ─▶ search_events, get_event
                                                   └─ask_desk───────▶ desk agent ─────▶ authenticate_student, get_student,
                                                                                         check_can_register, register_event*, notify_student*
                                                                          * side effects: run once per key
```

## Database Design & Supabase Support

The application supports both local SQLite databases (`agent.db` and `event.db`) for zero-dependency offline testing, as well as a single unified PostgreSQL database on **Supabase**.
- Single SQL migration file for Supabase: [`schema/supabase_combined.sql`](file:///c:/Users/DELL/Docs/Agentic-AI%20HOPE/event-registration-assistant/schema/supabase_combined.sql)
- Individual domain schema: [`schema/event.sql`](file:///c:/Users/DELL/Docs/Agentic-AI%20HOPE/event-registration-assistant/schema/event.sql)
- Agent queue schema: [`schema/agent.sql`](file:///c:/Users/DELL/Docs/Agentic-AI%20HOPE/event-registration-assistant/schema/agent.sql)

## Student Authentication (AuthN)

Student authentication is built into the student schema and Desk tools:
- Attributes: `reg_num` (e.g. `22CS045`), `password` (e.g. `pass123`).
- Tool: `authenticate_student(password)` verifies student credentials before executing registration requests when explicitly provided.

## Run it (no API key needed)

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m scripts.demo            # two questions, scripted models, every step printed
python -m scripts.demo --crash    # worker dies right after registering; second worker resumes: PASS
pytest                            # 22 tests, under a second
```

With Groq API (`export GROQ_API_KEY=gsk_...` or set `GROQ_API_KEY` in `.env`):

```bash
python -m scripts.demo --real                                      # same questions, real models
python -m scripts.worker                                           # terminal 1
python -m scripts.ask --student 22CS045 "Is AI Hackathon 2026 open? Register me for it."   # terminal 2
```

## Web UI & AI Assistant

Run the FastAPI web application with responsive event cards and real-time streaming AI chat:
```bash
python -m uvicorn app.server:app --port 8000
```
Open **http://127.0.0.1:8000/** in your browser.

## Architecture & Features

| Concept | Implementation |
|---|---|
| Domain & Business Rule in Data | `event.sql` (`student`, `event`, `policy` tables) |
| Student AuthN | `student` table (`reg_num`, `password`), `authenticate_student` tool |
| Agent memory apart from business data | `agent.db` vs `event.db` (or unified Supabase DB) |
| Job Queue & Worker Lease | `app/memory.py`, `app/worker.py`, `app/runner.py` |
| Idempotency & Safe Writes | `EventDb.once`, `EventDb.register`, `record_notification` |
| Multi-Agent Hierarchy | `SupervisorTools` delegates to `CatalogueTools` & `DeskTools` |
| LLM Provider | `GroqProvider` in `app/providers.py` (`GROQ_API_KEY`, `GROQ_MODEL`) |

## Seed Data

| Student | Registration No | Max Registrations | Existing Registrations | What Happens |
|---|---|---|---|---|
| Priya Raman | 22CS045 | 3 | 0 | Can register |
| Arjun Kumar | 22IT017 | 1 | 1 (Cyber Security Challenge) | Refused: max limit reached |
| Divya Sekar | 22EC031 | 1 | 1 (Algorithmic Code Sprint) | Refused: max limit reached |

Events: AI Hackathon 2026 (50 seats), Web3 & Cloud Symposium (1 seat), Algorithmic Code Sprint (29 available), Operating System Workshop (0 available), Cyber Security Challenge (24 available).
