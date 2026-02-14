# TODO: Deep Dive — Почему агент теряет данные

> Приоритет: HIGH
> Создано: 2026-02-14
> См. также: postmortem-agentic-search-2026-02-14.md

## Проблема в одном предложении

**В базе 64 человека из Google, find_people tool возвращает 10.**

## Быстрая диагностика

Запустить эти запросы для понимания:

```bash
# 1. Сколько людей с Google в базе?
# Supabase SQL Editor:
SELECT COUNT(*) FROM person p
JOIN assertion a ON p.person_id = a.subject_person_id
WHERE a.object_value ILIKE '%Google%'
AND p.status = 'active';

# 2. Сколько с разными статусами?
SELECT p.status, COUNT(DISTINCT p.person_id)
FROM person p
JOIN assertion a ON p.person_id = a.subject_person_id
WHERE a.object_value ILIKE '%Google%'
GROUP BY p.status;

# 3. Assertions без person?
SELECT COUNT(*) FROM assertion a
LEFT JOIN person p ON a.subject_person_id = p.person_id
WHERE a.object_value ILIKE '%Google%'
AND p.person_id IS NULL;
```

## Где смотреть в коде

```
service/app/api/chat.py:

Строка 681-720:  find_people начало, person_scores accumulation
Строка 755-770:  people_query — ЗДЕСЬ может быть потеря
Строка 795-808:  filter_and_motivate_results — ещё одна потеря
```

## Что изменить для диагностики

```python
# В find_people, после строки ~755:
print(f"[DEBUG] person_scores keys: {len(person_scores)}")
print(f"[DEBUG] top_person_ids: {len(top_person_ids)}")
print(f"[DEBUG] people_result.data: {len(people_result.data or [])}")
# Это покажет где именно теряются данные
```

## ✅ ПРИЧИНА НАЙДЕНА (2026-02-14)

```sql
SELECT status, COUNT(DISTINCT person_id) FROM person p
JOIN assertion a ON p.person_id = a.subject_person_id
WHERE a.object_value ILIKE '%Google%'
GROUP BY status;

-- Результат:
-- deleted: 47
-- active:  16
```

**75% людей с "Google" имеют status='deleted'!**

Pipeline:
1. Company search находит 63 person_ids из assertions
2. Fetch people с `eq('status', 'active')` → только 16
3. После мотиваций → 10

**Вопрос:** Почему так много deleted? Это rollback импорта? Или cleanup?

## Старая гипотеза (подтверждена частично)

**Скорее всего:** `people_result` query не находит person_id потому что:
- ~~Они принадлежат другому owner (RLS)~~
- ✅ **status != 'active'** — ЭТО ПРИЧИНА
- ~~Или person_id из assertion не существует в person table~~

## Ожидаемый результат

После deep dive должны понять:
1. Точное место потери данных
2. Причину (RLS, status, orphaned assertions)
3. Fix или workaround
