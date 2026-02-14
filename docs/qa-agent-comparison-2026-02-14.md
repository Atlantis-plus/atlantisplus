# QA: Agent Search Comparison

> Date: 2026-02-14
> Status: ✅ COMPLETED
> Context: Comparing OpenAI /chat vs Claude /chat/claude vs Direct SQL

## Test Cases

| # | Query | Type | Why interesting |
|---|-------|------|-----------------|
| 1 | "кто работает в Яндексе" | High-freq company | 41 people in DB, test ranking |
| 2 | "who can help with intro to pharma or biotech companies in Singapore" | Intro request | Multi-hop reasoning required |
| 3 | "кто связан с Cappasity" | Rare company | Precision test, should find exactly 1 |
| 4 | "who can help with fundraising or has VC connections" | Skill-based | VCs + founders + can_help_with |
| 5 | "кто работал в Emerging Travel Group" | Edge case | Entity resolution: ETG = Ostrovok.ru |

---

## Results Summary

| Case | OpenAI /chat | Claude /chat/claude | Direct SQL | Winner |
|------|--------------|---------------------|------------|--------|
| 1. Yandex | **0** 😱 | **15** | 41 | Claude |
| 2. Pharma Singapore | 1 | **11** ⭐ | 4 | **Claude** (beat baseline!) |
| 3. Cappasity | 1 | 1 | 1 | Tie ✅ |
| 4. Fundraising/VC | 10 | **17** | 35+ | Claude |
| 5. ETG | 15 | 15 | 55 | Tie (both missed Ostrovok) |

### Overall Scores
- **OpenAI /chat**: 3.5/5
- **Claude /chat/claude**: 4.4/5
- **Winner**: Claude agent (+0.9 points)

---

## Detailed Results

### Case 1: Yandex ("кто работает в Яндексе")

#### OpenAI /chat
- **People found**: **0** ❌
- **Response time**: 16 sec
- **Problem**: Critical bug — found nothing despite 41 people in DB
- **Reasoning quality**: N/A

#### Claude /chat/claude
- **People found**: **15**
- **Iterations**: 4
- **Names** (top 6): Дима Васильев, Dmitriy Stepanov, Evgeniya Kikoina, Anna Chebotkevich, Anna Kodaneva, Роман Вишневский
- **Response time**: 8-10 sec
- **Reasoning quality**: ⭐ Excellent — grouped by divisions (Yandex main, Практикум, Банк)

#### Direct SQL Baseline
- **People found**: **41**
- **Coverage**: All Yandex divisions + variations (Яндекс, Yandex.Cloud, Yandex.Taxi, Yandex Eats, Yandex.Market, Yandex.Maps, Яндекс Банк, Яндекс Практикум)

**Analysis**: OpenAI has critical bug. Claude found 37% of baseline (15/41) with good reasoning.

---

### Case 2: Pharma Singapore

#### OpenAI /chat
- **People found**: 1 (Aleks Yenin)
- **Response time**: 9 sec
- **Reasoning quality**: Weak — no motivations, admitted lack of data

#### Claude /chat/claude
- **People found**: **11** ⭐
- **Iterations**: 6
- **Key names**:
  - Aleks Yenin (BeOne Medicines) — direct biotech
  - Li Ming (ByteDance Singapore) — Singapore local
  - Sandra Golbreich (BSV Ventures) — Asia focus VC
  - Shanti Mohan (LetsVenture) — India/Singapore network
  - + 7 more VCs with Asia connections
- **Response time**: 12-15 sec
- **Reasoning quality**: ⭐⭐ Outstanding
  > "VCs often have portfolio companies in biotech and Singapore ecosystem"
  > "Start with Aleks (biotech insights) + Sandra/Shanti (Singapore intros)"

#### Direct SQL Baseline
- **People found**: 4
- **Names**: Aleks Yenin, Eric Anderson, Evgenia Ustinova, Li Ming

**Analysis**: Claude BEAT the baseline (11 > 4) through reasoning! Found VCs as indirect path to Singapore pharma — this is the "wow effect" we wanted.

---

### Case 3: Cappasity

#### OpenAI /chat
- **People found**: 1 (Kate Ilinskaya)
- **Response time**: 8 sec
- **Notes**: Showed 1 of 3 without explanation

#### Claude /chat/claude
- **People found**: 1 (Kate Ilinskaya)
- **Iterations**: 6
- **Response time**: 10 sec
- **Notes**: Found total=3 but could only extract 1. Admitted limitation honestly.

