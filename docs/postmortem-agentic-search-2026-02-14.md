# Postmortem: Agentic Search Comparison

> Дата: 2026-02-14
> Статус: ✅ RESOLVED
> Контекст: Сравнение Claude Code vs самодельного Claude Agent для поиска в базе

## Resolution (2026-02-14)

**Причина найдена:** 75% людей были в status='deleted' (откаты тестовых импортов).

**Исправлено:** Migration `cleanup_deleted_people_v2` удалила:
- 5264 deleted people
- 15836 orphaned assertions
- 3363 orphaned identities

**Результат после очистки:**
- Google в базе: 16 active
- Агент находит: 15 (1 отфильтрован LLM по релевантности)
- Числа теперь консистентны ✅

---

## Ключевой феномен

**В базе 64 человека из Google, но агенты возвращают только 10.**

```
[FIND_PEOPLE] query=Google
[FIND_PEOPLE] Name search found 1 people
[FIND_PEOPLE] Company search found 63 people
[FIND_PEOPLE] After company search: 64 total people
[FIND_PEOPLE] Hybrid search found 14 people        ← Куда делись 50?
[FIND_PEOPLE] Filtered 14 -> 10 with motivations   ← Ещё -4
```

---

## Что происходит в pipeline

```
64 человека в БД (Google)
        │
        ▼
┌─────────────────────────────────────────┐
│ 1. Name search: 1 человек               │
│ 2. Company multi-predicate: 63 человека │
│ 3. Semantic search: merge               │
│    ИТОГО: 64 unique person_ids          │
└─────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────┐
│ 4. Fetch person details                  │
│    - eq('status', 'active')              │
│    - in shared_mode: нет owner filter    │
│    РЕЗУЛЬТАТ: только 14 прошли          │  ← ПОТЕРЯ 50 человек!
└─────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────┐
│ 5. filter_and_motivate_results (LLM)     │
│    - Limit to top 15 for LLM             │
│    - LLM фильтрует по релевантности      │
│    РЕЗУЛЬТАТ: 10 с motivations          │  ← ПОТЕРЯ ещё 4
└─────────────────────────────────────────┘
        │
        ▼
   10 человек в ответе
```

---

## ✅ ПРИЧИНА НАЙДЕНА

### Status filtering — ПОДТВЕРЖДЕНО

```sql
SELECT status, COUNT(DISTINCT person_id) FROM person p
JOIN assertion a ON p.person_id = a.subject_person_id
WHERE a.object_value ILIKE '%Google%' GROUP BY status;

-- deleted: 47
-- active:  16
```

**75% людей с "Google" имеют status='deleted'!**

Assertions остались, но person soft-deleted. Pipeline:
- Company search находит 63 person_ids из assertions (не фильтрует по status)
- Fetch people с `eq('status', 'active')` → только 16 проходят
- После LLM мотиваций → 10 в финальном ответе

### Гипотеза 1: Status filtering — ✅ ПОДТВЕРЖДЕНО
```python
# Строка ~758 в chat.py
people_query = supabase.table('person').select(...).eq('status', 'active')
```
**Ответ:** Да, 47 человек имеют status='deleted'

### Гипотеза 2: person_ids не матчатся
Semantic search возвращает `subject_person_id` из assertion.
Company search ищет в assertion по `object_value`.
**Вопрос:** Эти person_id существуют в таблице person?

### Гипотеза 3: Дубликаты
Company search может вернуть один person_id несколько раз.
**Вопрос:** `len(person_scores)` считает unique или total?

### Гипотеза 4: RLS даже в shared mode
Supabase RLS может быть на уровне таблицы.
**Вопрос:** Service role key обходит RLS?

---

## Сравнение агентов

### Claude Code (я) vs Self-built Claude Agent

| Аспект | Claude Code | Self-built Agent |
|--------|-------------|------------------|
| Tool calls | Unlimited | 1-2 per query |
| Self-correction | Автоматически | Зависит от system prompt |
| Доступ к БД | Через Supabase MCP | Через find_people tool |
| Видит raw data | Да (SQL результаты) | Нет (только JSON ответ) |
| Может диагностировать | Да | Нет |

### Ключевое различие

**Claude Code может:**
```sql
SELECT COUNT(*) FROM person WHERE status = 'active';
-- и увидеть реальное число
```

**Self-built Agent получает:**
```json
{"people": [...10 items...], "total": 14, "showing": 10}
```
Он не знает что было 64 кандидата до фильтрации.

---

## Что агент НЕ делает (но мог бы)

1. **Не вызывает tool повторно с большим limit**
   - Видит "showing 10 of 14" но не запрашивает остальные

2. **Не пробует разные query variations**
   - "Google" работает → не пробует "Google Inc", "Alphabet"

3. **Не запрашивает детали по ID**
   - Мог бы: find_people → get_person_details для каждого

4. **Не диагностирует проблемы**
   - Не замечает что total < expected

---

## Данные для deep dive

### Файлы с кодом
- `service/app/api/chat.py` — find_people tool, строки 681-865
- `service/app/api/chat.py` — filter_and_motivate_results, строки 575-673
- `service/app/services/claude_agent.py` — agentic loop

### Логи тестов
- `/private/tmp/claude-501/.../tasks/a9862c4.output` — company search QA
- Server logs показывают точные counts на каждом этапе

### Ключевые вопросы для исследования

1. **Куда пропадают 50 человек между "64 total" и "14 fetched"?**
   - Проверить: статусы, существование person_id, RLS

2. **Почему агент не итерирует за большим количеством?**
   - System prompt не говорит ему делать это
   - Tool response не намекает что есть ещё

3. **Можно ли улучшить tool response?**
   ```json
   {
     "people": [...],
     "showing": 10,
     "total_accessible": 14,
     "total_matched": 64,  // ← Это бы помогло!
     "hint": "Call with limit=50 to get more"
   }
   ```

4. **Claude Code vs Agent: честное сравнение**
   - Дать обоим одинаковые constraints
   - Измерить quality of results, не quantity of calls

---

## Следующие шаги

### Немедленно
- [ ] SQL запрос: сколько людей с Google в person WHERE status='active'
- [ ] Проверить что возвращает company search без фильтрации
- [ ] Логировать каждый этап с counts

### Deep dive
- [ ] Понять где именно теряются данные
- [ ] Сравнить что видит агент vs что есть в БД
- [ ] Решить: улучшать tools или улучшать agent behavior

### Эксперимент
- [ ] Дать агенту hint в tool response
- [ ] Добавить в system prompt инструкцию итерировать
- [ ] Сравнить результаты

---

## Выводы (предварительные)

1. **Проблема не в agentic loop** — он работает
2. **Проблема в pipeline данных** — где-то теряется 80%
3. **Агент не может диагностировать** то, что не видит
4. **Claude Code имеет unfair advantage** — видит SQL, может исследовать

**Главный инсайт:** Чтобы агент был умным, ему нужны умные tools.
Tool который возвращает "10 из 14" без контекста — тупой tool.
