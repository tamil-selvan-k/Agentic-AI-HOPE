-- Lab 2: make SQLite itself refuse UPDATE and DELETE on message.

CREATE TRIGGER IF NOT EXISTS no_update_message
BEFORE UPDATE ON message
BEGIN
    SELECT RAISE(ABORT, 'message rows are append-only');
END;

CREATE TRIGGER IF NOT EXISTS no_delete_message
BEFORE DELETE ON message
BEGIN
    SELECT RAISE(ABORT, 'message rows are append-only');
END;
