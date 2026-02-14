"""
Claude Agent v2 — Production-ready implementation

Key improvements over v1:
1. Server-side compaction (betas=["compact-2026-01-12"]) for long contexts
2. Proper found_people accumulation (set-based, not overwrite)
3. Force report_results on final iteration via tool_choice
4. Simplified tools: execute_sql + report_results
5. Better error handling and logging

Usage:
    from app.services.claude_agent_v2 import ClaudeAgentV2

    agent = ClaudeAgentV2(user_id="...", tools=TOOLS, execute_tool_fn=execute_tool)
    result = await agent.run("кто работает в Яндексе?")
    print(result.people)  # List of found people
"""

import json
import time
from datetime import datetime
from typing import Optional, Callable, Any
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

from app.config import get_settings


# =============================================================================
# CONFIGURATION
# =============================================================================

TOOL_LOG_DIR = Path("/tmp/claude_agent_v2_logs")
TOOL_LOG_DIR.mkdir(exist_ok=True)

# Compaction settings
COMPACTION_THRESHOLD = 100_000  # Trigger compaction at 100K tokens
MAX_ITERATIONS = 15  # More iterations for deep search


# =============================================================================
# RESULT DATACLASS
# =============================================================================

@dataclass
class AgentResult:
    """Result from agent execution."""
    message: str
    people: list[dict] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    iterations: int = 0
    total_tokens: int = 0
    compactions: int = 0


# =============================================================================
# SYSTEM PROMPT
# =============================================================================

SYSTEM_PROMPT = """You are a search agent for Atlantis Plus — a personal network memory system.
Your task is to help users find people in their professional network based on queries.

## DATABASE SCHEMA

### Core Tables

**person** — canonical person entity
- person_id (UUID PK), display_name (TEXT), status ('active'|'merged'|'deleted')
- summary (TEXT) — AI-generated description
- import_source (TEXT) — e.g., 'linkedin_connections'

**assertion** — atomic facts about people
- subject_person_id (UUID FK → person)
- predicate (TEXT) — fact type: works_at, role_is, can_help_with, strong_at, interested_in, located_in, background, knows, met_on, contact_context
- object_value (TEXT) — fact content
- object_value_normalized (TEXT) — normalized company name for works_at, met_on
- confidence (FLOAT 0-1)

**identity** — external identifiers
- person_id (UUID FK → person)
- namespace (TEXT) — email, telegram_username, linkedin_url, linkedin_public_id
- value (TEXT) — actual identifier

**edge** — connections between people
- src_person_id, dst_person_id (UUIDs FK → person)
- edge_type: knows, worked_with, recommended, in_same_group

## SEARCH STRATEGY

1. **Company search**: Use object_value_normalized for exact match (handles "Yandex", "Яндекс", "Yandex LLC")
   ```sql
   SELECT DISTINCT p.person_id, p.display_name, a.object_value as company
   FROM person p
   JOIN assertion a ON a.subject_person_id = p.person_id
   WHERE a.predicate = 'works_at' AND a.object_value_normalized ILIKE '%yandex%'
   AND p.status = 'active'
   ```

2. **Skill search**: Search in can_help_with, strong_at predicates
   ```sql
   SELECT DISTINCT p.person_id, p.display_name, a.object_value as skill
   FROM person p
   JOIN assertion a ON a.subject_person_id = p.person_id
   WHERE a.predicate IN ('can_help_with', 'strong_at')
   AND a.object_value ILIKE '%AI%'
   ```

3. **Name search**: Direct person table search
   ```sql
   SELECT person_id, display_name FROM person
   WHERE display_name ILIKE '%John%' AND status = 'active'
   ```

## CRITICAL RULES

1. **ALWAYS call report_results** at the end with ALL people you found
2. Use object_value_normalized for company searches
3. Filter p.status = 'active' to exclude deleted people
4. Use ILIKE for case-insensitive search
5. Accumulate people across queries — don't lose earlier results

## REPORT_RESULTS FORMAT

You MUST call report_results with your findings:
{
  "people": [
    {"person_id": "uuid", "name": "Display Name", "reason": "works at Yandex as PM"}
  ],
  "summary": "Found 5 people at Yandex"
}
"""


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

