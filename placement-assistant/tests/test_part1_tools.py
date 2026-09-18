"""Part 1 — the five tools: two samples (given) and your TODO 1–3."""
import inspect

import pytest

from app.tools.placement_tools import PlacementTools

PART1_TOOLS = ["list_open_drives", "get_student", "check_eligibility", "apply_to_drive", "book_interview_slot"]


# ---------- descriptions (block B rules, checked mechanically)

@pytest.mark.parametrize("name", PART1_TOOLS)
def test_every_tool_has_a_real_description(name):
    fn = getattr(PlacementTools, name)
    doc = inspect.getdoc(fn) or ""
    assert len(doc) >= 150, f"{name}: description is too thin to steer a model"
    assert "TODO" not in doc, f"{name}: description still has a TODO"
    for param in list(inspect.signature(fn).parameters)[1:]:
        assert param in doc, f"{name}: parameter {param!r} is not described"


@pytest.mark.parametrize("name", [n for n in PlacementTools.READ_ONLY if n in PART1_TOOLS])
def test_read_only_tools_say_so(name):
    doc = inspect.getdoc(getattr(PlacementTools, name)) or ""
    assert "Read-only" in doc and "TODO" not in doc


@pytest.mark.parametrize("name", [n for n in PlacementTools.SIDE_EFFECTS if n in PART1_TOOLS])
def test_side_effect_tools_say_so(name):
    doc = inspect.getdoc(getattr(PlacementTools, name)) or ""
    assert "Side effect:" in doc and "TODO" not in doc


# ---------- list_open_drives

def test_open_drives_soonest_deadline_first(tools):
    result = tools.list_open_drives()
    assert [d["drive_id"] for d in result["drives"]] == [2, 1]
    first = result["drives"][0]
    assert set(first) == {"drive_id", "company", "role", "ctc_lpa", "deadline"}
    assert first["company"] == "TCS"


def test_open_drives_filtered_by_branch_rule(tools):
    result = tools.list_open_drives(branch="MECH")
    assert [d["drive_id"] for d in result["drives"]] == [2]


def test_open_drives_filtered_by_grad_year(tools):
    assert (tools.list_open_drives(grad_year=2025))["drives"] == []


# ---------- get_student

def test_get_student(tools):
    assert tools.get_student("22CS045") == {
        "student_id": "22CS045", "name": "Priya Raman", "branch": "CSE",
        "cgpa": 8.4, "backlogs": 0, "grad_year": 2026,
    }


def test_unknown_student_returns_an_instruction(tools):
    result = tools.get_student("99XX999")
    assert result["error"] == "unknown_student"
    assert "roll number" in result["hint"]


# ---------- check_eligibility

@pytest.mark.parametrize("roll, drive, failed_ids", [
    ("22CS045", 1, []),
    ("22IT017", 1, [1, 2]),
    ("22IT017", 2, []),
    ("22EC031", 1, [2]),
    ("22EC031", 2, [6]),
    ("22ME008", 1, [3]),
])
def test_check_eligibility(tools, roll, drive, failed_ids):
    result = tools.check_eligibility(roll, drive)
    assert result["student_id"] == roll and result["drive_id"] == drive
    assert result["eligible"] is (not failed_ids)
    assert [f["rule_id"] for f in result["failed_rules"]] == failed_ids


def test_failed_rule_carries_the_actual_value(tools):
    result = tools.check_eligibility("22IT017", 1)
    assert result["failed_rules"][0] == {"rule_id": 1, "rule": "cgpa >= 7.0", "actual": 6.8}


def test_check_eligibility_unknown_drive(tools):
    assert (tools.check_eligibility("22CS045", 99))["error"] == "unknown_drive"


# ---------- apply_to_drive

def test_apply_returns_what_the_next_step_needs(tools):
    result = tools.apply_to_drive("22CS045", 1)
    assert result["status"] == "applied"
    assert isinstance(result["application_id"], int)
    assert [s["slot_id"] for s in result["available_slots"]] == [1, 2]


def test_apply_rechecks_eligibility(tools):
    result = tools.apply_to_drive("22IT017", 1)
    assert result["error"] == "not_eligible"
    assert [f["rule_id"] for f in result["failed_rules"]] == [1, 2]


def test_apply_to_closed_drive(tools):
    assert (tools.apply_to_drive("22CS045", 3))["error"] == "drive_closed"


def test_apply_twice(tools):
    tools.apply_to_drive("22CS045", 1)
    assert (tools.apply_to_drive("22CS045", 1))["error"] == "already_applied"


# ---------- book_interview_slot

def test_book_slot(tools):
    tools.apply_to_drive("22CS045", 1)
    result = tools.book_interview_slot("22CS045", 1)
    assert result["status"] == "booked" and result["slot_id"] == 1 and result["drive_id"] == 1


def test_book_slot_needs_an_application(tools):
    assert (tools.book_interview_slot("22CS045", 1))["error"] == "no_application"


def test_losing_the_race_for_the_last_slot(tools):
    tools.apply_to_drive("22IT017", 2)
    tools.apply_to_drive("22CS045", 2)
    assert (tools.book_interview_slot("22IT017", 3))["status"] == "booked"
    result = tools.book_interview_slot("22CS045", 3)
    assert result["error"] == "slot_taken"
    assert result["available_slots"] == []


def test_slot_taken_lists_the_remaining_slots(tools):
    tools.apply_to_drive("22CS045", 1)
    tools.book_interview_slot("22CS045", 1)
    result = tools.book_interview_slot("22CS045", 1)
    assert result["error"] == "slot_taken"
    assert [s["slot_id"] for s in result["available_slots"]] == [2]


# ---------- dispatch (given code, tested so you can trust it)

def test_dispatch_coerces_float_ids(tools):
    result = tools.call("check_eligibility", {"student_id": "22CS045", "drive_id": 1.0})
    assert result["eligible"] is True


def test_dispatch_rejects_a_company_name_as_id(tools):
    result = tools.call("check_eligibility", {"student_id": "22CS045", "drive_id": "Zoho"})
    assert result["error"] == "invalid_arguments"


def test_dispatch_unknown_tool(tools):
    assert (tools.call("delete_student", {}))["error"] == "unknown_tool"
