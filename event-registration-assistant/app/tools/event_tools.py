"""The event platform's tools, split between two specialist agents. Descriptions are prompts (Day 2)."""
from datetime import datetime, timezone

from app.idempotency import notification_dedupe_key
from app.event_db import EventDb
from app.tools.dispatch import dispatch


class Toolset:
    SIDE_EFFECTS: tuple[str, ...] = ()     # run through EventDb.once with an idempotency key (Day 3)
    DELEGATES: tuple[str, ...] = ()        # hand work to another agent (Day 4)
    TOOL_NAMES: tuple[str, ...] = ()

    def functions(self) -> dict:
        return {n: getattr(self, n) for n in self.TOOL_NAMES}

    def call(self, name: str, args: dict) -> dict:
        return dispatch(self.functions(), name, args)


class CatalogueTools(Toolset):
    """Read-only. The catalogue agent can look, never change."""

    TOOL_NAMES = ("search_events", "get_event")

    def __init__(self, db: EventDb):
        self.db = db

    def search_events(self, text: str) -> dict:
        """Find events in the campus catalogue by words from the title, category or organizer.

        Use for "do you have ...", "is <title> open", "events on <category>". Returns at most five
        matches. Read-only: changes nothing. To register for an event, that is the desk's job, not this tool.

        Args:
            text: A few words from title, category or organizer, e.g. "hackathon" or "CSE Dept".

        Returns:
            {"events": [{"event_id", "title", "category", "organizer", "seats_available"}]}. An empty list
            means no match; try fewer or different words.
        """
        if not text.strip():
            return {"error": "empty_query", "hint": "Pass a few words from the title, category or organizer."}
        events = self.db.search_events(text)
        return {"events": [{"event_id": e["id"], "title": e["title"], "category": e["category"],
                            "organizer": e["organizer"], "seats_available": e["seats_available"]} for e in events]}

    def get_event(self, event_id: int) -> dict:
        """Get one event's details and how many seats are available right now.

        Use when you already have an event_id from search_events and need its current availability.
        Read-only: changes nothing.

        Args:
            event_id: Integer id returned by search_events.

        Returns:
            {"event_id", "title", "category", "organizer", "seats_total", "seats_available"}.
        """
        e = self.db.get_event(event_id)
        if e is None:
            return {"error": "unknown_event", "hint": "Use search_events to find the event_id first."}
        return {"event_id": e["id"], "title": e["title"], "category": e["category"], "organizer": e["organizer"],
                "seats_total": e["seats_total"], "seats_available": e["seats_available"]}


