"""Part 3 — side effects that are safe to repeat even with a NEW key."""
from datetime import date

from app.idempotency import notification_dedupe_key
from app.placement_db import PlacementDb
from app.providers import booking_mock
from app.tools.placement_tools import PlacementTools
from app.worker import Worker


# ---------- apply_to_drive: a conflict is a success

def test_duplicate_application_returns_the_same_one(placement):
    assert placement.create_application(1, 1) == (1, True)
    assert placement.create_application(1, 1) == (1, False)
    assert placement.count("application") == 1


def test_applying_twice_is_not_an_error(tools):
    first, second = tools.apply_to_drive("22CS045", 1), tools.apply_to_drive("22CS045", 1)
    assert first["status"] == second["status"] == "applied"
    assert first["application_id"] == second["application_id"]
    assert (first["already_applied"], second["already_applied"]) == (False, True)


# ---------- book_interview_slot: optimistic locking

def test_claim_needs_the_version_you_read(placement):
    assert placement.claim_slot(1, 1, expected_version=5) is False
    assert placement.claim_slot(1, 1, expected_version=0) is True
    assert placement.slot_version(1) == 1


def test_stale_version_loses_even_if_the_slot_is_free_again(placement):
    placement.claim_slot(1, 1, 0)
    placement.conn.execute("UPDATE interview_slot SET student_id = NULL WHERE id = 1")   # freed, version is now 1
    assert placement.claim_slot(1, 2, expected_version=0) is False
    assert placement.claim_slot(1, 2, expected_version=1) is True


def test_booking_the_same_slot_twice_is_not_an_error(tools):
    tools.apply_to_drive("22CS045", 1)
    first, second = tools.book_interview_slot("22CS045", 1), tools.book_interview_slot("22CS045", 1)
    assert first["status"] == second["status"] == "booked"
    assert (first["already_booked"], second["already_booked"]) == (False, True)


def test_losing_the_race_is_a_normal_outcome(tools):
    tools.apply_to_drive("22IT017", 2)
    tools.apply_to_drive("22CS045", 2)
    assert tools.book_interview_slot("22IT017", 3)["status"] == "booked"
    lost = tools.book_interview_slot("22CS045", 3)
    assert lost["error"] == "slot_taken" and lost["available_slots"] == []


# ---------- notify_student: deduplicated

def test_dedupe_key_ignores_spacing_but_not_the_day():
    today, tomorrow = date(2026, 9, 17), date(2026, 9, 18)
    assert notification_dedupe_key("22CS045", "Zoho  closes Friday", today) == \
        notification_dedupe_key("22CS045", " Zoho closes Friday ", today)
    assert notification_dedupe_key("22CS045", "Zoho closes Friday", today) != \
        notification_dedupe_key("22CS045", "Zoho closes Friday", tomorrow)
    assert notification_dedupe_key("22CS045", "a", today) != notification_dedupe_key("22IT017", "a", today)


def test_record_notification_dedupes(placement):
    assert placement.record_notification("22CS045", "hi", "k") == (1, True)
    assert placement.record_notification("22CS045", "hi", "k") == (1, False)
    assert placement.count("notification") == 1


def test_the_same_message_twice_is_sent_once(tools, placement):
    first = tools.notify_student("22CS045", "Your Zoho slot is booked.")
    second = tools.notify_student("22CS045", "Your Zoho slot is booked.")
    other = tools.notify_student("22CS045", "TCS closes Friday.")
    assert first["notification_id"] == second["notification_id"] != other["notification_id"]
    assert (first["duplicate"], second["duplicate"]) == (False, True)
    assert placement.count("notification") == 2


# ---------- the whole question asked twice: new run, new keys, still one of each

def test_asking_twice_still_gives_one_of_each(store, placement):
    t = store.create_thread("22CS045")
    for _ in range(2):
        store.enqueue(t, "Apply me to Zoho, book slot 1 and text me", "mock")
        Worker(store, placement, booking_mock(), worker_id="w").run_until_idle()
    booked = placement.conn.execute("SELECT count(*) FROM interview_slot WHERE student_id IS NOT NULL").fetchone()[0]
    assert (placement.count("application"), booked, placement.count("notification")) == (1, 1, 1)
    assert placement.count("idempotency") == 6          # two runs, three side effects each


def test_two_connections_race_for_one_slot(tmp_path):
    path = str(tmp_path / "placement.db")
    PlacementDb(path).migrate()
    a, b = PlacementTools(PlacementDb(path)), PlacementTools(PlacementDb(path))
    a.apply_to_drive("22IT017", 2)
    b.apply_to_drive("22CS045", 2)
    results = [a.book_interview_slot("22IT017", 3), b.book_interview_slot("22CS045", 3)]
    assert sorted(r.get("status", r.get("error")) for r in results) == ["booked", "slot_taken"]
