# Code Review: Architectural Issues Report

**Date:** 2026-02-15
**Reviewers:** 4 AI agents (DRY, Complexity, Architecture, Frontend)
**Scope:** Full codebase analysis

---

## Executive Summary

| Category | Issues Found | Critical | High | Medium |
|----------|-------------|----------|------|--------|
| DRY Violations | 10 | 1 | 2 | 7 |
| Complexity | 8 | 2 | 3 | 3 |
| Architecture | 12 | 3 | 4 | 5 |
| Frontend | 15 | 4 | 4 | 7 |
| **Total** | **45** | **10** | **13** | **22** |

### Top 5 Critical Issues

1. **BUG: `search_request` typo in search.py:56** — endpoint broken
2. **God Function: `execute_tool()` — 950+ lines, 30+ elif branches**
3. **Code duplication: handlers.py duplicates process.py (~160 lines)**
4. **Frontend: PeoplePage.tsx — 877 lines, monolithic**
5. **No service layer — API handlers contain business logic + DB calls**

---

## Part 1: Backend DRY & Redundancy

### Critical Bug

**File:** `service/app/api/search.py:56`

```python
query_embedding = generate_embedding(search_search_request.query)
#                                     ^^^^^^^^^^^^^^^^^^^^^^
# Should be: search_request.query
```

**Impact:** `/search` endpoint throws NameError on every call.

### DRY Violations

| Issue | Files | Lines | Fix Effort |
|-------|-------|-------|------------|
| Duplicate `find_person()` helper | chat.py | 1126, 1231 | 15 min |
| Duplicate `update_status/rollback` | import_linkedin.py, import_calendar.py | 338, 275 | 30 min |
| Unused `CLAUDE_SYSTEM_PROMPT` | chat.py | 1978-2009 | 1 min |
| Unused `extract_from_text()` | extraction.py | 8-41 | 1 min |
| TOOLS list (450 lines inline) | chat.py | 130-576 | 20 min |

### Dead Code

- `extract_from_text()` — never imported, only `extract_from_text_simple()` used
- `CLAUDE_SYSTEM_PROMPT` — defined but never used (ClaudeAgentV2 has its own)
- `ExtractionResult` import in process.py — not used directly

---

## Part 2: Complexity Analysis

### God Function: `execute_tool()`

**File:** `service/app/api/chat.py:674-1626`
**Lines:** ~950
**Cyclomatic Complexity:** ~35+

Contains 20+ tool handlers as elif branches:
- `find_people` (200 lines)
- `get_person_details` (70 lines)
- `merge_people` (60 lines)
- ... and 17 more

**Recommendation:** Extract to handler classes:

```python
TOOL_HANDLERS = {
    "find_people": FindPeopleHandler(),
    "get_person_details": GetPersonDetailsHandler(),
    # ...
}

async def execute_tool(tool_name: str, args: dict, user_id: str) -> str:
    handler = TOOL_HANDLERS.get(tool_name)
    if not handler:
        return f"Unknown tool: {tool_name}"
    return await handler.execute(args, user_id)
```

### Code Duplication: handlers.py ↔ process.py

**~160 lines** of nearly identical logic:
- Create raw_evidence
- Call extraction
- Create persons
- Generate embeddings
- Create assertions

`handle_note_message_direct()` should call `process_pipeline()` instead of duplicating.

### Long Methods

| Function | File | Lines | Recommendation |
|----------|------|-------|----------------|
| `execute_tool` | chat.py | 950 | Split into handlers |
| `process_linkedin_import_background` | import_linkedin.py | 260 | Split into phases |
| `chat` endpoint | chat.py | 150 | Extract tool loop |

### Code Smells

- **Primitive Obsession:** Results returned as `dict` instead of dataclasses
- **Data Clump:** `NAME_SYNONYMS` hardcoded in execute_tool
- **Global Mutable State:** `PENDING_DIG_DEEPER_QUERIES` dict

---

## Part 3: Architecture Issues

### Layering Problems

**Current:**
```
API Handler → Database (direct supabase.table() calls)
```

**Recommended:**
```
API Handler → Service Layer → Repository → Database
```

**Example problem in chat.py:**
```python
# Business logic mixed with DB access in API handler
person_result = supabase.table('person').select(
    'person_id, display_name'
).eq('person_id', args['person_id']).execute()
```

### Dependency Issues

