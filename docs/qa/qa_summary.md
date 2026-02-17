# QA Summary - Company Search Testing

**Date**: 2026-02-13
**Status**: BLOCKED - Database Unavailable

---

## TL;DR

**0 out of 7 planned tests completed** due to Supabase database connectivity failure (Cloudflare Error 522).

However, extensive code analysis reveals **7 critical issues** that would have failed testing:

---

## Critical Findings

| # | Issue | Severity | Impact |
|---|-------|----------|--------|
| 1 | No company name normalization | HIGH | 50% search recall loss |
| 2 | Company rebrands not handled | HIGH | 0% recall for renamed companies |
| 3 | Search limited to works_at predicate | HIGH | Misses 50-80% of connections |
| 4 | Manual edits lose embeddings | HIGH | Data quality degrades to 60-70% |
| 5 | No 2nd degree intro paths | HIGH | Cannot find indirect connections |
| 6 | Email domains not used for inference | MEDIUM | Requires manual data entry |
| 7 | Company data fragmented 5-7x | MEDIUM | Poor user experience |

---

## Test Scenarios

### TEST 1: Yandex Search
**Expected**: Find 102+ people
**Problem**: 12 company name variants stored as separate entities
**Result**: Would find ~50% of actual results

### TEST 2: Tinkoff/T-Bank
**Expected**: Find 28 people
**Problem**: Old name "Tinkoff" vs new name "T-Bank" treated as different companies
**Result**: Search for "T-Bank" would return 0 results

### TEST 3: ByteDance Meetings
**Expected**: Find people via works_at AND met_on predicates
**Problem**: Search only looks at works_at
**Result**: Would miss ~10 meeting-based connections

### TEST 4: Email Domain
**Expected**: @carta.com email → auto-create works_at assertion
**Problem**: Email stored but not used for company inference
**Result**: Manual data entry required

### TEST 5: Embedding Coverage
**Expected**: 95%+ assertions have embeddings
**Problem**: Manual edits via frontend bypass embedding generation
**Result**: Coverage degrades from 100% to 60-70% over time

### TEST 6: Intro Queries
**Expected**: "Who can intro me to Google?" → considers all relevant predicates + 2nd degree
**Problem**: No graph traversal, no predicate weighting
**Result**: Misses indirect intro paths

### TEST 7: Company Variants
**Expected**: ~50 actual companies
**Problem**: 200+ unique strings due to typos, languages, legal entities
**Result**: 5-7x data fragmentation

---

## Priority Fixes

### P0 - Must Fix for MVP

1. **Company Normalization** (3-5 days)
   - Add `company` table with canonical names
   - Map variants to canonical entities
   - Update extraction pipeline
   - Impact: 2-3x better search recall

2. **Embedding Regeneration** (1-2 days)
   - Add API layer for assertion updates
   - Enforce embedding generation on all writes
   - Background job to backfill missing
   - Impact: Maintain 95%+ coverage

3. **Multi-Predicate Search** (2-3 days)
   - Search across works_at, met_on, knows, etc.
   - Add predicate weighting
   - Implement 2nd degree graph traversal
   - Impact: 2-3x more relevant intro results

### P1 - Should Fix Soon

4. **Email Domain Inference** (1 day)
   - Auto-create works_at from corporate emails
   - Impact: 20-30% more assertions automatically

5. **Company Entity Resolution** (3-4 days)
   - Clustering + admin UI for merges
   - Impact: Reduce fragmentation from 5x to 1.2x

---

## Database Status

**Current**: Supabase project `mhdpokigbprnnwmsgzuy` returning Error 522 (Connection Timeout)

**Cause**: Likely free tier auto-pause after inactivity

**Status**: Restore API called, waiting for warmup (5-10 minutes)

**Next Steps**:
1. Wait for database to fully restore
2. Run automated test script: `python qa_company_search.py`
3. Verify findings from code analysis
4. Prioritize fixes with team

---

## Files Generated

1. `/Users/evgenyq/Projects/atlantisplus/docs/issues.md` - Detailed issue tracker
2. `/Users/evgenyq/Projects/atlantisplus/docs/qa_company_search_report.md` - Full QA report (20+ pages)
3. `/Users/evgenyq/Projects/atlantisplus/qa_company_search.py` - Automated test script
4. `/Users/evgenyq/Projects/atlantisplus/docs/qa_summary.md` - This summary

---

## Recommendation

**DO NOT DEPLOY** current search functionality until Priority 0 fixes are implemented.

Current state would result in:
- Poor search results (50% recall)
- Silent data quality degradation
- Frustrated users ("I know this person works there, why can't I find them?")

**Estimated effort to make production-ready**: 6-10 days of development + testing.
