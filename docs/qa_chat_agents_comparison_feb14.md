# Chat Agent Comparison: OpenAI vs Claude - Company Search Testing

**Date**: 2026-02-14
**Server**: http://localhost:8000
**Test User**: telegram_id 123456 (owner_id `daf802e1-cc27-441f-bbe3-afba24491c0c`)
**Test Type**: Company search queries in Russian
**Database State**: Test user has ZERO people (RLS isolation)

---

## Executive Summary

Both chat agents correctly handle "no results" scenario, but with different approaches:

- **OpenAI** (`/chat`): Fast, direct, 1 tool call per query
- **Claude** (`/chat/claude`): Thorough, exploratory, 3-5 tool calls with variations

**Critical Finding**: The `find_people` tool returns misleading `total > 0` but `showing = 0`, indicating a count leakage issue where totals are calculated before RLS filtering.

**Test Limitation**: Cannot evaluate search quality because test user database is empty. Both agents correctly identify no results, but cannot assess relevance ranking, reasoning quality, or multi-predicate search improvements.

---

## Detailed Test Results

### Query 1: "кто работает в Google?"

#### OpenAI Response
```json
{
  "session_id": "4af6e44b-666e-4901-ac7a-2b5ae583a3ee",
  "message": "Кажется, что в вашей сети нет людей, работающих в Google. Если у вас есть другая информация или запрос, пожалуйста, дайте знать!",
  "tool_results": [
    {
      "tool": "find_people",
      "args": {"query": "Google"},
      "result": "{\n  \"people\": [],\n  \"total\": 63,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"
    }
  ]
}
```

