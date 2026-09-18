# Part 3 — memory design notes

## 1. Which entities were hiding in the Day 1 ConversationStore?

A single Python list held the whole conversation, but it was actually several distinct things mixed together: a **thread** (who is talking), individual **messages** (what was said, in order), **runs** (one call to `ask` — the model trying to answer), **run steps** (each model generation or tool call within a run), and **tool calls** (the structured inputs and outputs for each tool invocation).

## 2. What is a run, and why is it not a message?

A run is one user turn processed by the agent loop — it begins when `ask` is called and ends when the model produces a reply or the loop fails. It is not a message because nobody *said* it: a run is something the agent *did*, with timing, token counts, and a success/failure status. Messages record what was communicated; runs record what was computed.

## 3. Why is tool_call one-to-one with run_step?

Each tool step in the loop is a single tool invocation, so one `run_step` row of kind `tool` always corresponds to exactly one `tool_call`. This keeps the schema simple: the step holds the sequencing metadata (run_id, seq, kind) and the tool_call holds the payload (name, args, result, latency). Keeping them separate avoids NULLs on model steps, which have no tool payload.

## 4. Why does the agent's memory live apart from the placement data, and what breaks if you put them together?

The agent's memory is an **audit log** of what the agent did. The placement data is the **domain** the agent acts on. They change for different reasons and at different rates, are owned by different teams, and have different retention and access rules. If they shared the same database, a migration to the placement schema could corrupt conversation history, or a replay of history could re-trigger side effects. One concrete failure: if `message` and `application` are in the same schema file and a transaction rolls back during a drive update, previously-committed conversation history could be lost along with it.
