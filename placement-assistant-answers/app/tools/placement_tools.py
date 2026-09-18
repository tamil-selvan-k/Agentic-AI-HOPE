import operator
from datetime import datetime, timezone

from app.domain import Rule, Student
from app.idempotency import notification_dedupe_key
from app.placement_db import PlacementDb
from app.tools.dispatch import dispatch

OPS = {
    ">=": operator.ge,
    "<=": operator.le,
    "==": operator.eq,
    "in": lambda actual, allowed: actual in allowed.split(","),
}


def _passes(rule: Rule, student_value) -> bool:
    return OPS[rule.op](student_value, rule.typed_value())


def _unknown_student(roll_no: str) -> dict:
    return {"error": "unknown_student",
            "hint": f"No student with roll number {roll_no!r}. Ask the user for their roll number, e.g. 22CS045."}


def _unknown_drive(drive_id: int) -> dict:
    return {"error": "unknown_drive",
            "hint": f"No drive with id {drive_id}. Call list_open_drives to get valid ids."}


class PlacementTools:
    """Every method named in TOOL_NAMES is exposed to the model. Its docstring IS the prompt."""

    READ_ONLY = ("list_open_drives", "get_student", "check_eligibility", "list_my_applications")
    SIDE_EFFECTS = ("apply_to_drive", "book_interview_slot", "notify_student")
    TOOL_NAMES = READ_ONLY + SIDE_EFFECTS

    def __init__(self, repo: PlacementDb, clock=lambda: datetime.now(timezone.utc)):
        self.repo = repo
        self.clock = clock

    def functions(self) -> dict:
        return {name: getattr(self, name) for name in self.TOOL_NAMES}

    def call(self, name: str, args: dict) -> dict:
        return dispatch(self.functions(), name, args)

    # ------------------------------------------------------------------ read-only

    def list_open_drives(self, branch: str | None = None, grad_year: int | None = None) -> dict:
        """List placement drives that are accepting applications right now, soonest deadline first.

        Use when the user asks which companies are coming, what drives are open, or what they
        could apply to. Do NOT use to decide whether a specific student is eligible for a
        specific drive; use check_eligibility for that. Read-only: changes nothing.

        Args:
            branch: Optional. Branch code such as "CSE", "IT", "ECE" or "MECH". Drives whose
                branch rule excludes this branch are left out.
            grad_year: Optional. Four-digit graduation year, e.g. 2026. Drives restricted to a
                different year are left out.

        Returns:
            {"drives": [{"drive_id", "company", "role", "ctc_lpa", "deadline"}]}. Use drive_id
            with check_eligibility and apply_to_drive.
        """
        filters = {"branch": branch, "grad_year": grad_year}
        drives = []
        for d in self.repo.list_open_drives(self.clock()):
            rules = self.repo.rules_for_drive(d.id)
            if any(r.field in filters and filters[r.field] is not None
                   and not _passes(r, filters[r.field]) for r in rules):
                continue
            drives.append({"drive_id": d.id, "company": d.company, "role": d.role,
                           "ctc_lpa": d.ctc_lpa, "deadline": d.deadline.date().isoformat()})
        return {"drives": drives}

    def get_student(self, student_id: str) -> dict:
        """Fetch the placement record for one student: name, branch, CGPA, backlogs, graduation year.

        Use when the user asks what is on record for them ("what's my CGPA", "how many backlogs
        do I have"). Do NOT use to check eligibility; check_eligibility reads the record itself.
        Read-only: changes nothing.

        Args:
            student_id: Roll number, two digits, two capital letters, three digits, e.g. "22CS045".

        Returns:
            {"student_id", "name", "branch", "cgpa", "backlogs", "grad_year"}
        """
        s = self.repo.get_student(student_id)
        if s is None:
            return _unknown_student(student_id)
        return {"student_id": s.roll_no, "name": s.name, "branch": s.branch,
                "cgpa": s.cgpa, "backlogs": s.backlogs, "grad_year": s.grad_year}

    def _evaluate(self, s: Student, drive_id: int) -> list[dict]:
        failed = []
        for rule in self.repo.rules_for_drive(drive_id):
            actual = getattr(s, rule.field)
            if not _passes(rule, actual):
                failed.append({"rule_id": rule.id, "rule": str(rule), "actual": actual})
        return failed

    def check_eligibility(self, student_id: str, drive_id: int) -> dict:
        """Decide whether ONE student may apply to ONE drive, using the drive's eligibility rules.

        Use before apply_to_drive, or when the user asks "can I apply", "am I eligible for
        <company>", or "why can't I apply". Do NOT use to find drives; use list_open_drives.
        Read-only: changes nothing.

        Args:
            student_id: Roll number, e.g. "22CS045".
            drive_id: Integer id returned by list_open_drives. Never a company name.

        Returns:
            {"student_id", "drive_id", "eligible", "failed_rules": [{"rule_id", "rule", "actual"}]}.
            Explain every failed rule to the user; do not invent rules that are not listed.
        """
        s = self.repo.get_student(student_id)
        if s is None:
            return _unknown_student(student_id)
        if self.repo.get_drive(drive_id) is None:
            return _unknown_drive(drive_id)
        failed = self._evaluate(s, drive_id)
        return {"student_id": s.roll_no, "drive_id": drive_id,
                "eligible": not failed, "failed_rules": failed}

    # ------------------------------------------------------------------ side effects

    def apply_to_drive(self, student_id: str, drive_id: int) -> dict:
        """Submit a placement application for ONE student to ONE drive.

        Side effect: creates an application record the placement cell will act on. Call it only
        when the user clearly asks to apply or register ("apply me", "sign me up"), never to
        check or explore. Eligibility is re-checked here, but call check_eligibility first so
        you can explain the result.

        Args:
            student_id: Roll number, e.g. "22CS045".
            drive_id: Integer id returned by list_open_drives.

        Returns:
            {"application_id", "student_id", "drive_id", "status": "applied", "already_applied",
             "available_slots": [{"slot_id", "starts_at"}]}. Calling it again for the same drive is
            safe and returns the same application. Offer the slots; book one only when they choose.
        """
        s = self.repo.get_student(student_id)
        if s is None:
            return _unknown_student(student_id)
        d = self.repo.get_drive(drive_id)
        if d is None:
            return _unknown_drive(drive_id)
        if d.status != "open" or d.deadline <= self.clock():
            return {"error": "drive_closed",
                    "hint": f"{d.company} is not accepting applications. Call list_open_drives for open ones."}
        failed = self._evaluate(s, drive_id)
        if failed:
            return {"error": "not_eligible", "failed_rules": failed,
                    "hint": "Explain the failed rules to the user. Do not retry."}
        # Day 3: a duplicate application is a success. Asking twice must not be an error.
        application_id, created = self.repo.create_application(s.id, drive_id)
        slots = self.repo.free_slots(drive_id)
        return {"application_id": application_id, "student_id": s.roll_no, "drive_id": drive_id,
                "status": "applied", "already_applied": not created,
                "available_slots": [{"slot_id": sl.id, "starts_at": sl.starts_at.isoformat()} for sl in slots]}

    def book_interview_slot(self, student_id: str, slot_id: int) -> dict:
        """Book one interview slot for a student who has already applied to that slot's drive.

        Side effect: reserves the slot so no other student can take it. Call it only after the
        user has picked a specific slot. Slot ids come from the available_slots returned by
        apply_to_drive.

        Args:
            student_id: Roll number, e.g. "22CS045".
            slot_id: Integer slot id from available_slots.

        Returns:
            {"slot_id", "drive_id", "starts_at", "status": "booked"}. If the slot was taken,
            the error lists other free slots; ask the user to choose again.
        """
        s = self.repo.get_student(student_id)
        if s is None:
            return _unknown_student(student_id)
        slot = self.repo.get_slot(slot_id)
        if slot is None:
            return {"error": "unknown_slot",
                    "hint": "Use a slot_id from available_slots returned by apply_to_drive."}
        if not self.repo.has_application(s.id, slot.drive_id):
            return {"error": "no_application",
                    "hint": f"The student must apply to drive {slot.drive_id} before booking a slot."}
        booked = {"slot_id": slot.id, "drive_id": slot.drive_id, "starts_at": slot.starts_at.isoformat(), "status": "booked"}
        if slot.student_id == s.id:
            return {**booked, "already_booked": True}          # asking twice is not an error
        version = self.repo.slot_version(slot_id)
        if slot.student_id is not None or not self.repo.claim_slot(slot_id, s.id, version):
            others = self.repo.free_slots(slot.drive_id)
            return {"error": "slot_taken",
                    "available_slots": [{"slot_id": o.id, "starts_at": o.starts_at.isoformat()} for o in others],
                    "hint": "Another student booked this slot. Ask the user to pick one of available_slots."}
        return {**booked, "already_booked": False}

    def notify_student(self, student_id: str, message: str) -> dict:
        """Send a short reminder or notice to a student by SMS and email.

        Side effect: a real message reaches the student's phone. Use ONLY when the user
        explicitly asks to be reminded, notified or messaged ("remind me", "text me", "send me
        a reminder"). Do NOT use to answer a question, even about deadlines or results; answer
        in the reply instead.

        Args:
            student_id: Roll number, e.g. "22CS045".
            message: The notice itself, plain text, at most 160 characters.

        Returns:
            {"notification_id", "status": "queued", "duplicate"}. The same message to the same
            student on the same day is sent once.
        """
        if self.repo.get_student(student_id) is None:
            return _unknown_student(student_id)
        if not message.strip() or len(message) > 160:
            return {"error": "invalid_message", "hint": "message must be 1 to 160 characters."}
        key = notification_dedupe_key(student_id, message, self.clock().date())
        notification_id, created = self.repo.record_notification(student_id, message, key)
        return {"notification_id": notification_id, "status": "queued", "duplicate": not created}

    # ------------------------------------------------------------------ read-only (Day 2 stretch)

    def list_my_applications(self, student_id: str) -> dict:
        """List the placement applications one student has already submitted, oldest first,
        with the interview slot they booked for each, if any.

        Use when the user asks "where have I applied", "did my application go through" or
        "when is my interview". Do NOT use to find new drives; use list_open_drives.
        Read-only: changes nothing.

        Args:
            student_id: Roll number, e.g. "22CS045".

        Returns:
            {"applications": [{"application_id", "drive_id", "company", "role", "status",
            "applied_on", "interview_at"}]}. interview_at is null until a slot is booked; offer
            book_interview_slot in that case.
        """
        s = self.repo.get_student(student_id)
        if s is None:
            return _unknown_student(student_id)
        return {"applications": [
            {"application_id": a["application_id"], "drive_id": a["drive_id"], "company": a["company"],
             "role": a["role"], "status": a["status"], "applied_on": a["created_at"].date().isoformat(),
             "interview_at": a["interview_at"].isoformat() if a["interview_at"] else None}
            for a in self.repo.list_applications(s.id)
        ]}
