-- Phase 8: truthful runtime context meter + compaction checkpoints.

CREATE TABLE IF NOT EXISTS runtime_context_checkpoints (
    id VARCHAR(64) PRIMARY KEY,
    owner_uid VARCHAR(255) NOT NULL,
    session_id VARCHAR(255) NOT NULL,
    summary TEXT NOT NULL,
    source_event_count INTEGER NOT NULL DEFAULT 0,
    token_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_runtime_context_checkpoints_owner_uid
    ON runtime_context_checkpoints(owner_uid);

CREATE INDEX IF NOT EXISTS ix_runtime_context_checkpoints_session_id
    ON runtime_context_checkpoints(session_id);
