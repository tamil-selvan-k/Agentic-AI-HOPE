"""Part 2 — the agent loop. Uses a scripted model: no network, no quota."""
import pytest

from app.agent import MAX_STEPS, Agent
from app.providers import AgentError, ModelTurn, ScriptedProvider, ToolCall
from app.tools.placement_tools import PlacementTools


def check(student="22CS045", drive=1):
    return ModelTurn(text=None, tool_calls=[ToolCall("check_eligibility", {"student_id": student, "drive_id": drive})])


def agent_with(tools, *turns, **kw):
    provider = ScriptedProvider(list(turns))
    return Agent(provider, tools, "22CS045", **kw), provider


def test_answer_without_tools(tools):
    agent, _ = agent_with(tools, ModelTurn(text="Hello!"))
    assert agent.ask("hi") == "Hello!"
    assert [t["kind"] for t in agent.trace] == ["model"]


def test_tool_call_then_answer(tools):
    agent, provider = agent_with(tools, check(), ModelTurn(text="You're eligible."))
    assert agent.ask("Am I eligible for Zoho?") == "You're eligible."
    assert [t["kind"] for t in agent.trace] == ["model", "tool", "model"]
    step = agent.trace[1]
    assert step["tool"] == "check_eligibility" and step["ok"] is True and step["result"]["eligible"] is True
    last_seen = provider.calls[1][-1]
    assert last_seen["role"] == "tool" and last_seen["result"]["eligible"] is True


def test_trace_steps_are_numbered(tools):
    agent, _ = agent_with(tools, check(), ModelTurn(text="ok"))
    agent.ask("x")
    assert [t["step"] for t in agent.trace] == [1, 2, 3]
    assert isinstance(agent.trace[1]["ms"], int)


def test_parallel_tool_calls_run_in_order(tools):
    both = ModelTurn(text=None, tool_calls=[ToolCall("check_eligibility", {"student_id": "22CS045", "drive_id": 1}),
                                            ToolCall("check_eligibility", {"student_id": "22CS045", "drive_id": 2})])
    agent, provider = agent_with(tools, both, ModelTurn(text="Both fine."))
    agent.ask("Zoho and TCS?")
    seen = provider.calls[1]
    assert [c["result"]["drive_id"] for c in seen if c["role"] == "tool"] == [1, 2]


def test_bad_arguments_are_fed_back_not_raised(tools):
    agent, provider = agent_with(tools, check(drive="Zoho"), ModelTurn(text="Which drive id?"))
    assert agent.ask("Zoho?") == "Which drive id?"
    assert agent.trace[1]["ok"] is False
    assert provider.calls[1][-1]["result"]["error"] == "invalid_arguments"


def test_unfinished_tool_does_not_crash_the_agent(repo, notifier):
    class Unfinished(PlacementTools):
        def get_student(self, student_id: str) -> dict:
            raise NotImplementedError

    agent, provider = agent_with(Unfinished(repo, notifier),
                                 ModelTurn(text=None, tool_calls=[ToolCall("get_student", {"student_id": "22CS045"})]),
                                 ModelTurn(text="Can't do that yet."))
    agent.ask("my record?")
    assert provider.calls[1][-1]["result"]["error"] == "not_implemented"


def test_crashing_tool_becomes_information(repo, notifier):
    class Buggy(PlacementTools):
        def get_student(self, student_id: str) -> dict:
            return {}["boom"]

    agent, provider = agent_with(Buggy(repo, notifier),
                                 ModelTurn(text=None, tool_calls=[ToolCall("get_student", {"student_id": "22CS045"})]),
                                 ModelTurn(text="Something went wrong."))
    assert agent.ask("my record?") == "Something went wrong."
    assert provider.calls[1][-1]["result"]["error"] == "tool_failed"


def test_step_limit_stops_a_looping_model(tools):
    provider = ScriptedProvider([check()], loop=True)
    agent = Agent(provider, tools, "22CS045")
    with pytest.raises(AgentError) as e:
        agent.ask("loop forever")
    assert e.value.code == "step_limit"
    assert len(agent.trace) <= MAX_STEPS + 1


def test_history_carries_across_turns(tools):
    agent, provider = agent_with(tools, ModelTurn(text="first answer"), ModelTurn(text="second answer"))
    agent.ask("one")
    agent.ask("two")
    assert [c.get("text") for c in provider.calls[1]] == ["one", "first answer", "two"]


def test_provider_errors_reach_the_caller(tools):
    agent, _ = agent_with(tools, AgentError("provider_rate_limited", "quota", retryable=True))
    with pytest.raises(AgentError) as e:
        agent.ask("hi")
    assert e.value.retryable is True


def test_on_step_sees_every_step(tools):
    seen = []
    agent, _ = agent_with(tools, check(), ModelTurn(text="ok"), on_step=seen.append)
    agent.ask("x")
    assert seen == agent.trace
