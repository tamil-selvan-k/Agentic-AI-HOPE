from collections.abc import Callable

from pydantic import BaseModel, Field, ValidationError, model_validator


class FailedRule(BaseModel):
    rule_id: int
    rule: str
    actual: str | float


class EligibilityVerdict(BaseModel):
    student_id: str = Field(pattern=r"^\d{2}[A-Z]{2}\d{3}$")
    drive_id: int
    eligible: bool
    failed_rules: list[FailedRule]
    summary: str = Field(min_length=1, max_length=280)

    @model_validator(mode="after")
    def eligible_agrees_with_failed_rules(self) -> "EligibilityVerdict":
        if self.eligible and self.failed_rules:
            raise ValueError("eligible contradicts failed_rules: cannot be True when there are failed rules")
        return self


class VerdictInvalid(Exception):
    def __init__(self, attempts: int, last_errors: list):
        super().__init__(f"no valid verdict after {attempts} attempts")
        self.attempts = attempts
        self.last_errors = last_errors


Generate = Callable[[list[str]], str]


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        t = t.rsplit("```", 1)[0]
    return t.strip()


def structured_verdict(generate: Generate, prompt: str, max_retries: int = 2) -> EligibilityVerdict:
    """Ask the model for an EligibilityVerdict; feed validation errors back; give up after max_retries."""
    messages = [prompt]
    last_errors: list = []
    for attempt in range(1 + max_retries):
        raw = generate(messages)
        try:
            return EligibilityVerdict.model_validate_json(_strip_fences(raw))
        except Exception as e:
            last_errors = e.errors() if isinstance(e, ValidationError) else [str(e)]
            if attempt < max_retries:
                messages.append(raw)
                messages.append(f"The response failed validation: {e}")
    raise VerdictInvalid(1 + max_retries, last_errors)
