# Atlantis Plus — MVP-0 Implementation Plan for Claude Code

> Этот файл — основной контекст для вайбкодинга первой версии продукта.
> Читай его ЦЕЛИКОМ перед началом любой работы.

---

## CRITICAL RULE: Interface Language

**ALL user-facing interfaces MUST be in English:**
- Telegram bot messages (commands, responses, errors)
- Mini App UI (buttons, labels, placeholders, navigation)
- API error messages shown to users
- Loading states, success/error notifications

**User content in database stays as-is:**
- Transcripts (Russian or any language)
- Person names, assertions, notes
- Evidence content

**Code/comments can be in English or Russian.**

---

## Что мы строим (одним абзацем)

**AI-first Personal Network Memory** — приватный агент, который помогает power-коннекторам помнить свой нетворк и находить нужных людей под конкретные задачи. Пользователь надиктовывает или пишет заметки о людях, которых знает. Агент извлекает структурированные данные (люди, связи, компетенции, контекст), сохраняет в граф, и потом отвечает на вопросы вроде «кто может помочь с выходом на фарм-компании в Сингапуре?» — с reasoning, а не просто списком.

**Первый пользователь**: основатель + 2-3 знакомых power-коннектора. Это не публичный продукт, а инструмент для dogfooding.

---

## Стек: Supabase Hybrid

| Компонент | Технология | Зачем |
|-----------|-----------|-------|
| Database | Supabase Postgres (с pgvector) | Managed, бесплатный tier, RLS, dashboard |
| Auth | Supabase Auth (custom Telegram provider) | Из коробки, JWT, RLS интеграция |
| File storage | Supabase Storage | Аудио файлы голосовых заметок |
| Realtime | Supabase Realtime | Подписка на статус обработки заметок |
| AI Service | Python (FastAPI), деплой на Railway | Whisper, GPT-4o extraction, reasoning |
| LLM | OpenAI API (GPT-4o + GPT-4o-mini) | Extraction, reasoning, embeddings |
| Speech-to-text | OpenAI Whisper API | Транскрипция голосовых |
| Embeddings | OpenAI text-embedding-3-small (1536d) | Semantic search по assertions |
| Frontend | Telegram Mini App (React + Vite) | Основной интерфейс |
| Frontend hosting | Cloudflare Pages / GitHub Pages | Бесплатная раздача статики |
| Bot | Telegram Bot (webhook → Python service) | Запуск Mini App + голосовые в чат |

### Почему гибрид

**Supabase закрывает** инфраструктуру: Postgres + pgvector, auth, storage, RLS, realtime, REST API, dashboard для данных. Всё это бесплатно на free tier для 3 пользователей.

**Python сервис закрывает** AI-логику: длинные цепочки (Whisper → extraction → embedding → multi-table insert), reasoning agent, entity resolution. Это слишком сложно и неудобно для edge functions / хранимок.

**Граница ответственности:**
- Supabase = хранение, auth, доставка файлов, простой CRUD (через PostgREST/SDK)
- Python = всё, что требует LLM вызовов или сложной бизнес-логики

---

## Архитектура

```
┌─────────────────────────────────────────────────────┐
│  TELEGRAM MINI APP (React + Vite, static hosting)   │
│  - голосовые заметки (запись + загрузка)             │
│  - текстовые заметки                                │
│  - умные запросы                                    │
│  - просмотр/редактирование людей                    │
│  - чат с агентом                                    │
└──────────┬────────────────────┬─────────────────────┘
           │                    │
           │ Supabase JS SDK    │ REST calls
           ▼                    ▼
┌──────────────────┐  ┌─────────────────────────────┐
│  SUPABASE        │  │  PYTHON AI SERVICE (Railway) │
│                  │  │                               │
│  • Postgres      │  │  • POST /process/voice        │
│    (+ pgvector)  │◄─┤  • POST /process/text         │
│  • Auth (JWT)    │  │  • POST /search               │
│  • Storage       │  │  • POST /chat                 │
│  • Realtime      │  │                               │
│  • RLS policies  │  │  Внутри:                      │
│                  │  │  • Whisper transcription       │
└──────────────────┘  │  • GPT-4o extraction          │
                      │  • GPT-4o reasoning           │
                      │  • Embedding generation        │
                      │  • Entity resolution           │
                      └───────────────────────────────┘
```

