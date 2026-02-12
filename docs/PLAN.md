# PLAN.md - Data Model Improvement Plan for Atlantis Plus

## Executive Summary

This plan addresses 8 critical issues in the Atlantis Plus data model, focusing on:
1. **Silent identity conflicts** (P0 - Critical bug)
2. **Pre-insertion dedup** (P0 - Prevents duplicate explosion)
3. **Assertion deduplication on merge** (P1)
4. **Temporal dimension** (P1 - Data freshness)
5. **Relationship strength (RFM)** (P1 - Core feature)
6. **Edge dynamics** (P2)
7. **Confidence-based ranking** (P2)
8. **Centrality metrics** (P3 - Future)

---

## Phase 1: Critical Bug Fixes (P0)

### 1.1 Fix Silent Identity Conflicts

**Problem:** In `/service/app/api/process.py` lines 113-117:
```python
for identity in identities:
    try:
        supabase.table("identity").insert(identity).execute()
    except Exception:
        pass  # Ignore duplicate identities  <-- BUG: silently ignores conflict
```

When an email/telegram identity already exists for a DIFFERENT person, the new person is created but NOT linked to the existing identity. This creates orphan records.

**Solution: Pre-check + Alert + Optional Auto-merge**

**Migration (SQL):**
```sql
-- 20250213100000_identity_conflict_detection.sql

-- Function to find existing person by identity
CREATE OR REPLACE FUNCTION find_person_by_identity(
    p_owner_id UUID,
    p_namespace TEXT,
    p_value TEXT
)
RETURNS UUID
LANGUAGE sql STABLE
AS $$
    SELECT p.person_id
    FROM identity i
    JOIN person p ON i.person_id = p.person_id
    WHERE i.namespace = p_namespace
      AND i.value = p_value
      AND p.owner_id = p_owner_id
      AND p.status = 'active'
    LIMIT 1;
$$;

-- Table to track identity conflicts for review
CREATE TABLE IF NOT EXISTS identity_conflict (
    conflict_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL REFERENCES auth.users(id),
    new_person_id UUID NOT NULL REFERENCES person(person_id),
    existing_person_id UUID NOT NULL REFERENCES person(person_id),
    namespace TEXT NOT NULL,
    value TEXT NOT NULL,
    resolution TEXT DEFAULT 'pending' CHECK (resolution IN ('pending', 'merged', 'kept_separate', 'auto_merged')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX idx_identity_conflict_owner ON identity_conflict(owner_id, resolution);
ALTER TABLE identity_conflict ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users see own conflicts" ON identity_conflict
    FOR ALL USING (owner_id = auth.uid());
```

**Python code change** in `process.py`:
```python
# BEFORE inserting identity, check if it exists
async def insert_identity_with_conflict_check(
    supabase, person_id: str, namespace: str, value: str, owner_id: str
) -> tuple[bool, Optional[str]]:
    """
    Insert identity, detecting conflicts.
    Returns (success, existing_person_id if conflict).
    """
    # Check if identity already exists
    existing = supabase.rpc(
        "find_person_by_identity",
        {"p_owner_id": owner_id, "p_namespace": namespace, "p_value": value}
    ).execute()

    if existing.data and existing.data[0]:
        existing_person_id = existing.data[0]
        if existing_person_id != person_id:
            # Conflict! Record it
            supabase.table("identity_conflict").insert({
                "owner_id": owner_id,
                "new_person_id": person_id,
                "existing_person_id": existing_person_id,
                "namespace": namespace,
                "value": value
            }).execute()
            return False, existing_person_id

    # No conflict, insert
    try:
        supabase.table("identity").insert({
            "person_id": person_id,
            "namespace": namespace,
            "value": value
        }).execute()
        return True, None
    except Exception:
        return False, None
```

### 1.2 Pre-Insertion Dedup Check

**Problem:** People are created without checking if a very similar person already exists. Currently dedup runs AFTER import, but by then duplicates are already in the database.

**Solution: Check before CREATE, not after**

