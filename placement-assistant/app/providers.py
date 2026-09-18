"""Model providers. The agent only knows `generate`. (Given.)"""
from dataclasses import dataclass, field
from typing import Any


class AgentError(Exception):
    """A run could not finish. `retryable` says whether trying again later could work."""

    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable


@dataclass
class ToolCall:
    name: str
    args: dict


@dataclass
class ModelTurn:
    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    raw: Any = None     # provider-native content, sent back as-is (keeps Gemini's thought signatures)


# `contents` is a plain list the agent builds up:
#   {"role": "user",  "text": str}
#   {"role": "model", "text": str | None, "tool_calls": [{"name", "args"}], "raw": ...}
#   {"role": "tool",  "name": str, "result": dict}


class GeminiProvider:
    def __init__(self, model: str):
        from google import genai

        self.client = genai.Client()        # reads GEMINI_API_KEY
        self.model = model

    def _to_gemini(self, contents: list[dict]):
        from google.genai import types

        out: list = []
        for c in contents:
            if c["role"] == "user":
                out.append(types.Content(role="user", parts=[types.Part.from_text(text=c["text"])]))
            elif c["role"] == "model":
                if c.get("raw") is not None:
                    out.append(c["raw"])
                    continue
                parts = [types.Part.from_text(text=c["text"])] if c.get("text") else []
                parts += [types.Part.from_function_call(name=t["name"], args=t["args"])
                          for t in c.get("tool_calls", [])]
                out.append(types.Content(role="model", parts=parts))
            elif c["role"] == "tool":
                part = types.Part.from_function_response(name=c["name"], response=c["result"])
                # Results of parallel calls travel together in one turn.
                if out and out[-1].role == "user" and all(p.function_response for p in out[-1].parts):
                    out[-1].parts.append(part)
                else:
                    out.append(types.Content(role="user", parts=[part]))
        return out

    def generate(self, system: str, contents: list[dict], tools: list) -> ModelTurn:
        from google.genai import errors, types

        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=tools,
            temperature=0,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        try:
            resp = self.client.models.generate_content(
                model=self.model, contents=self._to_gemini(contents), config=config)
        except errors.APIError as e:
            if e.code == 429:
                raise AgentError("provider_rate_limited", "Model quota exhausted. Wait a minute.", True) from e
            if e.code and e.code >= 500:
                raise AgentError("provider_unavailable", "Model provider failed.", True) from e
            raise AgentError("provider_error", str(e), False) from e

        content = resp.candidates[0].content if resp.candidates else None
        parts = (content.parts or []) if content else []
        text = "".join(p.text for p in parts if p.text and not p.thought) or None
        calls = [ToolCall(fc.name, dict(fc.args or {})) for fc in (resp.function_calls or [])]
        usage = resp.usage_metadata
        return ModelTurn(text=text, tool_calls=calls,
                         tokens_in=(usage.prompt_token_count or 0) if usage else 0,
                         tokens_out=(usage.candidates_token_count or 0) if usage else 0,
                         raw=content)


class ScriptedProvider:
    """Replays a fixed list of turns. No network, no quota. Used by the tests and --mock."""

    model = "mock"

    def __init__(self, script: list, loop: bool = False):
        self.original, self.script, self.loop = list(script), list(script), loop
        self.calls: list[list[dict]] = []      # what the agent sent on each call

    def generate(self, system: str, contents: list[dict], tools: list) -> ModelTurn:
        self.calls.append([dict(c) for c in contents])
        if not self.script and self.loop:
            self.script = list(self.original)
        if not self.script:
            return ModelTurn(text="(mock) script exhausted")
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def default_mock() -> ScriptedProvider:
    """Calls check_eligibility, which is a given sample, so it works before you write any tools."""
    return ScriptedProvider([
        ModelTurn(text=None, tool_calls=[ToolCall("check_eligibility", {"student_id": "22CS045", "drive_id": 1})],
                  tokens_in=120, tokens_out=12),
        ModelTurn(text="(mock) Yes, you meet all four Zoho rules.", tokens_in=180, tokens_out=14),
    ], loop=True)
