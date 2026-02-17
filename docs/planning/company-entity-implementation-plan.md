# Company Entity Implementation Plan

> Детальный план внедрения сущности "Company" в atlantisplus
> Создан: 2026-02-13

---

## Executive Summary

**Цель**: Выделить компании как отдельные сущности для:
- Кликабельной навигации к странице компании
- Поиска/фильтрации людей по компании
- Дедупликации названий компаний
- Обогащения данными о компаниях

**Решение**: Гибридный подход с отдельной таблицей `company` + `person_company` связи

---

## ⚠️ CRITICAL REVIEW (2026-02-13)

> Этот план прошёл критический анализ backend-architect агента.
> **Рекомендация: НЕ ДЕЛАТЬ в текущем виде. Использовать простые альтернативы.**

### Критические проблемы

| Проблема | Severity | Суть |
|----------|----------|------|
| **Dual source of truth** | 🔴 CRITICAL | assertion.works_at + person_company = два места для одной информации |
| **Prompt regression** | 🔴 CRITICAL | +20% к extraction prompt = риск ухудшения качества extraction людей |
| **Google vs Alphabet** | 🔴 CRITICAL | Fuzzy matching не решит проблему алиасов (Facebook/Meta, Тинькофф/T-Bank) |
| **Merge без unmerge** | 🟠 HIGH | Ошибочно объединили компании — механизма отката нет |
| **Миграция = мусор** | 🟠 HIGH | "ex-Google", "раньше в Яндексе" — автоматически не определить relationship_type |
| **~1000 LOC** | 🟠 HIGH | 3 таблицы, 5+ новых файлов — для 3 пользователей? |
| **CompanyPage over-engineering** | 🟡 MEDIUM | Нужна ли страница компании в MVP? |
| **Backward compatibility 2x** | 🟡 MEDIUM | Поддержка двух форматов = двойная нагрузка на разработку |

### Рекомендуемые альтернативы

**Альтернатива 1: `object_value_normalized` column** (5 минут работы)
```sql
ALTER TABLE assertion ADD COLUMN object_value_normalized TEXT;
-- "Google LLC" → "google"
```
Фильтр: `WHERE predicate='works_at' AND object_value_normalized = 'google'`

**Альтернатива 2: Virtual Company через GROUP BY** (0 изменений)
```sql
SELECT lower(trim(object_value)) as company, array_agg(person_id)
FROM assertion WHERE predicate='works_at' GROUP BY 1
```

**Альтернатива 3: JSONB в object_json** (уже есть в схеме)
```json
{"company_name": "Google", "normalized": "google", "domain": "google.com"}
```

### Когда вернуться к полному плану

- 100+ людей в базе
- Измеримая боль от дублей компаний
- Понятно какие фичи реально нужны (а не какие кажутся красивыми)

---

## 1. Анализ текущей архитектуры

### 1.1 Как компании хранятся сейчас

```
assertion (
    subject_person_id  → person.person_id
    predicate          = 'works_at'
    object_value       = 'Google LLC'  -- просто строка
    embedding          → vector(1536)
)
```

**Проблемы:**
- "Google", "Google LLC", "google.com" — разные строки
- Нет нормализации между источниками
- Нельзя найти "все из Google" одним запросом
- Нет страницы компании

### 1.2 Источники данных о компаниях

| Источник | Где берется | Формат |
|----------|-------------|--------|
| Voice/Text extraction | GPT-4o → `identifiers.company` | Свободный текст |
| LinkedIn import | CSV → `Company` column | Структурированный |
| Calendar import | Email → domain | `@google.com` |
| PDL enrichment | API → `job_company_name` | Нормализованный |

### 1.3 Текущие предикаты

```python
PREDICATES = [
    "works_at",        # ← компания здесь
    "role_is",
    "strong_at",
    "can_help_with",
    "worked_on",
    "background",
    "located_in",
    "speaks_language",
    "interested_in",
    "reputation_note",
    "contact_context",
    "relationship_depth",
    "recommend_for",
    "not_recommend_for"
]
```

