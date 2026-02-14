# Shared Database Search Testing Results

**Date**: 2026-02-14
**Feature**: SHARED_DATABASE_MODE=true
**Endpoints**: POST /chat (OpenAI) vs POST /chat/claude (Claude)
**Environment**: Local server (http://localhost:8000)

## Test Results

### Query: "кто работает в Google?"

| Agent | People Found | Names (first 5) | Tool Calls |
|-------|-------------|-----------------|------------|
| OpenAI | 10 | Alexey Skorikov, Viren Chugh, Serge Kuzmin, Woo Hyun Jin, Khyati Khandelwal | 1 |
| Claude | 10 | Alexey Skorikov, Viren Chugh, Serge Kuzmin, Woo Hyun Jin, Khyati Khandelwal | 2 |

### Query: "кто из Yandex?"

| Agent | People Found | Names (first 5) | Tool Calls |
|-------|-------------|-----------------|------------|
| OpenAI | 9 | Anna Chebotkevich, Evgeniya Kikoina, Dima Vasiliev, Sergey Belov, Vladimir Vodnev | 1 |
| Claude | 15 | Anna Chebotkevich, Evgeniya Kikoina, Dima Vasiliev, Sergey Belov, Maria Kurchushkina (Kamysheva) | 2 |

## Observations

### Correctness
- Both agents successfully found people in shared database mode
- Google query: Identical results (10 people, same names in same order)
- Yandex query: Different counts - OpenAI found 9, Claude found 15 (showing top 15 of 20 total)
- All queries used semantic search (is_semantic: true)

### Performance
- OpenAI response time: ~5 seconds per query
- Claude response time: ~60 seconds per query (12x slower)
- Tool calls: OpenAI uses 1, Claude uses 2 iterations

### Quality Differences

#### Google Query
- IDENTICAL results between agents
- Both found same 10 people
- Same ordering

#### Yandex Query
- Different result counts: 9 vs 15
- First 4 names identical: Anna Chebotkevich, Evgeniya Kikoina, Dima Vasiliev, Sergey Belov
- 5th name differs:
  - OpenAI: Vladimir Vodnev
  - Claude: Maria Kurchushkina (Kamysheva)
- Claude message mentioned "showing 15 of 20 total found"
- OpenAI showed fewer results (9 total)

## Issues Found

### CRITICAL: Claude Performance
- **Severity**: HIGH
- **Component**: POST /chat/claude
- **Issue**: Claude endpoint takes 60+ seconds vs 5 seconds for OpenAI
- **Impact**: User experience significantly degraded
- **Root cause**: Unknown - needs investigation
  - Possible causes: extra iteration, slower API, network latency
- **Reproduction**: Query "кто из Yandex?" on both endpoints

### MEDIUM: Inconsistent Result Counts
- **Severity**: MEDIUM
- **Component**: Both endpoints
- **Issue**: Same query returns different number of results (9 vs 15)
- **Expected**: Consistent result counts for same query
- **Actual**: OpenAI returns 9, Claude returns 15
- **Possible causes**:
  - Different search parameters
  - Different relevance thresholds
  - Different semantic matching logic

### COSMETIC: Extra Tool Call
- **Severity**: LOW
- **Component**: POST /chat/claude
- **Issue**: Claude uses 2 iterations vs 1 for OpenAI
- **Impact**: Contributes to slower response time
- **Root cause**: Agentic loop requires extra confirmation step

## Test Configuration

### Authentication
```bash
curl -X POST http://localhost:8000/auth/telegram/test \
  -H "Content-Type: application/json" \
  -H "X-Test-Secret: ***REMOVED***" \
  -d '{"telegram_id": 123456}'
```

### Test Requests
```bash
# OpenAI
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "кто работает в Google?"}'

# Claude
curl -X POST http://localhost:8000/chat/claude \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "кто работает в Google?"}'
```

## Recommendations

1. **Investigate Claude performance** - 60s is unacceptable for production
   - Profile API calls
   - Check network latency
   - Consider caching or parallel processing

2. **Standardize result counts** - decide on consistent behavior
   - Should both agents return same number of results?
   - Document intended behavior difference

3. **Add performance metrics** - track response times
   - Log API latency per agent
   - Set SLA targets (e.g., < 10s for searches)

4. **Consider timeout handling** - 60s might timeout in production
   - Add explicit timeouts
   - Stream results incrementally

## Files Generated
- /tmp/google_openai.json - OpenAI Google query response
- /tmp/google_claude.json - Claude Google query response
- /tmp/yandex_openai.json - OpenAI Yandex query response
- /tmp/yandex_claude_verbose.txt - Claude Yandex query verbose output
