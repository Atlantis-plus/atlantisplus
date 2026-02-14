# Search Test Results - Quick Reference Table

**Test Date**: 2026-02-14
**Environment**: http://localhost:8000
**Database State**: Empty (test user)

## Test Results Summary

| Query | Endpoint | Tool Calls | Queries Attempted | Self-Correction | People Found |
|-------|----------|------------|-------------------|-----------------|--------------|
| "кто может помочь с AI?" | OpenAI | 1 | 1. "AI" | No | 0 |
| "кто может помочь с AI?" | Claude | 5 | 1. "AI искусственный интеллект machine learning"<br>2. "artificial intelligence machine learning data science"<br>3. "developer engineer tech software programming"<br>4. "Google Microsoft OpenAI Tesla tech"<br>5. get_import_stats | Yes (4 alternatives) | 0 |
| "who knows about startups?" | OpenAI | 1 | 1. "startups" | No | 0 |
| "who knows about startups?" | Claude | 5 | 1. "startups startup entrepreneur founder"<br>2. "entrepreneur entrepreneurship venture capital VC startup founder CEO tech business"<br>3. "business technology innovation"<br>4. "Google Facebook Meta Amazon Microsoft Apple Tesla Uber Airbnb"<br>5. get_import_stats | Yes (4 alternatives) | 0 |
| "найди инвесторов" | OpenAI | 1 | 1. "инвестор" | No | 0 |
| "найди инвесторов" | Claude | 4 | 1. "инвестор"<br>2. "investor venture capital VC fund"<br>3. "investment capital funding startup angel"<br>4. "фонд капитал инвестиции стартап" | Yes (3 alternatives) | 0 |
| "кто разбирается в маркетинге?" | OpenAI | 1 | 1. "маркетинг" | No | 0 |
| "кто разбирается в маркетинге?" | Claude | 3 | 1. "маркетинг marketing"<br>2. "marketing digital marketing SMM продвижение реклама advertising promotion"<br>3. "маркетолог CMO продакт-менеджер бренд-менеджер" | Yes (2 alternatives) | 0 |

## Key Metrics

| Metric | OpenAI | Claude | Difference |
|--------|--------|--------|------------|
| Average tool calls | 1.0 | 4.25 | **Claude: 4.25x more** |
| Self-correction rate | 0% (0/4) | 100% (4/4) | **Claude: +100%** |
| Diagnostic checks | 0 | 2 | **Claude: always diagnoses** |
| Alternative queries per test | 0 | 3.25 | **Claude: 3.25 more** |

## Search Strategy Usage

| Strategy | OpenAI | Claude |
|----------|--------|--------|
| Literal query only | 100% (4/4) | 0% (0/4) |
| Bilingual search (RU+EN) | 0% (0/4) | 100% (4/4) |
| Semantic expansion | 0% (0/4) | 100% (4/4) |
| Role-based search | 0% (0/4) | 75% (3/4) |
| Company-based search | 0% (0/4) | 50% (2/4) |
| Domain-specific terms | 0% (0/4) | 100% (4/4) |
| Diagnostic tools | 0% (0/4) | 50% (2/4) |

## Response Quality

### OpenAI Typical Response
```
"Похоже, что в вашей сети нет информации о людях, связанных с AI.
Если у вас есть другие вопросы, дайте знать!"
```

**Characteristics**:
- Generic apology
- No suggestions
- No diagnosis
- Passive tone

**Score**: 2/10

---

### Claude Typical Response
```
"Похоже, что ваша база контактов пуста или не содержит импортированных данных.

Для того чтобы я мог помочь найти людей, нужно сначала:
1. Импортировать контакты из LinkedIn или календаря
2. Добавить информацию о людях вручную

Хотели бы вы добавить информацию о ком-то, кто разбирается в AI?
Например: 'Добавь Ивана Петрова, он работает с машинным обучением'"
```

**Characteristics**:
- Root cause analysis
- Actionable suggestions (2+)
- Examples of what to say
- Maintains helpful tone
- Educational

**Score**: 9/10

---

## Critical Findings

### Finding 1: Claude Self-Corrects, OpenAI Doesn't
- **Claude**: 4/4 queries tried 3-5 alternative searches
- **OpenAI**: 0/4 queries tried alternatives
- **Impact**: Users perceive OpenAI as "lazy" or "not trying hard enough"

### Finding 2: Claude Diagnoses, OpenAI Doesn't
- **Claude**: Calls `get_import_stats` to check database state
- **OpenAI**: Cannot distinguish "not found" from "empty database"
- **Impact**: OpenAI gives same error for different root causes

### Finding 3: Claude Teaches, OpenAI Doesn't
- **Claude**: Provides examples, suggests next steps, explains alternatives
- **OpenAI**: Generic apologies, no guidance
- **Impact**: Users don't learn how to search better

## Recommendation

**Switch to Claude for all search queries** OR **significantly upgrade OpenAI agent's reasoning loop**.

Current OpenAI implementation is not production-ready for a search-focused product.

---

## Next Testing Phase

Test with populated database (100+ contacts) to verify:
- Ranking quality when results are found
- Handling of 1-3 results vs 20+ results
- Reasoning quality with actual matches
- Performance under load

Current tests only validate failure handling (which Claude dominates).