---

## 2. Архитектурное решение

### 2.1 Почему отдельная таблица (а не soft entity)

| Критерий | Soft Entity (assertions) | Отдельная таблица ✓ |
|----------|--------------------------|---------------------|
| Дедупликация | Сложно | Легко — canonical record |
| UI навигация | Группировка на лету | FK → прямая навигация |
| Embedding | На каждый assertion | Один на компанию |
| Расширяемость | JSONB | Типизированные колонки |
| Performance | JOIN по тексту | JOIN по UUID |

### 2.2 Новая схема данных

```
┌─────────────────────────────────────────────────────────────┐
│  company                                                    │
├─────────────────────────────────────────────────────────────┤
│  company_id UUID PK                                         │
│  owner_id UUID FK → auth.users                              │
│  canonical_name TEXT (нормализованное: "google")            │
│  display_name TEXT (для UI: "Google LLC")                   │
│  summary TEXT (AI-generated)                                │
│  summary_embedding vector(1536)                             │
│  industry TEXT                                              │
│  size_bucket TEXT (1-10, 11-50, ...)                        │
│  location TEXT                                              │
│  linkedin_url TEXT                                          │
│  website TEXT                                               │
│  status TEXT (active, merged, deleted)                      │
│  merged_into_company_id UUID                                │
└─────────────────────────────────────────────────────────────┘
           │
           │ 1:N
           ▼
┌─────────────────────────────────────────────────────────────┐
│  company_identity (алиасы и идентификаторы)                 │
├─────────────────────────────────────────────────────────────┤
│  identity_id UUID PK                                        │
│  company_id UUID FK → company                               │
│  namespace TEXT (name_variation, email_domain, linkedin_url)│
│  value TEXT (google.com, Google Inc, linkedin.com/company/..)│
│  source TEXT (import_linkedin, extraction, enrichment)      │
│  UNIQUE(namespace, value) -- global dedup!                  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  person_company (связь человек-компания)                    │
├─────────────────────────────────────────────────────────────┤
│  id UUID PK                                                 │
│  person_id UUID FK → person                                 │
│  company_id UUID FK → company                               │
│  relationship_type TEXT (current_employee, former, founder) │
│  role_title TEXT                                            │
│  department TEXT                                            │
│  start_date DATE                                            │
│  end_date DATE (NULL = current)                             │
│  confidence FLOAT                                           │
│  evidence_id UUID FK → raw_evidence                         │
│  source TEXT                                                │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. NER и Extraction Strategy

### 3.1 Гибридный pipeline

```
INPUT SOURCES
    │
    ▼
┌──────────────────────────────────────────────┐
│  STAGE 1: FAST PASS (regex + rules)          │
│  • Email domains: @google.com → "Google"     │
│  • LinkedIn URLs: linkedin.com/company/...   │
│  • Известные паттерны: Inc, LLC, GmbH        │
└───────────────────┬──────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────┐
│  STAGE 2: GPT-4o EXTRACTION                  │
│  • Контекст: "он основал компанию XYZ"       │
│  • Связи: works_at → object_company_id       │
│  • Вариации: group "Google", "Google LLC"    │
└───────────────────┬──────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────┐
│  STAGE 3: DEDUPLICATION                      │
│  • Normalize: lowercase, remove suffixes     │
│  • Match: email_domain > linkedin > name     │
│  • Create or link to existing company        │
└───────────────────┬──────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────┐
│  STAGE 4: ENRICHMENT (optional)              │
│  • PDL / Hunter.io / Clearbit                │
│  • Industry, size, website                   │
└──────────────────────────────────────────────┘
```

### 3.2 Обновление промпта extraction

```python
# Добавить в EXTRACTION_SYSTEM_PROMPT:

"""
4. COMPANIES mentioned:
   - Extract company names as separate entities
   - For each company, capture:
     * name (as mentioned)
     * name_variations (Google, Google LLC, Google Inc → group them)
     * identifiers: email_domain, linkedin_url, website
     * industry (if mentioned)

   Map company references in assertions to company temp_ids.
   When person "works_at" a company, use company's temp_id, not raw string.
"""

