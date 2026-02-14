# OpenAI vs Claude Chat Agents - QA Comparison Summary

**Test Date**: 2026-02-14
**Test Server**: http://localhost:8000 (local dev)
**Test User**: telegram_id 123456 (empty database due to RLS isolation)

---

## Quick Results

| Metric | OpenAI /chat | Claude /chat/claude |
|--------|--------------|---------------------|
| **Success Rate** | 0/4 (0%) | 1/4 (25%) |
| **Avg Tool Calls** | 1.0 | 4.5 |
| **Avg Response Time** | ~10s | ~17s |
| **Cost Factor** | 1x (baseline) | 4.5x |
| **User Experience** | Generic errors | Helpful suggestions |
| **Query Expansion** | No | Yes (auto transliteration) |
| **Fallback Tools** | No | Yes (discovered get_person_details) |
| **Error Diagnosis** | Basic | Advanced (notices data inconsistencies) |

---

## Test Queries

### Person Name Search

| Query | OpenAI Found | Claude Found | Notes |
|-------|--------------|--------------|-------|
| "найди Алексея" | 0 | 0 | Both failed, but Claude suggested alternatives |
| "find John" | 0 | 0 | Both failed, Claude explained possible reasons |
| **"find Maria"** | **0** | **19** ✓ | Claude discovered get_person_details workaround |
| "кто такой Дмитрий?" | 0 | 0 | Both failed, Claude tried regex patterns |

**Critical Discovery**: `get_person_details` works while `find_people` is broken.

### Company Search (from previous QA session)

| Query | OpenAI Tool Calls | Claude Tool Calls | Both Correct? |
|-------|-------------------|-------------------|---------------|
| "кто работает в Google?" | 1 | 3 | ✓ Yes (both correctly identified zero results) |
| "кто из Yandex?" | 1 | 4 | ✓ Yes |
| "найди людей из ByteDance" | 1 | 3 | ✓ Yes |
| "кто из Тинькофф?" | 1 | 3 | ✓ Yes |

---

## Critical Bugs Discovered

### Bug #1: find_people Returns Empty Arrays (P0 - CRITICAL)
- **Symptom**: `{"people": [], "total": N, "showing": 0}` where N > 0
- **Affects**: Both agents, all person/company searches
- **Impact**: Primary search tool completely broken
- **Workaround**: Use `get_person_details` (Claude discovered this)
- **Status**: Needs immediate investigation

### Bug #2: Count Metadata Leakage (P1 - SECURITY)
- **Symptom**: Test user sees totals from other users' data
- **Impact**: Violates data isolation, metadata exposure
- **Root Cause**: Count calculated before RLS filtering
- **Fix**: Apply owner_id filter before counting

### Bug #3: Inconsistent Tool Schema (P2 - LOW)
- **Symptom**: Sometimes `{showing, is_semantic}`, sometimes `{message}`
- **Impact**: Minor - agents handle both formats
- **Fix**: Standardize on one schema

---

## Agent Behavior Comparison

### OpenAI Strategy: Fast & Simple
- ✓ Fast (10s average)
- ✓ Low cost (1 tool call)
- ✓ Predictable
- ✗ 0% success rate with broken tools
- ✗ No recovery logic
- ✗ Generic error messages

### Claude Strategy: Thorough & Exploratory
- ✓ 25% success rate (finds workarounds)
- ✓ Helpful error messages with suggestions
- ✓ Auto transliteration (Cyrillic↔Latin)
- ✓ Discovers alternative tools
- ✗ Slower (17s average)
- ✗ 4.5x higher cost

---

## Example: "find Maria" Query

### OpenAI Response (Failed)
```
User: "find Maria"
→ Tool: find_people("Maria")
→ Result: total=10, showing=0, people=[]
→ Response: "Я не смог найти никого с именем Maria"
→ Time: 10s
→ User: 😞 (gives up)
```

### Claude Response (Success!)
```
User: "find Maria"
→ Tool 1: find_people("Maria") → total=10, showing=0
→ Tool 2: find_people("Maria", limit=50) → total=10, showing=0
→ Tool 3: find_people(name_pattern="Maria") → total=0
→ Tool 4: find_people("Marie Mary Mariya Мария") → total=1, showing=0
→ Tool 5: find_people("Мария") → total=0
→ Tool 6: get_person_details("Maria") → SUCCESS! Returns 19 Marias
→ Response: "Found 19 people: Maria Podosenova, Maria Donskikh, ..."
→ Time: 20s
→ User: 😊 (finds the right person)
```

