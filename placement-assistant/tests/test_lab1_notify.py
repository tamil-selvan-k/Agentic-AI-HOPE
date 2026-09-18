"""Lab 1 — notify_student exists, is described, and does its one job."""
import inspect

from app.tools.placement_tools import PlacementTools


def test_notify_student_is_a_registered_side_effect_tool():
    assert "notify_student" in PlacementTools.SIDE_EFFECTS
    doc = inspect.getdoc(PlacementTools.notify_student) or ""
    assert len(doc) >= 150 and "TODO" not in doc
    assert "Side effect:" in doc
    assert "student_id" in doc and "message" in doc


def test_notify_student_sends_one_notification(tools, notifier):
    result = tools.notify_student("22CS045", "Zoho applications close on Friday.")
    assert result["status"] == "queued"
    assert notifier.sent == [{"id": result["notification_id"], "roll_no": "22CS045",
                              "message": "Zoho applications close on Friday."}]


def test_notify_student_rejects_long_messages(tools, notifier):
    result = tools.notify_student("22CS045", "x" * 161)
    assert result["error"] == "invalid_message"
    assert notifier.sent == []