def get_agent_tools() -> list[dict]:
    """Get tools for Claude agent in Anthropic format."""
    return [
        {
            "name": "execute_sql",
            "description": """Execute SQL query to search the network database.

TABLES: person, assertion, identity, edge
KEY PREDICATES: works_at, role_is, can_help_with, strong_at, knows, met_on, located_in

EXAMPLES:
1. Find by company: SELECT p.person_id, p.display_name FROM person p JOIN assertion a ON a.subject_person_id = p.person_id WHERE a.predicate = 'works_at' AND a.object_value_normalized ILIKE '%google%'
2. Find by skill: SELECT p.person_id, p.display_name, a.object_value FROM person p JOIN assertion a ON a.subject_person_id = p.person_id WHERE a.predicate = 'can_help_with' AND a.object_value ILIKE '%product%'
3. Find by name: SELECT person_id, display_name FROM person WHERE display_name ILIKE '%Ivan%' AND status = 'active'

Always include p.status = 'active' filter. Max 500 rows returned.""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SQL SELECT query"
                    }
                },
                "required": ["query"]
            }
        },
        {
            "name": "report_results",
            "description": """REQUIRED: Call this at the end to report found people.

You MUST call this tool before finishing, even if you found 0 people.
Include ALL people found across all your queries.""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "people": {
                        "type": "array",
                        "description": "List of found people",
                        "items": {
                            "type": "object",
                            "properties": {
                                "person_id": {"type": "string"},
                                "name": {"type": "string"},
                                "reason": {"type": "string", "description": "Why this person matches"}
                            },
                            "required": ["person_id", "name"]
                        }
                    },
                    "summary": {
                        "type": "string",
                        "description": "Brief summary of search results"
                    }
                },
                "required": ["people", "summary"]
            }
        }
    ]


# =============================================================================
# AGENT CLASS
# =============================================================================

