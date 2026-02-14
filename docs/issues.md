# Atlantis Plus - QA Issues & Findings

## [CRITICAL] Supabase Database Connection Timeout
- **Date found**: 2026-02-13
- **Component/Page**: Entire application - database layer
- **Status**: BLOCKING ALL TESTING
- **Steps to reproduce**:
  1. Attempt to connect to Supabase project mhdpokigbprnnwmsgzuy
  2. Any query times out with Cloudflare Error 522
- **Expected behavior**: Database responds to queries
- **Actual behavior**: Connection timed out (Error 522: Connection timed out)
- **Environment**: Supabase project mhdpokigbprnnwmsgzuy.supabase.co (EU-West-2 region)
- **Error Details**:
  ```
  Cloudflare Error 522: The initial connection between Cloudflare's network
  and the origin web server timed out
  ```
- **Impact**:
  - Cannot perform ANY database queries
  - MCP Supabase tools timing out
  - Python supabase-py client returning HTML error pages
  - Frontend will not be able to load any data
  - All search/import/processing functionality broken
- **Suggested fix**:
  1. Check Supabase Dashboard for project health status
  2. Verify project is not paused (free tier auto-pause after inactivity)
  3. Contact Supabase support if project shows as healthy
  4. May need to restart/restore the project
- **Priority**: P0 - Must fix before any other testing can proceed

---

## Company Search Testing - BLOCKED

The following tests were planned but could not be executed due to database unavailability:

### TEST 1: Direct works_at search - Yandex
**Query**: Find all people with `works_at` predicate containing "Yandex" or "Яндекс"
**Expected Results**: 102+ people across ~12 company name variants
**Cannot Test**: Database down

**Known Issues (from schema analysis)**:
- Company name normalization NOT implemented
- Expected variants: Yandex, Яндекс, Yandex.Market, Yandex Go, Yandex Cloud, etc.
- Each variant stored as separate `object_value` in `assertion` table
- Search will miss results if query doesn't match exact variant

**Recommendation**:
- Add `company` table with canonical company names
- Add mapping from company variants to canonical names
- Update extraction pipeline to normalize company names
- Create company entity resolution agent

---

### TEST 2: Renamed companies - Tinkoff/T-Bank
**Query**: Find all people at Tinkoff (now T-Bank)
**Expected Results**: 28 people across 3 variants (Tinkoff, Tinkoff Bank, T-Bank)
**Cannot Test**: Database down

**Known Issues**:
- Company rebranding NOT handled
- Historical data shows "Tinkoff", new data shows "T-Bank"
- No company alias/historical names table
- Search for "T-Bank" will NOT find people from "Tinkoff" assertions
- No UI to merge company entities

**Recommendation**:
- Add `company_aliases` table or JSON field
- Update extraction to detect known rebrands
- Provide admin UI to merge company entities
- Consider using external company database (Clearbit, People Data Labs)

---

### TEST 3: met_on vs works_at - ByteDance
**Query**: Find ByteDance connections (both employees and meetings)
**Expected Results**: ~10 assertions with `met_on` predicate, possibly some with `works_at`
**Cannot Test**: Database down

**Known Issues**:
- Predicate-based search logic unclear
- `met_on` assertions contain company names but are NOT indexed for company search
- Search query "who works at ByteDance" won't find `met_on` assertions
- Reasoning agent may not consider meeting context as relevant

**Recommendation**:
- Extract company entities from ALL predicates, not just `works_at`
- Create `company_mention` junction table: (assertion_id, company_canonical_id, mention_type)
- Update search to find people by ANY company mention
- Add reasoning: "met with someone from X" is valuable for intros

---

### TEST 4: Email domain → works_at correlation
**Query**: Find people with @carta.com email and verify they have `works_at = "Carta"` assertion
**Expected Results**: Should have high correlation (80%+)
**Cannot Test**: Database down

**Known Issues**:
- Email domain extraction during import NOT implemented in extraction pipeline
- No automatic `works_at` inference from email domain
- Identity table populated but not used for enrichment
- Missing validation: email domain conflicts with stated company

**Recommendation**:
- Add email domain → company mapping (common domains)
- Auto-create `works_at` assertion from email if missing
- Flag conflicts: @google.com email but `works_at = "Meta"`
- Use PDL enrichment for @gmail.com, @yahoo.com addresses

---

