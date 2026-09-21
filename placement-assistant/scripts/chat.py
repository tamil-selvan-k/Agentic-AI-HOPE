"""Talk to your Placement Assistant in the terminal. (Given.)

    python -m scripts.chat --mock                    # scripted model, no quota used
    python -m scripts.chat                           # real Gemini via LangChain agent
    python -m scripts.chat --student 22IT017         # act as a different student
    python -m scripts.chat --db agent.db             # Part 3: remember the conversation (mock only)
    python -m scripts.chat --db agent.db --thread <id>   # carry on an earlier conversation

Every tool call is printed so you can see which tool the model chose and what it returned.
"""
import argparse
import json
import os
import traceback

from dotenv import load_dotenv
load_dotenv()  # reads .env into os.environ automatically

from app.agent import Agent
from app.data import InMemoryPlacementRepo
from app.notify import OutboxNotifier
from app.providers import AgentError, default_mock
from app.tools.placement_tools import PlacementTools

DIM, CYAN, YELLOW, RED, RESET = "\033[2m", "\033[36m", "\033[33m", "\033[31m", "\033[0m"
if os.name == "nt":
    os.system("")          # enable colours in the Windows terminal


def short(obj, limit=160) -> str:
    text = json.dumps(obj, default=str) if not isinstance(obj, str) else obj
    return text if len(text) <= limit else text[: limit - 3] + "..."


def print_tool_call(tool: str, args: dict, result: str | None) -> None:
    print(f"  {YELLOW}→ {tool}{RESET}{DIM}({short(args, 100)}){RESET}")
    if result is not None:
        print(f"  {DIM}← {short(result)}  {RESET}")


def print_step(entry: dict) -> None:
    if entry["kind"] != "tool":
        return
    colour = YELLOW if entry["ok"] else RED
    print(f"  {colour}→ {entry['tool']}{RESET}{DIM}({short(entry['args'], 100)}){RESET}")
    print(f"  {DIM}← {short(entry['result'])}  [{entry['ms']} ms]{RESET}")


def run_lc_agent(student_id: str) -> None:
    """Interactive loop using the LangChain-native PlacementAgent."""
    from app.placement_agent import PlacementAgent
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    agent = PlacementAgent(model=model, student_id=student_id)
    print(f"Placement Assistant for {student_id} on {model} (LangChain agent). Type 'exit' to quit.\n")
    while True:
        try:
            text = input(f"{CYAN}you>{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if text.lower() in ("exit", "quit"):
            break
        if not text:
            continue
        try:
            reply, tool_log = agent.ask(text)
            for entry in tool_log:
                print_tool_call(entry["tool"], entry["args"], entry["result"])
            print(f"{CYAN}assistant>{RESET} {reply or '(no reply)'}\n")
        except Exception as e:
            print(f"{RED}error: {e}{RESET}\n")


def run_mock_agent(student_id: str, db: str | None, thread: str | None) -> None:
    """Interactive loop using the scripted mock provider (no API key needed)."""
    provider = default_mock()
    tools = PlacementTools(InMemoryPlacementRepo(), OutboxNotifier())

    memory = thread_id = None
    if db:
        from app.memory import ConversationStore
        memory = ConversationStore(db)
        memory.migrate()
        if thread and memory.get_thread(thread) is None:
            raise SystemExit(f"No thread {thread} in {db}.")
        thread_id = thread or memory.create_thread(student_id)
        print(f"{DIM}thread {thread_id}{RESET}")

    try:
        agent = Agent(provider, tools, student_id, memory=memory, thread_id=thread_id, on_step=print_step)
    except NotImplementedError:
        raise SystemExit("ConversationStore isn't finished yet: complete Part 3.2, or run without --db.")
    print(f"Placement Assistant for {student_id} on {provider.model}. Type 'exit' to quit.\n")
    while True:
        try:
            text = input(f"{CYAN}you>{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if text.lower() in ("exit", "quit"):
            break
        if not text:
            continue
        try:
            reply = agent.ask(text)
            print(f"{CYAN}assistant>{RESET} {reply or '(no reply)'}\n")
        except AgentError as e:
            print(f"{RED}{e.code}: {e.message}{RESET}\n")
        except NotImplementedError as e:
            where = traceback.extract_tb(e.__traceback__)[-1].name
            print(f"{RED}Not implemented yet: {where}(). Finish it, then try again.{RESET}\n")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--student", default="22CS045")
    p.add_argument("--mock", action="store_true", help="Use scripted mock provider (no API key needed)")
    p.add_argument("--db", help="SQLite file for conversation memory (mock mode only)")
    p.add_argument("--thread", help="Continue this thread id from --db")
    a = p.parse_args()

    if a.mock:
        run_mock_agent(a.student, a.db, a.thread)
    else:
        if a.db:
            print(f"{DIM}Note: --db memory is only supported in --mock mode. Running LangChain agent without persistence.{RESET}")
        run_lc_agent(a.student)


if __name__ == "__main__":
    main()