**Python utility function:**
```python
# /service/app/services/dedup.py - new method

async def find_existing_person_match(
    self,
    owner_id: UUID,
    display_name: str,
    identifiers: dict,  # {namespace: value, ...}
    name_threshold: float = 0.7
) -> Optional[UUID]:
    """
    Check if a person likely already exists before creating new one.

    Priority:
    1. Exact identity match (email, telegram, linkedin) -> definite match
    2. High name similarity (>0.7) -> potential match, return for confirmation

    Returns person_id if match found, None otherwise.
    """
    # 1. Check identities first (highest confidence)
    for namespace, value in identifiers.items():
        if not value:
            continue
        result = self.supabase.rpc(
            "find_person_by_identity",
            {"p_owner_id": str(owner_id), "p_namespace": namespace, "p_value": value}
        ).execute()
        if result.data and result.data[0]:
            return UUID(result.data[0])

    # 2. Check name similarity
    result = self.supabase.rpc(
        "find_similar_names",
        {"p_owner_id": str(owner_id), "p_name": display_name, "p_threshold": name_threshold}
    ).execute()

    if result.data:
        # Return top match if very high similarity
        top_match = result.data[0]
        if top_match["similarity"] >= 0.85:
            return UUID(top_match["person_id"])

    return None
```

**Integration in `process_pipeline`:**
```python
# In process.py, modify person creation loop:

for person in extraction.people:
    # Check if person already exists
    existing_id = await dedup_service.find_existing_person_match(
        owner_id=UUID(user_id),
        display_name=person.name,
        identifiers={
            "email": person.identifiers.email,
            "telegram_username": person.identifiers.telegram,
            "linkedin_url": person.identifiers.linkedin
        }
    )

    if existing_id:
        # Use existing person instead of creating new
        person_map[person.temp_id] = str(existing_id)
        # Still add new identities/name variations to existing person
        await add_identities_to_person(existing_id, person)
    else:
        # Create new person
        person_result = supabase.table("person").insert({...}).execute()
        person_map[person.temp_id] = person_result.data[0]["person_id"]
```

---

## Phase 2: Assertion Deduplication (P1)

### 2.1 Problem

When merging persons A and B, their assertions are simply moved to A. If both have "works_at: Google", now A has 2 identical assertions.

### 2.2 Solution: Assertion Signature + Merge Logic

**Migration:**
```sql
-- 20250213110000_assertion_dedup.sql

-- Add signature column for dedup
ALTER TABLE assertion ADD COLUMN IF NOT EXISTS signature TEXT;

-- Generate signature from subject + predicate + value (normalized)
CREATE OR REPLACE FUNCTION generate_assertion_signature(
    p_predicate TEXT,
    p_object_value TEXT
)
RETURNS TEXT
LANGUAGE sql IMMUTABLE
AS $$
    SELECT md5(lower(p_predicate) || '::' || lower(coalesce(p_object_value, '')));
$$;

-- Backfill existing assertions
UPDATE assertion
SET signature = generate_assertion_signature(predicate, object_value)
WHERE signature IS NULL;

-- Index for fast lookup
CREATE INDEX IF NOT EXISTS idx_assertion_signature
    ON assertion(subject_person_id, signature);

-- Trigger to auto-generate signature
CREATE OR REPLACE FUNCTION assertion_signature_trigger()
RETURNS TRIGGER AS $$
BEGIN
    NEW.signature := generate_assertion_signature(NEW.predicate, NEW.object_value);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tr_assertion_signature
    BEFORE INSERT OR UPDATE ON assertion
    FOR EACH ROW EXECUTE FUNCTION assertion_signature_trigger();
```

**Merge logic update** in `dedup.py`:
```python
async def merge_persons(
    self,
    owner_id: UUID,
    keep_person_id: UUID,
    merge_person_id: UUID
) -> MergeResult:
    # Get existing signatures for keep_person
    existing_sigs = self.supabase.table("assertion").select(
        "signature"
    ).eq("subject_person_id", str(keep_person_id)).execute()
    existing_set = {r["signature"] for r in existing_sigs.data or []}

    # Get assertions to move
    to_move = self.supabase.table("assertion").select(
        "assertion_id, signature"
    ).eq("subject_person_id", str(merge_person_id)).execute()

    assertions_moved = 0
    assertions_skipped = 0

    for a in to_move.data or []:
        if a["signature"] in existing_set:
            # Duplicate - delete instead of moving
            self.supabase.table("assertion").delete().eq(
                "assertion_id", a["assertion_id"]
            ).execute()
            assertions_skipped += 1
        else:
            # Unique - move to kept person
            self.supabase.table("assertion").update({
                "subject_person_id": str(keep_person_id)
            }).eq("assertion_id", a["assertion_id"]).execute()
            existing_set.add(a["signature"])  # Prevent further dupes
            assertions_moved += 1
```

---

## Phase 3: Temporal Model (P1)

