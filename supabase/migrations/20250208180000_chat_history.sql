-- ============================================
-- CHAT: Conversation history for agent
-- ============================================
CREATE TABLE chat_session (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL REFERENCES auth.users(id),
    title TEXT,  -- Auto-generated from first message
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_chat_session_owner ON chat_session(owner_id, updated_at DESC);

ALTER TABLE chat_session ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users see own chat sessions" ON chat_session
    FOR ALL USING (owner_id = auth.uid());

-- ============================================
-- CHAT MESSAGES: Individual messages in session
-- ============================================
CREATE TABLE chat_message (
    message_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES chat_session(session_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL,
    tool_calls JSONB,  -- For assistant messages with tool calls
    tool_call_id TEXT,  -- For tool response messages
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_chat_message_session ON chat_message(session_id, created_at);

ALTER TABLE chat_message ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users see own chat messages" ON chat_message
    FOR ALL USING (
        session_id IN (SELECT session_id FROM chat_session WHERE owner_id = auth.uid())
    );

-- Enable Realtime for chat messages
ALTER PUBLICATION supabase_realtime ADD TABLE chat_message;
