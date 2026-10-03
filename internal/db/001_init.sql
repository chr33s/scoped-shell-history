CREATE TABLE history (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    started_at INTEGER NOT NULL,
    duration_ms INTEGER,
    command TEXT NOT NULL,
    exit_status INTEGER,
    cwd TEXT NOT NULL,
    scope_type TEXT NOT NULL CHECK (scope_type IN ('project', 'directory')),
    scope_path TEXT NOT NULL,
    shell TEXT NOT NULL,
    hostname TEXT,
    tty TEXT
);
CREATE INDEX idx_history_scope_time ON history(scope_path, started_at DESC, id DESC);
CREATE INDEX idx_history_cwd_time ON history(cwd, started_at DESC, id DESC);
CREATE INDEX idx_history_time ON history(started_at DESC, id DESC);
CREATE UNIQUE INDEX idx_history_session_seq ON history(session_id, seq);
PRAGMA user_version = 1;
