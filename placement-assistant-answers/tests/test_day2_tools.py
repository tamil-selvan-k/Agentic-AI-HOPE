"""The Day 2 tools, now on placement.db. (Given. These pass from the start; keep them green.)"""
import inspect

import pytest

from app.tools.placement_tools import PlacementTools


@pytest.mark.parametrize("name", PlacementTools.TOOL_NAMES)
def test_every_tool_is_described(name):
    doc = inspect.getdoc(getattr(PlacementTools, name)) or ""
    assert len(doc) >= 150 and "TODO" not in doc


def test_open_drives(tools):
    assert [d["drive_id"] for d in tools.list_open_drives()["drives"]] == [2, 1]
    assert [d["drive_id"] for d in tools.list_open_drives(branch="MECH")["drives"]] == [2]


def test_student(tools):
    assert tools.get_student("22CS045")["name"] == "Priya Raman"
    assert tools.get_student("99XX999")["error"] == "unknown_student"


@pytest.mark.parametrize("roll, drive, failed_ids", [("22CS045", 1, []), ("22IT017", 1, [1, 2]), ("22ME008", 1, [3])])
def test_eligibility(tools, roll, drive, failed_ids):
    assert [f["rule_id"] for f in tools.check_eligibility(roll, drive)["failed_rules"]] == failed_ids


def test_apply_checks_still_run_in_order(tools):
    assert tools.apply_to_drive("22CS045", 3)["error"] == "drive_closed"
    assert tools.apply_to_drive("22IT017", 1)["error"] == "not_eligible"


def test_booking_needs_an_application(tools):
    assert tools.book_interview_slot("22CS045", 1)["error"] == "no_application"


def test_my_applications(tools):
    tools.apply_to_drive("22CS045", 2)
    assert [a["drive_id"] for a in tools.list_my_applications("22CS045")["applications"]] == [2]
