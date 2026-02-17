# Company Search Fixes — One-Shot Implementation Plan

> Этот файл содержит всё необходимое для имплементации fixes в one-shot режиме.
> После compaction запустить агентов по инструкциям ниже.

---

## Context: QA Findings (2026-02-13)

**Database stats**: 2,032 people, 21,971 assertions, 99.995% embedding coverage

| Проблема | Реальные данные | Impact |
|----------|-----------------|--------|
| **ByteDance в met_on** | 5 людей, 100% invisible | 🔴 CRITICAL |
| **Tinkoff rebrand** | 7 людей / 3 варианта, 86% loss | 🔴 HIGH |
| **Yandex variants** | 38 людей / 11 вариантов, 34% loss | 🟠 HIGH |
| **Company fragmentation** | 1,318 строк / ~400 реальных (3.3x) | 🟡 MEDIUM |
| **Threshold 0.3** | Слишком много мусора в результатах | 🟡 MEDIUM |

---

## Implementation Plan

### Phase 1: Multi-Predicate Search + Threshold (Quick Win)
**Effort**: 2-4 часа
**Impact**: Исправит ByteDance 100% loss + уменьшит мусор

### Phase 2: Simple Normalization
**Effort**: 1-2 часа
**Impact**: Исправит Yandex 34% + Tinkoff 86% loss

---

## Phase 1: Multi-Predicate Search

### 1.1 Problem
Текущий поиск в `find_people` tool ищет только по `works_at`. Люди из встреч (met_on), знакомые (knows) — невидимы.

### 1.2 Files to Change

**Primary**: `/Users/evgenyq/Projects/atlantisplus/service/app/api/chat.py`
- Function: `find_people` tool (lines ~567-723)
- Current: searches only assertions, no predicate filter
- Change: add predicate weighting + multi-predicate search

**Secondary**: `/Users/evgenyq/Projects/atlantisplus/service/app/api/search.py`
- Function: `search_network` (lines ~34-241)
- Current: `match_threshold: 0.3`
- Change: `match_threshold: 0.4`

### 1.3 Implementation Details

#### Step 1: Update threshold in search.py

```python
# search.py line ~55
# BEFORE:
match_result = supabase.rpc(
    'match_assertions',
    {
        'query_embedding': query_embedding,
        'match_threshold': 0.3,  # ← OLD
        'match_count': 20,
        'p_owner_id': user_id
    }
).execute()

# AFTER:
match_result = supabase.rpc(
    'match_assertions',
    {
        'query_embedding': query_embedding,
        'match_threshold': 0.4,  # ← NEW: balanced
        'match_count': 20,
        'p_owner_id': user_id
    }
).execute()
```

#### Step 2: Add predicate weights in chat.py

Add at top of file (after imports):

```python
# Predicate relevance weights for different query types
COMPANY_PREDICATES = {
    'works_at': 1.0,      # Direct employment - highest
    'met_on': 0.8,        # Met at meeting/conference
    'knows': 0.7,         # Personal connection
    'contact_context': 0.6,  # How we met (may mention company)
    'worked_on': 0.5,     # Past projects (may mention company)
    'background': 0.4,    # Career history
}
```

#### Step 3: Update find_people function

Find the semantic search section in `find_people` tool and update:

```python
# BEFORE (approximate location ~600-650):
# Current code only searches all assertions without predicate awareness

# AFTER: Add company-specific search when query mentions company
async def search_by_company_mention(query: str, user_id: str, supabase) -> list:
    """
    Search across multiple predicates for company mentions.
    Returns list of (person_id, predicate, object_value, weight) tuples.
    """
    results = []

    # Extract potential company name from query
    # Simple heuristic: look for capitalized words or known patterns
    company_keywords = extract_company_from_query(query)

    if company_keywords:
        for predicate, weight in COMPANY_PREDICATES.items():
            # Search this predicate for company mention
            matches = supabase.table('assertion').select(
                'subject_person_id, predicate, object_value, confidence'
            ).eq('predicate', predicate).ilike(
                'object_value', f'%{company_keywords}%'
            ).execute()

            for match in matches.data:
                results.append({
                    'person_id': match['subject_person_id'],
                    'predicate': match['predicate'],
                    'object_value': match['object_value'],
                    'weight': weight * match['confidence'],
                    'match_type': 'company_mention'
                })

    return results

def extract_company_from_query(query: str) -> str | None:
    """
    Extract company name from query.
    Examples:
    - "кто из ByteDance" → "ByteDance"
    - "кто работает в Google" → "Google"
    - "интро в Яндекс" → "Яндекс"
    """
    import re

    # Patterns for company extraction
    patterns = [
        r'(?:из|from|at|в|into)\s+([A-ZА-Яa-zа-я][A-Za-zА-Яа-я0-9\.\-]+)',
        r'(?:компани[яию]|company)\s+([A-ZА-Яa-zа-я][A-Za-zА-Яа-я0-9\.\-]+)',
        r'([A-Z][A-Za-z0-9\.]+(?:\s+(?:Inc|LLC|Ltd|Corp))?)',  # Capitalized with suffix
    ]

    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return None
```

