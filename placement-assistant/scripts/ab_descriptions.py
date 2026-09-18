"""Lab 1 — which tool does each prompt fire?

    python -m scripts.ab_descriptions --dry-run      # print exactly what the model sees
    python -m scripts.ab_descriptions --trials 3     # run the A/B against Gemini

Edit PROMPTS to your own four. Exactly one of them should fire TARGET.
Uses the in-memory placement data, so nothing is kept. (Given.)
"""
import argparse
import collections
import json
import os
import time

from app.agent import SYSTEM
from app.notify import OutboxNotifier
from app.tools.placement_tools import PlacementTools
from app.data import InMemoryPlacementRepo

TARGET = "notify_student"

PROMPTS = [
    ("Text me a reminder the day before my Zoho interview.", True),
    ("When does the Zoho drive close?", False),
    ("Did my TCS application go through?", False),
    ("Tell my friend 22IT017 that TCS is hiring.", False),
]


def main(trials: int, pause: float, dry_run: bool) -> None:
    from google import genai
    from google.genai import types

    tools = PlacementTools(InMemoryPlacementRepo(), OutboxNotifier())
    fns = list(tools.functions().values())
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY") or "dry-run")

    if dry_run:
        for fn in fns:
            decl = types.FunctionDeclaration.from_callable(client=client._api_client, callable=fn)
            print(json.dumps(decl.model_dump(mode="json", exclude_none=True), indent=2), "\n")
        return

    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM.format(student_id="22CS045"),
        tools=fns,
        temperature=0,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    print(f"| Prompt | Should fire {TARGET} | {TARGET} fired | Other tools |")
    print("|---|---|---|---|")
    for prompt, should in PROMPTS:
        fired, others = 0, collections.Counter()
        for _ in range(trials):
            resp = client.models.generate_content(model=model, contents=prompt, config=config)
            names = [fc.name for fc in (resp.function_calls or [])]
            fired += TARGET in names
            others.update(n for n in names if n != TARGET)
            time.sleep(pause)          # stay under the free-tier requests-per-minute limit
        other = ", ".join(f"{n} x{c}" for n, c in others.items()) or "none"
        print(f"| {prompt} | {'yes' if should else 'no'} | {fired}/{trials} | {other} |")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--trials", type=int, default=3)
    p.add_argument("--pause", type=float, default=6.0)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    main(a.trials, a.pause, a.dry_run)
