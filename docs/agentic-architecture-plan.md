# Agentic Architecture Plan for Atlantis Plus

> Документ создан: 2026-02-14
> Статус: Planning / Research

---

## Мотивация: Почему агентская архитектура

### Проблема: Complexity Explosion

Текущий подход — писать бизнес-логику под каждый edge case:

```
Проблема: ByteDance в met_on, а не works_at
  → Решение: Multi-predicate search

Проблема: Yandex vs Яндекс
  → Решение: Normalization table + trigger

Проблема: Tinkoff → T-Bank rebrand
  → Решение: Company aliases table

Проблема: Serge Faguet vs Serge F vs s.fage@gmail.com
  → Решение: ???
```

**Каждое решение:**
1. Дорого в разработке (часы-дни)
2. Требует maintenance
3. Не масштабируется на новые edge cases
4. Завтра появится новый кейс (intro paths, dedup, enrichment...)

### Решение: Agent с reasoning

Агент с доступом к базе, коду и интернету может:
- Попробовать несколько стратегий поиска
- Понять что "Serge F" и "s.fage@gmail.com" — один человек
- Найти компанию через домен email
- Построить intro path через 2-3 степени
- Self-correct если первый подход не сработал

**Claude Code (я) уже демонстрирует это:**
- Ищу в базе разными способами
- Пишу и запускаю тесты
- Нахожу неочевидные решения

Вопрос: зачем хардкодить approximations, если можно дать agent те же capabilities?

---

## Архитектура: "Release the Kraken"

### Два Tier'а

```
┌────────────────────────────────────────────────────────────────┐
│                    USER QUERY                                   │
│    "кто может инвестировать в роботикс на ранней стадии"       │
└────────────────────────┬───────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│              TIER 1: Fast Heuristics (~2 sec)                   │
│                                                                 │
│  GPT-4o-mini: Query classification                             │
│                                                                 │
│  Simple (80%):                Complex (20%):                    │
│  - Direct name lookup         - Multi-hop reasoning             │
│  - Single predicate search    - Disambiguation needed           │
│  - High confidence match      - No direct matches               │
│           │                              │                      │
│           ▼                              ▼                      │
│    Return fast result          RELEASE THE KRAKEN              │
└────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
┌────────────────────────────────────────────────────────────────┐
│              TIER 2: Claude Agent (30-60 sec)                   │
│                                                                 │
│  Claude Sonnet 4.5 + Agent SDK + MCP Tools                     │
│                                                                 │
│  Tools available:                                               │
│  - query_database(sql) — Supabase MCP                          │
│  - search_web(query) — Firecrawl/Brave MCP                     │
│  - enrich_person(name) — Apollo MCP                            │
│  - generate_embedding(text) — OpenAI                           │
│                                                                 │
│  Agent reasoning example:                                       │
│  1. "роботикс → robotics, robots, automation"                  │
│  2. Parallel: DB search + Web search for recent deals          │
│  3. "Found 3 robotics founders → who invested in them?"        │
│  4. Graph traversal: knows → knows → investor                  │
│  5. Geo filter: Russian-speaking VCs                           │
│  6. Confidence ranking + reasoning explanation                 │
└────────────────────────────────────────────────────────────────┘
```

### Wow Experience

При запросе "кто может помочь с инвестицией в роботикс":

1. **Прямой поиск:** robotics, роботы, автоматизация в нетворке
2. **Инвесторы:** поиск людей с role = investor + robotics context
3. **Reverse engineering:** топ robotics компании → кто в них инвестировал → есть ли в базе
4. **Web search:** последние сделки в robotics → match против нашей базы
5. **Inference:** кто МОЖЕТ захотеть инвестировать (adjacent industries)
6. **Geo/Language:** Russian-speaking VCs для русскоязычного пользователя

---

## Стек и Cost Model

### Модели

| Задача | Модель | Цена (per 1M tokens) |
|--------|--------|----------------------|
| Query classification | GPT-4o-mini | $0.15 / $0.60 |
| Fast search | GPT-4o-mini | $0.15 / $0.60 |
| Agent reasoning | Claude Sonnet 4.5 | $3 / $15 |
| Complex queries | Claude Opus 4.5 | $15 / $75 |
| Embeddings | text-embedding-3-small | $0.02 / - |

### Monthly Cost Estimate

| Tier | % Queries | Cost/Query | Monthly (3 users, 30/day) |
|------|-----------|------------|---------------------------|
| Tier 1 | 80% | $0.01 | $22 |
| Tier 2 | 20% | $0.30 | $162 |
| **Total** | | | **~$185/month** |

Для premium tier ($1000+/month клиенты): agent на каждый запрос = $500-900/month — 50%+ margin.

### MCP Servers

**Must have:**
- Supabase MCP — database access (read-only)
- Custom `atlantis-network` MCP — наши tools

**Should have:**
- Firecrawl MCP — web scraping
- Brave Search MCP — web search

**Nice to have:**
- LinkedIn MCP — profile enrichment
- Apollo MCP — B2B data
- Gmail/Calendar MCP — communication tracking

---

## Claude Agent SDK vs OpenAI

| Аспект | Claude | OpenAI |
|--------|--------|--------|
| Reasoning (SWE-bench) | **80.9%** | 80.0% |
| Context window | **1M tokens** | 400K tokens |
| Цена (balanced) | Sonnet: $3/$15 | GPT-4o: $5/$15 |
| MCP support | Native (creator) | Adopted |
| Code execution | Bash native | Sandbox |

