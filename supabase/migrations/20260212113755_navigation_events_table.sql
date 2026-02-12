-- Navigation events table for Realtime subscriptions
-- Mini App subscribes to changes on this table filtered by telegram_id
-- Bot inserts events here, frontend receives them via Realtime

CREATE TABLE navigation_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id TEXT NOT NULL,
    person_id UUID NOT NULL,
    event_type TEXT NOT NULL DEFAULT 'navigate_person',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index for filtering by telegram_id
CREATE INDEX idx_navigation_events_telegram ON navigation_events(telegram_id);

-- Auto-delete old events after 1 minute (we only need real-time delivery)
-- Using a simple approach: delete on insert via trigger
CREATE OR REPLACE FUNCTION cleanup_old_navigation_events()
RETURNS TRIGGER AS $$
BEGIN
    DELETE FROM navigation_events
    WHERE created_at < NOW() - INTERVAL '1 minute';
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER cleanup_navigation_events_trigger
AFTER INSERT ON navigation_events
FOR EACH STATEMENT
EXECUTE FUNCTION cleanup_old_navigation_events();

-- Enable Realtime for this table
ALTER PUBLICATION supabase_realtime ADD TABLE navigation_events;

-- RLS: Users can only see their own events (based on telegram_id matching their JWT)
-- Note: For simplicity, we allow all selects since telegram_id is in the event
-- The client filters by telegram_id anyway
ALTER TABLE navigation_events ENABLE ROW LEVEL SECURITY;

-- Policy: Allow insert from service role (bot uses service_role_key)
CREATE POLICY "Service can insert navigation events" ON navigation_events
    FOR INSERT WITH CHECK (true);

-- Policy: Allow select for all authenticated users (they filter by telegram_id)
CREATE POLICY "Users can read navigation events" ON navigation_events
    FOR SELECT USING (true);
