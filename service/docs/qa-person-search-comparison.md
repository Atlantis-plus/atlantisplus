# Person Name Search QA Report

**Test Date:** 2026-02-14
**Server:** http://localhost:8000
**Mode:** SHARED_DATABASE_MODE=true
**Test User:** telegram_id=123456

## Test Results

### Query: "найди Сергея"

| Agent | People Found | Names (first 5) | Tool Calls | Iterations |
|-------|-------------|-----------------|------------|------------|
| OpenAI | 5 | Сергей Толпыгин, Сергей Бадорин, Сергей Скаков, Сергей Прохоров, Сергей Володин | 0 | N/A |
| Claude | 6 (showing 6) | Сергей Толпыгин, Сергей Бадорин, Сергей Скаков, Сергей Прохоров, Сергей Володин | 1 | 2 |

**Note:** Claude reported finding 17 total people named Сергей in the network.

### Query: "find Maria"

| Agent | People Found | Names (first 5) | Tool Calls | Iterations |
|-------|-------------|-----------------|------------|------------|
| OpenAI | 5 | Maria Podosenova, Gurova Maria Dmitrievna, Maria Donskikh, Maria Chmir, Maria Radchenko | 0 | N/A |
| Claude | 5 | Maria Podosenova, Gurova Maria Dmitrievna, Maria Donskikh, Maria Chmir, Maria Solntseva | 1 | 2 |

## Key Findings

### Tool Usage Discrepancy
**CRITICAL ISSUE:** OpenAI agent shows 0 tool calls for both queries, but still returns correct results. This indicates:
- Either the tool calls are happening but not being tracked in the response
- Or the OpenAI agent is using a different mechanism to search

### Response Consistency
Both agents return similar people for the same queries, with minor differences in the 5th person for Maria query:
- OpenAI: Maria Radchenko
- Claude: Maria Solntseva

### Metadata Tracking
Claude provides better observability:
- Tracks iterations (both queries: 2 iterations)
- Tracks found_people array with person_id + name
- Tool calls are properly logged

OpenAI lacks this metadata in the response.

### Name Search Accuracy
Both agents successfully find people by first name across:
- Russian names (Сергей)
- English names (Maria)

Claude provides total count context (17 total Sergeys), which is more informative.

## Issues to Document

1. **OpenAI tool call tracking**: tool_calls array is empty despite successful search
2. **Response format inconsistency**: OpenAI doesn't include iterations or found_people metadata
3. **Different 5th result for Maria**: Minor discrepancy in ranking

## Test Authentication
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/telegram/test \
  -H "Content-Type: application/json" \
  -H "X-Test-Secret: ***REMOVED***" \
  -d '{"telegram_id": 123456}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

## Test Commands

### Query 1: OpenAI
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "найди Сергея"}'
```

### Query 1: Claude
```bash
curl -s -X POST http://localhost:8000/chat/claude \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "найди Сергея"}'
```

### Query 2: OpenAI
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "find Maria"}'
```

### Query 2: Claude
```bash
curl -s -X POST http://localhost:8000/chat/claude \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "find Maria"}'
```
