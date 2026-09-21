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
    """Gemini provider via LangChain (reads GOOGLE_API_KEY env var)."""

    def __init__(self, model: str):
        from langchain_google_genai import ChatGoogleGenerativeAI

        self.model = model
        self._llm = ChatGoogleGenerativeAI(model=model, temperature=0)

    def _to_messages(self, system: str, contents: list[dict]):
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

        messages = [SystemMessage(content=system)]
        pending_ids: list[str] = []
        tool_idx = 0

        for c in contents:
            if c["role"] == "user":
                messages.append(HumanMessage(content=c["text"]))
                pending_ids = []
                tool_idx = 0
            elif c["role"] == "model":
                calls = c.get("tool_calls", [])
                pending_ids = [f"call_{i}_{t['name']}" for i, t in enumerate(calls)]
                tool_idx = 0
                lc_calls = [
                    {"id": pending_ids[i], "name": t["name"], "args": t["args"], "type": "tool_call"}
                    for i, t in enumerate(calls)
                ]
                messages.append(AIMessage(content=c.get("text") or "", tool_calls=lc_calls))
            elif c["role"] == "tool":
                call_id = pending_ids[tool_idx] if tool_idx < len(pending_ids) else c["name"]
                messages.append(ToolMessage(content=str(c["result"]), tool_call_id=call_id, name=c["name"]))
                tool_idx += 1

        return messages

    def generate(self, system: str, contents: list[dict], tools: list) -> ModelTurn:
        llm = self._llm.bind_tools(tools) if tools else self._llm
        messages = self._to_messages(system, contents)
        try:
            resp = llm.invoke(messages)
        except Exception as e:
            msg = str(e)
            if "429" in msg or "quota" in msg.lower() or "rate" in msg.lower():
                raise AgentError("provider_rate_limited", "Model quota exhausted. Wait a minute.", True) from e
            if any(code in msg for code in ("500", "502", "503")):
                raise AgentError("provider_unavailable", "Model provider failed.", True) from e
            raise AgentError("provider_error", msg, False) from e

        text = resp.content if isinstance(resp.content, str) and resp.content else None
        calls = [ToolCall(tc["name"], tc["args"]) for tc in (resp.tool_calls or [])]
        usage = resp.usage_metadata or {}
        return ModelTurn(
            text=text,
            tool_calls=calls,
            tokens_in=usage.get("input_tokens", 0),
            tokens_out=usage.get("output_tokens", 0),
            raw=None,
        )


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