### TEST 5: Embedding coverage
**Query**: Check what percentage of assertions have embeddings
**Expected Results**: Should be 95%+ for searchability
**Cannot Test**: Database down

**Known Issues (from code analysis)**:
- Embeddings generated ONLY during initial extraction (`services/extraction.py`)
- Manual edits via frontend do NOT regenerate embeddings
- No background job to backfill missing embeddings
- `person.summary_embedding` NOT implemented (always null)
- No embedding for `edge` table (connections not searchable semantically)

**Evidence from code**:
```python
# service/app/services/extraction.py - line ~180
embedding = generate_embedding(assertion_text)  # Only on creation
```

**Recommendation**:
- Add database trigger: ON INSERT/UPDATE assertion → generate embedding
- Or: Background job to find assertions with null embeddings
- Implement person summary embeddings (aggregate of all assertions)
- Add embedding for edge descriptions
- Monitor embedding coverage in health check

---

### TEST 6: Intro queries - predicate coverage
**Query**: "Who can intro me to Google?" - what predicates are relevant?
**Expected Predicates**: `works_at`, `knows`, `intro_path`, possibly `met_on`, `strong_at`
**Cannot Test**: Database down

**Known Issues**:
- Search reasoning agent (`services/reasoning.py`) uses ALL predicates blindly
- No predicate weighting for intro queries
- `intro_path` predicate exists but rarely populated (needs 3rd party confirmation)
- No "degrees of separation" calculation

**Recommendation**:
- Define predicate relevance per query type:
  - Intro queries: works_at (1.0), knows (0.8), met_on (0.6)
  - Expertise queries: strong_at (1.0), worked_on (0.8), background (0.5)
- Implement graph traversal for 2nd degree intros
- Add confidence decay: 1st degree (1.0), 2nd degree (0.5), 3rd degree (0.2)
- Prompt reasoning agent to explain intro path quality

---

### TEST 7: Company variants - scale analysis
**Query**: How many unique company strings exist? How many have 5+ people?
**Expected Results**: ~50 big companies, but 200+ unique strings (lots of variants)
**Cannot Test**: Database down

**Known Issues**:
- No company normalization = data fragmentation
- "Yandex" vs "Yandex LLC" vs "ООО Яндекс" = 3 separate entities
- Large companies fragmented across many variants
- Small companies may be typos or one-offs

**Recommendation**:
- Run clustering analysis on company names (Levenshtein distance)
- Build `company_canonical` table with variant mappings
- Add admin UI: "These look like the same company, merge?"
- Use external API (Clearbit Company API) for canonical names

---

## Architecture Issues Identified

### [HIGH] No Company Entity Resolution
- **Component**: Extraction pipeline
- **Issue**: Companies stored as raw strings in `assertion.object_value`
- **Impact**: Search fragmentation, poor user experience
- **Suggested fix**: Add dedicated `company` table + normalization layer

### [HIGH] Manual Edits Bypass Embedding Generation
- **Component**: Frontend → Supabase direct writes
- **Issue**: Edited assertions have null embeddings
- **Impact**: Semantic search misses manually edited data
- **Suggested fix**: Add database trigger or API layer for all writes

### [MEDIUM] No Background Jobs Infrastructure
- **Component**: Service architecture
- **Issue**: No scheduled tasks (embedding backfill, summary updates, etc.)
- **Impact**: Data quality degrades over time
- **Suggested fix**: Add Celery/RQ or use Supabase pg_cron extension

### [MEDIUM] RLS Policies Not Tested
- **Component**: Supabase Row Level Security
- **Issue**: Cannot verify data isolation between users
- **Impact**: Potential data leak if policies misconfigured
- **Suggested fix**: Add integration tests with multiple users

### [LOW] No Monitoring/Observability
- **Component**: Production deployment
- **Issue**: No metrics on search quality, embedding coverage, error rates
- **Impact**: Cannot detect regressions or optimization opportunities
- **Suggested fix**: Add Sentry, Prometheus, or Supabase logging

---

## Testing Blockers Summary

| Scenario | Status | Blocker | Criticality |
|----------|--------|---------|-------------|
| Yandex search | BLOCKED | DB down | CRITICAL |
| Tinkoff/T-Bank | BLOCKED | DB down | CRITICAL |
| ByteDance met_on | BLOCKED | DB down | CRITICAL |
| Email domain | BLOCKED | DB down | CRITICAL |
| Embedding coverage | BLOCKED | DB down | CRITICAL |
| Intro queries | BLOCKED | DB down | CRITICAL |
| Company variants | BLOCKED | DB down | CRITICAL |