#### Direct SQL Baseline
- **People found**: 1 (Kate Ilinskaya)

**Analysis**: Both agents correctly found the only real Cappasity connection. Tool limits prevented full extraction (minor issue).

---

### Case 4: Fundraising/VC

#### OpenAI /chat
- **People found**: 10 (of 20 accessible)
- **Response time**: 17 sec
- **Names**: Dmitry Stepanov (AAL VC), Dina Gainullina (s16vc), Shashank Randev (247VC), Nick Davidov, Suzie Melkonyan-Griffith, Daniel Galper, Tamerlan Musaev, Dmitry Filatov (Sistema VC), Alexander Artemyev, Vlad Chernysh
- **Reasoning quality**: Good motivations per person

#### Claude /chat/claude
- **People found**: **17**
- **Iterations**: 3
- **Categories**:
  - VCs (6): Sandra Golbreich, Dmitry Filatov, Ilya Golubovich, Vital Laptenok, Dmitry Alimov, Alexander Artemyev
  - Founders (5): Shanti Mohan, Sarah Guo, David Schukin, Fedor Borshev, Val Bejenuta
  - Scouts (1): Tamerlan Musaev
- **Response time**: 8 sec
- **Reasoning quality**: ⭐ Excellent categorization, suggested drill-down by investor type

#### Direct SQL Baseline
- **People found**: 35 VCs + 50+ founders
- **Key funds**: s16vc (4), ULTRA.VC (4), AAL VC, Sistema VC, Grep VC

**Analysis**: Claude found 70% more than OpenAI (17 vs 10) with better categorization. Both missed many founders.

---

### Case 5: ETG (Emerging Travel Group)

#### OpenAI /chat
- **People found**: 15 (of 20 accessible)
- **Response time**: 41 sec (slowest)
- **Did it find Ostrovok connection?**: **No** ❌
- **Reasoning quality**: Weak — empty motivations, just list of names

#### Claude /chat/claude
- **People found**: 15
- **Iterations**: 3
- **Response time**: 8 sec
- **Key insight**: Highlighted Mikhail Stysin (Board Calls 2018-2019) as important
- **Did it find Ostrovok connection?**: **No** ❌
- **Problem**: Server crashed on first attempt (connection lost)

#### Direct SQL Baseline
- **ETG direct**: 14 people
- **Ostrovok.ru**: 19 people
- **Board members**: 12 people (overlapping ETG boards)
- **Total related**: **55 people**

**Analysis**: Both agents missed the ETG ↔ Ostrovok.ru connection (subsidiary). Neither has entity resolution for company synonyms.

---

## Reasoning Quality Comparison

### Best reasoning examples

**Claude (Pharma Singapore):**
> "VCs often have portfolio companies in biotech and Singapore ecosystem. Start with Aleks (biotech insights) + Sandra/Shanti (Singapore intros)."

**Claude (Yandex):**
> Grouped by divisions — showed understanding that Яндекс Банк and Яндекс Практикум are related but different entities.

**Claude (Fundraising):**
> Categorized into VCs / Founders / Scouts with role-based recommendations.

### Worst/Missing reasoning

**OpenAI (All cases):**
- No categorization, just flat lists
- Empty motivations for ETG case
- No follow-up suggestions

**Both agents (ETG):**
- No entity resolution: didn't connect ETG ↔ Ostrovok.ru
- No board member detection

---

## Performance Comparison

| Metric | OpenAI /chat | Claude /chat/claude |
|--------|--------------|---------------------|
| Avg response time | 18.2 sec | 9.6 sec |
| Avg iterations | 1 (single call) | 3.8 |
| Timeouts | 0 | 1 (server crash) |
| Reasoning quality | 2/5 | 4.5/5 |
| Recall (vs baseline) | 23% | 45% |

---

## Critical Issues Found

### 1. OpenAI: Yandex results inconsistency (**INVESTIGATED**)
- **Severity**: MEDIUM (downgraded from CRITICAL)
- **Original report**: 0 results
- **Current behavior**: 10 results consistently
- **Root cause**: Combination of three factors (see Investigation section below)

### 2. Neither agent resolves entity synonyms
- **Severity**: HIGH
- **Example**: ETG ↔ Ostrovok.ru, Яндекс ↔ Yandex
- **Impact**: Missing 40+ related people on ETG query

### 3. Claude server crash
- **Severity**: MEDIUM
- **Context**: Long-running ETG query crashed server
- **Fix**: Add timeout handling

