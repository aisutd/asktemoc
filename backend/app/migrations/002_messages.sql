-- Messages for a conversation, ordered by index within that conversation.

CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    "index" INTEGER NOT NULL,
    role TEXT NOT NULL,
    content JSONB,
    status TEXT NOT NULL DEFAULT 'pending',
    CONSTRAINT ck_messages_role CHECK (role IN ('user', 'assistant')),
    CONSTRAINT ck_messages_status CHECK (status IN ('pending', 'streaming', 'complete', 'error'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_conversation_index
    ON messages (conversation_id, "index");