### Data flow: голосовая заметка

```
1. User записывает аудио в Mini App
2. Mini App → Supabase Storage (upload аудио)
3. Mini App → Python service: POST /process/voice {audio_url, user_id}
4. Python: скачивает аудио → Whisper API → транскрипт
5. Python: транскрипт → GPT-4o → extracted people/assertions/edges
6. Python: генерирует embeddings для assertions
7. Python: пишет всё в Supabase Postgres (через supabase-py или напрямую asyncpg)
8. Python: обновляет статус raw_evidence → processed=true
9. Mini App: подписан на Realtime → видит обновление → показывает результат
```

### Data flow: умный запрос

```
1. User вводит вопрос в Mini App
2. Mini App → Python service: POST /search {query, user_id}
3. Python: query → embedding → pgvector cosine similarity → candidate assertions
4. Python: собирает candidate people + их assertions + edges
5. Python: отправляет в GPT-4o для reasoning
6. Python: возвращает ranked results + reasoning
7. Mini App: отображает карточки с объяснениями
```

---

## Database Schema (SQL — применить через Supabase SQL Editor или миграции)

```sql
-- Extensions (включить через Supabase Dashboard → Database → Extensions)
-- uuid-ossp: обычно включен по умолчанию
-- vector: включить pgvector через dashboard

-- ============================================
-- CORE: Person (каноническая сущность человека)
-- ============================================
CREATE TABLE person (
    person_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL REFERENCES auth.users(id),
    display_name TEXT NOT NULL,
    summary TEXT,  -- AI-generated краткое описание
    summary_embedding vector(1536),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'merged', 'deleted')),
    merged_into_person_id UUID REFERENCES person(person_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_person_owner ON person(owner_id) WHERE status = 'active';

-- RLS: пользователь видит только своих людей
ALTER TABLE person ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users see own people" ON person
    FOR ALL USING (owner_id = auth.uid());

-- ============================================
-- IDENTITY: привязки к внешним платформам
-- ============================================
CREATE TABLE identity (
    identity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id UUID REFERENCES person(person_id) ON DELETE CASCADE,
    namespace TEXT NOT NULL,
    -- namespaces: telegram_user_id, telegram_username, email_hash,
    --             phone_hash, linkedin_url, freeform_name
    value TEXT NOT NULL,
    verified BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(namespace, value)
);

CREATE INDEX idx_identity_person ON identity(person_id);

ALTER TABLE identity ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users see identities of own people" ON identity
    FOR ALL USING (
        person_id IN (SELECT person_id FROM person WHERE owner_id = auth.uid())
    );

-- ============================================
-- RAW EVIDENCE: сырые данные (транскрипты, заметки)
-- ============================================
CREATE TABLE raw_evidence (
    evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL REFERENCES auth.users(id),
    source_type TEXT NOT NULL CHECK (source_type IN ('voice_note', 'text_note', 'chat_message', 'import')),
    content TEXT NOT NULL,
    audio_storage_path TEXT,  -- path в Supabase Storage
    metadata JSONB DEFAULT '{}',
    processed BOOLEAN NOT NULL DEFAULT false,
    processing_status TEXT DEFAULT 'pending' CHECK (processing_status IN ('pending', 'transcribing', 'extracting', 'done', 'error')),
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_evidence_owner ON raw_evidence(owner_id, created_at DESC);

ALTER TABLE raw_evidence ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users see own evidence" ON raw_evidence
    FOR ALL USING (owner_id = auth.uid());

-- Включить Realtime для отслеживания статуса обработки
ALTER PUBLICATION supabase_realtime ADD TABLE raw_evidence;

-- ============================================
-- ASSERTION: атомарные факты о людях
-- ============================================
CREATE TABLE assertion (
    assertion_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_person_id UUID NOT NULL REFERENCES person(person_id) ON DELETE CASCADE,
    predicate TEXT NOT NULL,
    -- predicates v0:
    --   can_help_with, works_at, role_is, strong_at, interested_in,
    --   trusted_by, knows, intro_path, located_in, worked_on,
    --   speaks_language, background, contact_context, reputation_note
    object_value TEXT,
    object_person_id UUID REFERENCES person(person_id),
    object_json JSONB,
    author_identity_id UUID REFERENCES identity(identity_id),
    evidence_id UUID REFERENCES raw_evidence(evidence_id),
    scope TEXT NOT NULL DEFAULT 'personal',
    confidence FLOAT NOT NULL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
    embedding vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_assertion_subject ON assertion(subject_person_id);
CREATE INDEX idx_assertion_predicate ON assertion(predicate, subject_person_id);
CREATE INDEX idx_assertion_object_person ON assertion(object_person_id) WHERE object_person_id IS NOT NULL;
-- Semantic search index (создать после накопления данных, ~1000+ rows)
-- CREATE INDEX idx_assertion_embedding ON assertion USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

ALTER TABLE assertion ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users see assertions of own people" ON assertion
    FOR ALL USING (
        subject_person_id IN (SELECT person_id FROM person WHERE owner_id = auth.uid())
    );

-- ============================================
-- EDGE: нормализованные связи для графового traversal
-- ============================================
CREATE TABLE edge (
    edge_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    src_person_id UUID NOT NULL REFERENCES person(person_id) ON DELETE CASCADE,
    dst_person_id UUID NOT NULL REFERENCES person(person_id) ON DELETE CASCADE,
    edge_type TEXT NOT NULL,
    -- edge types: knows, recommended, worked_with, in_same_group,
    --             introduced_by, collaborates_with
    scope TEXT NOT NULL DEFAULT 'personal',
    weight FLOAT NOT NULL DEFAULT 1.0,
    evidence_assertion_id UUID REFERENCES assertion(assertion_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (src_person_id != dst_person_id)
);

CREATE INDEX idx_edge_src ON edge(src_person_id, edge_type);
CREATE INDEX idx_edge_dst ON edge(dst_person_id, edge_type);

ALTER TABLE edge ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users see edges of own people" ON edge
    FOR ALL USING (
        src_person_id IN (SELECT person_id FROM person WHERE owner_id = auth.uid())
    );

-- ============================================
-- PERSON MATCH CANDIDATES (для дедупа)
-- ============================================
CREATE TABLE person_match_candidate (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    a_person_id UUID NOT NULL REFERENCES person(person_id),
    b_person_id UUID NOT NULL REFERENCES person(person_id),
    score FLOAT NOT NULL,
    reasons JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'merged', 'rejected')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================
-- SEMANTIC SEARCH FUNCTION (pgvector)
-- ============================================
CREATE OR REPLACE FUNCTION match_assertions(
    query_embedding vector(1536),
    match_threshold float,
    match_count int,
    p_owner_id uuid
)
RETURNS TABLE (
    assertion_id uuid,
    subject_person_id uuid,
    predicate text,
    object_value text,
    confidence float,
    similarity float
)
LANGUAGE sql STABLE
AS $$
    SELECT
        a.assertion_id,
        a.subject_person_id,
        a.predicate,
        a.object_value,
        a.confidence,
        1 - (a.embedding <=> query_embedding) as similarity
    FROM assertion a
    JOIN person p ON a.subject_person_id = p.person_id
    WHERE p.owner_id = p_owner_id
      AND p.status = 'active'
      AND a.embedding IS NOT NULL
      AND 1 - (a.embedding <=> query_embedding) > match_threshold
    ORDER BY a.embedding <=> query_embedding
    LIMIT match_count;
$$;
```

