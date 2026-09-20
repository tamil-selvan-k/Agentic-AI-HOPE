"""Day 4: three agents. A supervisor talks to the member and delegates to two specialists.

    member ──▶ supervisor ──ask_catalogue──▶ catalogue agent  (search_books, get_book)
                          └─ask_desk───────▶ desk agent       (get_member, check_can_borrow,
                                                               reserve_book, notify_member)

Each specialist is an ordinary agent loop with its own system prompt and its own small tool set.
To the supervisor, a specialist is just a tool: "agent as tool", the simplest multi-agent pattern.
"""
import time
from collections.abc import Callable

from app.idempotency import idempotency_key
from app.library_db import LibraryDb
from app.providers import AgentError
from app.tools.library_tools import CatalogueTools, DeskTools, Toolset

SPECIALIST_MAX_STEPS = 6

SUPERVISOR_SYSTEM = """You are the Campus Library Assistant, talking to the member with roll number {roll_no}.
You never search the catalogue or change reservations yourself. Delegate:
- ask_catalogue for finding books and checking what is on the shelf;
- ask_desk for anything about this member's account, reservations or messages.
Give each specialist a complete, specific request, including book ids once you know them.
Then answer the member briefly, using only what the specialists reported."""

CATALOGUE_SYSTEM = """You are the catalogue specialist of a campus library. Find books and report
their book_id, title, author and copies_available. You cannot reserve anything. Be brief."""

DESK_SYSTEM = """You are the circulation desk specialist, acting for member {roll_no} only.
Always call check_can_borrow before reserve_book. Never decide policy yourself: report the reasons
the tools give. Confirm a successful reservation with notify_member. Report what you did, briefly."""


def run_tool(toolset: Toolset, db: LibraryDb, key: str, name: str, args: dict) -> tuple[dict, bool]:
    """Run one tool call for any agent. Returns (result, replayed). Never raises, except AgentError.

    Side effects run at most once per key (Day 3); replayed is True when the stored result was returned
    and nothing was done. Delegations hand the key down, so the specialist's side effects get keys
    derived from it: a replayed delegation replays its side effects safely too.
    """
    try:
        if name in toolset.DELEGATES:
            return toolset.delegate(name, args, key), False
        if name in toolset.SIDE_EFFECTS:
            result, fresh = db.once(key, name, lambda: toolset.call(name, args))
            return result, not fresh
        return toolset.call(name, args), False
    except AgentError:
        raise
    except NotImplementedError:
        return {"error": "not_implemented", "hint": f"{name} is not available yet."}, False
    except Exception as e:
        return {"error": "tool_failed", "hint": f"{name} failed ({type(e).__name__}). Try another way or tell the user."}, False


def run_specialist(agent: str, system: str, toolset: Toolset, *, db: LibraryDb, provider, task: str,
                   parent_key: str, on_step: Callable[[dict], None] | None = None) -> dict:
    """A specialist's whole agent loop, run inside one tool call of the supervisor."""
    contents = [{"role": "user", "text": task}]
    functions = list(toolset.functions().values())
    used = []
    seq = 0
    while seq < SPECIALIST_MAX_STEPS:
        turn = provider.generate(system, contents, functions)
        seq += 1
        if not turn.tool_calls:
            return {"agent": agent, "answer": turn.text or "", "tools_used": used}
        contents.append({"role": "model", "text": turn.text, "raw": turn.raw,
                         "tool_calls": [{"name": c.name, "args": c.args} for c in turn.tool_calls]})
        for call in turn.tool_calls:
            seq += 1
            key = idempotency_key(parent_key, seq, call.name, call.args)
            started = time.perf_counter()
            result, replayed = run_tool(toolset, db, key, call.name, call.args)
            used.append(call.name)
            if on_step:
                on_step({"agent": agent, "kind": "tool", "tool": call.name, "args": call.args, "result": result,
                         "ok": "error" not in result, "replayed": replayed,
                         "ms": round((time.perf_counter() - started) * 1000)})
            contents.append({"role": "tool", "name": call.name, "result": result})
    return {"agent": agent, "error": "specialist_step_limit", "tools_used": used,
            "hint": "The specialist could not finish. Tell the member to try a simpler request."}


class SupervisorTools(Toolset):
    """The supervisor's only tools are the two specialists."""

    TOOL_NAMES = ("ask_catalogue", "ask_desk")
    DELEGATES = ("ask_catalogue", "ask_desk")

    def __init__(self, db: LibraryDb, providers: dict, roll_no: str, on_step=None):
        self.db, self.providers, self.roll_no, self.on_step = db, providers, roll_no, on_step

    def ask_catalogue(self, question: str) -> dict:
        """Ask the catalogue specialist to find books or check how many copies are on the shelf.

        Use for "do you have", "is <title> available", "books about <subject>". It cannot reserve.

        Args:
            question: A complete request, e.g. "Is Designing Data-Intensive Applications available?"

        Returns:
            {"agent": "catalogue", "answer": str, "tools_used": [str]}.
        """
        raise RuntimeError("delegations run through delegate()")

    def ask_desk(self, request: str) -> dict:
        """Ask the circulation desk specialist to act on this member's account. It CAN CHANGE DATA:
        reserve books and send the member messages.

        Use for reservations, fines, "what have I reserved", and confirmations. Include the book_id
        from the catalogue when reserving. The desk always acts for the current member only.

        Args:
            request: A complete instruction, e.g. "Reserve book 2 and text the member to confirm."

        Returns:
            {"agent": "desk", "answer": str, "tools_used": [str]}.
        """
        raise RuntimeError("delegations run through delegate()")

    def delegate(self, name: str, args: dict, key: str) -> dict:
        bad = self.call_check(name, args)
        if bad:
            return bad
        if self.on_step:
            self.on_step({"agent": "supervisor", "kind": "delegate", "tool": name, "args": args})
        if name == "ask_catalogue":
            return run_specialist("catalogue", CATALOGUE_SYSTEM, CatalogueTools(self.db), db=self.db,
                                  provider=self.providers["catalogue"], task=args["question"],
                                  parent_key=key, on_step=self.on_step)
        return run_specialist("desk", DESK_SYSTEM.format(roll_no=self.roll_no), DeskTools(self.db, self.roll_no),
                              db=self.db, provider=self.providers["desk"], task=args["request"],
                              parent_key=key, on_step=self.on_step)

    def call_check(self, name: str, args: dict) -> dict | None:
        """Validate a delegation's arguments the same way dispatch validates any tool call."""
        field = "question" if name == "ask_catalogue" else "request"
        if set(args) != {field} or not isinstance(args[field], str) or not args[field].strip():
            return {"error": "invalid_arguments", "hint": f"{name} takes one non-empty string: {field}."}
        return None