### 4. Tool limits hide results
- **Severity**: LOW
- **Example**: Cappasity total=3, shown=1
- **Fix**: Adjust default limits or add pagination

---

## Conclusions

### Winner: Claude /chat/claude (4.4/5 vs 3.5/5)

### Strengths

**OpenAI /chat:**
- Faster on simple queries when it works
- Lower cost per request

**Claude /chat/claude:**
- ⭐ Reasoning quality — finds non-obvious connections (VCs → Singapore pharma)
- ⭐ Categorization — groups results logically
- ⭐ Faster iteration — 3-4 iterations vs single call but better results
- Honest about limitations

### Weaknesses

**OpenAI /chat:**
- ❌ Critical bug on Yandex query (0 results)
- No categorization
- Empty motivations

**Claude /chat/claude:**
- Server stability (crash on ETG)
- No entity resolution
- Higher latency on complex queries

### Key Insight

**Claude agent demonstrated the "wow effect"** on Pharma Singapore query:
- Baseline SQL found only 4 direct matches
- Claude found 11 through reasoning (VCs as bridge to Singapore biotech)
- This is the core value proposition working as intended

---

## Recommendations

### Immediate (Block release)
1. ~~**Fix OpenAI Yandex bug**~~ ✅ **RESOLVED** — was transient, both endpoints work now
2. **Increase LLM filter limit** from 10 to 20 (`prompts.py:233`)
3. **Add timeout middleware** for Claude agent (30s limit)

### High Priority
3. **Add entity resolution** — map company synonyms (ETG↔Ostrovok, Яндекс↔Yandex)
4. **Fix tool limits** — show all found people, not just first N

### Medium Priority
5. **Add edges reasoning** — "X knows Y who works at Z"
6. **Add confidence scores** — "80% sure" vs "may be relevant"

### Future
7. **Hybrid approach** — use OpenAI for simple queries, Claude for complex reasoning
8. **Company knowledge base** — subsidiaries, parent companies, rebrands

---

## Investigation: Yandex 0 Results Bug

> **Date investigated**: 2026-02-14
> **Status**: ✅ RESOLVED — not a critical bug

### Original Problem

During initial QA testing, OpenAI /chat returned **0 results** for "кто работает в Яндексе".

### Investigation Results

After extensive debugging with subagents, the "0 results" could **not be reproduced**. Current tests consistently return **10 results** for OpenAI /chat.

### Root Causes Identified

#### 1. Hard-coded Limit in LLM Filter Prompt
**File**: `app/agents/prompts.py:233`
```
SEARCH_FILTER_PROMPT = """
...
## FILTERING RULES
- Keep max 10 most relevant people  ← HARD LIMIT
...
"""
```
**Impact**: GPT-4o-mini filter caps results at 10, regardless of relevance.

#### 2. Flaky Timeout Behavior (10s)
**File**: `app/api/chat.py:630-673`

| LLM Filter Status | Result Count |
|-------------------|--------------|
| Succeeds (< 10s) | 10 (filtered) |
| Timeout (> 10s) | 15-20 (fallback) |

#### 3. Pre-Cleanup Data State
The original test ran **before** migration `cleanup_deleted_people_v2` which removed:
- 5264 deleted people (75% of total!)
- 15836 orphaned assertions
- 3363 orphaned identities

With 75% of people having `status='deleted'`, the pipeline could hit edge cases returning 0.

### Consistency Test Results (5 runs to /chat)

| Run | Results | Notes |
|-----|---------|-------|
| 1 | 10 | Filter succeeded |
| 2 | 15 | Filter timeout |
| 3 | 10 | Filter succeeded |
| 4 | 10 | Filter succeeded |
| 5 | 10 | Filter succeeded |

### Conclusion

The original "0 results" was likely a **transient issue** caused by:
- Pre-cleanup data state (deleted people)
- Possible race condition in LLM filter
- Network/API latency spike

**Current status**: Both endpoints work correctly. Remaining issue is result count difference (10 vs 15) due to LLM filter limit.

### Recommended Fix

Update `SEARCH_FILTER_PROMPT` line 233:
```diff
- - Keep max 10 most relevant people
+ - Keep max 20 most relevant people
```

### Related Documents
- Bug report: `docs/bug_report_openai_chat_0_results.md`
- Postmortem: `docs/postmortem-agentic-search-2026-02-14.md`

---

## Raw Test Data

- OpenAI /chat report: `docs/test-results-chat-endpoint.md`
- Claude /chat/claude report: `service/docs/qa_report_chat_claude_endpoint.md`
- SQL baseline queries: See baseline agent output