---

## Структура проекта

```
atlantis/
├── CLAUDE.md                      # ← этот файл
├── atlantis_plus_first_product_brief_v_0.md  # продуктовый бриф
│
├── service/                       # Python AI Service
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                # FastAPI app
│   │   ├── config.py              # Settings from env
│   │   ├── supabase_client.py     # Supabase Python client init
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py            # POST /auth/telegram
│   │   │   ├── process.py         # POST /process/voice, /process/text
│   │   │   ├── search.py          # POST /search
│   │   │   └── chat.py            # POST /chat
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── transcription.py   # Whisper API
│   │   │   ├── extraction.py      # GPT-4o extraction pipeline
│   │   │   ├── embedding.py       # Embedding generation
│   │   │   ├── reasoning.py       # Search reasoning agent
│   │   │   └── dedup.py           # Entity resolution
│   │   ├── agents/                # LLM prompts
│   │   │   ├── __init__.py
│   │   │   ├── prompts.py         # All prompts in one place
│   │   │   └── schemas.py         # Pydantic models for LLM outputs
│   │   └── middleware/
│   │       └── auth.py            # Validate Supabase JWT
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/                      # Telegram Mini App
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── lib/
│   │   │   ├── supabase.ts        # Supabase JS client
│   │   │   ├── api.ts             # Calls to Python service
│   │   │   └── telegram.ts        # Telegram Web App SDK helpers
│   │   ├── hooks/
│   │   │   ├── useAuth.ts         # Telegram → Supabase auth
│   │   │   ├── usePeople.ts       # Supabase realtime + queries
│   │   │   └── useRecorder.ts     # Audio recording
│   │   ├── pages/
│   │   │   ├── HomePage.tsx        # Dashboard / quick actions
│   │   │   ├── NotesPage.tsx       # Ввод заметок (голос + текст)
│   │   │   ├── SearchPage.tsx      # Умные запросы
│   │   │   ├── PeoplePage.tsx      # Список людей
│   │   │   ├── PersonPage.tsx      # Детали человека
│   │   │   └── ChatPage.tsx        # Диалог с агентом
│   │   └── components/
│   │       ├── VoiceRecorder.tsx
│   │       ├── PersonCard.tsx
│   │       ├── SearchResult.tsx
│   │       └── AssertionBadge.tsx
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── index.html
│
└── supabase/                      # Supabase config
    └── migrations/
        └── 001_initial_schema.sql  # Схема выше
```