### 3.1 Problem

Facts have no time dimension. "Works at Google" from 2018 is treated same as 2024.

### 3.2 Solution: Add temporal fields + extraction improvements

**Migration:**
```sql
-- 20250213120000_temporal_model.sql

-- Temporal fields for assertions
ALTER TABLE assertion ADD COLUMN IF NOT EXISTS valid_from DATE;
ALTER TABLE assertion ADD COLUMN IF NOT EXISTS valid_until DATE;
ALTER TABLE assertion ADD COLUMN IF NOT EXISTS is_current BOOLEAN DEFAULT true;

-- Mark old work/role assertions when new one added
CREATE OR REPLACE FUNCTION update_current_flags()
RETURNS TRIGGER AS $$
BEGIN
    -- When new works_at or role_is added, mark old ones as not current
    IF NEW.predicate IN ('works_at', 'role_is') AND NEW.is_current = true THEN
        UPDATE assertion
        SET is_current = false,
            valid_until = CURRENT_DATE
        WHERE subject_person_id = NEW.subject_person_id
          AND predicate = NEW.predicate
          AND assertion_id != NEW.assertion_id
          AND is_current = true;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tr_update_current_flags
    AFTER INSERT ON assertion
    FOR EACH ROW EXECUTE FUNCTION update_current_flags();

-- Index for current assertions
CREATE INDEX IF NOT EXISTS idx_assertion_current
    ON assertion(subject_person_id, predicate)
    WHERE is_current = true;
```

**Prompt update** for extraction (add to `prompts.py`):
```python
"""
## TEMPORAL INFORMATION
When extracting facts, pay attention to temporal markers:
- "works at" vs "used to work at" vs "worked at in 2015"
- "met in 2018" -> contact_context with year
- "was CEO" vs "is CEO"

For each assertion where time is mentioned or implied:
- is_current: boolean (true if currently true, false if historical)
- valid_from: year or date when this became true
- valid_until: year or date when this stopped being true (for historical)

Example:
- "John was at Google from 2015 to 2020" ->
  predicate: "works_at", value: "Google", is_current: false, valid_from: "2015", valid_until: "2020"
- "Now he's at Meta" ->
  predicate: "works_at", value: "Meta", is_current: true, valid_from: "2020"
"""
```

---

## Phase 4: Relationship Strength Model (P1)

### 4.1 RFM Model (Recency, Frequency, Momentum)

This is critical for answering "who do I know well enough to ask for help?"

**Migration:**
```sql
-- 20250213130000_relationship_strength.sql

-- New table for relationship metrics
CREATE TABLE IF NOT EXISTS relationship_metrics (
    metrics_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL REFERENCES auth.users(id),
    person_id UUID NOT NULL REFERENCES person(person_id) ON DELETE CASCADE,

    -- RFM scores (0-100)
    recency_score INT DEFAULT 0,      -- When did we last interact?
    frequency_score INT DEFAULT 0,    -- How often do we interact?
    momentum_score INT DEFAULT 0,     -- Is relationship growing/fading?

    -- Composite
    relationship_strength INT DEFAULT 0,  -- Combined score 0-100
    tie_strength TEXT DEFAULT 'unknown'   -- 'strong', 'weak', 'dormant', 'unknown'
        CHECK (tie_strength IN ('strong', 'weak', 'dormant', 'unknown')),

    -- Raw data
    last_contact_at TIMESTAMPTZ,
    contact_count INT DEFAULT 0,
    first_contact_at TIMESTAMPTZ,

    -- Relationship depth (from assertions)
    -- Values: worked_together, did_business, studied_together, social_friends, met_once, online_only
    deepest_interaction TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(owner_id, person_id)
);

CREATE INDEX idx_relationship_metrics_owner ON relationship_metrics(owner_id, relationship_strength DESC);
CREATE INDEX idx_relationship_metrics_tie ON relationship_metrics(owner_id, tie_strength);

ALTER TABLE relationship_metrics ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users see own metrics" ON relationship_metrics
    FOR ALL USING (owner_id = auth.uid());

-- Function to calculate RFM scores
CREATE OR REPLACE FUNCTION calculate_rfm_scores(p_person_id UUID)
RETURNS TABLE (
    recency_score INT,
    frequency_score INT,
    momentum_score INT,
    relationship_strength INT,
    tie_strength TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_last_contact TIMESTAMPTZ;
    v_contact_count INT;
    v_first_contact TIMESTAMPTZ;
    v_days_since_last INT;
    v_recency INT;
    v_frequency INT;
    v_momentum INT;
    v_strength INT;
    v_tie TEXT;
    v_depth TEXT;
BEGIN
    -- Get metrics data
    SELECT
        last_contact_at,
        contact_count,
        first_contact_at,
        deepest_interaction
    INTO v_last_contact, v_contact_count, v_first_contact, v_depth
    FROM relationship_metrics
    WHERE person_id = p_person_id;

    -- Calculate recency (0-100)
    -- 100 = contact in last week
    -- 50 = contact in last month
    -- 20 = contact in last quarter
    -- 0 = no contact in year+
    IF v_last_contact IS NOT NULL THEN
        v_days_since_last := EXTRACT(DAY FROM now() - v_last_contact);
        v_recency := GREATEST(0, 100 - (v_days_since_last * 0.3)::INT);
    ELSE
        v_recency := 0;
    END IF;

    -- Calculate frequency (0-100)
    -- Based on contact_count
    v_frequency := LEAST(100, v_contact_count * 10);

    -- Calculate momentum (0-100)
    -- Compare recent activity to historical
    -- Simplified: just use recency for now
    v_momentum := v_recency;

    -- Composite strength
    v_strength := (v_recency * 0.4 + v_frequency * 0.4 + v_momentum * 0.2)::INT;

    -- Determine tie strength
    IF v_depth IN ('worked_together_on_project', 'did_business_together', 'studied_together') THEN
        v_tie := 'strong';
    ELSIF v_strength >= 60 THEN
        v_tie := 'strong';
    ELSIF v_strength >= 30 THEN
        v_tie := 'weak';
    ELSIF v_strength > 0 THEN
        v_tie := 'dormant';
    ELSE
        v_tie := 'unknown';
    END IF;

    RETURN QUERY SELECT v_recency, v_frequency, v_momentum, v_strength, v_tie;
END;
$$;
```

