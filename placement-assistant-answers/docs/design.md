# Sprint — design notes (answer key)

1. A run can contain many side effects. Retrying the whole request would redo every side effect before the failure. Recording each step as it happens lets a retry resume at the first step with no record, and the idempotency key makes the one ambiguous step (effect done, record missing) safe to repeat. (`app/runner.py: rebuild`, `execute_run`.)

2. The key protects the side effect, so it must commit or roll back with it. If the key lived in agent.db, a crash between the placement.db commit and the agent.db commit would leave an application with no key, and the replay would apply again. In one placement.db transaction (`PlacementDb.once`), there is no moment where one exists without the other.

3. The reaper decides the worker is dead while it is still waiting on the model, requeues the run, and a second worker starts it. The first worker's next heartbeat fails, it raises LeaseLost and writes nothing more, so the design stays correct, but the model call is wasted and paid twice. Fix: a lease comfortably longer than the slowest model call, or a heartbeat thread during the call.

4. A plain BEGIN starts with a read lock. Two workers that both read the queue and then try to write would each wait for the other to release its read lock: a deadlock, which SQLite resolves by failing one with "database is locked" immediately. BEGIN IMMEDIATE takes the write lock first, so the second worker waits its turn (busy_timeout) instead of deadlocking. It is lock ordering, applied at the start of the transaction.

5. The notification row is exactly-once, but a real SMS gateway call is outside the transaction: a crash after the gateway accepts and before the row commits would send twice. Fix: an outbox (commit the row first, send from a separate process that marks rows sent) plus a gateway that accepts an idempotency key. The same applies to any external API the tools call.
