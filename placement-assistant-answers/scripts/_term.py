import json
import os

DIM, CYAN, YELLOW, RED, GREEN, RESET = "\033[2m", "\033[36m", "\033[33m", "\033[31m", "\033[32m", "\033[0m"
if os.name == "nt":
    os.system("")


def short(obj, limit=150) -> str:
    text = json.dumps(obj, default=str)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def print_step(step: dict) -> None:
    if step["kind"] == "model":
        if step.get("tool_calls"):
            names = ", ".join(c["name"] for c in step["tool_calls"])
            print(f"  {DIM}{step['seq'] if 'seq' in step else step['step']:>2} model asks for {names}{RESET}")
        return
    ok = step["ok"] if "ok" in step else True
    colour = YELLOW if ok else RED
    name = step.get("tool") or step.get("tool_name")
    seq = step.get("step") or step.get("seq")
    print(f"  {colour}{seq:>2} \u2192 {name}{RESET}{DIM}({short(step['args'], 90)}){RESET}")
    print(f"     {DIM}\u2190 {short(step['result'])}{RESET}")
