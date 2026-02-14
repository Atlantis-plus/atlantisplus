"""
Claude Agentic Loop - Basic Implementation

This module provides a Claude-based agent with automatic tool execution.
Key difference from OpenAI: Claude uses a different tools format and response structure.

Usage:
    from app.services.claude_agent import ClaudeAgent

    agent = ClaudeAgent(user_id="...")
    result = await agent.run("кто может помочь с фармой в Сингапуре?")
    print(result.message)
"""

import json
import asyncio
import time
from datetime import datetime
from typing import Optional, Any
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

from app.config import get_settings

# Tool call logging for analysis
TOOL_LOG_DIR = Path("/tmp/claude_agent_logs")
TOOL_LOG_DIR.mkdir(exist_ok=True)


@dataclass
class AgentResult:
    """Result from agent execution."""
    message: str
    tool_calls: list[dict] = field(default_factory=list)
    iterations: int = 0
    found_people: list[dict] = field(default_factory=list)


# Convert OpenAI tools format to Anthropic format
def convert_tools_to_anthropic(openai_tools: list[dict]) -> list[dict]:
    """
    Convert OpenAI function tools to Anthropic format.

    OpenAI format:
    {
        "type": "function",
        "function": {
            "name": "...",
            "description": "...",
            "parameters": {...}
        }
    }

    Anthropic format:
    {
        "name": "...",
        "description": "...",
        "input_schema": {...}
    }
    """
    anthropic_tools = []
    for tool in openai_tools:
        if tool.get("type") == "function":
            func = tool["function"]
            anthropic_tools.append({
                "name": func["name"],
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {"type": "object", "properties": {}})
            })
    return anthropic_tools