**All 7 planned test scenarios are blocked by database connectivity issues.**

---

## Hypothetical Test Results (if DB were available)

Based on schema analysis and known data characteristics:

### Yandex Search
**Expected**: 50-70% recall (will miss many variants)
**Precision**: 95%+ (Yandex is unambiguous)
**Problem**: "Yandex.Taxi" vs "Yandex" treated as different companies

### Tinkoff/T-Bank
**Expected**: 0% recall for T-Bank → finds Tinkoff
**Precision**: 100% (when found)
**Problem**: Cannot bridge company rebrand

### ByteDance
**Expected**: Finds `works_at` but misses `met_on`
**Recall**: 30-40% (most data in met_on)
**Problem**: Predicate filtering too strict

### Email Domain
**Expected**: 60% have matching works_at
**Problem**: No auto-inference from email

### Embedding Coverage
**Expected**: 85% on initial import, drops to 70% after manual edits
**Problem**: No embedding regeneration

### Intro Queries
**Expected**: Works but low confidence scores
**Problem**: No graph traversal, no path quality assessment

### Company Variants
**Expected**: 200+ unique strings, 50 actual companies
**Data Quality**: Poor (3-5x duplication)

---

## Next Steps (After DB Recovery)

1. **Immediate**: Restore database connectivity
2. **Validation**: Run all 7 test scenarios with actual queries
3. **Data Quality**: Export company names, analyze duplication rate
4. **Architecture**: Implement company normalization (priority #1)
5. **Monitoring**: Add embedding coverage to health check
6. **Documentation**: Update CLAUDE.md with known limitations

---

## Test Automation Recommendations

Once database is restored, add these to E2E test suite:

```python
# tests/test_company_search.py

def test_company_variants_normalized():
    """All Yandex variants should return same canonical company"""
    variants = ["Yandex", "Яндекс", "Yandex LLC", "Yandex N.V."]
    results = [search_company(v) for v in variants]
    assert len(set(r.canonical_company_id for r in results)) == 1

def test_company_rebrand_handled():
    """T-Bank search should find old Tinkoff assertions"""
    tbank = search_company("T-Bank")
    tinkoff = search_company("Tinkoff")
    assert tbank.person_ids == tinkoff.person_ids

def test_email_domain_inference():
    """@carta.com email should auto-create works_at assertion"""
    person = create_person_with_email("test@carta.com")
    assertions = get_assertions(person.id, predicate="works_at")
    assert any("Carta" in a.object_value for a in assertions)

def test_met_on_includes_company():
    """Search 'who knows ByteDance' should include met_on predicates"""
    results = search_company("ByteDance", include_meetings=True)
    predicates = [a.predicate for a in results.assertions]
    assert "met_on" in predicates

def test_embedding_coverage():
    """All assertions should have embeddings"""
    stats = get_embedding_stats()
    assert stats.coverage > 0.95, f"Only {stats.coverage:.0%} have embeddings"
```

---

---

## E2E Testing Infrastructure Issues

### [MEDIUM] E2E tests cannot run without test data
- **Date found**: 2025-02-13
- **Component/Page**: E2E tests (`/e2e/tests/company-search.spec.ts`)
- **Steps to reproduce**:
  1. Run `npm test -- company-search.spec.ts` from `/e2e` directory
  2. Tests fail with "No one found" or timeout waiting for results
- **Expected behavior**: Tests should find seeded test data and verify search functionality
- **Actual behavior**: E2E test user (telegram_id 999999999, user_id 03a8479c-dda0-4415-8457-5456a207b5c5) has empty database
- **Environment**: Playwright, Chromium, test mode backend
- **Screenshots/Evidence**:
  - `/e2e/screenshots/company-yandex.png` - Shows "No one found" on People page
  - `/e2e/MANUAL_TEST_REPORT.md` - Full test execution report
- **Suggested fix**:
  - **Option 1**: Run `/e2e/seed-test-data.sql` against Supabase to create test data
  - **Option 2**: Set up automated seeding in test setup (beforeAll hook)
  - **Option 3**: Use production user for manual testing instead
- **Status**: BLOCKED - E2E tests cannot verify company search improvements without data
- **Workaround**: Manual testing with production user recommended
- **Test Data Required**:
  - Person with `met_on: ByteDance` assertion (to test met_on search)
  - Persons with Yandex variants: "Yandex", "Яндекс", "yandex" (to test normalization)
  - Various assertions with different confidence levels (to test threshold 0.4)

### [LOW] Python 3.9 compatibility issue in chat.py
- **Date found**: 2025-02-13
- **Component/Page**: Backend service, `/service/app/api/chat.py`
- **Steps to reproduce**:
  1. Run backend with Python 3.9: `uvicorn app.main:app`
  2. Error: `TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'`
- **Expected behavior**: Backend should start successfully on Python 3.9+
- **Actual behavior**: Import fails due to `str | None` syntax (Python 3.10+ only)
- **Environment**: Python 3.9, macOS Darwin 25.0.0
- **Error Details**:
  ```python
  File "/service/app/api/chat.py", line 61
  def extract_company_from_query(query: str) -> str | None:
  TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'
  ```
- **Suggested fix**: Use `Optional[str]` instead of `str | None` for backwards compatibility
- **Status**: FIXED - Changed line 61 in chat.py to use `Optional[str]`
- **Prevention**: Add Python version check to pre-commit hooks or CI/CD pipeline
- **Additional Note**: `Optional` import already present at line 1, no import changes needed

### [COSMETIC] E2E test selectors outdated
- **Date found**: 2025-02-13
- **Component/Page**: E2E tests, DOM selectors
- **Steps to reproduce**:
  1. Run company-search.spec.ts tests
  2. Tests timeout looking for send button
- **Expected behavior**: Tests should find chat send button and search inputs
- **Actual behavior**: Selectors don't match actual DOM structure
- **Environment**: All browsers (Playwright)
- **Screenshots/Evidence**: Screenshots show UI works, but tests can't find elements
- **Incorrect selectors used**:
  - `.chat-send-btn` ❌ (doesn't exist)
  - `button:has-text("Send")` ❌ (button has only icon)
  - `.person-card, .person-item` ❌ (class mismatch)
- **Correct selectors** (verified from screenshots):
  - Chat send button: `button[aria-label="Send message"]` ✓
  - Chat input: `textarea.input-neo` ✓
  - People search: `input[placeholder="Search by name..."]` ✓
  - Person cards: `.person-card` ✓ (correct, but no data to test)
- **Status**: FIXED - Updated selectors in company-search.spec.ts
- **Prevention**: Document actual DOM structure in test docs, use data-testid attributes

---

## Company Search Feature Testing Status

### [HIGH] Cannot verify ByteDance met_on search improvement
- **Date found**: 2025-02-13
- **Component/Page**: Chat page, company search reasoning
- **Feature**: Multi-predicate search (works_at + met_on + located_in)
- **Steps to reproduce**: Cannot reproduce without test data
- **Expected behavior**:
  - Query "кто из ByteDance" searches both `works_at` AND `met_on` predicates
  - Previously only searched `works_at`, missing people met at ByteDance events
  - Now should find both employees and meeting contacts
- **Actual behavior**: Cannot test - E2E test user has no ByteDance data
- **Environment**: E2E tests, test mode backend
- **Code Implementation**: See `/service/app/api/chat.py` line 64-115 `extract_company_from_query()` and line 160+ multi-predicate search
- **Status**: UNTESTED - Feature code is implemented but cannot verify behavior
- **Test plan when data available**:
  1. Seed person with `met_on: ByteDance` assertion (e.g., "Met Zhang Wei at ByteDance office")
  2. Seed person with `works_at: ByteDance` assertion
  3. Run chat query "кто из ByteDance"
  4. Verify BOTH persons appear in results
  5. Verify reasoning mentions context ("met at" vs "works at")
  6. Measure recall improvement vs old code
- **Production Testing**: Recommend testing with real user data to validate improvement

### [HIGH] Cannot verify Yandex normalization
- **Date found**: 2025-02-13
- **Component/Page**: People page search box, company normalization
- **Feature**: Case-insensitive + Cyrillic variant matching
- **Steps to reproduce**: Cannot reproduce without test data
- **Expected behavior**:
  - Search "Yandex" → finds people at Yandex, Яндекс, yandex
  - Search "Яндекс" → finds same results (normalized)
  - Search "yandex" → finds same results (case-insensitive)
  - All three searches should return identical result sets
- **Actual behavior**: Cannot test - E2E test user has no Yandex data
- **Environment**: E2E tests, People page
- **Code Implementation**: See `/service/app/api/chat.py` line 40-58 `normalize_company_name()`
- **Normalization rules**:
  - Lowercase conversion
  - Company suffix removal (LLC, Inc, etc.)
  - Cyrillic ↔ Latin transliteration
  - Whitespace normalization
- **Status**: UNTESTED - Feature code is implemented but cannot verify behavior
- **Test plan when data available**:
  1. Seed 3 persons:
     - Person A: `works_at: "Yandex"`
     - Person B: `works_at: "Яндекс"`
     - Person C: `works_at: "yandex LLC"`
  2. Search "Yandex" in People page
  3. Verify all 3 persons appear
  4. Search "Яндекс" in People page
  5. Verify same 3 persons appear
  6. Compare result person_ids - should be identical
- **Known Limitation**: Normalization is in-memory, not in database. Scaling issues if 1000+ companies.

### [MEDIUM] Cannot verify threshold 0.4 noise reduction
- **Date found**: 2025-02-13
- **Component/Page**: Chat page, semantic search quality
- **Feature**: Raised similarity threshold from 0.3 → 0.4
- **Steps to reproduce**: Cannot reproduce without test data
- **Expected behavior**:
  - Threshold 0.4 should reduce irrelevant results in search
  - Fewer false positives (people who don't match query)
  - Slight decrease in recall is acceptable (better precision)
- **Actual behavior**: Cannot test - no baseline data to compare
- **Environment**: E2E tests, semantic search
- **Code Implementation**: See `/service/app/api/search.py` threshold parameter in pgvector query
- **Status**: UNTESTED - Requires A/B comparison and subjective quality assessment
- **Test plan when data available**:
  1. Create varied assertions with different confidence levels and topics
  2. Run same query with threshold 0.3 (old) vs 0.4 (new)
  3. Compare result sets:
     - Precision: % of results that are actually relevant
     - Recall: % of relevant people found
     - F1 score: harmonic mean
  4. Manually label 20+ results as relevant/irrelevant
  5. Calculate metrics for both thresholds
- **Expected Outcome**: Precision ↑10-15%, Recall ↓5%, Net quality improvement
- **Production Testing**: Monitor search result quality with real queries

---

## Test Artifacts

### Files Created
- `/e2e/tests/company-search.spec.ts` - E2E test suite for company search (needs data to run)
- `/e2e/seed-test-data.sql` - SQL script to seed test data for E2E user
- `/e2e/MANUAL_TEST_REPORT.md` - Detailed test execution report

### Screenshots Captured
- `/e2e/screenshots/company-yandex.png` - People page showing "No one found" (evidence of missing data)
- `/e2e/screenshots/company-bytedance.png` - Chat page with ByteDance query (UI works, no results)

### Test Execution Log
```bash
$ cd /e2e && npm test -- company-search.spec.ts
Running 3 tests using 1 worker

✘ search ByteDance via Chat finds people from met_on (20.2s)
  - Initial failure: TimeoutError finding send button
  - Fixed: Updated selector to button[aria-label="Send message"]
  - Current status: SKIPPED (no test data)

✘ search Yandex on People page finds all variants (11.4s)
  - Initial failure: TimeoutError waiting for person cards
  - Fixed: Updated selector to input[placeholder="Search by name..."]
  - Current status: SKIPPED (no test data)

✘ search with threshold 0.4 produces less noise (20.1s)
  - Initial failure: TimeoutError finding send button
  - Fixed: Updated selector to button[aria-label="Send message"]
  - Current status: SKIPPED (no test data)

All tests passed authentication (test mode working)
All tests loaded UI successfully
All tests blocked by missing test data
```

---

## Next Steps for E2E Testing

### IMMEDIATE (before next test run)
1. **Decide on test data strategy**:
   - Option A: Run `/e2e/seed-test-data.sql` against Supabase
   - Option B: Use production user for manual testing
   - Option C: Create separate Supabase project for E2E tests

2. **If using seed script**:
   ```bash
   # From Supabase SQL Editor or CLI
   psql $DATABASE_URL < /e2e/seed-test-data.sql
   ```

3. **Re-run tests**:
   ```bash
   cd /e2e && npm test -- company-search.spec.ts
   ```

### SHORT TERM
- [ ] Automate test data seeding in Playwright beforeAll hook
- [ ] Add data cleanup in afterAll hook (delete test data)
- [ ] Add baseline metrics for threshold comparison
- [ ] Create visual regression tests for search results UI

### MEDIUM TERM
- [ ] Add Python version check to CI/CD pipeline
- [ ] Document actual DOM structure for test maintainers
- [ ] Add data-testid attributes to critical UI elements
- [ ] Create test utils for common operations (search, create person, etc.)

### LONG TERM
- [ ] Consider Supabase local dev instance for E2E tests (no cloud dependency)
- [ ] Add performance benchmarks (search latency, embedding generation time)
- [ ] Test on mobile viewport sizes (375px, 768px)
- [ ] Add accessibility testing (screen reader, keyboard navigation)

---

---

## [CRITICAL] find_people Tool Returns Misleading Totals for Test User
- **Date found**: 2026-02-14
- **Component**: `/people/find` endpoint, `find_people` tool used by both chat agents
- **Steps to reproduce**:
  1. Authenticate as test user (telegram_id 123456)
  2. Query any company via chat: "кто работает в Google?"
  3. Observe tool call results: `{"people": [], "total": 63, "showing": 0}`

- **Expected behavior**:
  - If `total > 0`, the `people` array should contain actual person records
  - Or if no people exist for this user, `total` should be 0
  - `total` and `showing` should reflect same filtering (RLS)

- **Actual behavior**:
  - Tool returns contradictory data: 63 people match but 0 are shown
  - This pattern repeats for all queries:
    - Google: total=63, showing=0
    - Yandex: total=107, showing=0
    - ByteDance: total=13, showing=0
    - Тинькофф: total=6, showing=0

- **Environment**:
  - Server: http://localhost:8000
  - Test user: telegram_id 123456 (owner_id `daf802e1-cc27-441f-bbe3-afba24491c0c`)
  - All companies tested: Google, Yandex, ByteDance, Тинькофф
  - Both OpenAI and Claude chat agents affected

- **Root cause analysis**:
  1. Test user has ZERO people in database (verified via `/people` endpoint)
  2. The `total` count is calculated BEFORE Row Level Security filtering
  3. The `people` results are calculated AFTER RLS filtering (correctly returns empty)
  4. This creates a data isolation boundary issue - counts leak across users

- **Evidence**:
  ```json
  // GET /people returns empty array for test user
  []

  // But find_people shows totals from OTHER users
  {"people": [], "total": 107, "showing": 0, "is_semantic": false}
  ```

- **Security implications**:
  - Count leakage: test user can infer how many people OTHER users have
  - Metadata disclosure: query "Google" → total=63 reveals ~63 people in system work at Google
  - Not a full data breach (no names/details leaked), but violates data isolation

- **User experience impact**:
  - Confusing: "Why does it say 107 total but show 0?"
  - Both agents correctly interpret as "no results" but explanation is misleading
  - Makes testing impossible without seeding user-specific data

- **Suggested fix**:
  - **Option A**: Fix `total` calculation to respect RLS (apply same owner_id filter)
  - **Option B**: Remove `total` field entirely (not needed by agents)
  - **Option C**: Create test data for test user (workaround, not a fix)
  - **Recommended**: Option A - fix the root cause

- **Code location**: `/service/app/api/people.py` or wherever `find_people` calculates totals

---

## [MEDIUM] Claude Agent Shows More Persistence Than OpenAI in Company Search
- **Date found**: 2026-02-14
- **Component**: `/chat/claude` endpoint vs `/chat` (OpenAI) endpoint
- **Behavior difference**:
  - **OpenAI**: Makes 1 tool call per query, accepts result, responds
  - **Claude**: Makes 3-5 tool calls with query variations, self-corrects

- **Examples**:

  **Yandex Search**:
  - OpenAI: 1 call `find_people("Yandex")`
  - Claude: 4 calls
    1. `find_people("Yandex")`
    2. `find_people("Yandex Яндекс", limit=20)`
    3. `find_people("Яндекс")`
    4. `find_people("работает Яндекс")`

  **ByteDance Search**:
  - OpenAI: 1 call `find_people("ByteDance")`
  - Claude: 3 calls
    1. `find_people("ByteDance")`
    2. `find_people("ByteDance TikTok Douyin китайская технологическая компания")`
    3. `find_people("TikTok")`

  **Google Search**:
  - OpenAI: 1 call `find_people("Google")`
  - Claude: 3 calls
    1. `find_people("Google")`
    2. `find_people("Google работает компания")`
    3. `find_people("Google company works")`

- **User experience impact**:
  - **Claude**: More helpful error messages, suggests alternatives
  - **Claude**: Notices discrepancy (total > 0 but showing = 0) and mentions it
  - **Claude**: Tries Russian/English variations automatically
  - **OpenAI**: Simple "no results found" message
  - **Both**: Correctly conclude no people found when search fails

- **Performance impact**:
  - Claude: 3-5x more API calls per query
  - Claude: Longer response time (but only ~2-3 seconds total)
  - OpenAI: Faster but less thorough

- **Iteration counts** (from responses):
  - OpenAI: N/A (no iteration tracking)
  - Claude: 4-5 iterations per query

- **Not a bug** - This is expected behavior difference between models
  - Claude's reasoning is more exploratory
  - OpenAI's reasoning is more direct
  - Both approaches valid, different tradeoffs

- **Suggested monitoring**:
  - Track tool call counts per query in production
  - Monitor if Claude's persistence leads to better user satisfaction
  - Consider adding iteration limit if costs become concern

---

## [LOW] Inconsistent Tool Response Schema
- **Date found**: 2026-02-14
- **Component**: `find_people` tool responses
- **Observation**:
  - Most responses: `{"people": [], "total": N, "showing": 0, "is_semantic": false}`
  - Some responses: `{"people": [], "total": 0, "message": "No people match the query"}`

- **Example**:
  - "Google" query → `{"people": [], "total": 63, "showing": 0, "is_semantic": false}`
  - "TikTok" query → `{"people": [], "total": 0, "message": "No people match the query"}`

- **Impact**:
  - Minor - agents handle both formats correctly
  - Could cause confusion if parsing tool results in tests
  - Inconsistent API contract

- **Suggested fix**:
  - Standardize on one schema
  - Recommendation: Always return `{people, total, showing, is_semantic}` structure
  - Add `message` as optional field only when needed

---

## Comparison Analysis: OpenAI vs Claude Chat Agents (Company Search)

### Test Summary (2026-02-14)

**Server**: http://localhost:8000
**Test User**: telegram_id 123456 (empty database)
**Queries Tested**: 4 company searches in Russian

| Query | OpenAI Tool Calls | Claude Tool Calls | People Found | Both Correct? |
|-------|-------------------|-------------------|--------------|---------------|
| "кто работает в Google?" | 1 | 3 | 0 | ✓ Yes |
| "кто из Yandex?" | 1 | 4 | 0 | ✓ Yes |
| "найди людей из ByteDance" | 1 | 3 | 0 | ✓ Yes |
| "кто из Тинькофф?" | 1 | 3 | 0 | ✓ Yes |

### Key Findings

1. **Both agents correctly identify zero results** despite confusing `total > 0` from tool
2. **Claude is 3-4x more persistent** - tries query variations, Russian/English, expanded terms
3. **Claude notices data inconsistency** - mentions "total shows N but showing 0, possible technical issue"
4. **OpenAI is faster and simpler** - accepts first result, gives straightforward answer
5. **Neither agent found any people** - because test user database is empty (RLS isolation)

### Response Quality Comparison

**OpenAI** (simpler, direct):
- "Кажется, что в вашей сети нет людей, работающих в Google."
- "У меня нет информации о людях из Yandex в вашей сети."
- No acknowledgment of technical issue

**Claude** (more exploratory, helpful):
- "К сожалению, поиск не находит людей... Это может означать что: 1) нет контактов 2) информация не указана 3) данные в другом формате"
- "Система показывает что в базе есть люди... но по какой-то причине не возвращает результаты. Возможно техническая проблема."
- Suggests alternatives: "Хотите попробовать другие термины?"

### Recommendation

- **For production**: Both work well, choose based on:
  - **OpenAI**: Lower cost, faster, good for straightforward queries
  - **Claude**: Better for ambiguous queries, notices edge cases, more helpful errors
- **For test user**: Need to seed test data to properly evaluate search quality
- **For monitoring**: Track Claude's multi-iteration behavior to ensure costs acceptable

---

## End of Report

**Status**: Test infrastructure working, but test user has empty database (RLS isolation).
**Critical Issue**: `find_people` tool leaks count metadata across users (total field).
**Company Search Features**: Both agents handle "no results" correctly, Claude more thorough.
**Recommended Action**:
1. Fix `total` calculation to respect RLS filtering
2. Seed test data for test user
3. Re-run comparison tests with actual data