---

## Порядок реализации (спринты)

### Sprint 0: Фундамент (день 1)
**Цель**: Supabase проект создан, схема применена, Python сервис отвечает на healthcheck, Mini App открывается.

**Supabase:**
- [ ] Создать проект на supabase.com
- [ ] Включить extensions: pgvector
- [ ] Применить SQL-схему (через SQL Editor в dashboard)
- [ ] Создать Storage bucket `voice-notes` (private)

**Python service:**
- [ ] Инициализация: `requirements.txt` с fastapi, uvicorn, supabase, openai, python-multipart
- [ ] `main.py` с healthcheck endpoint
- [ ] `config.py` читает env vars
- [ ] `supabase_client.py` — инициализация supabase-py с service_role key
- [ ] `middleware/auth.py` — валидация Supabase JWT из Authorization header
- [ ] Dockerfile + deploy на Railway

**Frontend:**
- [ ] `npm create vite@latest frontend -- --template react-ts`
- [ ] Установить `@supabase/supabase-js`, `@twa-dev/sdk`
- [ ] Базовый App.tsx с Telegram Web App init
- [ ] `lib/supabase.ts` — клиент с anon key
- [ ] Deploy на Cloudflare Pages
- [ ] Создать Telegram бота, настроить Menu Button → Mini App URL

**Telegram Auth flow:**
```
1. User открывает Mini App через Telegram
2. Mini App получает initData от Telegram
3. Mini App → Python service: POST /auth/telegram {init_data}
4. Python: валидирует HMAC → создаёт/находит user в Supabase Auth
5. Python: возвращает Supabase session (access_token + refresh_token)
6. Mini App: использует токен для Supabase JS SDK и Python API calls
```

### Sprint 1: Input Pipeline (дни 2-3)
**Цель**: надиктовал голосовую → транскрипция → извлечение людей и фактов.

- [ ] **VoiceRecorder component**: MediaRecorder API → blob → Supabase Storage upload
- [ ] `POST /process/voice`:
  - Принимает `{storage_path, user_id}`
  - Скачивает аудио из Supabase Storage
  - Создаёт `raw_evidence` со статусом `transcribing`
  - Whisper API → транскрипт
  - Статус → `extracting`
  - GPT-4o extraction → people + assertions + edges
  - Embeddings для каждого assertion
  - Пишет всё в БД
  - Статус → `done`
