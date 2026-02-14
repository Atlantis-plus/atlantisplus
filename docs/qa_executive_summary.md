# QA Executive Summary - Company Search Testing
**Date**: 2026-02-13
**Status**: 7/7 tests completed with real data
**Verdict**: DO NOT DEPLOY (3 critical issues found)

---

## Key Findings

| Metric | Value | Status |
|--------|-------|--------|
| Tests Completed | 7/7 | ✅ |
| Tests Passed | 1/7 | ❌ |
| Critical Issues | 1 | 🔴 |
| High Priority Issues | 2 | 🟠 |
| Medium Priority Issues | 3 | 🟡 |
| Database Health | 2,032 people, 21,971 assertions | ✅ |
| Embedding Coverage | 99.995% | ✅ |

---

## Test Results at a Glance

| Test | Result | Recall Loss | Severity |
|------|--------|-------------|----------|
| ✅ Embedding coverage | 99.995% | 0% | LOW |
| ❌ ByteDance (met_on) | 0 people found | 100% | 🔴 CRITICAL |
| ❌ Tinkoff rebrand | 1/7 people | 86% | 🟠 HIGH |
| ❌ Yandex variants | 25/38 people | 34% | 🟠 HIGH |
| ❌ Email inference | 0% correlation | - | 🟡 MEDIUM |
| ❌ Google intro predicates | 14/18 mentions | 22% | 🟡 MEDIUM |
| ❌ Company fragmentation | 1,318 strings / ~400 companies | 3.3x | 🟡 MEDIUM |

---

## Critical Issue: ByteDance Case

**Problem**: Search query "кто работает в ByteDance?" returns 0 results, but database contains 5 relevant people.

**Root Cause**: All ByteDance connections stored in `met_on` predicate (meeting context), but search only looks at `works_at`.

```
Database:
- met_on: 5 people (Irene Hong, sharon.jiang, etc.)
- works_at: 0 people

Current search: filters by works_at only
Result: 0 people found (100% recall loss)
```

**User Impact**: Any company mentioned in meeting context becomes invisible to search.

**Fix Required**: Search across multiple predicates (works_at, met_on, knows, worked_on).

**Effort**: 1-2 days

---

## High Priority Issues

### 1. Tinkoff/T-Bank Rebrand (86% recall loss)

```
Company rebranded: Tinkoff → T-Bank (2023)

Database:
- Tinkoff: 3 people
- Tinkoff Bank: 3 people
- T-Bank: 1 person

Search "T-Bank": finds 1 person (14%)
Search "Tinkoff": finds 6 people (86%)
```

**Fix**: Company alias table mapping old/new names.

### 2. Yandex Variants (34% recall loss)

```
11 Yandex variants in database:
- Yandex (25), Yandex Cloud (2), Yandex Eats (2),
- Yandex.Market (2), Яндекс (1), etc.

Search "Yandex": finds 25 people (66%)
Should find: 38 people (100%)
```

**Fix**: Company normalization with canonical names.

---

## Medium Priority Issues

### 3. Email Domain Inference (0% correlation)

20 corporate emails checked: 0 have corresponding `works_at` assertion.

Example: `john@stripe.com` → works_at is NULL (should auto-create "Stripe")

### 4. Intro Predicates (22% missed)

Google mentions: 14 works_at, 3 met_on, 1 role_is

Search only looks at works_at → misses 4/18 connections (22%)

### 5. Company Fragmentation (3.3x duplication)

1,318 unique company strings for ~400 actual companies.

Examples: "Freelance" vs "Фриланс", "Self-employed" vs "Предприниматель"

---

## Priority Roadmap

### P0 - CRITICAL (Must fix before deploy)

1. **Multi-predicate search** (1-2 days)
   - Fix ByteDance case (100% recall loss)
   - Search across works_at, met_on, knows, worked_on

2. **Company normalization** (3-4 days)
   - Fix Yandex (34% loss) and Tinkoff (86% loss)
   - Add canonical company table + variant mapping

**Total P0**: 4-6 days

### P1 - HIGH (Should fix soon)

3. **Email domain inference** (1 day)
   - Auto-create works_at from corporate emails

4. **Company clustering** (2-3 days)
   - Reduce 3.3x fragmentation to <2x
   - Build admin UI for merging

**Total P1**: 3-4 days

### P2 - MEDIUM (Nice to have)

5. **Embedding regeneration** (1 day)
   - Future-proof manual edits

**Total effort**: 7-10 days

---

## Recommended Action

**DO NOT DEPLOY** current search functionality.

**Why**:
- 100% recall loss for meeting-based connections (ByteDance case)
- 86% recall loss for rebranded companies (Tinkoff→T-Bank)
- 34% recall loss for company variants (Yandex)
- Users would be frustrated: "I know this person works there, why can't I find them?"

**Next Steps**:
1. Review findings with team
2. Approve P0 roadmap (4-6 days)
3. Schedule implementation sprint
4. Re-test after fixes
5. Deploy when recall >90%

---

## Good News

### What Works Well

✅ **Embedding coverage**: 99.995% (excellent)
✅ **Database health**: 2,032 people, 21,971 assertions
✅ **Infrastructure**: Database stable, queries fast
✅ **Data volume**: Sufficient for MVP testing

### Quick Wins

Some issues have straightforward fixes:
- Multi-predicate search: 1-2 days
- Email inference: 1 day
- Both have clear implementation paths

---

## Files Generated

All findings documented in `/Users/evgenyq/Projects/atlantisplus/docs/`:

1. `qa_executive_summary.md` - This summary
2. `qa_results_final.md` - Detailed test results (20+ pages)
3. `qa_summary.md` - Original predictions
4. `qa_company_search_report.md` - Architectural analysis
5. `issues.md` - Issue tracker

**Test script ready**: `/Users/evgenyq/Projects/atlantisplus/qa_company_search.py`

---

**Bottom Line**: Fix P0 issues (4-6 days) before deploying. Current state has 3 critical search quality issues that would frustrate users.