# Новая структура output:
{
  "people": [...],
  "companies": [
    {
      "temp_id": "c1",
      "name": "Google",
      "name_variations": ["Google LLC", "Alphabet"],
      "identifiers": {
        "email_domain": "google.com",
        "linkedin_url": "linkedin.com/company/google"
      },
      "industry": "Technology"
    }
  ],
  "assertions": [
    {
      "subject": "p1",
      "predicate": "works_at",
      "value": "Google",
      "object_company_id": "c1",  // NEW: ссылка на компанию
      "confidence": 0.9
    }
  ]
}
```

### 3.3 Company Deduplication Service

```python
class CompanyDeduplicationService:
    """
    Приоритет matching:
    1. Exact email_domain match (google.com)
    2. Exact linkedin_url match
    3. High name similarity (pg_trgm > 0.8)
    4. Embedding similarity (> 0.9)
    5. Create new if no match
    """

    def normalize_company_name(self, name: str) -> str:
        """
        "Google Inc." → "google"
        "Apple, LLC" → "apple"
        """
        suffixes = ['inc', 'llc', 'ltd', 'gmbh', 'corp', 'company', 'co']
        name_lower = name.lower().strip()
        for suffix in suffixes:
            if name_lower.endswith(' ' + suffix):
                name_lower = name_lower[:-len(suffix)-1].strip()
        return name_lower

    def extract_email_domain(self, email: str) -> Optional[str]:
        """Skip generic domains (gmail, yahoo, etc.)"""
        ...

    async def find_or_create_company(
        self,
        owner_id: UUID,
        name: str,
        identifiers: dict,
        source: str
    ) -> UUID:
        """Find existing or create new company."""
        ...
```

---

## 4. UX Changes

### 4.1 Confidence Visualization

```
CONFIRMED (≥85%)     → Green border, ✓ icon
INFERRED (60-84%)    → Orange dashed border, ~ icon
UNCERTAIN (<60%)     → Gray dotted border, ? icon

PersonCard:
┌─────────────────────────────────────┐
│ John Smith                          │
│ 📍 San Francisco                    │
│ 🏢 Google [✓] ← GREEN, кликабельно │
│ Senior Engineer                     │
└─────────────────────────────────────┘
```

### 4.2 CompanyPage (новая страница)

```
/companies/:id

┌─────────────────────────────────────────────┐
│ 🏢 Google                                   │
│ Technology • 10,000+ employees • Mountain View │
├─────────────────────────────────────────────┤
│ People in your network (47)                 │
│ ┌─────────────────────────────────────────┐│
│ │ John Smith      • Senior Engineer   ✓  ││
│ │ Jane Doe        • Product Manager   ⚠️  ││
│ │ Mike Chen       • Designer          ✓  ││
│ └─────────────────────────────────────────┘│
│                                             │
│ [Filter by role ▼] [Sort by confidence ▼]  │
└─────────────────────────────────────────────┘
```

### 4.3 Hover Preview

```
Hover over company link:
┌──────────────────────────┐
│ 🏢 Google                │
│                          │
│ Technology               │
│ Mountain View, CA        │
│                          │
│ 47 people in network    │
│ • 12 engineers          │
│ • 5 PMs                 │
│ • 30 other              │
│                          │
│ [View Company →]        │
└──────────────────────────┘
```

### 4.4 Search Enhancement

```
Query: "кто работает в AI компаниях?"

Results include:
1. People with works_at assertions matching "AI"
2. People at companies with industry="AI/ML"
3. People at companies whose embeddings match query