class DeskTools(Toolset):
    """The event registration desk, bound to ONE student. The model cannot pick a different registration number."""

    TOOL_NAMES = ("authenticate_student", "get_student", "check_can_register", "register_event", "unregister_event", "notify_student")
    SIDE_EFFECTS = ("register_event", "unregister_event", "notify_student")

    def __init__(self, db: EventDb, reg_num: str, clock=lambda: datetime.now(timezone.utc)):
        self.db, self.reg_num, self.clock = db, reg_num, clock

    def _student(self) -> dict:
        s = self.db.get_student(self.reg_num)
        if s is None:
            raise LookupError(f"student {self.reg_num} not found")
        return s

    def authenticate_student(self, password: str) -> dict:
        """Verify the current student's password.

        Use ONLY when the student explicitly provides their password in the prompt to login or authenticate.
        Do NOT call this tool for normal event registration requests unless a password was explicitly provided.

        Args:
            password: The student's password string.

        Returns:
            {"authenticated": bool, "reg_num": str}.
        """
        valid = self.db.authenticate_student(self.reg_num, password)
        return {"authenticated": valid, "reg_num": self.reg_num}

    def get_student(self) -> dict:
        """Get the current student's record: name, department, max registrations and active registrations.

        Use for "what am I registered for", "my account status". Read-only: changes nothing.

        Returns:
            {"reg_num", "name", "dept", "max_registrations", "registrations": [{"event_id", "title", "category"}]}.
        """
        s = self._student()
        return {"reg_num": s["reg_num"], "name": s["name"], "dept": s["dept"],
                "max_registrations": s["max_registrations"], "registrations": self.db.active_registrations(s["id"])}

    def check_can_register(self) -> dict:
        """Decide whether the current student may register for another event, using business policy.

        Use BEFORE register_event, and whenever the student asks "can I register". The decision comes from
        the database policy and student limits: never decide it yourself. Read-only: changes nothing.

        Returns:
            {"can_register": bool, "reasons": [str]}. Every reason is a rule the student currently breaks.
        """
        s = self._student()
        reasons = []
        limit = self.db.policy("max_registrations_per_student")
        allowed = min(s["max_registrations"], limit) if limit > 0 else s["max_registrations"]
        held = len(self.db.active_registrations(s["id"]))
        if held >= allowed:
            reasons.append(f"already registered for {held} of {allowed} allowed events")
        return {"can_register": not reasons, "reasons": reasons}

    def register_event(self, event_id: int) -> dict:
        """Register for one seat in an event for the current student. CHANGES DATA: takes a seat in the event.

        Use only when the student has asked to register for this event and check_can_register allowed it.
        Asking again for the same event is safe and returns the existing registration.

        Args:
            event_id: Integer id returned by search_events.

        Returns:
            {"event_id", "title", "status": "registered" | "already_registered"}, or an error:
            not_allowed (with reasons), unknown_event, or no_seats (none available right now).
        """
        verdict = self.check_can_register()
        if not verdict["can_register"]:
            return {"error": "not_allowed", "reasons": verdict["reasons"],
                    "hint": "Explain the reasons to the student. Do not retry."}
        event = self.db.get_event(event_id)
        if event is None:
            return {"error": "unknown_event", "hint": "Ask the catalogue for the right event_id."}
        status = self.db.register(self._student()["id"], event_id)
        if status == "no_seats":
            return {"error": "no_seats", "hint": "No seats are available. Tell the student; do not retry."}
        return {"event_id": event_id, "title": event["title"], "status": status}

    def unregister_event(self, event_id: int = 0, event_title: str = "") -> dict:
        """Cancel or unregister an event registration for the current student. CHANGES DATA: returns seat to event.

        Use when the student asks to "unregister", "cancel my registration", "withdraw from event", or drop out.
        If the student does NOT know the event_id, pass event_id=0 or event_title="". If the student holds one registration,
        it will automatically resolve and unregister that event.

        Args:
            event_id: Integer event_id (optional, pass 0 if unknown).
            event_title: Optional event title or keyword to match (e.g. "AI Hackathon").

        Returns:
            {"event_id", "title", "status": "unregistered" | "already_unregistered"}, or an error:
            not_allowed, not_registered, or multiple_registrations (list of active events).
        """
        student = self._student()
        status, details = self.db.unregister(student["id"], event_id, event_title)
        if status == "not_registered":
            return {"error": "not_registered", "hint": "Student is not currently registered for any matching event."}
        if status == "multiple_registrations":
            return {"error": "multiple_registrations", "active": details.get("active", []),
                    "hint": "Ask the student which specific event they want to unregister."}
        return {"event_id": details["id"], "title": details["title"], "status": status}

    def notify_student(self, message: str) -> dict:
        """Send the current student a short text message. CHANGES DATA: a message goes out.

        Use to confirm something that just happened, such as an event registration. The same message on the
        same day is sent only once. Never use it to answer a question; reply in the chat instead.

        Args:
            message: 1 to 160 characters.

        Returns:
            {"notification_id", "status": "queued", "duplicate": bool}.
        """
        if not message.strip() or len(message) > 160:
            return {"error": "invalid_message", "hint": "message must be 1 to 160 characters."}
        key = notification_dedupe_key(self.reg_num, message, self.clock().date())
        notification_id, created = self.db.record_notification(self.reg_num, message, key)
        return {"notification_id": notification_id, "status": "queued", "duplicate": not created}
