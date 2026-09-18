"""Stretch — structured output: a typed verdict, validation failure as feedback."""
import json

import pytest
from pydantic import ValidationError

from app.verdict import EligibilityVerdict, VerdictInvalid, structured_verdict

GOOD = {"student_id": "22IT017", "drive_id": 1, "eligible": False,
        "failed_rules": [{"rule_id": 1, "rule": "cgpa >= 7.0", "actual": 6.8}],
        "summary": "CGPA 6.8 is below the 7.0 cutoff."}


def test_valid_verdict_parses():
    assert EligibilityVerdict.model_validate(GOOD).eligible is False


def test_eligible_must_agree_with_failed_rules():
    with pytest.raises(ValidationError, match="contradicts"):
        EligibilityVerdict.model_validate({**GOOD, "eligible": True})


def test_roll_number_format_is_enforced():
    with pytest.raises(ValidationError):
        EligibilityVerdict.model_validate({**GOOD, "student_id": "Arjun"})


class FakeModel:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.seen: list[list[str]] = []

    def __call__(self, messages):
        self.seen.append(messages)
        return self.replies.pop(0)


def test_first_reply_valid_means_one_call():
    model = FakeModel(json.dumps(GOOD))
    verdict = structured_verdict(model, "prompt")
    assert verdict.drive_id == 1 and len(model.seen) == 1


def test_markdown_fences_are_tolerated():
    model = FakeModel("```json\n" + json.dumps(GOOD) + "\n```")
    assert (structured_verdict(model, "prompt")).student_id == "22IT017"


def test_validation_errors_are_fed_back():
    model = FakeModel(json.dumps({**GOOD, "eligible": True}), json.dumps(GOOD))
    verdict = structured_verdict(model, "prompt")
    assert verdict.eligible is False
    assert len(model.seen) == 2
    feedback = model.seen[1][-1]
    assert "failed validation" in feedback and "contradicts" in feedback


def test_gives_up_after_max_retries():
    model = FakeModel("not json", "still not json", "{}", "unused")
    with pytest.raises(VerdictInvalid):
        structured_verdict(model, "prompt", max_retries=2)
    assert len(model.seen) == 3
