"""Day 4: a supervisor that delegates to two specialists."""
from app.agents import SupervisorTools, run_specialist, run_tool
from app.providers import ModelTurn, ScriptedProvider, ToolCall, demo_providers
from app.tools.event_tools import CatalogueTools


def test_the_supervisor_only_has_delegation_tools(db):
    tools = SupervisorTools(db, demo_providers(), "22CS045")
    assert set(tools.functions()) == {"ask_catalogue", "ask_desk"}
    assert set(tools.DELEGATES) == set(tools.TOOL_NAMES)


def test_catalogue_specialist_answers_a_question(db):
    result, replayed = run_tool(SupervisorTools(db, demo_providers(), "22CS045"), db, "k1", "ask_catalogue",
                                {"question": "Is AI Hackathon 2026 available?"})
    assert result["agent"] == "catalogue" and result["tools_used"] == ["search_events"] and not replayed
    assert "50 seats" in result["answer"]


def test_desk_specialist_registers_and_notifies_for_the_bound_student(db):
    result, _ = run_tool(SupervisorTools(db, demo_providers(), "22CS045"), db, "k1", "ask_desk",
                         {"request": "Register for event 1 (AI Hackathon 2026) and text the student."})
    assert result["tools_used"] == ["check_can_register", "register_event", "notify_student"]
    assert [r["event_id"] for r in db.active_registrations(1)] == [1]
    assert db.count("notification") == 1


def test_a_repeated_delegation_with_the_same_key_does_nothing_twice(db):
    tools = SupervisorTools(db, demo_providers(), "22CS045")
    args = {"request": "Register for event 1 (AI Hackathon 2026) and text the student."}
    run_tool(tools, db, "same-key", "ask_desk", args)
    run_tool(tools, db, "same-key", "ask_desk", args)
    assert db.count("registration") == 3 and db.count("notification") == 1 and db.count("idempotency") == 2


def test_bad_delegation_arguments_are_fed_back(db):
    result, _ = run_tool(SupervisorTools(db, demo_providers(), "22CS045"), db, "k", "ask_desk", {"request": ""})
    assert result["error"] == "invalid_arguments"


def test_a_looping_specialist_stops(db):
    looping = ScriptedProvider([ModelTurn(text=None, tool_calls=[ToolCall("search_events", {"text": "hackathon"})])], loop=True)
    result = run_specialist("catalogue", "sys", CatalogueTools(db), db=db, provider=looping, task="x", parent_key="k")
    assert result["error"] == "specialist_step_limit"


def test_specialists_see_only_their_own_task(db):
    providers = demo_providers()
    run_tool(SupervisorTools(db, providers, "22CS045"), db, "k", "ask_catalogue", {"question": "Find Web3"})
    seen = providers["catalogue"].calls[0]
    assert seen == [{"role": "user", "text": "Find Web3"}]
    assert providers["desk"].calls == []


def test_desk_specialist_unregisters_student(db):
    """Desk can unregister a student who has an active registration (22IT017 is pre-seeded with event 5)."""
    result, _ = run_tool(
        SupervisorTools(db, demo_providers(), "22IT017"), db, "k-unreg", "ask_desk",
        {"request": "Unregister or cancel the student's active event registration."}
    )
    assert "unregister_event" in result["tools_used"], f"Expected unregister_event in tools_used: {result}"
    assert db.count("registration") == 1          # was 2 seed rows; 22IT017 removed
    assert db.count("notification") == 1          # confirmation sent


def test_supervisor_routes_cancel_keyword_to_desk(db):
    """Supervisor RoutedMock routes 'cancel' keyword to the desk via ask_desk delegation."""
    providers = demo_providers()
    # Call through the full supervisor delegation path
    result, _ = run_tool(
        SupervisorTools(db, providers, "22IT017"), db, "k-sup-cancel", "ask_desk",
        {"request": "cancel my registration"}
    )
    assert result["agent"] == "desk"
    assert "unregister_event" in result["tools_used"]