#### Step 4: Integrate into find_people main logic

In the `find_people` function, after the existing semantic search:

```python
# Add company-specific search results
company_results = await search_by_company_mention(query, user_id, supabase)

# Merge with semantic results
# Deduplicate by person_id, keep highest weight
all_results = {}
for r in semantic_results + company_results:
    pid = r['person_id']
    if pid not in all_results or r.get('weight', 0) > all_results[pid].get('weight', 0):
        all_results[pid] = r

# Sort by weight descending
sorted_results = sorted(all_results.values(), key=lambda x: x.get('weight', 0), reverse=True)
```

### 1.4 Testing Phase 1

After implementation, test these queries:

```
Test 1: "кто из ByteDance"
Expected: Should find 5 people from met_on predicate (was 0)

Test 2: "с кем из Google я встречался"
Expected: Should find people from met_on, not just works_at

Test 3: "кто работает в Yandex"
Expected: Should still work (regression test)

Test 4: Random query without company
Expected: Should not break (regression test)
```

SQL verification:
```sql
-- Verify ByteDance people exist in met_on
SELECT p.display_name, a.predicate, a.object_value
FROM assertion a
JOIN person p ON a.subject_person_id = p.person_id
WHERE a.object_value ILIKE '%bytedance%';
-- Expected: 5 rows, all with predicate='met_on'
```

---

## Phase 2: Simple Normalization

### 2.1 Problem
Companies stored as raw strings: "Google", "Google LLC", "Гугл" = 3 different entries.

### 2.2 Solution: object_value_normalized column

Add a normalized column that stores lowercase, trimmed version for grouping/filtering.

### 2.3 Files to Change

**Database Migration**: New migration file
**Extraction**: `/Users/evgenyq/Projects/atlantisplus/service/app/api/process.py`
**Search**: Already covered in Phase 1

### 2.4 Implementation Details

#### Step 1: Create migration

File: `/Users/evgenyq/Projects/atlantisplus/supabase/migrations/YYYYMMDDHHMMSS_add_normalized_company.sql`

```sql
-- Add normalized column for company grouping
ALTER TABLE assertion
ADD COLUMN IF NOT EXISTS object_value_normalized TEXT;

-- Create index for fast lookups
CREATE INDEX IF NOT EXISTS idx_assertion_normalized
ON assertion(object_value_normalized)
WHERE predicate = 'works_at' AND object_value_normalized IS NOT NULL;

-- Function to normalize company names
CREATE OR REPLACE FUNCTION normalize_company_name(name TEXT)
RETURNS TEXT
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    result TEXT;
BEGIN
    IF name IS NULL THEN
        RETURN NULL;
    END IF;

    -- Lowercase and trim
    result := lower(trim(name));

    -- Remove common suffixes
    result := regexp_replace(result, '\s*(inc\.?|llc\.?|ltd\.?|gmbh|corp\.?|corporation|company|co\.?)$', '', 'i');

    -- Remove extra whitespace
    result := regexp_replace(result, '\s+', ' ', 'g');

    -- Trim again
    result := trim(result);

    RETURN result;
END;
$$;

-- Backfill existing data
UPDATE assertion
SET object_value_normalized = normalize_company_name(object_value)
WHERE predicate = 'works_at'
  AND object_value IS NOT NULL
  AND object_value_normalized IS NULL;

-- Create trigger for future inserts/updates
CREATE OR REPLACE FUNCTION trigger_normalize_company()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.predicate = 'works_at' AND NEW.object_value IS NOT NULL THEN
        NEW.object_value_normalized := normalize_company_name(NEW.object_value);
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS assertion_normalize_company ON assertion;
CREATE TRIGGER assertion_normalize_company
BEFORE INSERT OR UPDATE OF object_value ON assertion
FOR EACH ROW
EXECUTE FUNCTION trigger_normalize_company();
```

#### Step 2: Update search to use normalized column

In chat.py `search_by_company_mention`:

```python
# BEFORE:
matches = supabase.table('assertion').select(
    'subject_person_id, predicate, object_value, confidence'
).eq('predicate', predicate).ilike(
    'object_value', f'%{company_keywords}%'
).execute()

# AFTER: Use normalized for matching, return original for display
normalized_query = normalize_company_name(company_keywords)
matches = supabase.table('assertion').select(
    'subject_person_id, predicate, object_value, object_value_normalized, confidence'
).eq('predicate', predicate).or_(
    f'object_value_normalized.eq.{normalized_query},'
    f'object_value_normalized.ilike.%{normalized_query}%'
).execute()
```

Add Python normalization function to match SQL:

```python
def normalize_company_name(name: str) -> str:
    """Normalize company name for matching. Must match SQL function."""
    import re
    if not name:
        return ""

    result = name.lower().strip()

    # Remove common suffixes
    result = re.sub(
        r'\s*(inc\.?|llc\.?|ltd\.?|gmbh|corp\.?|corporation|company|co\.?)$',
        '',
        result,
        flags=re.IGNORECASE
    )

    # Normalize whitespace
    result = re.sub(r'\s+', ' ', result).strip()

    return result
```

