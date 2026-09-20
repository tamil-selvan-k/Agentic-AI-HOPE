"""The library's tools, split between two specialist agents. Descriptions are prompts (Day 2)."""
from datetime import datetime, timezone

from app.idempotency import notification_dedupe_key
from app.library_db import LibraryDb
from app.tools.dispatch import dispatch


class Toolset:
    SIDE_EFFECTS: tuple[str, ...] = ()     # run through LibraryDb.once with an idempotency key (Day 3)
    DELEGATES: tuple[str, ...] = ()        # hand work to another agent (Day 4)
    TOOL_NAMES: tuple[str, ...] = ()

    def functions(self) -> dict:
        return {n: getattr(self, n) for n in self.TOOL_NAMES}

    def call(self, name: str, args: dict) -> dict:
        return dispatch(self.functions(), name, args)


class CatalogueTools(Toolset):
    """Read-only. The catalogue agent can look, never change."""

    TOOL_NAMES = ("search_books", "get_book")

    def __init__(self, db: LibraryDb):
        self.db = db

    def search_books(self, text: str) -> dict:
        """Find books in the campus library catalogue by words from the title, author or subject.

        Use for "do you have ...", "is <title> available", "books on <subject>". Returns at most five
        matches. Read-only: changes nothing. To reserve a book, that is the desk's job, not this tool.

        Args:
            text: A few words from the title, author or subject, e.g. "Kleppmann" or "operating systems".

        Returns:
            {"books": [{"book_id", "title", "author", "subject", "copies_available"}]}. An empty list
            means no match; try fewer or different words.
        """
        if not text.strip():
            return {"error": "empty_query", "hint": "Pass a few words from the title, author or subject."}
        books = self.db.search_books(text)
        return {"books": [{"book_id": b["id"], "title": b["title"], "author": b["author"],
                           "subject": b["subject"], "copies_available": b["copies_available"]} for b in books]}

    def get_book(self, book_id: int) -> dict:
        """Get one book's details and how many copies are on the shelf right now.

        Use when you already have a book_id from search_books and need its current availability.
        Read-only: changes nothing.

        Args:
            book_id: Integer id returned by search_books.

        Returns:
            {"book_id", "title", "author", "subject", "copies_total", "copies_available"}.
        """
        b = self.db.get_book(book_id)
        if b is None:
            return {"error": "unknown_book", "hint": "Use search_books to find the book_id first."}
        return {"book_id": b["id"], "title": b["title"], "author": b["author"], "subject": b["subject"],
                "copies_total": b["copies_total"], "copies_available": b["copies_available"]}


class DeskTools(Toolset):
    """The circulation desk, bound to ONE member. The model cannot pick a different roll number."""

    TOOL_NAMES = ("get_member", "check_can_borrow", "reserve_book", "notify_member")
    SIDE_EFFECTS = ("reserve_book", "notify_member")

    def __init__(self, db: LibraryDb, roll_no: str, clock=lambda: datetime.now(timezone.utc)):
        self.db, self.roll_no, self.clock = db, roll_no, clock

    def _member(self) -> dict:
        m = self.db.get_member(self.roll_no)
        if m is None:
            raise LookupError(f"member {self.roll_no} not found")
        return m

    def get_member(self) -> dict:
        """Get the current member's library record: name, department, fine due and reservations.

        Use for "what do I owe", "what have I reserved". Read-only: changes nothing.

        Returns:
            {"roll_no", "name", "dept", "fine_due", "max_loans", "reservations": [{"book_id", "title"}]}.
        """
        m = self._member()
        return {"roll_no": m["roll_no"], "name": m["name"], "dept": m["dept"], "fine_due": m["fine_due"],
                "max_loans": m["max_loans"], "reservations": self.db.active_reservations(m["id"])}

    def check_can_borrow(self) -> dict:
        """Decide whether the current member may reserve another book, using the library's policy.

        Use BEFORE reserve_book, and whenever the member asks "can I borrow". The decision comes from
        the policy table: never decide it yourself. Read-only: changes nothing.

        Returns:
            {"can_borrow": bool, "reasons": [str]}. Every reason is a rule the member currently breaks.
        """
        m = self._member()
        reasons = []
        limit = self.db.policy("max_fine_to_borrow")
        if m["fine_due"] > limit:
            reasons.append(f"fine due Rs {m['fine_due']} is above the Rs {limit} limit")
        held = len(self.db.active_reservations(m["id"]))
        if held >= m["max_loans"]:
            reasons.append(f"already holds {held} of {m['max_loans']} allowed reservations")
        return {"can_borrow": not reasons, "reasons": reasons}

    def reserve_book(self, book_id: int) -> dict:
        """Reserve one copy of a book for the current member. CHANGES DATA: takes a copy off the shelf.

        Use only when the member has asked to reserve this book and check_can_borrow allowed it.
        Asking again for the same book is safe and returns the existing reservation.

        Args:
            book_id: Integer id returned by search_books.

        Returns:
            {"book_id", "title", "status": "reserved" | "already_reserved"}, or an error:
            not_allowed (with reasons), unknown_book, or no_copies (none on the shelf right now).
        """
        verdict = self.check_can_borrow()
        if not verdict["can_borrow"]:
            return {"error": "not_allowed", "reasons": verdict["reasons"],
                    "hint": "Explain the reasons to the member. Do not retry."}
        book = self.db.get_book(book_id)
        if book is None:
            return {"error": "unknown_book", "hint": "Ask the catalogue for the right book_id."}
        status = self.db.reserve(self._member()["id"], book_id)
        if status == "no_copies":
            return {"error": "no_copies", "hint": "No copy is on the shelf. Tell the member; do not retry."}
        return {"book_id": book_id, "title": book["title"], "status": status}

    def notify_member(self, message: str) -> dict:
        """Send the current member a short text message. CHANGES DATA: a message goes out.

        Use to confirm something that just happened, such as a reservation. The same message on the
        same day is sent only once. Never use it to answer a question; reply in the chat instead.

        Args:
            message: 1 to 160 characters.

        Returns:
            {"notification_id", "status": "queued", "duplicate": bool}.
        """
        if not message.strip() or len(message) > 160:
            return {"error": "invalid_message", "hint": "message must be 1 to 160 characters."}
        key = notification_dedupe_key(self.roll_no, message, self.clock().date())
        notification_id, created = self.db.record_notification(self.roll_no, message, key)
        return {"notification_id": notification_id, "status": "queued", "duplicate": not created}