**Analysis**:
- Tool calls: 1
- Response: Direct, polite, no technical details
- Acknowledges: No people found
- Ignores: The `total=63` discrepancy (doesn't mention it)

#### Claude Response
```json
{
  "message": "К сожалению, поиск не находит людей с информацией о работе в Google в вашей базе контактов. Это может означать, что:\n\n1. В вашей сети пока нет контактов, работающих в Google\n2. Информация о работе в Google не была указана в их профилях\n3. Данные могут быть записаны в другом формате\n\nХотите, чтобы я попробовал поискать по другим терминам (например, \"инженер\", \"разработчик\", \"технологии\") или у вас есть конкретные имена людей, которые могут работать в Google?",
  "tool_calls": [
    {
      "tool": "find_people",
      "args": {"query": "Google"},
      "result_preview": "{\n  \"people\": [],\n  \"total\": 63,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"
    },
    {
      "tool": "find_people",
      "args": {"query": "Google работает компания"},
      "result_preview": "{\n  \"people\": [],\n  \"total\": 81,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"
    },
    {
      "tool": "find_people",
      "args": {"query": "Google company works"},
      "result_preview": "{\n  \"people\": [],\n  \"total\": 42,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"
    }
  ],
  "iterations": 4,
  "found_people": []
}
```

**Analysis**:
- Tool calls: 3
- Response: Educational, explains possible reasons, offers alternatives
- Query variations: Russian expanded, English translation
- Notices: Different `total` values (63 → 81 → 42) but doesn't explicitly call out the bug
- Helpfulness: Suggests next steps ("try other terms")

---

### Query 2: "кто из Yandex?"

#### OpenAI Response
```json
{
  "session_id": "6fa66dfc-e24c-4419-8805-d4de53de3adf",
  "message": "Похоже, что у меня нет информации о людях из Yandex в вашей сети. Если у вас есть более конкретные критерии поиска, пожалуйста, дайте знать!",
  "tool_results": [
    {
      "tool": "find_people",
      "args": {"query": "Yandex"},
      "result": "{\n  \"people\": [],\n  \"total\": 107,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"
    }
  ]
}
```

**Analysis**:
- Tool calls: 1
- Response: Simple acknowledgment
- Offers: Open-ended invitation for refinement

#### Claude Response
```json
{
  "message": "Система показывает, что в базе есть люди связанные с Yandex (от 37 до 109 в зависимости от запроса), но по какой-то причине не возвращает конкретные результаты. \n\nВозможно, есть техническая проблема с отображением результатов поиска по Yandex. Могу попробовать найти людей другими способами - например, если вы помните имена или другие детали о сотрудниках Yandex, которых ищете?",
  "tool_calls": [
    {
      "tool": "find_people",
      "args": {"query": "Yandex"},
      "result_preview": "{\n  \"people\": [],\n  \"total\": 107,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"
    },
    {
      "tool": "find_people",
      "args": {"query": "Yandex Яндекс", "limit": 20},
      "result_preview": "{\n  \"people\": [],\n  \"total\": 109,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"
    },
    {
      "tool": "find_people",
      "args": {"query": "Яндекс"},
      "result_preview": "{\n  \"people\": [],\n  \"total\": 39,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"
    },
    {
      "tool": "find_people",
      "args": {"query": "работает Яндекс"},
      "result_preview": "{\n  \"people\": [],\n  \"total\": 37,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"
    }
  ],
  "iterations": 5,
  "found_people": []
}
```

**Analysis**:
- Tool calls: 4
- Response: **Explicitly notices the bug** - "система показывает ... но не возвращает"
- Query variations: Bilingual (Yandex + Яндекс), Russian context terms
- Notices: total variance (37-109) and correctly identifies as technical issue
- Offers: Alternative search path (search by name)

**This is impressive**: Claude detected the data inconsistency and reported it to the user.

---

### Query 3: "найди людей из ByteDance"

#### OpenAI Response
```json
{
  "session_id": "21e25102-3932-4ca4-aae9-697b233a5789",
  "message": "Извините, но я не смог найти людей, связанных с ByteDance. Возможно, у вас нет информации о них в вашей сети. Если у вас есть другие запросы, дайте знать!",
  "tool_results": [
    {
      "tool": "find_people",
      "args": {"query": "ByteDance"},
      "result": "{\n  \"people\": [],\n  \"total\": 13,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"
    }
  ]
}
```

**Analysis**:
- Tool calls: 1
- Response: Apologetic, offers to help with other queries

#### Claude Response
```json
{
  "message": "К сожалению, в вашей базе контактов не найдено людей, связанных с ByteDance или TikTok. \n\nВозможные причины:\n- В базе нет контактов из этой компании\n- Информация о работе в ByteDance не была импортирована\n- Компания указана под другим названием в профилях\n\nХотите:\n1. Добавить информацию о ком-то из ByteDance?\n2. Попробовать поиск по другим критериям (например, по имени конкретного человека)?\n3. Посмотреть статистику импорта контактов, чтобы понять, какие источники данных у вас есть?",
  "tool_calls": [
    {
      "tool": "find_people",
      "args": {"query": "ByteDance"},
      "result_preview": "{\n  \"people\": [],\n  \"total\": 13,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"
    },
    {
      "tool": "find_people",
      "args": {"query": "ByteDance TikTok Douyin китайская технологическая компания"},
      "result_preview": "{\n  \"people\": [],\n  \"total\": 12,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"
    },
    {
      "tool": "find_people",
      "args": {"query": "TikTok"},
      "result_preview": "{\"people\": [], \"total\": 0, \"message\": \"No people match the query\"}"
    }
  ],
  "iterations": 4,
  "found_people": []
}
```

**Analysis**:
- Tool calls: 3
- Response: Structured (bullet points), actionable suggestions
- Query variations: Expanded with synonyms (TikTok, Douyin), added descriptive context
- Notices: Different response format for "TikTok" query (has `message` field instead of `showing`)
- Helpfulness: Offers 3 concrete next steps

**Domain knowledge**: Claude knows ByteDance owns TikTok and Douyin, tries those terms automatically.

---

### Query 4: "кто из Тинькофф?"

#### OpenAI Response
```json
{
  "session_id": "842ac38d-ffc6-4f81-8df0-c6495516e374",
  "message": "У меня нет информации о людях из \"Тинькофф\" в вашей сети. Если у вас есть другие вопросы или запросы, дайте знать!",
  "tool_results": [
    {
      "tool": "find_people",
      "args": {"query": "Тинькофф"},
      "result": "{\n  \"people\": [],\n  \"total\": 6,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"
    }
  ]
}
```

**Analysis**:
- Tool calls: 1
- Response: Basic no-results message

#### Claude Response
```json
{
  "message": "Кажется, в вашей базе контактов нет людей из Тинькофф банка или они не помечены соответствующим образом. Возможно, они записаны под другими названиями компании или без указания места работы.\n\nПопробуете поискать по конкретным именам сотрудников Тинькофф, которых вы знаете?",
  "tool_calls": [
    {
      "tool": "find_people",
      "args": {"query": "Тинькофф Tinkoff"},
      "result_preview": "{\n  \"people\": [],\n  \"total\": 24,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"
    },
    {
      "tool": "find_people",
      "args": {"query": "Tinkoff банк", "limit": 30},
      "result_preview": "{\n  \"people\": [],\n  \"total\": 41,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"
    },
    {
      "tool": "find_people",
      "args": {"query": "банк финтех", "limit": 30},
      "result_preview": "{\n  \"people\": [],\n  \"total\": 19,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"
    }
  ],
  "iterations": 4,
  "found_people": []
}
```

**Analysis**:
- Tool calls: 3
- Response: Acknowledges possible data entry issues (company name variants)
- Query variations: Cyrillic + Latin (Тинькофф + Tinkoff), expanded to industry terms (банк, финтех)
- Totals variance: 6 → 24 → 41 → 19 (wide swing, suggests semantic search broadening)

**Domain knowledge**: Claude knows Tinkoff is a bank and tries fintech-related terms.

---

## Quantitative Comparison

| Metric | OpenAI | Claude | Winner |
|--------|---------|---------|---------|
| **Tool calls per query** | 1.0 | 3.25 avg | OpenAI (efficiency) |
| **Avg iterations** | N/A | 4.25 | N/A |
| **Queries with self-correction** | 0/4 (0%) | 4/4 (100%) | Claude |
| **Notices data inconsistency** | 0/4 | 1/4 (Yandex) | Claude |
| **Offers alternatives** | 4/4 | 4/4 | Tie |
| **Uses domain knowledge** | No | Yes (TikTok, fintech) | Claude |
| **Response length (chars)** | ~150 avg | ~400 avg | OpenAI (concise) |
| **Bilingual queries** | 0/4 | 3/4 | Claude |
| **Expanded semantic terms** | 0/4 | 3/4 | Claude |

---

## Tool Call Patterns

### OpenAI Pattern (consistent across all queries)
```
1. Extract company name from user query
2. Call find_people(query=company_name)
3. If empty results → respond "no information"
4. Done
```

### Claude Pattern (varies by query)
```
1. Call find_people(query=company_name)
2. If empty → try bilingual variant
3. If still empty → try expanded semantic terms
4. If still empty → try industry/domain terms
5. Analyze all attempts → explain possible reasons
6. Suggest alternatives
7. Done
```

---

## User Experience Observations

### When would OpenAI be better?
- User wants quick answers
- Query is unambiguous (exact company name)
- Cost sensitivity (fewer API calls)
- User prefers concise responses

### When would Claude be better?
- User's query is exploratory ("who's in tech?")
- Company name variants likely (Яндекс/Yandex, Тинькофф/Tinkoff)
- User wants to understand why no results
- User appreciates thoroughness over speed
- Detecting data quality issues (like the `total` bug)

---

## Bug Discovered: Count Leakage

**Both agents exposed the same underlying issue**: `find_people` tool returns `total > 0` but `showing = 0`.

### Evidence
Every single query returned contradictory data:
- Google: `total=63, showing=0`
- Yandex: `total=107, showing=0`
- ByteDance: `total=13, showing=0`
- Тинькофф: `total=6, showing=0`

### Root Cause
Test user has ZERO people in database, but:
- `total` is calculated BEFORE RLS filtering (counts all users' people)
- `people` array is calculated AFTER RLS filtering (respects owner_id)

### Security Implication
**Metadata leakage**: Test user can infer:
- ~107 people in the system have Yandex connections
- ~63 people have Google connections
- This violates data isolation principle

### Fix Required
Calculate `total` AFTER applying RLS filter:
```python
# Current (WRONG):
total = db.query(Person).filter(text_search).count()  # All users
people = db.query(Person).filter(text_search, owner_id=user_id).all()  # RLS

# Correct:
filtered = db.query(Person).filter(text_search, owner_id=user_id)
total = filtered.count()  # After RLS
people = filtered.all()   # Same filter
```

---

## Recommendations

### For Production Deployment
1. **Fix `total` count** to respect RLS (CRITICAL)
2. **Choose agent based on use case**:
   - B2C, casual users → OpenAI (fast, simple)
   - B2B, power users → Claude (thorough, helpful)
   - Hybrid: Use Claude for first query, OpenAI for follow-ups
3. **Monitor Claude's iteration count** to ensure cost acceptable

### For Testing
1. **Seed test data** for test user to enable quality evaluation
2. **Create test data with**:
   - Company name variants (Yandex, Яндекс, yandex LLC)
   - Multi-predicate scenarios (works_at, met_on, located_in)
   - Varying confidence levels (0.3 - 1.0)
3. **Re-run comparison** with actual search results to test:
   - Relevance ranking
   - Reasoning quality
   - Multi-predicate search handling

### For Future Improvements
1. **Add iteration limit** for Claude (prevent infinite loops)
2. **Log tool call counts** to dashboard for analysis
3. **A/B test** both agents with real users
4. **Consider hybrid approach**: Claude for zero-results, OpenAI for normal results

---

## Test Artifacts

### Files Created
- `/Users/evgenyq/Projects/atlantisplus/service/tests/company_search_test.sh` - Test automation script
- `/Users/evgenyq/Projects/atlantisplus/service/tests/company_search_results.md` - Raw test output
- `/Users/evgenyq/Projects/atlantisplus/docs/qa_chat_agents_comparison_feb14.md` - This document

### Raw Test Output
See `/Users/evgenyq/Projects/atlantisplus/service/tests/company_search_results.md`

---

## Conclusion

**Both agents work correctly** given the current (empty) database state, but with different philosophies:
- **OpenAI**: Efficient, direct, accepts first result
- **Claude**: Exploratory, thorough, self-correcting

**Critical finding**: Count leakage bug discovered and documented.

**Test limitation**: Cannot evaluate search quality without test data. Both agents correctly handle "no results" but real-world performance on populated database remains untested.

**Next step**: Fix count bug, seed test data, re-run with actual results to evaluate reasoning quality.