**Python service** (`/service/app/services/relationship.py`):
```python
class RelationshipService:
    """Service for tracking relationship strength."""

    DEPTH_WEIGHTS = {
        'worked_together_on_project': 100,
        'did_business_together': 90,
        'studied_together': 80,
        'traveled_together': 70,
        'social_friends': 50,
        'met_at_event': 30,
        'introduced_through_someone': 20,
        'online_only': 10
    }

    async def update_metrics_from_evidence(
        self,
        owner_id: UUID,
        person_id: UUID,
        evidence_date: datetime = None
    ):
        """Update metrics when new evidence is added."""
        supabase = get_supabase_admin()

        # Get or create metrics record
        existing = supabase.table("relationship_metrics").select("*").eq(
            "person_id", str(person_id)
        ).execute()

        if not existing.data:
            # Create initial record
            supabase.table("relationship_metrics").insert({
                "owner_id": str(owner_id),
                "person_id": str(person_id),
                "last_contact_at": (evidence_date or datetime.utcnow()).isoformat(),
                "first_contact_at": (evidence_date or datetime.utcnow()).isoformat(),
                "contact_count": 1
            }).execute()
        else:
            # Update existing
            metrics = existing.data[0]
            contact_date = evidence_date or datetime.utcnow()

            update_data = {
                "contact_count": metrics["contact_count"] + 1,
                "updated_at": datetime.utcnow().isoformat()
            }

            if not metrics["last_contact_at"] or contact_date > datetime.fromisoformat(
                metrics["last_contact_at"].replace('Z', '+00:00')
            ):
                update_data["last_contact_at"] = contact_date.isoformat()

            supabase.table("relationship_metrics").update(update_data).eq(
                "metrics_id", metrics["metrics_id"]
            ).execute()

        # Update depth from assertions
        await self.update_depth_from_assertions(owner_id, person_id)

    async def update_depth_from_assertions(self, owner_id: UUID, person_id: UUID):
        """Extract relationship depth from assertions."""
        supabase = get_supabase_admin()

        # Get relationship_depth assertions
        depth_assertions = supabase.table("assertion").select(
            "object_value"
        ).eq("subject_person_id", str(person_id)).eq(
            "predicate", "relationship_depth"
        ).execute()

        if not depth_assertions.data:
            return

        # Find deepest interaction
        deepest = None
        deepest_weight = 0
        for a in depth_assertions.data:
            depth = a["object_value"]
            weight = self.DEPTH_WEIGHTS.get(depth, 0)
            if weight > deepest_weight:
                deepest = depth
                deepest_weight = weight

        if deepest:
            supabase.table("relationship_metrics").update({
                "deepest_interaction": deepest
            }).eq("person_id", str(person_id)).execute()
```