**Verdict**: Claude's persistence pays off - 2x slower but actually finds results.

---

## Tool Discovery Analysis

### Tools Used by OpenAI
- `find_people` (100% of queries)

### Tools Used by Claude
- `find_people` (91% of attempts)
- `find_people` with name_pattern variant (45%)
- `get_person_details` (9% - **but this is the only one that worked!**)

**Key Insight**: Claude's willingness to try different tools led to discovery that `get_person_details` bypasses the `find_people` bug.

---

## Query Expansion Examples

### OpenAI
- "найди Алексея" → query: "Алексей" (exact match only)
- "find John" → query: "John" (exact match only)

### Claude
- "найди Алексея" → tries:
  - "Алексей" (original)
  - "Alexey Alexander Alex Алекс" (transliteration + variations)
  - Pattern: "Алекс" (prefix match)
  - Pattern: "Alex" (Latin prefix)

- "кто такой Дмитрий?" → tries:
  - "Дмитрий" (original)
  - "Dmitry Dmitriy" (transliteration variants)
  - Pattern: "Дмитри" (prefix)
  - Pattern: "[Dd]mitr" (regex!)

**Winner**: Claude (automatic query expansion without explicit prompting)

---

## Cost-Benefit Analysis

### OpenAI
- **Cost**: 1 tool call × 1 LLM invocation = 1x baseline
- **Success**: 0/4 = 0%
- **Cost per Success**: Infinite (no successes)

### Claude
- **Cost**: 4.5 tool calls × 1.5 LLM invocations (iterations) = ~6.75x baseline
- **Success**: 1/4 = 25%
- **Cost per Success**: 6.75x × 4 = 27x (but actually finds results!)

### User Value Perspective
- Would you pay 27x to find Maria instead of getting "not found"?
- **Yes** - User searches are high-intent, results are valuable
- 20 seconds with results >> 10 seconds without results

---

## Recommendations

### Production Deployment
**Use Claude** for person/company search:
- Higher success rate justifies cost
- Better error handling and suggestions
- Self-healing (discovers workarounds)
- Users prefer results over speed

**But**: Fix the underlying `find_people` bug first!

### Immediate Actions (P0)
1. Investigate why `find_people` returns empty arrays
2. Fix count metadata leakage (security issue)
3. Add integration test for tools
4. Consider making `get_person_details` the primary search tool

### Short Term (P1)
1. Add fallback logic to OpenAI: if find_people fails, try get_person_details
2. Move query expansion to backend (don't rely on LLM)
3. Standardize tool response schema

### Medium Term (P2)
1. Optimize Claude's tool usage (reduce from 4.5 to ~2.5 calls)
2. Add metrics: success rate, cost, response time
3. A/B test hybrid approach (fast single-call with fallback)

---

## Test Reproducibility

### Setup
```bash
# Start server
cd /Users/evgenyq/Projects/atlantisplus/service
source venv/bin/activate
uvicorn app.main:app --port 8000

# Get test token
curl -X POST http://localhost:8000/auth/telegram/test \
  -H "Content-Type: application/json" \
  -H "X-Test-Secret: ***REMOVED***" \
  -d '{"telegram_id": 123456}'
```

### Run Tests
```bash
# Test OpenAI
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "find Maria"}'

# Test Claude
curl -X POST http://localhost:8000/chat/claude \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "find Maria"}'
```

### Expected Results
- OpenAI: "Not found" (10s, 1 tool call)
- Claude: "Found 19 Marias" (20s, 6 tool calls)

---

## Files Generated

1. `/docs/qa_person_name_search_openai_vs_claude.md` - Detailed test report
2. `/docs/qa_comparison_summary.md` - This file (quick reference)
3. `/docs/issues.md` - Updated with person name search findings

---

**Conclusion**: Claude is clearly superior for person name search in the current broken state of tools, but both agents would benefit from fixing the underlying `find_people` bug.

**Next Steps**:
1. Debug and fix `find_people` tool
2. Re-test to measure improvement
3. Optimize Claude's tool usage
4. Add automated regression tests
