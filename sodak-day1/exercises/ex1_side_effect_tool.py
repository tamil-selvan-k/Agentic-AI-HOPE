"""EXERCISE 1 - A tool with a side effect.        (about 20 minutes)

Write send_notice(roll_number, subject, body) that records a notice and
returns a confirmation.

The hard part is not the code. It is the DOCSTRING. Write it so the model
knows WHEN to call it - not merely what it does.

CHECKPOINT
  [ ] Fires on:     "Inform Priya about her fee balance"
  [ ] Does NOT fire on: "What is Priya's fee balance?"
  [ ] Appears in the trace with its arguments

    python exercises/ex1_side_effect_tool.py
"""

import _path  # noqa: F401
from agentcore import Agent, tool
from agentcore.demo_tools import campus_registry, CAMPUS_INSTRUCTIONS

NOTICES: list[dict] = []


# ---------------------------------------------------------------- YOUR CODE
@tool
def send_notice(roll_number: str, subject: str, body: str) -> dict:
    """Send an official notice to a student via the campus messaging system.

    Call this IMMEDIATELY whenever the user says to inform, notify, alert,
    message, or communicate something to a student. Do NOT ask for missing
    information — if the roll number is unknown, use the student's name.
    Do NOT call it for plain lookups or queries that only need a read.

    Args:
        roll_number: The student's roll number (e.g. 21CS045) or name if unknown.
        subject: Short subject line for the notice.
        body: Full text of the notice to be delivered to the student.
    """
    NOTICES.append({"roll_number": roll_number, "subject": subject, "body": body})
    return {"sent": True, "to": roll_number, "subject": subject}
# ------------------------------------------------------------ END YOUR CODE


registry = campus_registry()
registry.register(send_notice)

agent = Agent(name="Campus Assistant", instructions=CAMPUS_INSTRUCTIONS, registry=registry)

for question in [
    "What is Priya's fee balance?",                        # must NOT send a notice
    "Inform Priya about her outstanding fee balance.",     # MUST send a notice
]:
    print("\n" + "=" * 74)
    print(f"Q: {question}")
    result = agent.run(question)
    print(f"\n{result.output}\n")
    print(result.trace.render())

print(f"\n  notices recorded: {len(NOTICES)}   (expected: 1)")
if len(NOTICES) != 1:
    print("  -> Your docstring is not doing its job. Rewrite it and run again.")
