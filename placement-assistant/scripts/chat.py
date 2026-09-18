"""Talk to your Placement Assistant in the terminal. (Given.)

    python -m scripts.chat --mock                    # scripted model, no quota used
    python -m scripts.chat                           # real Gemini (needs GEMINI_API_KEY)
    python -m scripts.chat --student 22IT017         # act as a different student
    python -m scripts.chat --db agent.db             # Part 3: remember the conversation
    python -m scripts.chat --db agent.db --thread <id>   # carry on an earlier conversation

Every tool call is printed, so you can see which tool the model chose and what your code returned.
"""
import argparse
import json
import os
import traceback

from app.agent import Agent
from app.data import InMemoryPlacementRepo
from app.notify import OutboxNotifier
from app.providers import AgentError, GeminiProvider, default_mock
from app.tools.placement_tools import PlacementTools

DIM, CYAN, YELLOW, RED, RESET = "\033[2m", "\033[36m", "\033[33m", "\033[31m", "\033[0m"
if os.name == "nt":
    os.system("")          # enable colours in the Windows terminal


def short(obj, limit=160) -> str:
    text = json.dumps(obj, default=str)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def print_step(entry: dict) -> None:
    if entry["kind"] != "tool":
        return
    colour = YELLOW if entry["ok"] else RED
    print(f"  {colour}\u2192 {entry['tool']}{RESET}{DIM}({short(entry['args'], 100)}){RESET}")
    print(f"  {DIM}\u2190 {short(entry['result'])}  [{entry['ms']} ms]{RESET}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--student", default="22CS045")
    p.add_argument("--mock", action="store_true")
    p.add_argument("--db", help="SQLite file for the agent's memory (Part 3)")
    p.add_argument("--thread", help="continue this thread id from --db")
    a = p.parse_args()

    provider = default_mock() if a.mock else GeminiProvider(os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"))
    tools = PlacementTools(InMemoryPlacementRepo(), OutboxNotifier())

    memory = thread_id = None
    if a.db:
        from app.memory import ConversationStore

        memory = ConversationStore(a.db)
        memory.migrate()
        if a.thread and memory.get_thread(a.thread) is None:
            raise SystemExit(f"No thread {a.thread} in {a.db}.")
        thread_id = a.thread or memory.create_thread(a.student)
        print(f"{DIM}thread {thread_id}{RESET}")

    try:
        agent = Agent(provider, tools, a.student, memory=memory, thread_id=thread_id, on_step=print_step)
    except NotImplementedError:
        raise SystemExit("ConversationStore isn't finished yet: complete Part 3.2, or run without --db.")
    print(f"Placement Assistant for {a.student} on {provider.model}. Type 'exit' to quit.\n")
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


if __name__ == "__main__":
    main()