1. **No connection pooling** — `get_supabase_admin()` creates new client each call
2. **Circular import risk** — handlers.py imports from api/chat.py
3. **Singletons via global variables** — hard to test

### N+1 Query Pattern

**File:** `chat.py:87-109`

```python
for predicate, weight in COMPANY_PREDICATES.items():
    matches = supabase.table('assertion').select(...).execute()
```

6 predicates = 6 separate queries. Should be single query with IN clause.

### Missing Indexes

```python
.ilike('display_name', f'%{query}%')  # Full table scan
```

Needs: `CREATE INDEX ... USING gin (display_name gin_trgm_ops)`

### Blocking in Telegram Handlers

Webhook handler **waits** for Whisper + GPT-4o + DB inserts synchronously.
Should use `asyncio.create_task()` for heavy processing.

### Security: CORS Too Permissive

```python
allow_origins=["*"],
allow_credentials=True,
```

Should restrict to:
```python
allow_origins=["https://evgenyq.github.io", "https://web.telegram.org"]
```

---

## Part 4: Frontend Issues

### Monolithic Components

| Component | Lines | Should Be |
|-----------|-------|-----------|
| PeoplePage.tsx | 877 | 6-8 components |
| HomePage.tsx | 1239 | 5-6 components |
| icons/index.tsx | 1184 | Separate files |

### No Shared State

Each page fetches data independently. Navigating People → Chat → People reloads everything.

**Recommendation:** Use Zustand or React Context for people/evidence state.

### Missing useMemo

```typescript
// Recalculated on every render
const ownPeople = people.filter(p => p.owner_id === currentUserId);
const filteredPeople = displayPeople.filter(p => ...);
```

### TypeScript Issues

- `any` types in ChatPage.tsx
- No generated Supabase types
- Inconsistent Person interface

### Performance

- No virtualization for 5000+ contacts
- All icons in single file (not tree-shakable)

### Accessibility

- `<li onClick>` — should be `<button>`
- No focus management in modals
- Missing ARIA labels

---

## Priority Matrix

### P0 — Fix Immediately

| Issue | File | Effort |
|-------|------|--------|
| `search_search_request` typo | search.py:56 | 1 min |
| Blocking telegram handlers | handlers.py | 2 hours |

### P1 — Fix This Week

| Issue | File | Effort |
|-------|------|--------|
| Split `execute_tool()` | chat.py | 2-3 days |
| Remove handlers.py duplication | handlers.py | 4 hours |
| Add input validation | all Pydantic models | 2 hours |
| Singleton clients (@lru_cache) | supabase_client.py | 1 hour |

### P2 — Fix This Month

| Issue | File | Effort |
|-------|------|--------|
| Extract service layer | new files | 1 week |
| Split PeoplePage.tsx | frontend | 1 day |
| Generate Supabase types | frontend | 1 hour |
| Add pg_trgm indexes | migrations | 1 hour |

### P3 — Backlog

| Issue | Effort |
|-------|--------|
| Parallel tool execution | 2 hours |
| Virtualization for lists | 4 hours |
| Task queue (Celery/ARQ) | 2 days |
| OpenTelemetry | 1 day |

---

## Metrics

### chat.py Breakdown (2144 lines)

| Section | Lines | % |
|---------|-------|---|
| Tool definitions | 446 | 21% |
| System prompts | 93 | 4% |
| execute_tool() | 952 | 44% |
| REST endpoints | 200 | 9% |
| Helper classes | 150 | 7% |
| Other | 303 | 15% |

### Estimated Technical Debt

| Category | Hours |
|----------|-------|
| Critical bugs | 1 |
| DRY violations | 8 |
| Complexity reduction | 24 |
| Architecture refactor | 40 |
| Frontend cleanup | 16 |
| **Total** | **~89 hours** |

---

## Recommendations Summary

### Immediate Actions (Today)

1. Fix `search_search_request` typo
2. Delete unused `CLAUDE_SYSTEM_PROMPT`
3. Delete unused `extract_from_text()`

### Short-term (This Week)

4. Create `app/services/person_service.py`
5. Extract tool handlers from `execute_tool()`
6. Make telegram handlers non-blocking

### Medium-term (This Month)

7. Refactor frontend into smaller components
8. Generate and use Supabase TypeScript types
9. Add database indexes for search

### Long-term (Backlog)

10. Implement proper task queue
11. Add observability (logging, tracing)
12. Virtualize large lists in frontend
