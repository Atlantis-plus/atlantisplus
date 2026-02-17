# Agentic Architecture Research Notes

> Заметки из исследования Claude Agent SDK vs Anthropic Python SDK
> Дата: 2026-02-14

---

## Ключевой вывод

**Оба SDK**: Claude решает какие tools вызывать и в каком порядке.
**Разница**: Кто управляет loop'ом.

| Аспект | Anthropic Python SDK | Claude Agent SDK |
|--------|---------------------|------------------|
| Loop | Ты пишешь (~50 строк) | Автоматический |
| Tools | JSON schema | @tool decorator + MCP |
| Infrastructure | Direct API | MCP server runtime |
| Setup | Минимальная | Сложнее |

---

## Compaction / Context Management

**В Anthropic SDK нет автоматического compaction.** Ты сам управляешь:

```python
messages = []

while True:
    response = client.messages.create(messages=messages)

    # Твоя ответственность:
    if count_tokens(messages) > 150_000:
        messages = summarize_and_truncate(messages)
```

**Что нужно реализовать:**
- Token counting (tiktoken или anthropic's counter)
- Summarization strategy
- History management (sliding window)

**Для atlantisplus MVP:** При 3 пользователях и коротких сессиях (5-10 tool calls) compaction не нужен. Sonnet: 200K context.

---

## MCP + Anthropic SDK

MCP — протокол, не фича SDK. Можно использовать с любым SDK:

```python
from mcp import ClientSession

async with ClientSession(server_params) as session:
    tools = await session.list_tools()
    anthropic_tools = convert_mcp_to_anthropic(tools)

    response = client.messages.create(tools=anthropic_tools, ...)

    if tool_use:
        result = await session.call_tool(name, args)
```

**Когда MCP полезен:**
- Готовые интеграции (Firecrawl, Brave Search, Supabase MCP)
- Изоляция tools от основного кода
- Платформа для разных agents

**Для atlantisplus MVP:** Overkill. У нас уже есть Supabase client, OpenAI client.

---

## Parallel Tool Execution

**Сложность: LOW (~30 строк)**

Claude может запрашивать несколько tools за раз:

```python
response.content = [
    TextBlock(text="Let me search..."),
    ToolUseBlock(name="search_people", input={"query": "pharma"}),
    ToolUseBlock(name="semantic_search", input={"query": "Singapore"}),
]

async def execute_tools_parallel(tool_blocks):
    tasks = [
        execute_tool(block.name, block.input)
        for block in tool_blocks
        if block.type == "tool_use"
    ]
    return await asyncio.gather(*tasks)
```

---

## Streaming to Telegram

**Сложность: MEDIUM (~80 строк)**

```python
async def stream_to_telegram(query: str, chat_id: int, bot):
    message = await bot.send_message(chat_id, "🤔 Thinking...")
    full_text = ""

    with client.messages.stream(...) as stream:
        for event in stream:
            if event.type == "content_block_delta":
                if event.delta.type == "text_delta":
                    full_text += event.delta.text
                    if len(full_text) % 100 == 0:
                        await bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message.message_id,
                            text=full_text + "▌"
                        )
```

**Нюансы:**
- Telegram rate limits на edit_message (~30/min)
- Tool blocks приходят целиком после текста
- Нужен debouncing

---

## Sub-agents Orchestration

**Сложность: HIGH (~300+ строк)**

Концептуально:

```python
class SubAgent:
    def __init__(self, parent_context, tools_subset, goal):
        self.context = parent_context.fork()
        self.tools = tools_subset
        self.goal = goal

    async def run(self) -> str:
        # Own agentic loop with focused goal
        ...

class Orchestrator:
    async def handle_complex_query(self, query):
        plan = await self.create_plan(query)

        if plan.needs_parallel_research:
            agents = [
                SubAgent(self.context, ["search_db"], "Find pharma people"),
                SubAgent(self.context, ["web_search"], "Recent deals"),
            ]
            results = await asyncio.gather(*[a.run() for a in agents])
            return await self.synthesize(query, results)
```

**Что продумать:**
1. Context sharing между sub-agents
2. Resource limits (tokens/turns per agent)
3. Error handling
4. Cost control (3 sub-agents = 3x API calls)
5. Result aggregation

---

## Implementation Roadmap

| Phase | Фича | Сложность | Строк | Нужно для MVP? |
|-------|------|-----------|-------|----------------|
| 1 | Basic agentic loop | Low | ~50 | ✅ |
| 1 | Parallel tool execution | Low | ~30 | ✅ |
| 2 | Streaming to Telegram | Medium | ~80 | ⚠️ Nice to have |
| 3 | Context compaction | Medium | ~100 | ❌ Не для 3 users |
| 3 | MCP integration | Medium | ~150 | ❌ Overkill |
| 4 | Sub-agents | High | ~300+ | ❌ V2 |

---

## References

- [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python)
- [Claude Tool Use](https://docs.anthropic.com/claude/docs/tool-use)
- [MCP Specification](https://modelcontextprotocol.io/)
- [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)
