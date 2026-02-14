# Postmortem: Tier 2 Search Architecture Overhaul

> Date: 2026-02-14
> Status: RESOLVED
> Duration: ~4 hours debugging, ~2 hours implementation
> Author: Claude Code + Evgeny

---

## Executive Summary

Complete rewrite of Tier 2 (Dig Deeper) search from broken state to working production system. Changed from 16 specialized tools with fragile extraction logic to 2 tools (SQL + report_results) with agent-driven queries.

**Results:**
- Tier 1: 40+ seconds → **8 seconds** (5x faster)
- Tier 2: 0 people found → **38 people found** (was completely broken)
- Architecture: 16 tools → **2 tools** (simpler, more flexible)

---

## Problem Statement

### What Was Broken

1. **Tier 1 (fast search)** took 40+ seconds due to `filter_and_motivate_results()` calling gpt-4o-mini for every search

2. **Tier 2 (Dig Deeper)** returned 0 people after 10 iterations:
   - Agent would search, find people, but "forget" them
   - `found_people` was overwritten (not accumulated) on each `report_results` call
   - Retry logic at max_iterations didn't work
   - Context grew to 150KB+ causing agent to lose early results

3. **Architectural issues:**
   - 16 specialized tools with different response formats
   - 4 different places extracting people from tool results
   - Each tool had different JSON structure (people[] vs assertions[])
   - Silent failures when parsing failed

### Root Cause Analysis

```
┌─────────────────────────────────────────────────────────────┐
│                    OLD ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Agent calls: find_people, search_by_company_exact,         │
│               semantic_search_raw, explore_company_names... │
│                        ↓                                    │
│  Each tool returns DIFFERENT format:                        │
│  - find_people: {people: [{person_id, name, motivation}]}   │
│  - semantic_search_raw: {assertions: [{subject_person_id}]} │
│  - explore_company_names: {variations: [...]}               │
│                        ↓                                    │
│  Code intercepts in 4 places trying to extract people       │
│  Different logic in each place, some tools missed           │
│                        ↓                                    │
│  found_people = args.get("people", [])  ← OVERWRITES!       │
│                        ↓                                    │
│  Result: 0 people after 10 iterations                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Solution Implemented

### New Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    NEW ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Agent has 2 tools:                                         │
│  1. execute_sql - write any SELECT query                    │
│  2. report_results - report found people at the end         │
│                        ↓                                    │
│  Agent writes SQL based on system prompt with DB schema     │
│  "SELECT p.person_id, p.display_name FROM person p          │
│   JOIN assertion a ON ... WHERE a.object_value_normalized   │
│   ILIKE '%yandex%'"                                         │
│                        ↓                                    │
│  SQL tool: validates, adds owner filter CTE, executes       │
│                        ↓                                    │
│  Agent accumulates results across iterations (dict, not     │
│  list) and calls report_results with ALL found people       │
│                        ↓                                    │
│  Result: 38 people from 7 iterations                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Key Changes

#### 1. Tier 1 Speedup (chat.py)

**Removed** `filter_and_motivate_results()` call from `find_people`:

```python
# BEFORE (slow - called gpt-4o-mini for every search)
if results and len(results) > 1:
    results = await filter_and_motivate_results(query, results, ...)

# AFTER (fast - no LLM call)
# NOTE: Removed filter_and_motivate_results() call to speed up Tier 1
```

**Added timing logs** for diagnosis:
```python
t0 = _time.time()
query_embedding = generate_embedding(query)
print(f"[FIND_PEOPLE] Embedding generated in {(t1-t0)*1000:.0f}ms")
# ... pgvector search ...
print(f"[FIND_PEOPLE] pgvector search in {(t2-t1)*1000:.0f}ms")
```

#### 2. New Claude Agent v2 (claude_agent_v2.py)

Key improvements:

```python
class ClaudeAgentV2:
    def __init__(self, ...):
        # Accumulated results (dict to avoid duplicates)
        self._found_people: dict[str, dict] = {}  # person_id -> {name, reason}

    def _accumulate_people(self, people: list[dict]):
        """Add people to accumulated results (deduped by person_id)."""
        for p in people:
            pid = p.get("person_id")
            if pid and pid not in self._found_people:
                self._found_people[pid] = {...}

    def _serialize_content(self, content: list) -> list:
        """Convert Pydantic content blocks to dict for API reuse."""
        # Fixes: TypeError: 'NoneType' object cannot be converted to 'PyBool'
