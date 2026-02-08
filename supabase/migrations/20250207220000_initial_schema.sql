-- Atlantis Plus Initial Schema

-- Make vector type visible from extensions schema
SET search_path TO public, extensions;

-- ============================================
-- CORE: Person (canonical person entity)
-- ============================================
CREATE TABLE IF NOT EXISTS person (
    person_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL REFERENCES auth.users(id),
    display_name TEXT NOT NULL,
    summary TEXT,
    summary_embedding vector(1536),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'merged', 'deleted')),
    merged_into_person_id UUID REFERENCES person(person_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_person_owner ON person(owner_id) WHERE status = 'active';

ALTER TABLE person ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users see own people" ON person;
CREATE POLICY "Users see own people" ON person
    FOR ALL USING (owner_id = auth.uid());

-- ============================================
-- IDENTITY: external platform bindings
-- ============================================
CREATE TABLE IF NOT EXISTS identity (
    identity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id UUID REFERENCES person(person_id) ON DELETE CASCADE,
    namespace TEXT NOT NULL,
    value TEXT NOT NULL,
    verified BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(namespace, value)
);

CREATE INDEX IF NOT EXISTS idx_identity_person ON identity(person_id);

ALTER TABLE identity ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users see identities of own people" ON identity;
CREATE POLICY "Users see identities of own people" ON identity
    FOR ALL USING (
        person_id IN (SELECT person_id FROM person WHERE owner_id = auth.uid())
    );

-- ============================================
-- RAW EVIDENCE: transcripts, notes
-- ============================================
CREATE TABLE IF NOT EXISTS raw_evidence (
    evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL REFERENCES auth.users(id),
    source_type TEXT NOT NULL CHECK (source_type IN ('voice_note', 'text_note', 'chat_message', 'import')),
    content TEXT NOT NULL,
    audio_storage_path TEXT,
    metadata JSONB DEFAULT '{}',
    processed BOOLEAN NOT NULL DEFAULT false,
    processing_status TEXT DEFAULT 'pending' CHECK (processing_status IN ('pending', 'transcribing', 'extracting', 'done', 'error')),
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_evidence_owner ON raw_evidence(owner_id, created_at DESC);

ALTER TABLE raw_evidence ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users see own evidence" ON raw_evidence;
CREATE POLICY "Users see own evidence" ON raw_evidence
    FOR ALL USING (owner_id = auth.uid());

-- Enable Realtime for processing status tracking
ALTER PUBLICATION supabase_realtime ADD TABLE raw_evidence;

-- ============================================
-- ASSERTION: atomic facts about people
-- ============================================
CREATE TABLE IF NOT EXISTS assertion (
    assertion_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_person_id UUID NOT NULL REFERENCES person(person_id) ON DELETE CASCADE,
    predicate TEXT NOT NULL,
    object_value TEXT,
    object_person_id UUID REFERENCES person(person_id),
    object_json JSONB,
    author_identity_id UUID REFERENCES identity(identity_id),
    evidence_id UUID REFERENCES raw_evidence(evidence_id),
    scope TEXT NOT NULL DEFAULT 'personal',
    confidence FLOAT NOT NULL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
    embedding vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_assertion_subject ON assertion(subject_person_id);
CREATE INDEX IF NOT EXISTS idx_assertion_predicate ON assertion(predicate, subject_person_id);
CREATE INDEX IF NOT EXISTS idx_assertion_object_person ON assertion(object_person_id) WHERE object_person_id IS NOT NULL;

ALTER TABLE assertion ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users see assertions of own people" ON assertion;
CREATE POLICY "Users see assertions of own people" ON assertion
    FOR ALL USING (
        subject_person_id IN (SELECT person_id FROM person WHERE owner_id = auth.uid())
    );

-- ============================================
-- EDGE: normalized connections for graph traversal
-- ============================================
CREATE TABLE IF NOT EXISTS edge (
    edge_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    src_person_id UUID NOT NULL REFERENCES person(person_id) ON DELETE CASCADE,
    dst_person_id UUID NOT NULL REFERENCES person(person_id) ON DELETE CASCADE,
    edge_type TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'personal',
    weight FLOAT NOT NULL DEFAULT 1.0,
    evidence_assertion_id UUID REFERENCES assertion(assertion_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (src_person_id != dst_person_id)
);

CREATE INDEX IF NOT EXISTS idx_edge_src ON edge(src_person_id, edge_type);
CREATE INDEX IF NOT EXISTS idx_edge_dst ON edge(dst_person_id, edge_type);

ALTER TABLE edge ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users see edges of own people" ON edge;
CREATE POLICY "Users see edges of own people" ON edge
    FOR ALL USING (
        src_person_id IN (SELECT person_id FROM person WHERE owner_id = auth.uid())
    );

-- ============================================
-- PERSON MATCH CANDIDATES (for deduplication)
-- ============================================
CREATE TABLE IF NOT EXISTS person_match_candidate (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    a_person_id UUID NOT NULL REFERENCES person(person_id),
    b_person_id UUID NOT NULL REFERENCES person(person_id),
    score FLOAT NOT NULL,
    reasons JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'merged', 'rejected')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================
-- SEMANTIC SEARCH FUNCTION (pgvector)
-- ============================================
CREATE OR REPLACE FUNCTION match_assertions(
    query_embedding vector(1536),
    match_threshold float,
    match_count int,
    p_owner_id uuid
)
RETURNS TABLE (
    assertion_id uuid,
    subject_person_id uuid,
    predicate text,
    object_value text,
    confidence float,
    similarity float
)
LANGUAGE sql STABLE
AS $$
    SELECT
        a.assertion_id,
        a.subject_person_id,
        a.predicate,
        a.object_value,
        a.confidence,
        1 - (a.embedding <=> query_embedding) as similarity
    FROM assertion a
    JOIN person p ON a.subject_person_id = p.person_id
    WHERE p.owner_id = p_owner_id
      AND p.status = 'active'
      AND a.embedding IS NOT NULL
      AND 1 - (a.embedding <=> query_embedding) > match_threshold
    ORDER BY a.embedding <=> query_embedding
    LIMIT match_count;
$$;
