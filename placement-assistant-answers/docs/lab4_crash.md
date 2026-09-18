# Lab 4 — crash drill (answer key)

1. Worker-A was killed during `--gap`, after `notify_student` committed its notification row and idempotency key in placement.db, and before `record_tool_call` wrote the step to agent.db. So: application, booking and notification exist; the notify step has no record.
2. `rebuild()` reads the recorded steps: the last model step asked for book_interview_slot and notify_student, and only book_interview_slot has a result, so notify_student is pending at the same step number.
3. Same run id, same step, same tool, same arguments give the same `idempotency_key`, and `PlacementDb.once` finds it and returns the stored result without calling the tool. Before Part 2, the key was random and the tool ran again: two notifications. (Part 3's dedupe key would also catch this one, as a second line of defence.)
