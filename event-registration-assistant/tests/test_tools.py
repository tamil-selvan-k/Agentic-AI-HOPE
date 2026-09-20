"""Day 2 + Day 3: the tools, the rules in data, and writes that are safe to repeat."""
import inspect

import pytest

from app.tools.event_tools import CatalogueTools, DeskTools


@pytest.mark.parametrize("cls", [CatalogueTools, DeskTools])
def test_every_tool_is_described(cls):
    for name in cls.TOOL_NAMES:
        assert len(inspect.getdoc(getattr(cls, name)) or "") >= 120, name


def test_search_and_availability(db):
    events = CatalogueTools(db).search_events("hackathon")["events"]
    assert len(events) >= 1
    assert CatalogueTools(db).search_events("  ")["error"] == "empty_query"


def test_student_authn(db):
    priya = DeskTools(db, "22CS045")
    assert priya.authenticate_student("pass123") == {"authenticated": True, "reg_num": "22CS045"}
    assert priya.authenticate_student("wrongpass") == {"authenticated": False, "reg_num": "22CS045"}


def test_policy_comes_from_the_database(db):
    arjun = DeskTools(db, "22IT017")
    assert arjun.check_can_register() == {"can_register": False, "reasons": ["already registered for 1 of 1 allowed events"]}
    db.conn.execute("UPDATE student SET max_registrations = 3 WHERE reg_num = '22IT017'")
    assert arjun.check_can_register()["can_register"] is True


def test_registration_limit(db):
    assert DeskTools(db, "22EC031").check_can_register()["reasons"] == ["already registered for 1 of 1 allowed events"]


def test_register_refuses_when_policy_says_no_even_if_the_model_skips_the_check(db):
    assert DeskTools(db, "22IT017").register_event(1)["error"] == "not_allowed"
    assert db.count("registration") == 2


def test_registering_twice_is_not_an_error(db):
    desk = DeskTools(db, "22CS045")
    assert desk.register_event(1)["status"] == "registered"
    assert desk.register_event(1)["status"] == "already_registered"


def test_unregister_event_auto_resolves_single_registration(db):
    arjun = DeskTools(db, "22IT017")
    # Arjun is registered for event 5 in seed data
    res = arjun.unregister_event()
    assert res["status"] == "unregistered" and res["event_id"] == 5
    assert db.get_event(5)["seats_available"] == 25


def test_unregister_when_not_registered(db):
    priya = DeskTools(db, "22CS045")
    assert priya.unregister_event()["error"] == "not_registered"


def test_last_seat_goes_to_one_student(db):
    assert DeskTools(db, "22CS045").register_event(2)["status"] == "registered"
    db.conn.execute("UPDATE student SET max_registrations = 3 WHERE reg_num = '22EC031'")
    assert DeskTools(db, "22EC031").register_event(2)["error"] == "no_seats"


def test_same_text_same_day_is_sent_once(db):
    desk = DeskTools(db, "22CS045")
    first, second = desk.notify_student("Registered."), desk.notify_student("Registered.")
    assert first["notification_id"] == second["notification_id"] and second["duplicate"] is True


def test_the_desk_cannot_act_for_another_student(db):
    params = {n: list(inspect.signature(getattr(DeskTools, n)).parameters) for n in DeskTools.TOOL_NAMES}
    assert all("reg_num" not in p and "roll_no" not in p for p in params.values())