- [ ] `POST /process/text` — то же без Whisper
- [ ] NotesPage с переключением голос/текст
- [ ] Realtime подписка на `raw_evidence` → статус обработки
- [ ] Background processing: `asyncio.create_task`, сразу 202

**Extraction — ключевой промпт:**
```python
EXTRACTION_SYSTEM_PROMPT = """You are an AI that extracts structured information about people from personal notes.
The notes are written by a power-connector who knows many people professionally.

Given a text (transcript of voice note or written note), extract:

1. PEOPLE mentioned:
   - name (as mentioned, preserve original language)
   - identifying details (company, role, city, etc.)

2. FACTS (assertions) about each person:
   - what they do / work at / their role
   - what they're good at / can help with
   - where they're located
   - how the author knows them
   - any context about trust, reputation, relationship quality
   - notable projects or achievements

3. CONNECTIONS between people:
   - who knows whom
   - who worked with whom
   - who recommended whom
   - who is in the same company/group

Be thorough but don't hallucinate. If something is uncertain, set lower confidence.
Preserve the original language of names and descriptions.
One person may be mentioned multiple times with different name variations — group them."""

EXTRACTION_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "people": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "temp_id": {"type": "string"},
                    "name": {"type": "string"},
                    "name_variations": {"type": "array", "items": {"type": "string"}},
                    "identifiers": {
                        "type": "object",
                        "properties": {
                            "company": {"type": "string"},
                            "role": {"type": "string"},
                            "city": {"type": "string"},
                            "linkedin": {"type": "string"},
                            "telegram": {"type": "string"},
                            "email": {"type": "string"}
                        }
                    }
                },
                "required": ["temp_id", "name"]
            }
        },
        "assertions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "temp_id of person"},
                    "predicate": {
                        "type": "string",
                        "enum": ["can_help_with", "works_at", "role_is", "strong_at",
                                 "interested_in", "trusted_by", "knows", "intro_path",
                                 "located_in", "worked_on", "speaks_language",
                                 "background", "contact_context", "reputation_note"]
                    },
                    "value": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1}
                },
                "required": ["subject", "predicate", "value"]
            }
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": ["knows", "recommended", "worked_with",
                                 "in_same_group", "introduced_by", "collaborates_with"]
                    },
                    "context": {"type": "string"}
                },
                "required": ["source", "target", "type"]
            }
        }
    },
    "required": ["people", "assertions", "edges"]
}
```

### Sprint 2: Browse & Edit (дни 4-5)
**Цель**: посмотреть извлечённых людей, поправить ошибки.

- [ ] PeoplePage: список карточек (Supabase JS SDK напрямую, RLS фильтрует)
- [ ] PersonPage: все assertions, связи, evidence
- [ ] Inline edit: имя, удаление assertion, добавление заметки
- [ ] CRUD через Supabase JS SDK — Python service не нужен
- [ ] Поиск по имени (ilike), сортировка

### Sprint 3: Smart Search (дни 6-8)
**Цель**: North Star — вопрос → люди с reasoning.

- [ ] SearchPage: текстовый ввод + голосовой через Web Speech API
- [ ] `POST /search` в Python:
  1. Query → embedding
  2. pgvector search через `match_assertions` RPC
  3. Group by person, fetch full profiles
  4. GPT-4o reasoning → ranked results
- [ ] Отображение: карточки с reasoning text

**Reasoning промпт:**
```python
REASONING_SYSTEM_PROMPT = """You are a personal network advisor. You help people find the right
connections in their professional network.

The user is a power-connector looking for people who can help with a specific need.
You receive candidate people with their known facts (assertions) and connections (edges).

For each relevant person, provide:
1. WHY they are relevant (be specific, reference facts)
2. CONNECTION PATH — how the user knows them or could reach them
3. CONFIDENCE — how certain you are, and any caveats
4. SUGGESTED ACTION — what to do next (intro message, question to ask, etc.)

Think step by step. Consider NON-OBVIOUS connections — this is your main value.
A person might be relevant not because of their direct expertise,
but because of who they know, where they work, or what they've done before.

The user should feel: "I wouldn't have thought of this person myself."

Skip clearly irrelevant people. 3 great suggestions > 10 mediocre ones.
Preserve the original language of names and descriptions from assertions."""
```

