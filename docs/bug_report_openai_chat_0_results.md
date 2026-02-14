# Bug Report: OpenAI /chat Returns Fewer Results Than Claude

**Date**: 2026-02-14
**Reporter**: QA Agent
**Severity**: MEDIUM

## Summary

The `/chat` endpoint (OpenAI-based) returns inconsistent and fewer results compared to `/chat/claude` endpoint for the same query "кто работает в Яндексе".

## Reproduction

### Test Environment
- Backend: http://localhost:8000
- Auth: Test user (telegram_id: 123456)
- Query: "кто работает в Яндексе"

### Steps to Reproduce
1. Start backend server
2. Get test auth token
3. POST /chat with message "кто работает в Яндексе"
4. POST /chat/claude with the same message
5. Compare results

## Actual Behavior

### OpenAI /chat Endpoint
- **Inconsistent results**: 10, 15, 10, 10 people across 5 identical requests
- When successful: returns exactly 10 people
- Server logs show: `[FIND_PEOPLE] Filtered 15 -> 10 with motivations`

### Claude /chat/claude Endpoint
- **Consistent results**: 15 people (all tests)
- Server logs show: `[FIND_PEOPLE] LLM filter error: Request timed out.`
- Fallback returns all 20 candidates unfiltered

## Expected Behavior

Both endpoints should return the same number of relevant results for identical queries.

## Root Cause Analysis

### Issue 1: Hard-coded Limit in LLM Filter

**Location**: `app/agents/prompts.py:233`

```python
SEARCH_FILTER_PROMPT = """...
## FILTERING RULES
- Remove people who only matched on generic terms
- Remove people where the connection to query is too weak
- Keep max 10 most relevant people  # <-- HARD-CODED LIMIT
- Quality > quantity
..."""
```

The filter prompt explicitly instructs GPT-4o-mini to "Keep max 10 most relevant people", causing it to arbitrarily reduce results from 15 to 10.

### Issue 2: Timeout Flakiness

**Location**: `app/api/chat.py:630-673`

The `add_motivations_to_candidates()` function has a 10-second timeout for LLM filtering:

```python
try:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        ...
        timeout=10.0  # 10 seconds max
    )
    # Success path: filters 15 -> 10
    return filtered_results
except Exception as e:
    print(f"[FIND_PEOPLE] LLM filter error: {e}")
    # Fallback: returns ALL 20 candidates
    return candidates
```

**Behavior:**
- When LLM filter succeeds (within 10s): returns 10 filtered results
- When LLM filter times out: returns all 20 unfiltered candidates
- Claude endpoint consistently times out → returns 20
- OpenAI endpoint sometimes succeeds → returns 10

### Issue 3: Inconsistent Test Results

Running the same query 5 times to `/chat`:
- Test 1: 10 results
- Test 2: 15 results (timeout fallback)
- Test 3: 10 results
- Test 4: 10 results
- Test 5: (interrupted)

This proves the timeout is flaky and produces non-deterministic results.

## Impact

### User Experience
- **Inconsistent results**: Same query returns different number of people
- **Missing people**: Hard-coded limit of 10 may hide relevant results
- **Unpredictability**: Timeout fallback returns different data structure

### Technical Debt
- LLM filter adds latency (up to 10s)
- Timeout handling is unreliable
- Different endpoints behave differently

## Evidence

### Server Logs (OpenAI /chat - successful filter)
```
[FIND_PEOPLE] Hybrid search found 20 people
[FIND_PEOPLE] Adding motivations for 20 results...
[FIND_PEOPLE] Filtered 15 -> 10 with motivations
```

### Server Logs (Claude /chat/claude - timeout fallback)
```
[FIND_PEOPLE] Hybrid search found 20 people
[FIND_PEOPLE] Adding motivations for 20 results...
[FIND_PEOPLE] LLM filter error: Request timed out.
```

### Response Comparison

**OpenAI /chat** (when filter succeeds):
```json
{
  "tool_results": [{
    "result": {
      "people": [...],
      "total": 20,
      "showing": 10  // Only 10 returned
    }
  }]
}
```

**Claude /chat/claude** (timeout fallback):
```json
{
  "found_people": [
    // 15 people total
  ]
}
```

## Recommendations

### Option 1: Remove Hard-coded Limit (Recommended)
Change `SEARCH_FILTER_PROMPT` line 233:
```diff
- - Keep max 10 most relevant people
+ - Keep all relevant people (usually 10-20)
```

### Option 2: Increase Limit
```diff
- - Keep max 10 most relevant people
+ - Keep max 20 most relevant people
```

### Option 3: Remove LLM Filter Entirely
- Let the agent decide how many results to show
- Saves 1-10s latency per query
- More consistent behavior

### Option 4: Fix Timeout Handling
- Increase timeout from 10s to 30s
- Or make fallback behavior match success behavior (return top 10)

## Testing Plan

1. Change prompt to remove limit
2. Run same query 10 times to both endpoints
3. Verify consistent results
4. Check performance impact
5. User testing with real queries

## Related Files

- `/Users/evgenyq/Projects/atlantisplus/service/app/agents/prompts.py` (line 233)
- `/Users/evgenyq/Projects/atlantisplus/service/app/api/chat.py` (lines 595-673)
- Test logs: `/tmp/chat_response.json`, `/tmp/chat_claude_response.json`

## Status

- [x] Bug reproduced
- [x] Root cause identified
- [ ] Fix proposed
- [ ] Fix implemented
- [ ] Fix tested
- [ ] Deployed to production

## Notes

The original task stated "OpenAI /chat returned 0 results" but actual testing shows it returns 10 results (not 0). The real issue is:
1. Inconsistent results (10 vs 15 vs 20)
2. Hard-coded limit of 10 in filter prompt
3. Flaky timeout behavior

All three issues combine to create unpredictable behavior.
