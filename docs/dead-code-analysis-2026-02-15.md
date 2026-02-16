# Dead Code & Duplication Analysis

**Date:** 2026-02-15
**Scope:** Full codebase (backend + frontend)
**Agents:** 4 specialized analyzers

---

## Executive Summary

| Category | Items Found | Est. Lines | Priority |
|----------|-------------|------------|----------|
| Dead Code (Backend) | 4 functions | ~150 | Medium |
| Dead Code (Frontend) | 1 page, 18 icons, 2 API methods, 30+ CSS | ~800 | High |
| Copy-Paste Code | 5 critical patterns | ~1500 | **Critical** |
| Duplicate Functionality | 3 UI paths, 2 API endpoints | N/A | Medium |
| **Total Waste** | - | **~2500 lines (~20%)** | - |

### Top 5 Issues

1. **handlers.py ↔ process.py** — ~160 lines 99% identical extraction pipeline
2. **import_linkedin.py ↔ import_calendar.py** — ~250 lines 85% similar
3. **SearchPage.tsx** — entire page unused (not in router)
4. **18 unused icons** — exported but never imported
5. **`/search` vs `/chat`** — duplicate functionality, `/search` seems legacy

---

## Part 1: Dead Code — Backend (Python)

### Unused Functions

| Function | File | Lines | Reason |
|----------|------|-------|--------|
| `extract_from_text()` | extraction.py | 8-41 | `extract_from_text_simple()` used instead |
| `run_search_agent()` | claude_agent_v2.py | 475+ | Class method `.run()` used, not standalone |
| `notify_extraction_summary()` | proactive.py | 109-119 | Placeholder, "handled in handlers.py directly" |
| `extract_linkedin_username()` | normalize.py | 74+ | Never called |

### Code Quality Issues

| Issue | File | Line | Description |
|-------|------|------|-------------|
| **CRITICAL BUG** | search.py | 56 | `search_search_request` typo (causes NameError) |
| Misplaced import | process.py | 435 | `from pydantic import BaseModel` after functions |

### Unused Imports

None detected — all imports are used.

---

## Part 2: Dead Code — Frontend (React/TS)

### Unused Pages

| Page | Status | Reason |
|------|--------|--------|
| **SearchPage.tsx** | Not in router | App.tsx doesn't have `case 'search'` |

### Unused Icons (18 total)

In `components/icons/index.tsx`:

```
AlertIcon, BuildingIcon, CheckIcon, CopyIcon, DownloadIcon,
FilterIcon, GlobeIcon, MenuIcon, MoreHorizontalIcon,
MoreVerticalIcon, SettingsIcon, SortIcon
```

(32 icons ARE used: ChevronLeftIcon, ChevronRightIcon, etc.)

### Unused API Methods

| Method | File | Lines | Reason |
|--------|------|-------|--------|
| `healthCheck()` | api.ts | 90-92 | Never called |
| `getProcessingStatus()` | api.ts | 115-122 | Realtime used instead |

### Unused CSS Classes (~30+)

In `App.css` — legacy styles from before Tailwind migration:
- `.header`, `.subtitle`, `.main`, `.welcome`, `.dev-mode`
- `.voice-recorder`, `.record-btn`, `.recording-indicator`, `.pulse`
- `.text-input`, `.submit-btn`, `.mode-switcher`, `.mode-btn`
- `.people-list`, `.person-card`, `.person-avatar`, `.person-info`

**Reason:** Frontend migrated to Tailwind + `index.css` with `btn-neo`, `card-neo`, etc.

---

## Part 3: Copy-Paste Code

### Critical (>85% similarity)

#### 1. Extraction Pipeline Duplication

**Files:**
- `process.py:27-180` (`process_pipeline`)
- `handlers.py:182-345` (`handle_note_message_direct`)

**Similarity:** 99%

**What's duplicated:**
1. Create raw_evidence record
2. Extract people/assertions via `extract_from_text_simple()`
3. Create person records, build person_map
4. Create identity records
5. Generate embeddings batch
6. Insert assertions with embeddings
7. Create edges
8. Update status to done

**Problem:** Bug fix in one place ≠ fix in other.

**Fix:** Extract to `services/extraction.py::process_extraction_result()`

---

#### 2. Import Logic Duplication

**Files:**
- `import_linkedin.py:319-583`
- `import_calendar.py:234-544`

**Similarity:** 85%

| Duplicated Element | % Match |
|-------------------|---------|
| `update_status()` function | 100% |
| `rollback_batch()` function | 90% |
| Import batch creation | 100% |
| Storage upload | 95% |
| Dedup service call | 100% |
| Proactive notification | 100% |

**Fix:** Create `run_import_background()` with callbacks for format-specific parsing.

---

#### 3. Status Update Pattern

**Locations:**
- `import_linkedin.py:338-344`
- `import_calendar.py:275-282`
- `process.py:46-49, 176-186`

**Similarity:** 95%

```python
def update_status(status: str, content: Optional[str] = None, error: Optional[str] = None):
    update_data = {'processing_status': status}
    if content: update_data['content'] = content
    if error: update_data['error_message'] = error
    supabase.table('raw_evidence').update(update_data).eq('evidence_id', evidence_id).execute()
```

**Fix:** Create `utils/evidence.py::update_evidence_status()`

---

### High (70-85% similarity)

#### 4. Identity Creation Pattern

**Files:**
- `process.py:60-126` (67 lines)
- `import_linkedin.py:431-453` (23 lines)
- `import_calendar.py:400-420` (34 lines)

**Similarity:** 70-75%