**Вывод:** Для "найди неочевидную связь" Claude выигрывает.

---

## Implementation Phases

### Phase 1: Proof of Wow (1-2 дня)
**Цель:** Демо multi-step search, показать максимум возможностей.

```
service/
└── claude_agent/
    ├── agent.py          # Claude Agent SDK wrapper
    ├── tools/
    │   ├── database.py   # Supabase queries (SELECT only)
    │   ├── search.py     # Web search via Firecrawl
    │   └── reasoning.py  # Graph traversal logic
    └── sandbox.py        # Permission + cost limits
```

### Phase 2: Router Integration (1 день)
**Цель:** Tier 1 → Tier 2 routing в production.

```python
async def handle_query(query: str, user_id: str):
    complexity = await classify_query(query)  # GPT-4o-mini

    if complexity.score < 0.5 and complexity.confidence > 0.8:
        return await fast_search(query, user_id)
    else:
        return await agent_search(query, user_id)  # Kraken
```

### Phase 3: MCP Integration (2-3 дня)
**Цель:** Ready-made MCP servers.

### Phase 4: Extraction Agent (optional)
**Цель:** Self-correcting extraction с disambiguation.

---

## Sandboxing Requirements

### Permission Model

```python
ClaudeAgentOptions(
    permissionMode="default",  # Explicit approval
    maxTurns=50,               # Prevent infinite loops
    allowed_tools=["query_database", "search_web", "think"],
    canUseTool=approval_callback,  # Runtime decisions
)
```

### Security Layers

1. **Database:** Read-only credentials, table whitelist
2. **Tools:** Declarative deny/allow/ask rules
3. **Cost:** Budget per request, monthly caps
4. **Timeout:** 60 sec hard limit
5. **Audit:** Log all tool invocations

### Infrastructure

- Container isolation (Docker/Firecracker)
- Credential proxy (agent never sees API keys)
- Rate limiting at gateway level

---

## Open Questions

1. **Deployment:** Separate service vs integrated in current FastAPI?
2. **State:** Session persistence между agent calls?
3. **Streaming:** Real-time updates во время agent thinking?
4. **Fallback:** Что делать если agent fails/timeouts?

---

---

## Infrastructure Analysis

### ⚠️ Важное уточнение: Claude Agent SDK vs Anthropic Python SDK

**Claude Agent SDK** (он же `claude-agent-sdk`, Claude Code SDK) — это CLI tool для локальной разработки с Claude. Он **НЕ предназначен** для интеграции в FastAPI backend.

**Что нужно для atlantisplus**: `anthropic` Python SDK для вызова Claude API с tools.

```python
# Правильный подход
import anthropic

client = anthropic.Anthropic()
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=4096,
    tools=TOOLS,
    messages=[...]
)
```

### Текущая инфраструктура (готова)

| Компонент | Статус | Комментарий |
|-----------|--------|-------------|
| FastAPI async | ✅ | Полностью совместимо |
| BackgroundTasks | ✅ | Можно queue agent runs |
| Pydantic Settings | ✅ | Добавить ANTHROPIC_API_KEY |
| Railway Docker | ✅ | Без изменений |
| Node.js | ❌ Не нужен | Только для CLI, не для SDK |

### Что нужно изменить

**Минимальные изменения:**
```diff
# requirements.txt
+ anthropic>=0.39.0

# config.py
+ anthropic_api_key: str

# .env
+ ANTHROPIC_API_KEY=sk-ant-...
```

### Supabase Sync SDK — Tech Debt

Текущий код использует синхронный Supabase client:
```python
supabase.table('person').select(...).execute()  # Blocking I/O
```

**Для MVP это OK** — 3 пользователя, agent делает 5-10 tool calls.

**Для scale**: обернуть в `asyncio.to_thread` или мигрировать на async client.

### Security: Credential Proxy — НЕ НУЖЕН

Текущая архитектура:
```
Mini App → FastAPI → Supabase
                  ↘ OpenAI/Anthropic API
```

Agent (LLM) не видит credentials — получает только tool results. Proxy избыточен для MVP.

### Потенциальные проблемы

| Риск | Severity | Mitigation |
|------|----------|------------|
| Anthropic rate limits | LOW | Tier 1 достаточно для 3 users |
| Tool format differences | LOW | ~20 строк conversion |
| Response format differences | LOW | ~50 строк в chat.py |

---

## Revised Implementation Plan

### Phase 1: Parallel Testing (4-6 часов)

1. `pip install anthropic`
2. Создать `app/services/claude_client.py`
3. Создать `/chat/claude` endpoint (параллельно с OpenAI)
4. Сравнить качество reasoning

### Phase 2: Tool Migration (2-4 часа)

1. Конвертировать TOOLS в Anthropic format
2. Обработать response differences
3. Протестировать все tools

### Phase 3: Cutover (когда Claude лучше)

1. Переключить `/chat` на Claude
2. Оставить OpenAI для extraction/embeddings (дешевле)

---

## References

- [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python)
- [Claude Tool Use](https://docs.anthropic.com/claude/docs/tool-use)
- [MCP Specification](https://modelcontextprotocol.io/)
- [Anthropic: Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)
- [Supabase MCP Server](https://supabase.com/docs/guides/getting-started/mcp)
