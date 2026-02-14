# Agentic Loop Implementation: Anthropic SDK vs Agent SDK

## Quick Answer to Your Questions

### Q: Who decides which tools to call?

| SDK | Answer |
|-----|--------|
| **Anthropic Python SDK** | **Claude decides**, returns `tool_use` blocks. **You execute** and return results. |
| **Claude Agent SDK** | **Claude decides**, SDK **executes automatically**. You just receive messages. |

### Q: How to implement multi-turn tool calling loop?

| SDK | Answer |
|-----|--------|
| **Anthropic Python SDK** | **Manual** - You write the `while` loop, accumulate messages, check `stop_reason` |
| **Claude Agent SDK** | **Automatic** - SDK handles the loop. You call `query()` and iterate `receive_response()` |

### Q: Is there built-in retry/self-correction?

| SDK | Answer |
|-----|--------|
| **Anthropic Python SDK** | **No** - You catch errors, return them as `tool_result`, Claude adapts based on system prompt |
| **Claude Agent SDK** | **Built-in** - SDK handles tool execution errors, Claude sees them and self-corrects |

### Q: Can Agent SDK use CUSTOM tools?

**Yes!** Via in-process MCP servers using `@tool` decorator + `create_sdk_mcp_server()`.

---

## Detailed Comparison

### Anthropic Python SDK - Manual Loop

```python
# YOU write this loop
while iteration < max_iterations:
    response = client.messages.create(...)

    if response.stop_reason == "tool_use":
        # YOU execute tools
        for block in response.content:
            if block.type == "tool_use":
                result = YOUR_execute_tool(block.name, block.input)
                tool_results.append({"tool_use_id": block.id, "content": result})

        # YOU accumulate messages
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    elif response.stop_reason == "end_turn":
        return extract_text(response)  # Done
```

**Pros:**
- Full control over the loop
- Can add custom logic between iterations
- No additional dependencies
- Works with any tools/functions

**Cons:**
- More code to write
- You handle all error cases
- You manage message history

### Claude Agent SDK - Automatic Loop

```python
# SDK handles the loop
async with ClaudeSDKClient(options=options) as client:
    await client.query("Your prompt")

    async for msg in client.receive_response():
        # Just process messages - loop is automatic
        print(msg)
```

**Pros:**
- Zero loop code
- Built-in error handling
- Tool execution is automatic
- Cleaner, less code

**Cons:**
- Less control over individual iterations
- Requires MCP format for custom tools
- Additional SDK dependency
- Async-only

---

## Custom Tools Comparison

### Anthropic SDK - Direct Tool Definitions

```python
TOOLS = [
    {
        "name": "search_people",
        "description": "Search for people",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"}
            }
        }
    }
]

def execute_tool(name, input):
    if name == "search_people":
        return your_search_logic(input["query"])
```

### Agent SDK - MCP Server Format

```python
from claude_agent_sdk import tool, create_sdk_mcp_server

@tool("search_people", "Search for people", {"query": str})
async def search_people(args):
    result = your_search_logic(args["query"])
    return {"content": [{"type": "text", "text": json.dumps(result)}]}

server = create_sdk_mcp_server(
    name="my-tools",
    version="1.0.0",
    tools=[search_people]
)
```

---

## Self-Correction Behavior

### How It Works (Both SDKs)

Self-correction is **prompt-driven** in both cases. Claude decides to try alternative approaches based on:

1. **System prompt instructions** - Tell Claude to try different strategies
2. **Tool results** - Empty results, errors, or suggestions trigger adaptation
3. **Context** - Claude reasons about what to try next

**Example System Prompt for Self-Correction:**
```
STRATEGY:
- Start with the most appropriate search
- If first search returns no results, TRY A DIFFERENT STRATEGY
- Consider synonyms, related terms, broader/narrower queries
- Don't give up after one failed attempt
```

**Example Tool Response Triggering Retry:**
```json
{
  "results": [],
  "total": 0,
  "suggestion": "Try 'pharmaceutical' or company names"
}
```

### Difference in Error Handling

| Scenario | Anthropic SDK | Agent SDK |
|----------|--------------|-----------|
| Tool throws exception | **You** catch it, return as error result | SDK catches, passes to Claude |
| Claude sees error | Via your `tool_result` with `is_error: true` | Via SDK's automatic handling |
| Claude's response | Adapts based on error message | Same - adapts based on error |

---

## Which Should You Use?

### Use Anthropic Python SDK if:

- You need **full control** over each iteration
- You want to add **custom logic** between tool calls (logging, rate limiting, approval flows)
- You prefer **synchronous code** or need sync compatibility
- You want **minimal dependencies**
- Your tools are **simple functions**, not MCP servers

### Use Claude Agent SDK if:

- You want **less boilerplate** code
- You're building a **production agent** with many tools
- You're already using **MCP ecosystem** (external MCP servers)
- You prefer **async-native** design
- You want **built-in streaming** and message handling

---

## Real-World Recommendation for Atlantis Plus

For the Atlantis Plus network search agent, I recommend:

### Short-term (MVP): Anthropic Python SDK

**Reasons:**
1. Simpler setup - no MCP server infrastructure
2. Easier to debug - you see every step
3. Fits existing FastAPI architecture
4. Can add custom logging/metrics between calls

### Long-term (Production): Consider Agent SDK

**When to switch:**
1. If you add many tools (>10)
2. If you want MCP ecosystem integration
3. If you need complex multi-agent orchestration

---

## Code Examples Location

- **Anthropic SDK Example**: `/docs/examples/anthropic_sdk_agentic_loop.py`
- **Agent SDK Example**: `/docs/examples/agent_sdk_custom_tools.py`

Both examples demonstrate:
- Custom tool definitions
- Multi-turn conversations
- Self-correction when first approach fails
- Claude deciding which tools to use

---

## Sources

- [Claude Agent SDK Custom Tools](https://platform.claude.com/docs/en/agent-sdk/custom-tools)
- [Claude Agent SDK GitHub](https://github.com/anthropics/claude-agent-sdk-python)
- [Anthropic Python SDK GitHub](https://github.com/anthropics/anthropic-sdk-python)
- [Building Agents with Claude Agent SDK](https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk)
- [MCP in the SDK](https://docs.claude.com/en/docs/agent-sdk/mcp)
