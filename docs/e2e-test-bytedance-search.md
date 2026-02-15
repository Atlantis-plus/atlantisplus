# E2E Test Report: ByteDance Search via Chat API

**Date**: 2026-02-13
**Test Type**: End-to-End Integration Test
**Status**: ❌ FAIL (Wrong Test Data)

## Executive Summary

The ByteDance search feature **is working correctly** but the test failed because we used test users who don't own any ByteDance-related data. This is a **data issue, not a code issue**.

## Test Procedure

### 1. Server Setup
```bash
cd /Users/evgenyq/Projects/atlantisplus/service
source venv/bin/activate
ENVIRONMENT=test TEST_MODE_ENABLED=true TEST_AUTH_SECRET=dev-secret-123 \
  uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 2. Authentication
```bash
# Test User 1 (telegram_id: 123456789)
curl -X POST http://localhost:8000/auth/telegram/test \
  -H "Content-Type: application/json" \
  -H "X-Test-Secret: dev-secret-123" \
  -d '{"telegram_id": 123456789}'
# Result: user_id = a4f42a2c-8096-4fbf-ae70-7048e6404a83

# Test User 2 (telegram_id: 987654321)
curl -X POST http://localhost:8000/auth/telegram/test \
  -H "Content-Type: application/json" \
  -H "X-Test-Secret: dev-secret-123" \
  -d '{"telegram_id": 987654321}'
# Result: user_id = a299d463-b12d-4ddd-85b7-03c65d0dab61
```

### 3. Search Request
```bash
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"message": "кто из ByteDance"}'
```

**Response**:
```json
{
  "session_id": "...",
  "message": "Похоже, что в моей базе данных нет информации о людях, связанных с ByteDance.",
  "tool_results": [{
    "tool": "find_people",
    "args": {"query": "ByteDance"},
    "result": {
      "people": [],
      "total": 13,
      "showing": 0,
      "is_semantic": false
    }
  }]
}
```

## Root Cause Analysis

### Investigation Steps

**Step 1**: Check database for ByteDance data
```python
# Found 12 unique person_ids with ByteDance mentions
# in assertions (works_at, met_on predicates)
```

**Step 2**: Check person records status
```
Found 12 person records:
- 6 with status='active'
- 6 with status='deleted'
```

**Step 3**: Check owner_id for active people
```
Active ByteDance people owner_ids:
- cf7f3d2e-xxxx (some people)
- 03a8479c-xxxx (other people)

Test users owner_ids:
- a4f42a2c-xxxx (test user 1)
- a299d463-xxxx (test user 2)

NO OVERLAP → Test users don't own ByteDance data!
```

### Why the Search Returned 0 Results

The search code works as follows:

1. **Company search** (line 702-730 in chat.py):
   - Finds assertions with `object_value ILIKE '%ByteDance%'`
   - Returns 12 person_ids (NO owner_id filter at this stage)
   - Adds them to `person_scores` dict

2. **Fetch person details** (line 755-757):
   ```python
   people_result = supabase.table('person').select(
       'person_id, display_name, import_source, owner_id'
   ).in_('person_id', top_person_ids)
    .eq('owner_id', user_id)  # ← FILTERS BY OWNER
    .eq('status', 'active')   # ← EXCLUDES DELETED
    .execute()
   ```
   - Filters by test user's owner_id: **NO MATCHES**
   - Filters out status='deleted': **Removes 6 more**

3. **Build results** (line 778-788):
   ```python
   for pid in top_person_ids:
       if pid not in people_by_id:  # ← ALL pids filtered out
           continue
   ```
   - All 12 person_ids are skipped
   - Result: `"people": []`

## Verdict

### Test Result: **FAIL**
The API returned 0 people when ByteDance data exists in the database.

### Code Status: **WORKING CORRECTLY**
The code is correctly:
1. Finding ByteDance mentions in assertions
2. Filtering results by owner_id (RLS/privacy)
3. Excluding deleted records
4. Returning empty results when no data matches the user's criteria

This is **working as designed** - users should only see their own network data.

### Issue: **Wrong Test Data**
The test users (telegram_id: 123456789, 987654321) don't have any ByteDance-related people in their network.

## Recommendations

To make this test PASS, choose one option:

### Option A: Import ByteDance Data for Test User
```bash
# Use the import flow to add some ByteDance people
# for test user a4f42a2c-8096-4fbf-ae70-7048e6404a83
POST /process/text
{
  "content": "Talked to Zhang Wei from ByteDance about AI infrastructure"
}
```

### Option B: Use Production User Token
Find the actual production user who owns the ByteDance data:
```sql
SELECT DISTINCT owner_id FROM person
WHERE person_id IN (
  SELECT subject_person_id FROM assertion
  WHERE object_value ILIKE '%ByteDance%'
)
AND status = 'active';
```

Then authenticate as that user and rerun the test.

### Option C: Create Dedicated Test Dataset
Set up a test fixture with known data:
```python
# In test setup:
1. Create test user
2. Add 3-5 test people with ByteDance assertions
3. Run search
4. Assert results match expected
```

## Server Logs

```
[FIND_PEOPLE] query=ByteDance, name_pattern=None, limit=20
[FIND_PEOPLE] Name search found 0 people
[FIND_PEOPLE] Detected company query: 'ByteDance'
[FIND_PEOPLE] Company search found 12 people
[FIND_PEOPLE] After company search: 12 total people
[FIND_PEOPLE] After semantic: 13 total people
[FIND_PEOPLE] Top scores: [('aaaaaaaa', 0.95), ('0d0a4974', 0.8), ...]
[FIND_PEOPLE] Hybrid search found 0 people  ← ALL FILTERED OUT
```

## Conclusion

This was a valuable E2E test that **confirmed the system is working correctly** but revealed a **test data preparation gap**. The privacy/RLS features are functioning as intended - users only see their own data.

For future testing:
1. Always verify test user owns the data being searched
2. Check both status='active' and owner_id filters
3. Consider using SQL fixtures for predictable test data