---

## Phase 5: Search & Reasoning Improvements (P2)

### 5.1 Incorporate Confidence + Relationship Strength in Ranking

**Update `match_assertions` function:**
```sql
-- 20250213140000_improved_search.sql

CREATE OR REPLACE FUNCTION match_assertions_ranked(
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
    similarity float,
    relationship_strength int,
    tie_strength text,
    is_current boolean,
    final_score float
)
LANGUAGE sql STABLE
AS $$
    SELECT
        a.assertion_id,
        a.subject_person_id,
        a.predicate,
        a.object_value,
        a.confidence,
        1 - (a.embedding <=> query_embedding) as similarity,
        COALESCE(rm.relationship_strength, 0) as relationship_strength,
        COALESCE(rm.tie_strength, 'unknown') as tie_strength,
        COALESCE(a.is_current, true) as is_current,
        -- Final score combines: similarity (50%), confidence (20%), relationship (20%), recency (10%)
        (
            (1 - (a.embedding <=> query_embedding)) * 0.5 +
            a.confidence * 0.2 +
            COALESCE(rm.relationship_strength, 50)::float / 100 * 0.2 +
            CASE WHEN COALESCE(a.is_current, true) THEN 0.1 ELSE 0 END
        ) as final_score
    FROM assertion a
    JOIN person p ON a.subject_person_id = p.person_id
    LEFT JOIN relationship_metrics rm ON rm.person_id = p.person_id
    WHERE p.owner_id = p_owner_id
      AND p.status = 'active'
      AND a.embedding IS NOT NULL
      AND 1 - (a.embedding <=> query_embedding) > match_threshold
    ORDER BY final_score DESC
    LIMIT match_count;
$$;
```

### 5.2 Update Reasoning Prompt for Weak Ties

Add to `REASONING_SYSTEM_PROMPT` in `prompts.py`:
```python
"""
## WEAK TIES (Granovetter's Theory)

IMPORTANT: For many requests (especially job hunting, deals, new information),
WEAK TIES are more valuable than strong ones!

- Strong ties (worked together, close friends) -> same information bubble
- Weak ties (acquaintances, old colleagues) -> bridges to NEW information

When you see:
- tie_strength: "weak" or "dormant" - this is often MORE valuable for new opportunities
- relationship_depth: "met_at_event", "introduced_through_someone" - bridge contacts

Explicitly mention weak tie opportunities:
"Maria is a weak tie (met at conference), but weak ties are often best for
finding new opportunities - she likely has access to different networks than you."
"""
```

---

## Phase 6: Edge Dynamics (P2)

### 6.1 Problem

Edge weights are static and don't reflect actual interaction patterns.

### 6.2 Solution: Evidence-based edge weights

**Migration:**
```sql
-- 20250213150000_edge_dynamics.sql

-- Add dynamics to edges
ALTER TABLE edge ADD COLUMN IF NOT EXISTS evidence_count INT DEFAULT 1;
ALTER TABLE edge ADD COLUMN IF NOT EXISTS last_evidence_at TIMESTAMPTZ;
ALTER TABLE edge ADD COLUMN IF NOT EXISTS first_evidence_at TIMESTAMPTZ DEFAULT now();

-- Auto-update weight based on evidence count
CREATE OR REPLACE FUNCTION recalculate_edge_weight()
RETURNS TRIGGER AS $$
BEGIN
    -- Weight = base (0.5) + log(evidence_count) * 0.2
    -- Caps at 2.0
    NEW.weight := LEAST(2.0, 0.5 + ln(GREATEST(1, NEW.evidence_count)) * 0.2);
    NEW.last_evidence_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tr_edge_weight
    BEFORE UPDATE ON edge
    FOR EACH ROW EXECUTE FUNCTION recalculate_edge_weight();
```

**Python update** - increment edge evidence when mentioned:
```python
def update_edge_evidence(src_id: str, dst_id: str, edge_type: str):
    # Try to update existing edge
    result = supabase.table("edge").update({
        "evidence_count": supabase.raw("evidence_count + 1")
    }).eq("src_person_id", src_id).eq(
        "dst_person_id", dst_id
    ).eq("edge_type", edge_type).execute()

    if not result.data:
        # Create new edge
        supabase.table("edge").insert({
            "src_person_id": src_id,
            "dst_person_id": dst_id,
            "edge_type": edge_type,
            "evidence_count": 1
        }).execute()
```

