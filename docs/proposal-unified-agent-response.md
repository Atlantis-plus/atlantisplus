# Proposal: Unified Agent Response Format

> Date: 2026-02-14
> Status: DRAFT - needs review
> Context: Dig Deeper feature broke, revealed deeper architectural problem

## Problem Statement

### What we wanted
Agent-based architecture where:
- Agent decides which tools to call
- Agent returns results
- We show results to user
- **No business logic for each tool**

### What we built
```
┌─────────────────────────────────────────────────────────────┐
│                    CURRENT ARCHITECTURE                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  chat_direct():                                             │
│    for each tool_call:                                      │
│      result = execute_tool(tool_name, args)                 │
│                                                             │
│      if tool_name == "find_people":        ← special case   │
│        extract_people(result)                               │
│      if tool_name == "search_by_company_exact":  ← added    │
│        extract_people(result)                               │
│      if tool_name == "search_by_name_fuzzy":     ← added    │
│        extract_people(result)                               │
│      if tool_name == "semantic_search_raw":      ← added    │
│        extract_people(result)  # BROKEN - different format! │
│                                                             │
│  ClaudeAgent.run():                                         │
│    for each tool_call:                                      │
│      result = execute_tool(tool_name, args)                 │
│                                                             │
│      if tool_name == "find_people":        ← only this one  │
│        extract_people(result)                               │
│      # other tools ignored!                                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Problems
1. **Duplication**: Same extraction logic in 2 places (ClaudeAgent + chat_direct)
2. **Inconsistency**: chat_direct extracts from 4 tools, ClaudeAgent from 1
3. **Fragility**: Each tool has different response format, extraction breaks
4. **Growing complexity**: Every new tool = new special case in 2 places
5. **semantic_search_raw**: Returns `assertions[]`, not `people[]` - extraction silently fails

## Root Cause

We're trying to **intercept tool results** and parse them differently per tool.

This is backwards. The agent should tell us what it found.

## Proposed Solution

### Core Idea
Agent returns **structured final response** with found people. We don't intercept tools.

```
┌─────────────────────────────────────────────────────────────┐
│                   PROPOSED ARCHITECTURE                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Agent runs, calls whatever tools it wants                  │
│                        ↓                                    │
│  Agent returns structured response:                         │
│  {                                                          │
│    "message": "Found 15 people at Yandex...",              │
│    "people": [                                              │
│      {"person_id": "abc", "name": "Дима Васильев"},        │
│      {"person_id": "def", "name": "Роман Вишневский"},     │
│      ...                                                    │
│    ]                                                        │
│  }                                                          │
│                        ↓                                    │
│  We take message + people, show to user with buttons        │
│                                                             │
│  NO tool-specific extraction logic anywhere                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Implementation Options

#### Option A: Structured Output from Agent

Use Claude's structured output / tool_choice to force final response format:

```python
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "message": {"type": "string"},
        "people": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "person_id": {"type": "string"},
                    "name": {"type": "string"}
                }
            }
        }
    }
}
```

Agent MUST return this format. Tools return whatever they want.

**Pros:**
- Cleanest solution
- Agent is responsible for formatting
- No extraction logic needed

**Cons:**
- Requires prompt engineering to ensure agent includes people
- May need to update system prompt

#### Option B: Final Response Tool

Add a special tool `report_results` that agent MUST call at the end:

```python
{
    "name": "report_results",
    "description": "Call this at the end to report found people to the user",
    "parameters": {
        "message": "string",
        "people": [{"person_id": "string", "name": "string"}]
    }
}
```

**Pros:**
- Explicit contract
- Easy to extract

**Cons:**
- Agent might forget to call it
- Extra tool call

#### Option C: Parse Agent's Final Text

After agent finishes, parse the final text response to extract person IDs mentioned.

**Pros:**
- No changes to agent behavior

**Cons:**
- Unreliable parsing
- Person IDs might not be in text
- Adds complexity, not reduces it

### Recommendation

**Option A (Structured Output)** is the cleanest.

The system prompt should instruct:
```
When you finish searching, respond with JSON:
{
  "message": "Your response text here",
  "people": [{"person_id": "...", "name": "..."}, ...]
}

Include ALL people you found relevant to the query in the people array.
```

## Migration Path

1. Update ClaudeAgent system prompt to require structured JSON response
2. Update ClaudeAgent.run() to parse JSON response and extract people
3. Remove all tool-specific extraction logic from ClaudeAgent
4. Apply same pattern to chat_direct (OpenAI)
5. Delete duplicate extraction code

## What Gets Deleted

```python
# DELETE from claude_agent.py:
if tool_name == "find_people":
    try:
        result_data = json.loads(result)
        # ... 15 lines of extraction logic
    except:
        pass

# DELETE from chat.py:
PEOPLE_RETURNING_TOOLS = {
    "find_people",
    "search_by_company_exact",
    # ...
}
if tool_name in PEOPLE_RETURNING_TOOLS:
    # ... 30 lines of extraction logic
```

## Result

- **Before**: 2 places × N tools × custom parsing = O(2N) complexity
- **After**: 1 structured response format = O(1) complexity

Agent is smart. Let it decide what to return. Don't micromanage its tool calls.

## Open Questions

1. Will Claude reliably return JSON format?
2. Should we validate the response schema?
3. What if agent returns malformed JSON?
4. Does OpenAI (Tier 1) need same treatment?

---

## Appendix: Current Code Locations

| Component | File | Lines |
|-----------|------|-------|
| ClaudeAgent extraction | `service/app/services/claude_agent.py` | 203-220 |
| chat_direct extraction | `service/app/api/chat.py` | 2136-2177 |
| PEOPLE_RETURNING_TOOLS | `service/app/api/chat.py` | 2136-2140 |
| Tool definitions | `service/app/api/chat.py` | 300-700 |
