-- AiPal v11: conversation memory + plan drafts
CREATE TABLE IF NOT EXISTS conversation_turns (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id VARCHAR(64) NOT NULL,
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_conversation_turns_user_session ON conversation_turns(user_id, session_id, created_at);

CREATE TABLE IF NOT EXISTS plan_drafts (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