```

**Force report_results on last iteration:**
```python
tool_choice = {"type": "tool", "name": "report_results"} if force_report else {"type": "auto"}
```

#### 3. SQL Tool (sql_tool.py)

5 levels of security:

| Level | Protection |
|-------|------------|
| 1 | Whitelist SELECT only (no INSERT/UPDATE/DELETE) |
| 2 | Block write keywords with word boundaries |
| 3 | Block system tables (auth.*, pg_*, information_schema) |
| 4 | CTE wrapper auto-filters all tables by owner_id |
| 5 | Statement timeout (5 seconds) via RPC function |

```python
def add_owner_filter(query: str, user_id: str) -> str:
    """Wrap query in CTE that pre-filters all tables by owner_id."""
    return f"""
    WITH
        person AS (SELECT * FROM public.person WHERE owner_id = '{user_id}'::uuid),
        assertion AS (SELECT a.* FROM public.assertion a
                      JOIN public.person p ON a.subject_person_id = p.person_id
                      WHERE p.owner_id = '{user_id}'::uuid),
        ...
    {query}
    """
```

#### 4. System Prompt with DB Schema

Agent now knows the database structure:

```
## DATABASE SCHEMA

**person** — canonical person entity
- person_id (UUID PK), display_name (TEXT), status ('active'|'merged'|'deleted')

**assertion** — atomic facts about people
- subject_person_id (UUID FK → person)
- predicate: works_at, role_is, can_help_with, strong_at, knows, met_on...
- object_value (TEXT), object_value_normalized (TEXT)

## SEARCH STRATEGY
1. Company search: Use object_value_normalized for exact match
2. Skill search: Search in can_help_with, strong_at predicates
...
```

---

## Files Changed

| File | Change |
|------|--------|
| `service/app/api/chat.py` | Removed motivations, added timing, integrated v2 agent |
| `service/app/services/claude_agent_v2.py` | **NEW** - Production agent with accumulation |
| `service/app/services/sql_tool.py` | **NEW** - Secure SQL execution |
| `service/tests/test_sql_tool.py` | **NEW** - 38 test cases |
| `supabase/migrations/20260214120000_add_readonly_query_function.sql` | **NEW** - RPC with timeout |

---

## Performance Metrics

### Tier 1 (Fast Search)

| Metric | Before | After |
|--------|--------|-------|
| Total time | 40+ sec (timeout) | **8 sec** |
| Embedding | ~1.2 sec | ~1.2 sec |
| pgvector | ~2.7 sec | ~2.7 sec |
| LLM motivations | ~40 sec | **0 sec** (removed) |

### Tier 2 (Dig Deeper)

| Metric | Before | After |
|--------|--------|-------|
| Total time | 2+ min | **~60 sec** |
| Iterations | 10 (max, stuck) | 7 (completed) |
| People found | 0 | **38** |
| Tools used | 16 specialized | 2 (SQL + report) |

---

## Lessons Learned

### 1. Don't Make LLM Do What Code Does Better

> "We keep making LLM do tasks code does better (aggregation, format following)"

The old architecture had the agent call specialized tools, then code tried to parse different response formats. The new architecture:
- Agent writes SQL (flexible, creative)
- Code executes SQL (deterministic, secure)
- Agent reports results (structured output)

### 2. Accumulate, Don't Overwrite

```python
# BAD: Iteration 9 overwrites iterations 1-8
found_people = args.get("people", [])

# GOOD: Dict accumulates unique people
self._found_people[pid] = {...}  # Only adds if not exists
```

### 3. Serialize Pydantic Objects Before Reuse

Anthropic SDK returns Pydantic models. Adding `response.content` directly to messages causes:
```
TypeError: argument 'by_alias': 'NoneType' object cannot be converted to 'PyBool'
```

Fix: Convert to dict first:
```python
messages.append({"role": "assistant", "content": self._serialize_content(response.content)})
```

### 4. Give Agent the Schema, Not the Tools

Instead of 16 tools with hardcoded logic:
```python
TOOLS = [find_people, search_by_company_exact, search_by_name_fuzzy,
         semantic_search_raw, explore_company_names, ...]
```

Give agent the DB schema and one flexible tool:
```python
TOOLS = [execute_sql, report_results]
SYSTEM_PROMPT = """
## DATABASE SCHEMA
- person: person_id, display_name, status
- assertion: subject_person_id, predicate, object_value_normalized
...
"""
```

---

## What's Next

1. **Monitor production** - Watch for SQL injection attempts, slow queries
2. **Add caching** - Cache common embeddings to speed up Tier 1
3. **Improve Tier 1 recall** - Company name normalization could be better ("Яндекса" → "Yandex")
4. **Consider compaction** - For very long agent sessions, use Anthropic's `betas=["compact-2026-01-12"]`

---

## Appendix: Test Results

**Query:** "кто из Яндекса?" (who from Yandex?)

**Tier 1:** 20 people, 8 seconds
**Tier 2:** 38 people, 60 seconds (+18 additional)

**What Tier 2 found that Tier 1 missed:**
- Different spellings (Yandex vs Яндекс)
- Subsidiaries (Yandex Cloud, Taxi, Eats, Market, Maps)
- Related companies (Яндекс Практикум, Яндекс Банк)
- Former employees (background predicate)
- Met-at connections (met_on predicate)
