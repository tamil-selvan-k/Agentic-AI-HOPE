import time
from collections.abc import Callable

from app.memory import ConversationStore
from app.providers import AgentError
from app.tools.placement_tools import PlacementTools

MAX_STEPS = 8

SYSTEM = """You are the Placement Assistant for an engineering college's placement cell.
You are talking to the student with roll number {student_id}. Act only for this student.
Use the tools for every fact about drives, eligibility, applications and slots; never guess.
Eligibility is decided by check_eligibility, not by you. Keep replies short and concrete."""


class Agent:
    """A small agent: one student, one conversation, the placement tools."""

    def __init__(self, provider, tools: PlacementTools, student_id: str,
                 memory: ConversationStore | None = None, thread_id: str | None = None,
                 on_step: Callable[[dict], None] | None = None):
        self.provider = provider
        self.tools = tools
        self.system = SYSTEM.format(student_id=student_id)
        self.memory = memory
        self.thread_id = thread_id
        self.on_step = on_step
        self.trace: list[dict] = []
        if memory and thread_id:
            history = memory.load_history(thread_id)
            self.contents: list[dict] = [{"role": m["role"], "text": m["text"]} for m in history]
        else:
            self.contents: list[dict] = []

    def _log(self, entry: dict) -> None:
        """Add one entry to the trace and tell on_step about it. (Given.)"""
        self.trace.append(entry)
        if self.on_step:
            self.on_step(entry)

    # ------------------------------------------------------------------ Part 2.1

    def run_tool(self, name: str, args: dict) -> dict:
        """Call one tool with self.tools.call(name, args). Never raise."""
        try:
            return self.tools.call(name, args)
        except NotImplementedError:
            return {"error": "not_implemented", "hint": f"Tool {name!r} is not yet implemented."}
        except Exception as e:
            return {"error": "tool_failed", "hint": type(e).__name__}

    # ------------------------------------------------------------------ Part 2.2

    def ask(self, text: str) -> str:
        """One user turn: loop model calls and tool calls until the model answers."""
        self.contents.append({"role": "user", "text": text})

        run_id = None
        if self.memory and self.thread_id:
            self.memory.append_message(self.thread_id, "user", text)
            run_id = self.memory.start_run(self.thread_id, self.provider.model)

        step = 0
        try:
            while True:
                if step >= MAX_STEPS:
                    raise AgentError("step_limit", f"Agent exceeded {MAX_STEPS} steps without answering.")

                turn = self.provider.generate(self.system, self.contents, list(self.tools.functions().values()))
                step += 1
                self._log({"step": step, "kind": "model",
                           "tokens_in": turn.tokens_in, "tokens_out": turn.tokens_out})

                if run_id:
                    self.memory.record_model_step(run_id, step, turn.tokens_in, turn.tokens_out)

                if not turn.tool_calls:
                    reply = turn.text or ""
                    self.contents.append({"role": "model", "text": reply, "raw": turn.raw})
                    if run_id:
                        self.memory.append_message(self.thread_id, "model", reply)
                        self.memory.finish_run(run_id, "succeeded")
                    return reply

                self.contents.append({
                    "role": "model",
                    "text": turn.text,
                    "raw": turn.raw,
                    "tool_calls": [{"name": c.name, "args": c.args} for c in turn.tool_calls],
                })

                for call in turn.tool_calls:
                    t0 = time.monotonic()
                    result = self.run_tool(call.name, call.args)
                    ms = int((time.monotonic() - t0) * 1000)
                    ok = "error" not in result
                    step += 1
                    self._log({"step": step, "kind": "tool", "tool": call.name,
                               "args": call.args, "result": result, "ok": ok, "ms": ms})
                    if run_id:
                        self.memory.record_tool_call(run_id, step, call.name, call.args, result, ok, ms)
                    self.contents.append({"role": "tool", "name": call.name, "result": result})

        except AgentError as e:
            if run_id:
                self.memory.finish_run(run_id, "failed", e.code)
            raise
