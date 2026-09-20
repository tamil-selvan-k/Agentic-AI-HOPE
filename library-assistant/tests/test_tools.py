"""Day 2 + Day 3: the tools, the rules in data, and writes that are safe to repeat."""
import inspect

import pytest

from app.tools.library_tools import CatalogueTools, DeskTools


@pytest.mark.parametrize("cls", [CatalogueTools, DeskTools])
def test_every_tool_is_described(cls):
    for name in cls.TOOL_NAMES:
        assert len(inspect.getdoc(getattr(cls, name)) or "") >= 120, name


def test_search_and_availability(db):
    books = CatalogueTools(db).search_books("kleppmann")["books"]
    assert [b["book_id"] for b in books] == [2] and books[0]["copies_available"] == 1
    assert CatalogueTools(db).search_books("  ")["error"] == "empty_query"


def test_policy_comes_from_the_database(db):
    arjun = DeskTools(db, "22IT017")
    assert arjun.check_can_borrow() == {"can_borrow": False, "reasons": ["fine due Rs 150 is above the Rs 100 limit"]}
    db.conn.execute("UPDATE policy SET value = 200 WHERE name = 'max_fine_to_borrow'")
    assert arjun.check_can_borrow()["can_borrow"] is True


def test_loan_limit(db):
    assert DeskTools(db, "22EC031").check_can_borrow()["reasons"] == ["already holds 1 of 1 allowed reservations"]


def test_reserve_refuses_when_policy_says_no_even_if_the_model_skips_the_check(db):
    assert DeskTools(db, "22IT017").reserve_book(1)["error"] == "not_allowed"
    assert db.count("reservation") == 1


def test_reserving_twice_is_not_an_error(db):
    desk = DeskTools(db, "22CS045")
    assert desk.reserve_book(2)["status"] == "reserved"
    assert desk.reserve_book(2)["status"] == "already_reserved"
    assert db.get_book(2)["copies_available"] == 0


def test_last_copy_goes_to_one_member(db):
    assert DeskTools(db, "22CS045").reserve_book(2)["status"] == "reserved"
    db.conn.execute("UPDATE member SET max_loans = 3 WHERE roll_no = '22EC031'")
    assert DeskTools(db, "22EC031").reserve_book(2)["error"] == "no_copies"


def test_same_text_same_day_is_sent_once(db):
    desk = DeskTools(db, "22CS045")
    first, second = desk.notify_member("Reserved."), desk.notify_member("Reserved.")
    assert first["notification_id"] == second["notification_id"] and second["duplicate"] is True


def test_the_desk_cannot_act_for_another_member(db):
    params = {n: list(inspect.signature(getattr(DeskTools, n)).parameters) for n in DeskTools.TOOL_NAMES}
    assert all("roll_no" not in p for p in params.values())
