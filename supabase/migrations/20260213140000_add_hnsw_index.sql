-- Migration: Add HNSW index for semantic search on assertion.embedding
-- Created: 2026-02-13
--
-- Problem: Sequential scan on 22,000+ assertion rows causes timeouts (>2 min)
-- Solution: HNSW index for approximate nearest neighbor search
--
-- Parameters (optimized after review):
--   m=24: number of bi-directional links (better recall than default 16)
--   ef_construction=128: larger candidate list for better index quality
--
-- HNSW vs IVFFlat: HNSW has better query performance and doesn't require
-- training on data distribution. Better for our scale (10k-100k rows).
--
-- Note: Index creation will briefly lock table (~30-40 sec). Acceptable for MVP.

-- Set search_path to include extensions schema where pgvector operators live
SET search_path TO public, extensions;

-- Increase statement timeout for index creation
SET statement_timeout = '5min';

-- Create HNSW index for cosine similarity search
-- Uses vector_cosine_ops because match_assertions uses <=> (cosine distance)
-- WHERE clause excludes NULL embeddings explicitly
CREATE INDEX IF NOT EXISTS idx_assertion_embedding_hnsw
ON assertion
USING hnsw (embedding vector_cosine_ops)
WITH (m = 24, ef_construction = 128)
WHERE embedding IS NOT NULL;

COMMENT ON INDEX idx_assertion_embedding_hnsw IS 'HNSW index for semantic search on assertion embeddings, created 2026-02-13';

-- Note: Index creation on 22k rows should take ~30-40 seconds
-- Query time should improve from >2min to <100ms