class ClaudeAgent:
    """
    Claude-based agentic loop.

    Claude decides which tools to call. We execute them and feed results back.
    Loop continues until Claude gives a final answer (no more tool calls).
    """

    def __init__(
        self,
        user_id: str,
        tools: list[dict],
        execute_tool_fn,
        system_prompt: str,
        model: str = "claude-sonnet-4-20250514",
        max_iterations: int = 10
    ):
        """
        Args:
            user_id: User ID for tool execution context
            tools: List of tools in OpenAI format (will be converted)
            execute_tool_fn: async function(tool_name, args, user_id) -> str
            system_prompt: System prompt for agent behavior
            model: Claude model to use
            max_iterations: Max tool-calling iterations to prevent infinite loops
        """
        self.user_id = user_id
        self.tools = convert_tools_to_anthropic(tools)
        self.execute_tool = execute_tool_fn
        self.system_prompt = system_prompt
        self.model = model
        self.max_iterations = max_iterations

        settings = get_settings()
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        # Session ID for logging
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = TOOL_LOG_DIR / f"session_{self.session_id}.jsonl"

    def _log_tool_call(self, iteration: int, tool_name: str, args: dict, result: str, duration_ms: float, error: Optional[str] = None):
        """Log tool call to file for analysis."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "iteration": iteration,
            "tool": tool_name,
            "args": args,
            "result_length": len(result),
            "result_preview": result[:500] if len(result) > 500 else result,
            "duration_ms": round(duration_ms, 2),
            "error": error
        }

        try:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[CLAUDE_AGENT] Log write error: {e}")

    async def run(self, user_message: str) -> AgentResult:
        """
        Run the agentic loop.

        Args:
            user_message: The user's query

        Returns:
            AgentResult with final message and tool call history
        """
        messages = [{"role": "user", "content": user_message}]
        tool_calls_history = []
        found_people = []
        iteration = 0

        # Log session start
        self._log_tool_call(0, "__session_start__", {"query": user_message}, "", 0)

        while iteration < self.max_iterations:
            iteration += 1
            print(f"[CLAUDE_AGENT] Iteration {iteration}")

            # Call Claude
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=self.system_prompt,
                tools=self.tools,
                messages=messages
            )

            print(f"[CLAUDE_AGENT] Stop reason: {response.stop_reason}")

            # Check if Claude wants to use tools
            if response.stop_reason == "tool_use":
                # Process all tool calls in this response
                tool_results = []
                assistant_content = []

                for block in response.content:
                    if block.type == "text":
                        assistant_content.append({
                            "type": "text",
                            "text": block.text
                        })
                    elif block.type == "tool_use":
                        tool_name = block.name
                        tool_input = block.input
                        tool_use_id = block.id

                        print(f"[CLAUDE_AGENT] Tool call: {tool_name}({json.dumps(tool_input, ensure_ascii=False)[:100]}...)")

                        # Execute the tool with timing
                        start_time = time.time()
                        try:
                            result = await self.execute_tool(tool_name, tool_input, self.user_id)
                            duration_ms = (time.time() - start_time) * 1000

                            # Log for analysis
                            self._log_tool_call(iteration, tool_name, tool_input, result, duration_ms)

                            # Track tool call
                            tool_calls_history.append({
                                "tool": tool_name,
                                "args": tool_input,
                                "result_preview": result[:200] if len(result) > 200 else result
                            })

                            # Extract people from report_results tool call
                            if tool_name == "report_results":
                                try:
                                    # Claude returns input as dict, not string
                                    args = tool_input if isinstance(tool_input, dict) else json.loads(tool_input)
                                    found_people = args.get("people", [])
                                except (json.JSONDecodeError, TypeError):
                                    pass

                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tool_use_id,
                                "content": result
                            })

                            assistant_content.append({
                                "type": "tool_use",
                                "id": tool_use_id,
                                "name": tool_name,
                                "input": tool_input
                            })

                        except Exception as e:
                            duration_ms = (time.time() - start_time) * 1000
                            print(f"[CLAUDE_AGENT] Tool error: {e}")

                            # Log error for analysis
                            self._log_tool_call(iteration, tool_name, tool_input, "", duration_ms, error=str(e))

                            # Return error so Claude can adapt
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tool_use_id,
                                "content": json.dumps({"error": str(e)}),
                                "is_error": True
                            })

                # Add assistant response and tool results to messages
                messages.append({"role": "assistant", "content": assistant_content})
                messages.append({"role": "user", "content": tool_results})

            elif response.stop_reason == "end_turn":
                # Claude is done - extract final text response
                final_text = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        final_text += block.text

                # If agent searched but didn't report results, ask once more
                if not found_people and iteration > 1:
                    print(f"[CLAUDE_AGENT] No people found, requesting report_results...")
                    retry_response = self.client.messages.create(
                        model=self.model,
                        max_tokens=1024,
                        system=self.system_prompt,
                        messages=messages + [{"role": "assistant", "content": response.content}, {"role": "user", "content": "Please call report_results with all people you found."}],
                        tools=self.tools
                    )
                    for block in retry_response.content:
                        if block.type == "tool_use" and block.name == "report_results":
                            try:
                                found_people = block.input.get("people", [])
                                print(f"[CLAUDE_AGENT] Extracted {len(found_people)} people from retry")
                            except (AttributeError, TypeError):
                                pass

                print(f"[CLAUDE_AGENT] Finished after {iteration} iterations")

                return AgentResult(
                    message=final_text,
                    tool_calls=tool_calls_history,
                    iterations=iteration,
                    found_people=found_people
                )

            else:
                # Unexpected stop reason
                print(f"[CLAUDE_AGENT] Unexpected stop_reason: {response.stop_reason}")
                break

        # Max iterations reached
        return AgentResult(
            message="I apologize, but I'm having trouble completing this request. Please try again.",
            tool_calls=tool_calls_history,
            iterations=iteration,
            found_people=found_people
        )


async def run_claude_agent(
    user_message: str,
    user_id: str,
    tools: list[dict],
    execute_tool_fn,
    system_prompt: str,
    model: str = "claude-sonnet-4-20250514"
) -> AgentResult:
    """
    Convenience function to run Claude agent.

    Args:
        user_message: User's query
        user_id: User ID for tool context
        tools: List of tools in OpenAI format
        execute_tool_fn: Tool executor function
        system_prompt: System prompt
        model: Claude model

    Returns:
        AgentResult
    """
    agent = ClaudeAgent(
        user_id=user_id,
        tools=tools,
        execute_tool_fn=execute_tool_fn,
        system_prompt=system_prompt,
        model=model
    )
    return await agent.run(user_message)
