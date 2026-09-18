"""The college's placement data, held in memory. (Given.)

In production this is the placement cell's own database. The agent never owns it: it reads and
writes it only through these methods. The agent's memory lives somewhere else (Part 3).
"""
from datetime import datetime, timedelta, timezone

from app.domain import AlreadyApplied, Drive, Rule, Slot, Student


class InMemoryPlacementRepo:
    def __init__(self, now: datetime | None = None):
        now = now or datetime.now(timezone.utc)
        self.students = {s.roll_no: s for s in [
            Student(1, "22CS045", "Priya Raman", "CSE", 8.4, 0, 2026),
            Student(2, "22IT017", "Arjun Kumar", "IT", 6.8, 1, 2026),
            Student(3, "22EC031", "Divya Sekar", "ECE", 7.2, 2, 2026),
            Student(4, "22ME008", "Karthik Murugan", "MECH", 7.9, 0, 2026),
        ]}
        self.drives = {d.id: d for d in [
            Drive(1, "Zoho", "Member Technical Staff", 8.4, now + timedelta(days=30), "open"),
            Drive(2, "TCS", "Ninja", 3.6, now + timedelta(days=21), "open"),
            Drive(3, "Freshworks", "Software Engineer I", 12.0, now - timedelta(days=2), "closed"),
        ]}
        self.rules = [
            Rule(1, 1, "cgpa", ">=", "7.0"), Rule(2, 1, "backlogs", "<=", "0"),
            Rule(3, 1, "branch", "in", "CSE,IT,ECE"), Rule(4, 1, "grad_year", "==", "2026"),
            Rule(5, 2, "cgpa", ">=", "6.0"), Rule(6, 2, "backlogs", "<=", "1"),
            Rule(7, 2, "grad_year", "==", "2026"),
            Rule(8, 3, "cgpa", ">=", "8.0"), Rule(9, 3, "backlogs", "<=", "0"),
            Rule(10, 3, "branch", "in", "CSE,IT"),
        ]
        self.slots = {s.id: s for s in [
            Slot(1, 1, now + timedelta(days=35), None),
            Slot(2, 1, now + timedelta(days=35, hours=1), None),
            Slot(3, 2, now + timedelta(days=25), None),
        ]}
        self._applications: dict[tuple[int, int], dict] = {}

    # ---- students and drives

    def get_student(self, roll_no: str) -> Student | None:
        return self.students.get(roll_no)

    def get_drive(self, drive_id: int) -> Drive | None:
        return self.drives.get(drive_id)

    def list_open_drives(self, now: datetime) -> list[Drive]:
        """Drives with status open and a deadline after `now`, soonest deadline first."""
        return sorted((d for d in self.drives.values() if d.status == "open" and d.deadline > now),
                      key=lambda d: d.deadline)

    def rules_for_drive(self, drive_id: int) -> list[Rule]:
        return [r for r in self.rules if r.drive_id == drive_id]

    # ---- applications

    def create_application(self, student_id: int, drive_id: int) -> int:
        """Raises AlreadyApplied if this student already applied to this drive."""
        if (student_id, drive_id) in self._applications:
            raise AlreadyApplied()
        application_id = len(self._applications) + 1
        self._applications[(student_id, drive_id)] = {
            "application_id": application_id, "status": "applied",
            "created_at": datetime.now(timezone.utc)}
        return application_id

    def has_application(self, student_id: int, drive_id: int) -> bool:
        return (student_id, drive_id) in self._applications

    def list_applications(self, student_id: int) -> list[dict]:
        """Oldest first: application_id, drive_id, company, role, status, created_at, interview_at."""
        out = []
        for (sid, drive_id), app in sorted(self._applications.items(), key=lambda kv: kv[1]["application_id"]):
            if sid != student_id:
                continue
            d = self.drives[drive_id]
            slot = next((s for s in self.slots.values() if s.drive_id == drive_id and s.student_id == sid), None)
            out.append({"application_id": app["application_id"], "drive_id": drive_id, "company": d.company,
                        "role": d.role, "status": app["status"], "created_at": app["created_at"],
                        "interview_at": slot.starts_at if slot else None})
        return out

    # ---- interview slots

    def get_slot(self, slot_id: int) -> Slot | None:
        return self.slots.get(slot_id)

    def free_slots(self, drive_id: int) -> list[Slot]:
        """Unbooked slots for the drive, earliest first."""
        return sorted((s for s in self.slots.values() if s.drive_id == drive_id and s.student_id is None),
                      key=lambda s: s.starts_at)

    def claim_slot(self, slot_id: int, student_id: int) -> bool:
        """Book the slot if it is still free. True if this call booked it, False if it was already taken."""
        s = self.slots[slot_id]
        if s.student_id is not None:
            return False
        self.slots[slot_id] = Slot(s.id, s.drive_id, s.starts_at, student_id)
        return True
