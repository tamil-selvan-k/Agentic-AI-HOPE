"""Plain domain objects. Repositories return these; tools consume them."""
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Student:
    id: int
    roll_no: str
    name: str
    branch: str
    cgpa: float
    backlogs: int
    grad_year: int


@dataclass(frozen=True)
class Drive:
    id: int
    company: str
    role: str
    ctc_lpa: float
    deadline: datetime
    status: str


@dataclass(frozen=True)
class Rule:
    id: int
    drive_id: int
    field: str
    op: str
    value: str

    def typed_value(self):
        if self.field == "cgpa":
            return float(self.value)
        if self.field in ("backlogs", "grad_year"):
            return int(self.value)
        return self.value

    def __str__(self) -> str:
        return f"{self.field} {self.op} {self.value}"


@dataclass(frozen=True)
class Slot:
    id: int
    drive_id: int
    starts_at: datetime
    student_id: int | None


class AlreadyApplied(Exception):
    """Raised by a repository when (student, drive) already has an application."""
