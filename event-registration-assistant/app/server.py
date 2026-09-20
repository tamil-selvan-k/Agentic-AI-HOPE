"""FastAPI Web Server for Event Registration Assistant Platform with Session Memory."""
import asyncio
import json
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import make_providers, open_stores
from app.worker import Worker

app = FastAPI(title="Campus Event Registration Platform")

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class ChatRequest(BaseModel):
    student_id: str
    message: str
    thread_id: Optional[str] = None


@app.get("/", response_class=HTMLResponse)
def get_index():
    index_file = STATIC_DIR / "index.html"
    return index_file.read_text(encoding="utf-8")


@app.get("/api/events")
def get_events():
    _, db = open_stores()
    events = db.search_events("", limit=50)
    return events


@app.get("/api/students")
def get_students():
    _, db = open_stores()
    rows = db.conn.execute("SELECT reg_num, name, dept FROM student").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    store, db = open_stores()
    
    # Session Memory: reuse existing thread for student or create a new thread
    thread_id = req.thread_id
    if not thread_id:
        row = store.conn.execute(
            "SELECT id FROM thread WHERE student_id = ? ORDER BY created_at DESC LIMIT 1",
            (req.student_id,)
        ).fetchone()
        thread_id = row["id"] if row else store.create_thread(req.student_id)

    # Use real model if API key is present, otherwise mock provider
    use_mock = not bool(os.environ.get("GROQ_API_KEY") or os.environ.get("GEMINI_API_KEY"))
    providers = make_providers(mock=use_mock)

    model = providers["supervisor"].model
    run_id = store.enqueue(thread_id, req.message, model)

    async def event_generator():
        log_queue = asyncio.Queue()

        def on_step(step_data):
            agent = step_data.get("agent", "")
            kind = step_data.get("kind", "")
            if kind == "delegate":
                msg = f"  supervisor ➔ {step_data.get('tool')}({json.dumps(step_data.get('args', {}))})"
            elif kind == "tool":
                res_str = json.dumps(step_data.get("result", {}))
                if len(res_str) > 80:
                    res_str = res_str[:77] + "..."
                msg = f"      {agent} ➔ {step_data.get('tool')}({json.dumps(step_data.get('args', {}))})\n           ← {res_str}"
            elif kind == "model" and step_data.get("text"):
                msg = f"  {agent} ➔ {step_data.get('text')}"
            else:
                msg = f"  [{agent}] {kind}"
            log_queue.put_nowait(msg)

        worker = Worker(store, db, providers, worker_id="web-worker", on_step=on_step)

        # Run worker in background thread
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(None, worker.run_until_idle)

        while not future.done() or not log_queue.empty():
            try:
                log_msg = await asyncio.wait_for(log_queue.get(), timeout=0.1)
                yield f"data: {json.dumps({'type': 'log', 'text': log_msg})}\n\n"
            except asyncio.TimeoutError:
                pass

        run = store.get_run(run_id)
        if run["status"] == "succeeded":
            history = store.load_history(thread_id)
            final_text = history[-1]["text"] if history else "Run succeeded."
            yield f"data: {json.dumps({'type': 'answer', 'text': final_text, 'thread_id': thread_id})}\n\n"
        else:
            err_msg = f"Run status: {run['status']} ({run.get('error_code', 'unknown')})"
            yield f"data: {json.dumps({'type': 'answer', 'text': err_msg, 'thread_id': thread_id})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.server:app", host="127.0.0.1", port=8000, reload=True)
