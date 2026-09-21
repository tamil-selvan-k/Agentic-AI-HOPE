"""LangChain-native placement agent using @tool decorator and create_agent."""
import json

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

from app.data import InMemoryPlacementRepo
from app.notify import OutboxNotifier
from app.tools.placement_tools import PlacementTools

SYSTEM = """You are the Placement Assistant for an engineering college's placement cell.
You are talking to the student with roll number {student_id}. Act only for this student.
Use the tools for every fact about drives, eligibility, applications and slots; never guess.
Eligibility is decided by check_eligibility, not by you. Keep replies short and concrete.
If the user asks a general question that doesn't need placement data, answer it directly."""


def build_tools(pt: PlacementTools) -> list:
    """Create LangChain @tool functions backed by PlacementTools methods."""

    @tool
    def check_eligibility(student_id: str, drive_id: int) -> str:
        """Check whether a student is eligible for a placement drive.

        Use before applying, or when asked 'can I apply?' or 'am I eligible for <company>?'.
        Do NOT use to list drives — use list_open_drives for that.

        Args:
            student_id: Roll number, e.g. '22CS045'.
            drive_id: Integer drive id returned by list_open_drives.

        Returns JSON with eligible (bool) and failed_rules if any."""
        return json.dumps(pt.check_eligibility(student_id, drive_id))

    @tool
    def list_open_drives(branch: str = None, grad_year: int = None) -> str:
        """List all currently open placement drives with their IDs, company, role, CTC and deadline.

        Use this whenever the user asks about available companies, drives, or opportunities.
        Always call this before check_eligibility or apply_to_drive to get valid drive IDs.

        Args:
            branch: Optional branch filter, e.g. 'CSE'. Drives that exclude this branch are hidden.
            grad_year: Optional graduation year filter, e.g. 2026.

        Returns JSON with a list of drives."""
        return json.dumps(pt.list_open_drives(branch, grad_year))

    @tool
    def get_student(student_id: str) -> str:
        """Retrieve a student's profile: name, branch, CGPA, backlogs, and graduation year.

        Args:
            student_id: Roll number, e.g. '22CS045'.

        Returns JSON with student profile fields."""
        return json.dumps(pt.get_student(student_id))

    @tool
    def apply_to_drive(student_id: str, drive_id: int) -> str:
        """Submit a placement application for a student to a drive.

        Call ONLY when the student explicitly asks to apply ('apply me', 'sign me up').
        Always run check_eligibility first so you can explain the result.
        Returns application_id and available interview slots to offer the student.

        Args:
            student_id: Roll number, e.g. '22CS045'.
            drive_id: Integer drive id from list_open_drives."""
        return json.dumps(pt.apply_to_drive(student_id, drive_id))

    @tool
    def book_interview_slot(student_id: str, slot_id: int) -> str:
        """Reserve an interview slot for a student who has already applied.

        Call ONLY when the student explicitly selects a slot to confirm.
        Offer the available slots first (from apply_to_drive) so the student can choose.

        Args:
            student_id: Roll number, e.g. '22CS045'.
            slot_id: Integer slot id from apply_to_drive's available_slots list."""
        return json.dumps(pt.book_interview_slot(student_id, slot_id))

    @tool
    def notify_student(student_id: str, message: str) -> str:
        """Send a notification (SMS/email) to a student.

        Call ONLY when the user explicitly asks to send a notification or reminder.
        Do NOT call for eligibility checks or informational queries.

        Args:
            student_id: Roll number, e.g. '22CS045'.
            message: Notification body, must be 1–160 characters."""
        return json.dumps(pt.notify_student(student_id, message))

    @tool
    def list_my_applications(student_id: str) -> str:
        """List all placement applications for a student, oldest first.

        Use for questions like 'where have I applied?', 'what is my status?',
        or 'when is my interview?'.

        Args:
            student_id: Roll number, e.g. '22CS045'.

        Returns JSON with application list including interview_at if a slot is booked."""
        return json.dumps(pt.list_my_applications(student_id))

    return [
        check_eligibility,
        list_open_drives,
        get_student,
        apply_to_drive,
        book_interview_slot,
        notify_student,
        list_my_applications,
    ]


def _extract_text(content) -> str:
    """Normalize AIMessage content: handles plain str and list-of-blocks formats."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content)


class PlacementAgent:
    """Agent-driven placement assistant.

    Uses LangChain's create_agent with @tool-decorated functions.
    Calls tools when needed; answers directly for general questions.
    """

    def __init__(self, model: str, student_id: str,
                 repo: InMemoryPlacementRepo | None = None,
                 notifier: OutboxNotifier | None = None):
        self.model = model
        self.student_id = student_id
        pt = PlacementTools(repo or InMemoryPlacementRepo(), notifier or OutboxNotifier())
        tools = build_tools(pt)
        llm = ChatGoogleGenerativeAI(model=model, temperature=0)
        system = SYSTEM.format(student_id=student_id)
        self._agent = create_agent(model=llm, tools=tools, system_prompt=system)
        self._history: list = []

    def ask(self, text: str) -> tuple[str, list[dict]]:
        """Send a user message; return (reply_text, tool_call_log).

        tool_call_log entries: {"tool": str, "args": dict, "result": str}.
        """
        self._history.append(HumanMessage(content=text))
        result = self._agent.invoke({"messages": self._history})
        new_messages = result["messages"][len(self._history):]
        self._history = list(result["messages"])

        reply = ""
        tool_log: list[dict] = []

        for msg in new_messages:
            if isinstance(msg, AIMessage):
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        tool_log.append({"tool": tc["name"], "args": tc["args"], "result": None})
                if msg.content:
                    reply = _extract_text(msg.content)
            elif isinstance(msg, ToolMessage):
                for entry in reversed(tool_log):
                    if entry["tool"] == msg.name and entry["result"] is None:
                        entry["result"] = msg.content
                        break

        return reply, tool_log