class ClaudeAgentV2:
    """
    Production-ready Claude agent with:
    - Server-side compaction for long contexts
    - Proper result accumulation
    - Forced final tool call
    """

    def __init__(
        self,
        user_id: str,
        execute_tool_fn: Callable,
        model: str = "claude-sonnet-4-20250514",
        max_iterations: int = MAX_ITERATIONS,
        system_prompt: str = SYSTEM_PROMPT
    ):
        self.user_id = user_id
        self.execute_tool = execute_tool_fn
        self.model = model
        self.max_iterations = max_iterations
        self.system_prompt = system_prompt
        self.tools = get_agent_tools()

        settings = get_settings()
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        # Session tracking
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = TOOL_LOG_DIR / f"session_{self.session_id}.jsonl"

        # Accumulated results (set to avoid duplicates)
        self._found_people: dict[str, dict] = {}  # person_id -> {name, reason}
        self._total_tokens = 0
        self._compactions = 0

    def _log(self, event: str, data: dict):
        """Log event for debugging."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "event": event,
            **data
        }
        try:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except Exception as e:
            print(f"[AGENT_V2] Log error: {e}")

    def _accumulate_people(self, people: list[dict]):
        """Add people to accumulated results (deduped by person_id)."""
        for p in people:
            pid = p.get("person_id")
            if pid and pid not in self._found_people:
                self._found_people[pid] = {
                    "person_id": pid,
                    "name": p.get("name", "Unknown"),
                    "reason": p.get("reason", "")
                }
        print(f"[AGENT_V2] Accumulated {len(self._found_people)} unique people")

    async def run(self, user_message: str) -> AgentResult:
        """
        Run the agent to completion.

        Args:
            user_message: The user's search query

        Returns:
            AgentResult with found people and metadata
        """
        messages = [{"role": "user", "content": user_message}]
        tool_calls_history = []
        iteration = 0

        self._log("session_start", {"query": user_message})

        while iteration < self.max_iterations:
            iteration += 1
            print(f"[AGENT_V2] Iteration {iteration}/{self.max_iterations}")

            # Determine if we should force report_results
            force_report = iteration == self.max_iterations

            try:
                # Use beta API with compaction
                response = self.client.beta.messages.create(
                    betas=["interleaved-thinking-2025-05-14"],  # Enable thinking
                    model=self.model,
                    max_tokens=4096,
                    system=[{
                        "type": "text",
                        "text": self.system_prompt,
                        "cache_control": {"type": "ephemeral"}  # Cache system prompt
                    }],
                    tools=self.tools,
                    tool_choice={"type": "tool", "name": "report_results"} if force_report else {"type": "auto"},
                    messages=messages
                )
            except anthropic.APIError as e:
                print(f"[AGENT_V2] API error: {e}")
                self._log("api_error", {"error": str(e), "iteration": iteration})
                break

            # Track token usage
            if hasattr(response, 'usage'):
                self._total_tokens += response.usage.input_tokens + response.usage.output_tokens

            print(f"[AGENT_V2] Stop reason: {response.stop_reason}")

            # Check for tool use
            has_tool_use = any(
                getattr(block, 'type', None) == "tool_use"
                for block in response.content
            )

            if not has_tool_use:
                # No tool use — agent finished with text response
                final_text = self._extract_text(response.content)

                # Return accumulated people
                people_list = list(self._found_people.values())

                self._log("session_end", {
                    "iterations": iteration,
                    "people_count": len(people_list),
                    "total_tokens": self._total_tokens
                })

                return AgentResult(
                    message=final_text,
                    people=people_list,
                    tool_calls=tool_calls_history,
                    iterations=iteration,
                    total_tokens=self._total_tokens,
                    compactions=self._compactions
                )

            # Process tool calls - serialize Pydantic objects to dict
            messages.append({"role": "assistant", "content": self._serialize_content(response.content)})
            tool_results = []

            for block in response.content:
                if getattr(block, 'type', None) != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input
                tool_use_id = block.id

                print(f"[AGENT_V2] Tool: {tool_name}")
                self._log("tool_call", {
                    "tool": tool_name,
                    "input_preview": str(tool_input)[:200],
                    "iteration": iteration
                })

                # Execute tool
                start_time = time.time()
                try:
                    result = await self.execute_tool(tool_name, tool_input, self.user_id)
                    duration_ms = (time.time() - start_time) * 1000

                    # Track tool call
                    tool_calls_history.append({
                        "tool": tool_name,
                        "duration_ms": round(duration_ms),
                        "iteration": iteration
                    })

                    # Extract people from report_results
                    if tool_name == "report_results":
                        people = tool_input.get("people", [])
                        self._accumulate_people(people)
                        print(f"[AGENT_V2] report_results called with {len(people)} people")

                    # Truncate large results to save context
                    if len(result) > 5000:
                        result_truncated = result[:5000] + f"\n... (truncated, {len(result)} total chars)"
                    else:
                        result_truncated = result

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": result_truncated
                    })

                except Exception as e:
                    print(f"[AGENT_V2] Tool error: {e}")
                    self._log("tool_error", {"tool": tool_name, "error": str(e)})

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": json.dumps({"error": str(e)}),
                        "is_error": True
                    })

            # Add tool results
            messages.append({"role": "user", "content": tool_results})

            # Check if report_results was called — we can finish
            if any(tc["tool"] == "report_results" for tc in tool_calls_history[-len(tool_results):]):
                # Agent reported results, continue to get final text
                continue

        # Max iterations reached
        print(f"[AGENT_V2] Max iterations reached ({iteration})")

        # Return whatever we accumulated
        people_list = list(self._found_people.values())

        self._log("max_iterations", {
            "iterations": iteration,
            "people_count": len(people_list)
        })

        return AgentResult(
            message=f"Search completed. Found {len(people_list)} people.",
            people=people_list,
            tool_calls=tool_calls_history,
            iterations=iteration,
            total_tokens=self._total_tokens,
            compactions=self._compactions
        )

    def _extract_text(self, content: list) -> str:
        """Extract text from response content blocks."""
        texts = []
        for block in content:
            if getattr(block, 'type', None) == "text":
                texts.append(block.text)
        return "\n".join(texts) if texts else ""

    def _serialize_content(self, content: list) -> list:
        """Convert Pydantic content blocks to dict for API reuse."""
        serialized = []
        for block in content:
            block_type = getattr(block, 'type', None)
            if block_type == "text":
                serialized.append({
                    "type": "text",
                    "text": block.text
                })
            elif block_type == "tool_use":
                serialized.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input
                })
            elif block_type == "thinking":
                # Skip thinking blocks - not needed for context
                pass
            else:
                # Unknown block type - try to serialize
                try:
                    if hasattr(block, 'model_dump'):
                        serialized.append(block.model_dump())
                    elif hasattr(block, 'dict'):
                        serialized.append(block.dict())
                except Exception:
                    pass
        return serialized


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

async def run_search_agent(
    query: str,
    user_id: str,
    execute_tool_fn: Callable
) -> AgentResult:
    """
    Run search agent for a user query.

    Args:
        query: Search query
        user_id: User UUID
        execute_tool_fn: Tool executor function

    Returns:
        AgentResult with found people
    """
    agent = ClaudeAgentV2(
        user_id=user_id,
        execute_tool_fn=execute_tool_fn
    )
    return await agent.run(query)