---

## Phase 7: Centrality Metrics (P3 - Future)

### 7.1 Basic Implementation

For MVP, we can compute centrality on-demand rather than storing it.

**Migration:**
```sql
-- 20250213160000_centrality_metrics.sql

-- Simple degree centrality function
CREATE OR REPLACE FUNCTION get_degree_centrality(p_owner_id UUID)
RETURNS TABLE (
    person_id UUID,
    display_name TEXT,
    out_degree INT,  -- How many people they know
    in_degree INT,   -- How many people know them (in user's network)
    total_degree INT
)
LANGUAGE sql STABLE
AS $$
    WITH out_edges AS (
        SELECT e.src_person_id, COUNT(*) as cnt
        FROM edge e
        JOIN person p ON e.src_person_id = p.person_id
        WHERE p.owner_id = p_owner_id AND p.status = 'active'
        GROUP BY e.src_person_id
    ),
    in_edges AS (
        SELECT e.dst_person_id, COUNT(*) as cnt
        FROM edge e
        JOIN person p ON e.dst_person_id = p.person_id
        WHERE p.owner_id = p_owner_id AND p.status = 'active'
        GROUP BY e.dst_person_id
    )
    SELECT
        p.person_id,
        p.display_name,
        COALESCE(o.cnt, 0)::INT as out_degree,
        COALESCE(i.cnt, 0)::INT as in_degree,
        (COALESCE(o.cnt, 0) + COALESCE(i.cnt, 0))::INT as total_degree
    FROM person p
    LEFT JOIN out_edges o ON p.person_id = o.src_person_id
    LEFT JOIN in_edges i ON p.person_id = i.dst_person_id
    WHERE p.owner_id = p_owner_id AND p.status = 'active'
    ORDER BY total_degree DESC;
$$;
```

---

## Implementation Priority & Timeline

### Week 1: Critical Fixes (P0)
- [ ] 1.1 Identity conflict detection
- [ ] 1.2 Pre-insertion dedup check
- [ ] Tests for both

### Week 2: Data Quality (P1)
- [ ] 2.1 Assertion deduplication
- [ ] 3.1 Temporal model
- [ ] 3.2 Extraction prompt updates

### Week 3: Relationship Model (P1)
- [ ] 4.1 Relationship metrics table
- [ ] 4.2 RFM calculation
- [ ] 4.3 Integration with extraction

### Week 4: Search Improvements (P2)
- [ ] 5.1 Ranked search function
- [ ] 5.2 Reasoning prompt updates
- [ ] 6.1 Edge dynamics

### Future (P3)
- [ ] 7.1 Centrality metrics
- [ ] Community detection (Louvain)
- [ ] Trust propagation

---

## Critical Files for Implementation

| File | Purpose |
|------|---------|
| `/service/app/api/process.py` | Core extraction pipeline - fix identity conflicts (lines 113-117), add pre-dedup check |
| `/service/app/services/dedup.py` | Dedup service - add `find_existing_person_match`, update `merge_persons` for assertion dedup |
| `/service/app/agents/prompts.py` | Extraction/reasoning prompts - add temporal awareness, weak ties guidance |
| `/service/app/api/search.py` | Search endpoint - integrate `match_assertions_ranked`, add relationship context |
| `/supabase/migrations/` | New migrations for schema changes |

---

## Research Sources

### Current Model Analysis
- 14 predicates: works_at, role_is, strong_at, can_help_with, worked_on, background, located_in, speaks_language, interested_in, reputation_note, contact_context, relationship_depth, recommend_for, not_recommend_for
- 5 identity namespaces: freeform_name, telegram_username, email, linkedin_url, phone
- 6 edge types: knows, recommended, worked_with, in_same_group, introduced_by, collaborates_with

### Industry Practices
- **Monica CRM**: Activity timeline, relationship types, reminders
- **Clay**: RFM model (Recency, Frequency, Momentum), waterfall enrichment
- **Folk**: Flexible custom fields, smart lists

### Theoretical Models
- **Granovetter's Weak Ties**: Weak ties bridge different networks, crucial for new opportunities
- **Network Centrality**: Betweenness (bridges), Degree (connections), Closeness (reach)
- **Community Detection**: Louvain algorithm for clustering
- **Trust Propagation**: Transitive trust with decay over path length