Reasoning: "John works at OpenAI, which specializes in AI research."
```

---

## 5. Implementation Phases

### Phase 1: Улучшение extraction (1-2 дня)
**Без изменения схемы БД**

- [ ] Обновить EXTRACTION_SYSTEM_PROMPT для лучшего выделения компаний
- [ ] Добавить name_variations для компаний
- [ ] Улучшить нормализацию названий
- [ ] Добавить email domain extraction в calendar import
- [ ] Тестирование на реальных данных

**Файлы:**
- `/service/app/agents/prompts.py`
- `/service/app/api/import_calendar.py`

### Phase 2: Структурированное хранение (3-5 дней)
**Новые таблицы + базовый UI**

- [ ] Миграция: company, company_identity, person_company
- [ ] CompanyDeduplicationService
- [ ] Обновить process_pipeline
- [ ] Обновить LinkedIn/Calendar import
- [ ] Обновить PDL enrichment
- [ ] Миграция существующих works_at assertions
- [ ] API: GET /companies, GET /company/{id}
- [ ] CompanyPage.tsx
- [ ] Кликабельные ссылки в PeoplePage
- [ ] Фильтр по компании

**Файлы:**
- `/supabase/migrations/YYYYMMDD_company_tables.sql`
- `/service/app/services/company_dedup.py`
- `/service/app/api/company.py`
- `/frontend/src/pages/CompanyPage.tsx`

### Phase 3: Дедупликация + enrichment (3-5 дней)
**Умная дедупликация и обогащение**

- [ ] find_similar_companies RPC (pg_trgm + embedding)
- [ ] company_match_candidate автоматически
- [ ] UI для merge компаний
- [ ] Интеграция Clearbit
- [ ] Поиск по компаниям
- [ ] Company summary generation
- [ ] Company embedding

**Файлы:**
- `/supabase/migrations/YYYYMMDD_company_dedup_functions.sql`
- `/service/app/services/company_enrichment.py`
- `/frontend/src/pages/CompanyMergePage.tsx`

---

## 6. Migration Strategy

### 6.1 Миграция существующих данных

```sql
-- Извлечь уникальные компании из works_at assertions
SELECT DISTINCT
    lower(trim(object_value)) as canonical_name,
    object_value as display_name,
    COUNT(*) as people_count
FROM assertion
WHERE predicate = 'works_at'
  AND object_value IS NOT NULL
GROUP BY canonical_name, display_name
ORDER BY people_count DESC;