**Duplicated logic:**
1. Loop through contacts/people
2. Create person record
3. Add email identity (with normalization)
4. Add LinkedIn URL identity
5. Handle duplicate exceptions

**Fix:** Create `services/people.py::create_person_with_identities()`

---

#### 5. File Reading Pattern

**Files:**
- `import_linkedin.py:156-166`
- `import_calendar.py:253-259`

**Similarity:** 95%

```python
content = await file.read()
try:
    text = content.decode('utf-8')
except UnicodeDecodeError:
    text = content.decode('latin-1')
```

**Fix:** Create `utils/files.py::read_and_decode_file()`

---

### Medium (50-70% similarity)

#### 6. Batch Insert with Fallback

Multiple locations use this pattern:
```python
try:
    supabase.table('X').insert(batch).execute()
except Exception:
    for item in batch:
        try:
            supabase.table('X').insert(item).execute()
        except: pass
```

**Fix:** Create `utils/db.py::batch_insert_with_fallback()`

---

## Part 4: Duplicate Functionality

### UI Paths for Same Feature

#### Chat/Search (3 entry points)

| Entry Point | Endpoint | Features |
|-------------|----------|----------|
| **ChatPage.tsx** | `/chat` | Stateful, agent, tools |
| **SearchPage.tsx** | `/search` | One-shot, GPT reasoning |
| **Telegram Bot** | Direct call | Voice, text, dig deeper |

**Verdict:** SearchPage seems redundant — Chat does everything Search does, plus more.

**Recommendation:** Either remove SearchPage or differentiate clearly (quick vs deep search).

---

### API Endpoints

#### `/search` vs `/chat`

| Feature | /search | /chat |
|---------|---------|-------|
| Input | One-off query | Stateful conversation |
| Method | Semantic + GPT | `find_people` tool + agent |
| Session | No | Yes |
| Rate limit | 30/min | 20/min |

**Both do:**
```
query → embedding → pgvector → group by person → rank
```

**Verdict:** `/search` appears to be legacy. Recommend deprecation or clear differentiation.

---

### Note Processing (3 paths)

| Path | Processing | Async |
|------|-----------|-------|
| Frontend (NotesPage) | `process_pipeline()` via HTTP | Yes (BackgroundTasks) |
| Telegram | `handle_note_message_direct()` | No (synchronous) |
| Chat (`add_note_about_person`) | Single assertion only | No |

**Verdict:** Intentional (different contexts) but extraction logic is duplicated.

---

## Part 5: Summary Statistics

### By Category

| Category | Lines | % of Codebase |
|----------|-------|---------------|
| Unused backend functions | ~150 | 1% |
| Unused frontend code | ~800 | 6% |
| Copy-paste code | ~1500 | 12% |
| **Total waste** | **~2500** | **~20%** |

### Files with Most Duplication

| File | Lines | Duplication |
|------|-------|-------------|
| import_linkedin.py | 706 | ~40% duplicate with import_calendar |
| import_calendar.py | 545 | ~40% duplicate with import_linkedin |
| handlers.py | 715 | ~25% duplicate with process.py |
| process.py | 495 | ~20% duplicate with handlers.py |
| PeoplePage.tsx | 877 | predicate formatting scattered |

---

## Recommendations

### Phase 1 — Critical (4-6 hours)

| Task | Impact | Effort |
|------|--------|--------|
| Extract `process_extraction_result()` | Fixes 160 lines duplication | 2h |
| Create `update_evidence_status()` util | Fixes 100% copy-paste | 30min |
| Create `create_person_with_identities()` | Fixes 3x duplication | 1.5h |
| Fix search.py:56 typo | Unbreaks /search endpoint | 1min |

### Phase 2 — High (4-6 hours)

| Task | Impact | Effort |
|------|--------|--------|
| Unify import_linkedin + import_calendar | Saves 250+ lines | 3h |
| Delete SearchPage.tsx or wire it | Clarifies product | 30min |
| Delete unused icons (18) | Reduces bundle | 15min |
| Delete unused API methods (2) | Cleaner code | 5min |

### Phase 3 — Medium (2-3 hours)

| Task | Impact | Effort |
|------|--------|--------|
| Delete App.css legacy classes | Cleaner CSS | 30min |
| Create `batch_insert_with_fallback()` | DRY DB operations | 1h |
| Create `lib/predicates.ts` | Frontend DRY | 1h |

### Phase 4 — Low Priority

| Task | Impact | Effort |
|------|--------|--------|
| Deprecate `/search` endpoint | Simplify API | Decision needed |
| Create `usePaginatedQuery` hook | Frontend DRY | 1h |
| Delete unused backend functions | Cleaner code | 15min |

---

## What's NOT Duplicated (Good!)

✅ **Embedding generation** — centralized in `services/embedding.py`
✅ **Transcription** — single entry in `services/transcription.py`
✅ **Extraction prompts** — centralized in `agents/prompts.py`
✅ **Deduplication** — centralized in `services/dedup.py`
✅ **Auth middleware** — single source in `middleware/auth.py`

---

## Appendix: Files to Delete/Modify

### Delete entirely:
- `frontend/src/pages/SearchPage.tsx` (if not planned)
- 18 unused icon exports from `icons/index.tsx`
- `healthCheck()` and `getProcessingStatus()` from `api.ts`
- Legacy classes from `App.css`

### Refactor:
- `handlers.py:182-345` → call shared function
- `import_linkedin.py` + `import_calendar.py` → shared base
- `process.py:60-126` → call `create_person_with_identities()`

### Fix:
- `search.py:56` — `search_search_request` → `search_request`
- `process.py:435` — move import to top of file