### 2.5 Testing Phase 2

```sql
-- Test normalization function
SELECT normalize_company_name('Google LLC');  -- → 'google'
SELECT normalize_company_name('Yandex N.V.'); -- → 'yandex n.v' or 'yandex'
SELECT normalize_company_name('Tinkoff Bank'); -- → 'tinkoff bank'

-- Test grouping works
SELECT
    object_value_normalized,
    COUNT(DISTINCT subject_person_id) as people_count,
    array_agg(DISTINCT object_value) as variants
FROM assertion
WHERE predicate = 'works_at'
GROUP BY object_value_normalized
HAVING COUNT(DISTINCT object_value) > 1
ORDER BY people_count DESC
LIMIT 20;
-- Should show Yandex variants grouped together
```

API test:
```
Query: "кто из Яндекса"
Expected: Should find people with "Yandex", "Яндекс", "Yandex.Market" etc.
```

---

## Agent Instructions

### For Implementation Agent

```
You are implementing company search fixes for atlantisplus.

IMPORTANT RULES:
1. Make changes incrementally - one file at a time
2. Test after each change before proceeding
3. Do NOT create new files unless specified
4. Preserve existing functionality (regression safety)
5. Follow rate limiting for Supabase (max 3 concurrent queries, 1s delays)

PHASE 1 ORDER:
1. Update threshold in search.py (0.3 → 0.4)
2. Add COMPANY_PREDICATES constant to chat.py
3. Add extract_company_from_query function to chat.py
4. Add search_by_company_mention function to chat.py
5. Integrate into find_people main logic
6. Test with ByteDance query

PHASE 2 ORDER:
1. Create migration file
2. Apply migration: supabase db push
3. Verify backfill worked
4. Add normalize_company_name Python function to chat.py
5. Update search to use normalized column
6. Test with Yandex/Tinkoff queries

After each phase, run verification queries and report results.
```

### For QA Agent (Post-Implementation)

```
You are verifying company search fixes.

TEST CASES:
1. ByteDance (met_on): "кто из ByteDance" → expect 5 people (was 0)
2. Yandex variants: "кто из Яндекса" → expect 38+ people across variants
3. Tinkoff rebrand: "кто из Тинькофф" → expect 7+ people
4. Threshold: random query → less noise than before
5. Regression: existing searches still work

RATE LIMITING:
- Max 3 concurrent Supabase queries
- 1 second delay between queries
- Stop immediately on Error 522

Report: pass/fail for each test with actual vs expected numbers.
```

---

## Parallel Execution Strategy

These phases CAN be run in parallel by separate agents:

```
Agent 1: Phase 1 (chat.py + search.py changes)
Agent 2: Phase 2 (migration + normalization)

No conflicts because:
- Phase 1 changes Python code
- Phase 2 changes database schema + adds new column
- Both touch chat.py but different functions

Merge point: After both complete, final integration test
```

---

## Rollback Plan

If something breaks:

**Phase 1 rollback**:
```python
# Revert threshold to 0.3
# Remove COMPANY_PREDICATES and related functions
# find_people reverts to semantic-only search
```

**Phase 2 rollback**:
```sql
-- Drop column (data preserved in object_value)
ALTER TABLE assertion DROP COLUMN IF EXISTS object_value_normalized;
DROP FUNCTION IF EXISTS normalize_company_name;
DROP FUNCTION IF EXISTS trigger_normalize_company;
DROP TRIGGER IF EXISTS assertion_normalize_company ON assertion;
```

---

## Success Criteria

| Metric | Before | After Target |
|--------|--------|--------------|
| ByteDance recall | 0% | 100% |
| Yandex recall | 66% | 95%+ |
| Tinkoff recall | 14% | 90%+ |
| Search noise | High | Reduced |
| Regressions | N/A | 0 |

---

## Files Summary

| File | Phase | Changes |
|------|-------|---------|
| `service/app/api/search.py` | 1 | threshold 0.3→0.4 |
| `service/app/api/chat.py` | 1+2 | COMPANY_PREDICATES, extract_company, search_by_company, normalize |
| `supabase/migrations/XXX.sql` | 2 | New migration for normalized column |

---

## Post-Implementation

After both phases complete:

1. Run full QA test suite
2. Deploy to Railway: `cd service && railway up`
3. Apply migration: `supabase db push`
4. Monitor for errors in Railway logs
5. Test in production Mini App

---

## Appendix: Known Company Variants

For reference during testing:

**Yandex** (11 variants): Yandex, Яндекс, Yandex.Market, Yandex Go, Yandex Cloud, Yandex LLC, Yandex.Taxi, etc.

**Tinkoff** (3 variants): Tinkoff, Tinkoff Bank, T-Bank

**Meta** (2 variants): Meta, Facebook

**Google** (1 variant): Google (no Alphabet in database)