### Sprint 4: Chat Agent (дни 9-10)
**Цель**: диалоговый режим — уточнения, disambiguation.

- [ ] `POST /chat` — stateful (history в Supabase table)
- [ ] Agent: disambiguation, enrichment, merge suggestions, follow-up search
- [ ] ChatPage в Mini App
- [ ] Tool use: agent может вызывать search и CRUD

### Sprint 5: Polish & Dogfood (дни 11-14)
**Цель**: работает для ежедневного использования.

- [ ] Загрузка реальных данных (2+ часов голосовых)
- [ ] Итерация промптов по реальным результатам
- [ ] Onboarding flow
- [ ] Error handling, loading states, retry
- [ ] Приглашение 2-3 тестеров

---

## Ключевые технические решения

### Supabase Auth + Telegram

```python
# Python service: POST /auth/telegram
from supabase import create_client

supabase = create_client(url, service_role_key)

async def auth_telegram(init_data: str):
    # 1. Validate Telegram initData (HMAC-SHA-256 with bot token)
    telegram_user = validate_init_data(init_data, bot_token)

    # 2. Find or create user in Supabase Auth
    fake_email = f"tg_{telegram_user.id}@atlantis.local"

    try:
        user = supabase.auth.admin.create_user({
            "email": fake_email,
            "email_confirm": True,
            "user_metadata": {
                "telegram_id": telegram_user.id,
                "telegram_username": telegram_user.username,
                "display_name": telegram_user.first_name
            }
        })
    except:  # user exists
        pass

    # 3. Generate session
    session = supabase.auth.admin.generate_link({
        "type": "magiclink",
        "email": fake_email
    })

    return session
```

### Supabase Python Client

```python
# service/app/supabase_client.py
from supabase import create_client, Client

def get_supabase_admin() -> Client:
    """Service role client — bypasses RLS, for server-side operations"""
    return create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_ROLE_KEY
    )
```

Python service всегда использует `service_role_key` (обходит RLS), но фильтрует по `owner_id`.
Frontend использует `anon_key` + JWT — RLS изолирует данные.

### Audio Recording

```typescript
// hooks/useRecorder.ts
const useRecorder = () => {
    const [recording, setRecording] = useState(false);
    const mediaRecorder = useRef<MediaRecorder | null>(null);

    const start = async () => {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder.current = new MediaRecorder(stream, { mimeType: 'audio/webm' });
        const chunks: Blob[] = [];
        mediaRecorder.current.ondataavailable = (e) => chunks.push(e.data);
        mediaRecorder.current.onstop = async () => {
            const blob = new Blob(chunks, { type: 'audio/webm' });
            await uploadAndProcess(blob);
        };
        mediaRecorder.current.start();
        setRecording(true);
    };

    const stop = () => {
        mediaRecorder.current?.stop();
        setRecording(false);
    };

    return { recording, start, stop };
};
```

### Embeddings Strategy

- Каждый assertion → embedding при создании
- person.summary_embedding = embedding от AI-generated summary всех assertions
- Summary пересчитывается при новых assertions (debounced)
- `text-embedding-3-small` (дёшево, 1536d, достаточно для MVP)

---

## Env Variables

### Python Service (.env)
```env
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...
OPENAI_API_KEY=sk-...
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
ENVIRONMENT=development
```

### Frontend (.env)
```env
VITE_SUPABASE_URL=https://xxx.supabase.co
VITE_SUPABASE_ANON_KEY=eyJ...
VITE_API_URL=https://your-service.railway.app
```

---

## Критические принципы (не нарушай)

