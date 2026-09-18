"""Stretch — design a tool of your own: list_my_applications.

Skipped until PlacementTools has a list_my_applications method.
The repository method it needs, list_applications, is already given.
"""
import inspect

import pytest

from app.tools.placement_tools import PlacementTools

pytestmark = pytest.mark.skipif(
    not hasattr(PlacementTools, "list_my_applications"),
    reason="stretch: add list_my_applications to PlacementTools",
)

FIELDS = {"application_id", "drive_id", "company", "role", "status", "applied_on", "interview_at"}


def test_registered_and_described():
    assert "list_my_applications" in PlacementTools.READ_ONLY
    doc = inspect.getdoc(PlacementTools.list_my_applications) or ""
    assert len(doc) >= 150 and "TODO" not in doc
    assert "Read-only" in doc and "student_id" in doc


def test_no_applications_yet(tools):
    assert tools.list_my_applications("22CS045") == {"applications": []}


def test_lists_applications_oldest_first_with_booked_slot(tools):
    tools.apply_to_drive("22CS045", 2)
    tools.apply_to_drive("22CS045", 1)
    tools.book_interview_slot("22CS045", 1)
    apps = (tools.list_my_applications("22CS045"))["applications"]
    assert [a["drive_id"] for a in apps] == [2, 1]
    assert set(apps[0]) == FIELDS
    assert apps[0]["interview_at"] is None
    assert apps[1]["company"] == "Zoho" and apps[1]["interview_at"] is not None


def test_only_the_students_own_applications(tools):
    tools.apply_to_drive("22IT017", 2)
    assert (tools.list_my_applications("22CS045"))["applications"] == []


def test_unknown_student(tools):
    assert (tools.list_my_applications("99XX999"))["error"] == "unknown_student"
