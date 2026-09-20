"""Model providers. The agent only knows `generate`. (Given.)"""
import json
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
    raw: Any = None     # provider-native content, sent back as-is


# `contents` is a plain list the agent builds up:
#   {"role": "user",  "text": str}
#   {"role": "model", "text": str | None, "tool_calls": [{"name", "args"}], "raw": ...}
#   {"role": "tool",  "name": str, "result": dict}


class GroqProvider:
    """Model provider powered by Groq API with function calling."""

    def __init__(self, model: str | None = None):
        import os
        from groq import Groq

        api_key = os.environ.get("GROQ_API_KEY") or os.environ.get("GEMINI_API_KEY")
        self.client = Groq(api_key=api_key) if api_key else Groq()
        self.model = os.environ.get("GROQ_MODEL") or model or "llama-3.3-70b-versatile"

    def _to_groq_messages(self, system: str, contents: list[dict]) -> list[dict]:
        messages = [{"role": "system", "content": system}]
        for c in contents:
            role = c["role"]
            if role == "user":
                messages.append({"role": "user", "content": c["text"]})
            elif role == "model":
                msg = {"role": "assistant"}
                if c.get("text"):
                    msg["content"] = c["text"]
                if c.get("tool_calls"):
                    msg["tool_calls"] = [
                        {
                            "id": f"call_{i}_{tc['name']}",
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": json.dumps(tc["args"])},
                        }
                        for i, tc in enumerate(c["tool_calls"])
                    ]
                messages.append(msg)
            elif role == "tool":
                messages.append({
                    "role": "tool",
                    "tool_call_id": f"call_0_{c['name']}",
                    "content": json.dumps(c["result"])
                })
        return messages

    def _func_to_tool(self, func):
        import inspect
        doc = inspect.getdoc(func) or ""
        params = inspect.signature(func).parameters
        properties = {}
        required = []
        for param_name, param in params.items():
            param_type = "string"
            if param.annotation == int:
                param_type = "integer"
            elif param.annotation == bool:
                param_type = "boolean"
            elif param.annotation == float:
                param_type = "number"
            properties[param_name] = {"type": param_type}
            if param.default == inspect.Parameter.empty:
                required.append(param_name)
        return {
            "type": "function",
            "function": {
                "name": func.__name__,
                "description": doc,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }

    def generate(self, system: str, contents: list[dict], tools: list) -> ModelTurn:
        from groq import APIError

        messages = self._to_groq_messages(system, contents)
        tool_specs = [self._func_to_tool(f) for f in tools] if tools else None

        kwargs = {"model": self.model, "messages": messages, "temperature": 0}
        if tool_specs:
            kwargs["tools"] = tool_specs

        try:
            resp = self.client.chat.completions.create(**kwargs)
        except APIError as e:
            if getattr(e, "status_code", None) == 429:
                raise AgentError("provider_rate_limited", "Groq rate limited. Wait a minute.", True) from e
            raise AgentError("provider_error", str(e), False) from e

        choice = resp.choices[0].message
        text = choice.content or None
        calls = []
        if choice.tool_calls:
            for tc in choice.tool_calls:
                args = json.loads(tc.function.arguments) if tc.function.arguments and tc.function.arguments.strip() else {}
                calls.append(ToolCall(tc.function.name, args))

        usage = resp.usage
        tokens_in = usage.prompt_tokens if usage else 0
        tokens_out = usage.completion_tokens if usage else 0

        return ModelTurn(text=text, tool_calls=calls, tokens_in=tokens_in, tokens_out=tokens_out, raw=choice)


# Alias GeminiProvider to GroqProvider for backward compatibility
GeminiProvider = GroqProvider


class ScriptedProvider:
    """Replays a fixed list of turns in call order. No network, no quota. Used by the tests."""

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


class PositionalMock:
    """A scripted model that answers by position in the current turn, not by call count.
    A fresh process that resumes a half-finished run gets the NEXT turn, not the first one.
    `slow` sleeps before each answer, so you have time to kill the worker mid-run."""

    model = "mock"

    def __init__(self, turns: list[ModelTurn], slow: float = 0.0):
        self.turns, self.slow = turns, slow
        self.calls: list[list[dict]] = []

    def generate(self, system: str, contents: list[dict], tools: list) -> ModelTurn:
        import time

        self.calls.append([dict(c) for c in contents])
        last_user = max(i for i, c in enumerate(contents) if c["role"] == "user")
        position = sum(1 for c in contents[last_user:] if c["role"] == "model")
        if self.slow:
            time.sleep(self.slow)
        if position >= len(self.turns):
            return ModelTurn(text="(mock) nothing more to do.")
        return self.turns[position]


class RoutedMock:
    """Several scripted conversations in one mock: picks a script by a phrase in the current request,
    then answers by position (like PositionalMock). Used by the demo and the tests."""

    model = "mock"

    def __init__(self, routes: dict[str, list[ModelTurn]], slow: float = 0.0):
        self.routes, self.slow = routes, slow
        self.calls: list[list[dict]] = []

    def generate(self, system: str, contents: list[dict], tools: list) -> ModelTurn:
        import time

        self.calls.append([dict(c) for c in contents])
        last_user = max(i for i, c in enumerate(contents) if c["role"] == "user")
        request = contents[last_user]["text"]
        position = sum(1 for c in contents[last_user:] if c["role"] == "model")
        if self.slow:
            time.sleep(self.slow)
        for phrase, turns in self.routes.items():
            if phrase and phrase.lower() in request.lower():
                return turns[position] if position < len(turns) else ModelTurn(text="(mock) done.")
        # Catch-all fallback route if no phrase matches
        if "" in self.routes:
            turns = self.routes[""]
            return turns[position] if position < len(turns) else ModelTurn(text="(mock) done.")
        return ModelTurn(text="(mock) I have no script for that request.")


def _call(name, **args):
    return ModelTurn(text=None, tool_calls=[ToolCall(name, args)], tokens_in=100, tokens_out=10)


def demo_providers(slow: float = 0.0) -> dict:
    """Scripted models for the three agents, covering demo questions and UI fallback."""
    ai_hackathon_supervisor = [
        _call("ask_catalogue", question="Is AI Hackathon 2026 available?"),
        _call("ask_desk", request="Register for event 1 (AI Hackathon 2026) and text the student to confirm."),
        ModelTurn(text="(mock) Good news: it was available, you are now registered, and a confirmation text is on its way."),
    ]
    web3_supervisor = [
        _call("ask_catalogue", question="Find Web3 & Cloud Symposium"),
        _call("ask_desk", request="Register for event 2 (Web3 & Cloud Symposium) for the student."),
        ModelTurn(text="(mock) Web3 & Cloud Symposium is open, but the desk can't register: you already reached your max registration limit."),
    ]
    unregister_supervisor = [
        _call("ask_desk", request="Unregister or cancel the student's active event registration. If they have multiple registrations, list them and ask which one to cancel."),
        ModelTurn(text="(mock) Done — the desk has unregistered you from the event and sent a confirmation text."),
    ]

    return {
        "supervisor": RoutedMock({
            "AI Hackathon": ai_hackathon_supervisor,
            "Web3": web3_supervisor,
            "unregister": unregister_supervisor,
            "cancel": unregister_supervisor,
            "remove me": unregister_supervisor,
            "drop": unregister_supervisor,
            "withdraw": unregister_supervisor,
            "": ai_hackathon_supervisor,  # catch-all fallback for UI prompts
        }, slow),
        "catalogue": RoutedMock({
            "AI Hackathon": [_call("search_events", text="AI Hackathon"),
                             ModelTurn(text="(mock) Event 1, AI Hackathon 2026 by CSE Dept: 50 seats available.")],
            "Web3": [_call("search_events", text="Web3"),
                     ModelTurn(text="(mock) Event 2, Web3 & Cloud Symposium by IT Dept: 1 seat available.")],
            "": [_call("search_events", text="AI Hackathon"),
                 ModelTurn(text="(mock) Event 1, AI Hackathon 2026 by CSE Dept: 50 seats available.")],
        }, slow),
        "desk": RoutedMock({
            "Register for event 1": [
                _call("check_can_register"),
                ModelTurn(text=None, tool_calls=[
                    ToolCall("register_event", {"event_id": 1}),
                    ToolCall("notify_student", {"message": "Your registration for AI Hackathon 2026 is confirmed."})],
                    tokens_in=150, tokens_out=25),
                ModelTurn(text="(mock) Registered for event 1 and sent the confirmation."),
            ],
            "Register for event 2": [
                _call("check_can_register"),
                ModelTurn(text="(mock) Not registered: student reached maximum allowed registrations."),
            ],
            # All unregister/cancel/drop/remove requests share the same script
            "Unregister": [
                _call("get_student"),
                ModelTurn(text=None, tool_calls=[
                    ToolCall("unregister_event", {"event_id": 0, "event_title": ""}),
                    ToolCall("notify_student", {"message": "You have been unregistered from the event successfully."})],
                    tokens_in=100, tokens_out=20),
                ModelTurn(text="(mock) Unregistered from the event. Confirmation text sent."),
            ],
            "cancel": [
                _call("get_student"),
                ModelTurn(text=None, tool_calls=[
                    ToolCall("unregister_event", {"event_id": 0, "event_title": ""}),
                    ToolCall("notify_student", {"message": "Your registration has been cancelled successfully."})],
                    tokens_in=100, tokens_out=20),
                ModelTurn(text="(mock) Registration cancelled. Confirmation text sent."),
            ],
            "remove": [
                _call("get_student"),
                ModelTurn(text=None, tool_calls=[
                    ToolCall("unregister_event", {"event_id": 0, "event_title": ""}),
                    ToolCall("notify_student", {"message": "Your event registration has been removed successfully."})],
                    tokens_in=100, tokens_out=20),
                ModelTurn(text="(mock) Registration removed. Confirmation text sent."),
            ],
            "": [
                _call("check_can_register"),
                ModelTurn(text=None, tool_calls=[
                    ToolCall("register_event", {"event_id": 1}),
                    ToolCall("notify_student", {"message": "Your registration for AI Hackathon 2026 is confirmed."})],
                    tokens_in=150, tokens_out=25),
                ModelTurn(text="(mock) Registered for event 1 and sent the confirmation."),
            ],
        }, slow),
    }