1. **Person ≠ Identity ≠ Assertion** — всегда отдельные записи
2. **Всё из assertion** — каждый факт = отдельная запись с evidence и confidence
3. **Scope обязателен** — пока всё `personal`, но поле заполнено
4. **Raw evidence сохраняется** — никогда не теряй исходный транскрипт
5. **Никаких численных скоров пользователю** — confidence внутренний
6. **Дедуп осторожно** — лучше дубль, чем неправильный merge
7. **Reasoning > Lists** — в поиске всегда объясняй ПОЧЕМУ
8. **RLS на всех таблицах** — данные изолированы по owner_id
9. **Frontend → Supabase напрямую для CRUD** — Python только для AI
10. **Service role key только на сервере** — никогда в frontend

---

## Чего НЕ делать в MVP-0

- ❌ Социальные профили, публичные страницы
- ❌ Подтверждения от третьих лиц
- ❌ Community/group фичи
- ❌ Скрейпинг
- ❌ Монетизация
- ❌ Красивый дизайн (функциональность > визуал)
- ❌ Оптимизация перформанса
- ❌ Edge functions / хранимки для бизнес-логики (только match_assertions RPC)
- ❌ Сложные миграции (SQL руками пока)

---

## Success Criteria

1. Надиктовать 30-минутный поток → система извлекает людей с >70% accuracy
2. Спросить «кто может помочь с X?» → неочевидный полезный ответ
3. Основатель пользуется хотя бы раз в неделю

---

## Supabase CLI — Правила работы

**Project Reference**: `mhdpokigbprnnwmsgzuy`

### Миграции
```bash
# Создать новую миграцию
supabase migration new migration_name

# Применить миграции к remote
supabase db push

# Откатить статус миграции (если файл удалён)
supabase migration repair --status reverted TIMESTAMP

# Показать список миграций
supabase migration list
```

### Формат файлов миграций
- Имя: `YYYYMMDDHHMMSS_description.sql`
- Папка: `supabase/migrations/`
- Для pgvector: добавить `SET search_path TO public, extensions;` в начало

### Storage buckets
- Создавать через SQL миграции (CLI не поддерживает create bucket)
- RLS политики: `storage.foldername(name))[1]` для user-scoped доступа

---

## Deployment Commands

### Python Service (Railway)
```bash
# Railway Project: heartfelt-flexibility
# Service: atlantisplus
# URL: https://atlantisplus-production.up.railway.app

# Деплой на Railway (из папки service/)
cd /Users/evgenyq/Projects/atlantisplus/service
railway up

# Посмотреть логи
railway logs

# Посмотреть статус
railway status

# Открыть dashboard
railway open

# Переменные окружения (установлены в Railway Dashboard):
# - SUPABASE_URL=https://mhdpokigbprnnwmsgzuy.supabase.co
# - SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY, SUPABASE_JWT_SECRET
# - OPENAI_API_KEY
# - TELEGRAM_BOT_TOKEN
# - PDL_API_KEY (опционально, для People Data Labs enrichment)
```

### Frontend (GitHub Pages)
```bash
# GitHub repo: evgenyq/atlantisplus
# URL: https://evgenyq.github.io/atlantisplus/

# Из папки frontend/
cd /Users/evgenyq/Projects/atlantisplus/frontend
npm run build
npm run deploy  # или gh-pages -d dist

# VITE_API_URL должен указывать на Railway:
# Production: https://atlantisplus-production.up.railway.app
# Local dev: http://localhost:8000
```

### Supabase
```bash
# Project Reference: mhdpokigbprnnwmsgzuy
# URL: https://mhdpokigbprnnwmsgzuy.supabase.co
# Dashboard: https://supabase.com/dashboard/project/mhdpokigbprnnwmsgzuy

# Применить миграции
supabase db push

# Список миграций
supabase migration list
```

### Telegram Bot
```
Bot: @atlantisplus_bot
Mini App URL: https://evgenyq.github.io/atlantisplus/

Настройка в BotFather:
1. /mybots → @atlantisplus_bot
2. Bot Settings → Menu Button → Configure
3. URL: https://evgenyq.github.io/atlantisplus/
```

---

## Как начать в Claude Code

```
Прочитай CLAUDE.md и начни Sprint 0.
Сначала создай структуру проекта, потом Python service, потом frontend.
```