-- Создать company records
-- Создать person_company relationships
-- НЕ удалять works_at assertions (backward compatibility)
```

### 6.2 Backward Compatibility

1. **works_at assertions остаются** — для backward compatibility
2. **Параллельное хранение** — и assertion, и person_company
3. **Постепенный переход UI** — сначала оба источника
4. **API versioning** — v2 endpoints включают companies

### 6.3 Rollback Plan

1. Soft-delete company records (status = 'deleted')
2. UI fallback на works_at assertions
3. person_company можно удалить без потери данных

---

## 7. Enrichment APIs

### 7.1 Рекомендуемые API

| Use case | API | Tier |
|----------|-----|------|
| Email → Company | Hunter.io | Free (25/мес) |
| Company normalization | PDL | Pro ($100/мес) |
| Firmographics | Clearbit | Enterprise ($500+/мес) |
| Timeline enrichment | PDL | Pro |

### 7.2 Integration Flow

```
1. Extract raw company mention → name: "Google"
2. Hunter.io domain search: "google.com" → official_domain
3. PDL company search: query by name+domain → canonical ID
4. Store: (canonical_name, official_domain, pdl_id, logo_url)
5. Dedup: по pdl_id всегда merge
```

---

## 8. Risks & Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Дубликаты после миграции | High | Medium | Консервативный threshold (0.9), ручной review |
| Сложность extraction | Medium | High | Постепенное внедрение, A/B тест |
| Performance degradation | Low | High | Индексы, кэширование, мониторинг |
| UI complexity | Medium | Medium | Phased rollout, user feedback |

---

## 9. Success Metrics

1. **Дедупликация**: % уменьшения уникальных company names
2. **Покрытие**: % людей с привязкой к company
3. **UX**: клики на компании, использование фильтра
4. **Search**: релевантность результатов "кто из компании X"

---

## 10. Files to Modify

### Backend
- `/service/app/agents/prompts.py` — extraction prompt
- `/service/app/agents/schemas.py` — ExtractedCompany model
- `/service/app/api/process.py` — process_pipeline
- `/service/app/api/import_linkedin.py` — LinkedIn import
- `/service/app/api/import_calendar.py` — Calendar import
- `/service/app/services/enrichment.py` — PDL enrichment
- `/service/app/services/company_dedup.py` — NEW
- `/service/app/api/company.py` — NEW

### Frontend
- `/frontend/src/pages/CompanyPage.tsx` — NEW
- `/frontend/src/pages/PeoplePage.tsx` — clickable links
- `/frontend/src/components/CompanyChip.tsx` — NEW
- `/frontend/src/components/CompanyHoverCard.tsx` — NEW

### Database
- `/supabase/migrations/YYYYMMDD_company_tables.sql` — NEW
- `/supabase/migrations/YYYYMMDD_company_dedup_functions.sql` — NEW
- `/supabase/migrations/YYYYMMDD_migrate_works_at.sql` — NEW

---

## Appendix A: SQL Migration Template

```sql
-- 1. Create company table
CREATE TABLE IF NOT EXISTS company (
    company_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL REFERENCES auth.users(id),
    canonical_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    summary TEXT,
    summary_embedding vector(1536),
    industry TEXT,
    size_bucket TEXT CHECK (size_bucket IN ('1-10', '11-50', '51-200', '201-500', '501-1000', '1001-5000', '5000+')),
    location TEXT,
    linkedin_url TEXT,
    website TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'merged', 'deleted')),
    merged_into_company_id UUID REFERENCES company(company_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. Create company_identity table
CREATE TABLE IF NOT EXISTS company_identity (
    identity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES company(company_id) ON DELETE CASCADE,
    namespace TEXT NOT NULL,
    value TEXT NOT NULL,
    source TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(namespace, value)
);

-- 3. Create person_company table
CREATE TABLE IF NOT EXISTS person_company (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id UUID NOT NULL REFERENCES person(person_id) ON DELETE CASCADE,
    company_id UUID NOT NULL REFERENCES company(company_id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL CHECK (relationship_type IN (
        'current_employee', 'former_employee', 'founder',
        'investor', 'board_member', 'advisor', 'contractor'
    )),
    role_title TEXT,
    department TEXT,
    start_date DATE,
    end_date DATE,
    confidence FLOAT NOT NULL DEFAULT 0.5,
    evidence_id UUID REFERENCES raw_evidence(evidence_id),
    source TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(person_id, company_id, relationship_type, role_title)
);

-- 4. Indexes
CREATE INDEX idx_company_owner ON company(owner_id) WHERE status = 'active';
CREATE INDEX idx_company_canonical_name ON company(owner_id, canonical_name);
CREATE INDEX idx_company_name_trgm ON company USING gin (display_name gin_trgm_ops);
CREATE INDEX idx_company_identity_value ON company_identity(namespace, value);
CREATE INDEX idx_person_company_person ON person_company(person_id);
CREATE INDEX idx_person_company_company ON person_company(company_id);

-- 5. RLS
ALTER TABLE company ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users see own companies" ON company FOR ALL USING (owner_id = auth.uid());

ALTER TABLE company_identity ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users see company identities" ON company_identity FOR ALL USING (
    company_id IN (SELECT company_id FROM company WHERE owner_id = auth.uid())
);

ALTER TABLE person_company ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users see person_company" ON person_company FOR ALL USING (
    person_id IN (SELECT person_id FROM person WHERE owner_id = auth.uid())
);
```

---

## Appendix B: UX Research Sources

- Notion CRM — Two-way relations pattern
- Airtable — Linked record fields
- LinkedIn — Experience → Company navigation
- Affinity CRM — Inferred vs confirmed connections
- Neo4j Graph Visualization — Network display patterns
