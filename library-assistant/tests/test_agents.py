"""Day 4: a supervisor that delegates to two specialists."""
from app.agents import SupervisorTools, run_specialist, run_tool
from app.providers import ModelTurn, ScriptedProvider, ToolCall, demo_providers
from app.tools.library_tools import CatalogueTools


def test_the_supervisor_only_has_delegation_tools(db):
    tools = SupervisorTools(db, demo_providers(), "22CS045")
    assert set(tools.functions()) == {"ask_catalogue", "ask_desk"}
    assert set(tools.DELEGATES) == set(tools.TOOL_NAMES)


def test_catalogue_specialist_answers_a_question(db):
    result, replayed = run_tool(SupervisorTools(db, demo_providers(), "22CS045"), db, "k1", "ask_catalogue",
                                {"question": "Is Designing Data-Intensive Applications available?"})
    assert result["agent"] == "catalogue" and result["tools_used"] == ["search_books"] and not replayed
    assert "1 copy" in result["answer"]


def test_desk_specialist_reserves_and_notifies_for_the_bound_member(db):
    result, _ = run_tool(SupervisorTools(db, demo_providers(), "22CS045"), db, "k1", "ask_desk",
                         {"request": "Reserve book 2 (Designing Data-Intensive Applications) and text the member."})
    assert result["tools_used"] == ["check_can_borrow", "reserve_book", "notify_member"]
    assert [r["book_id"] for r in db.active_reservations(1)] == [2]
    assert db.count("notification") == 1


def test_a_repeated_delegation_with_the_same_key_does_nothing_twice(db):
    tools = SupervisorTools(db, demo_providers(), "22CS045")
    args = {"request": "Reserve book 2 (Designing Data-Intensive Applications) and text the member."}
    run_tool(tools, db, "same-key", "ask_desk", args)
    run_tool(tools, db, "same-key", "ask_desk", args)
    assert db.count("reservation") == 2 and db.count("notification") == 1 and db.count("idempotency") == 2


def test_bad_delegation_arguments_are_fed_back(db):
    result, _ = run_tool(SupervisorTools(db, demo_providers(), "22CS045"), db, "k", "ask_desk", {"request": ""})
    assert result["error"] == "invalid_arguments"


def test_a_looping_specialist_stops(db):
    looping = ScriptedProvider([ModelTurn(text=None, tool_calls=[ToolCall("search_books", {"text": "code"})])], loop=True)
    result = run_specialist("catalogue", "sys", CatalogueTools(db), db=db, provider=looping, task="x", parent_key="k")
    assert result["error"] == "specialist_step_limit"


def test_specialists_see_only_their_own_task(db):
    providers = demo_providers()
    run_tool(SupervisorTools(db, providers, "22CS045"), db, "k", "ask_catalogue", {"question": "Find Clean Code"})
    seen = providers["catalogue"].calls[0]
    assert seen == [{"role": "user", "text": "Find Clean Code"}]
    assert providers["desk"].calls == []
