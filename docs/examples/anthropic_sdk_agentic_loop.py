"""
Anthropic Python SDK - Complete Agentic Loop Implementation

This demonstrates:
1. Claude decides which tools to call
2. Multi-turn tool calling loop (YOU implement)
3. Self-correction on errors (YOU implement)
4. Claude decides what to do next based on results
"""

import anthropic
from typing import Any
import json

client = anthropic.Anthropic()

# ============================================
# STEP 1: Define your custom tools
# ============================================
TOOLS = [
    {
        "name": "search_people",
        "description": "Search for people in the network by query. Returns list of matching people.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (name, skill, company, etc.)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_person_details",
        "description": "Get detailed information about a specific person by ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "person_id": {
                    "type": "string",
                    "description": "UUID of the person"
                }
            },
            "required": ["person_id"]
        }
    },
    {
        "name": "semantic_search",
        "description": "Search using embeddings for semantic similarity. Better for complex queries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query"
                },
                "threshold": {
                    "type": "number",
                    "description": "Similarity threshold (0-1)",
                    "default": 0.7
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "find_connections",
        "description": "Find connection paths between two people in the network.",
        "input_schema": {
            "type": "object",
            "properties": {
                "from_person_id": {"type": "string"},
                "to_person_id": {"type": "string"},
                "max_hops": {"type": "integer", "default": 3}
            },
            "required": ["from_person_id", "to_person_id"]
        }
    }
]


# ============================================
# STEP 2: Implement tool execution
# ============================================
def execute_tool(tool_name: str, tool_input: dict) -> Any:
    """
    Execute a tool and return the result.
    This is where YOUR business logic lives.
    """
    print(f"  [Executing] {tool_name}({json.dumps(tool_input, ensure_ascii=False)[:100]}...)")

    # Simulated implementations - replace with real ones
    if tool_name == "search_people":
        # Simulated: first search might return nothing
        if "pharma" in tool_input["query"].lower():
            return {"results": [], "total": 0, "suggestion": "Try 'pharmaceutical' or company names"}
        return {
            "results": [
                {"person_id": "uuid-1", "name": "John Doe", "role": "CEO at BioTech"},
                {"person_id": "uuid-2", "name": "Jane Smith", "role": "VP Sales, Healthcare"}
            ],
            "total": 2
        }

    elif tool_name == "get_person_details":
        return {
            "person_id": tool_input["person_id"],
            "name": "John Doe",
            "assertions": [
                {"predicate": "works_at", "value": "BioTech Corp"},
                {"predicate": "can_help_with", "value": "pharma distribution in APAC"},
                {"predicate": "knows", "value": "Singapore healthcare regulators"}
            ],
            "connections": ["uuid-3", "uuid-4"]
        }

    elif tool_name == "semantic_search":
        return {
            "results": [
                {
                    "person_id": "uuid-5",
                    "name": "Maria Chen",
                    "relevance": 0.89,
                    "reason": "Has pharma connections in Singapore"
                }
            ]
        }

    elif tool_name == "find_connections":
        return {
            "paths": [
                ["uuid-1", "uuid-3", "uuid-5"],
            ],
            "shortest_path_length": 2
        }

    return {"error": f"Unknown tool: {tool_name}"}


# ============================================
# STEP 3: The Agentic Loop (YOU implement this)
# ============================================
def run_agent(user_query: str, max_iterations: int = 10) -> str:
    """
    Main agentic loop.

    KEY INSIGHT: Claude decides what to do, but YOU control the loop.
    - Claude returns tool_use blocks
    - You execute them and return results
    - Claude decides next action based on results
    - Loop until Claude gives final answer (no more tool calls)
    """

    messages = [{"role": "user", "content": user_query}]

    system_prompt = """You are a network search agent helping find people and connections.

You have access to multiple search strategies:
1. search_people - direct text search (fast but literal)
2. semantic_search - embedding-based search (better for complex queries)
3. get_person_details - get full info about a person
4. find_connections - find paths between people

STRATEGY:
- Start with the most appropriate search for the query
- If first search returns no results, TRY A DIFFERENT STRATEGY
- For complex queries, use semantic_search
- Always get_person_details for promising candidates
- Explain your reasoning and why each person is relevant

SELF-CORRECTION:
- If a search returns nothing, analyze why and try alternatives
- Consider synonyms, related terms, broader/narrower queries
- Don't give up after one failed attempt
"""

    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        print(f"\n=== Iteration {iteration} ===")

        # Call Claude
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=system_prompt,
            tools=TOOLS,
            messages=messages
        )

        print(f"Stop reason: {response.stop_reason}")

        # Check if Claude wants to use tools
        if response.stop_reason == "tool_use":
            # Process all tool calls in this response
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input
                    tool_use_id = block.id

                    # Execute the tool (YOUR code)
                    try:
                        result = execute_tool(tool_name, tool_input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": json.dumps(result, ensure_ascii=False)
                        })
                    except Exception as e:
                        # Self-correction: return error so Claude can adapt
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": json.dumps({"error": str(e)}),
                            "is_error": True
                        })

            # Add assistant response and tool results to messages
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        elif response.stop_reason == "end_turn":
            # Claude is done - extract final text response
            final_response = ""
            for block in response.content:
                if hasattr(block, "text"):
                    final_response += block.text

            print(f"\n=== Agent finished after {iteration} iterations ===")
            return final_response

        else:
            # Unexpected stop reason
            print(f"Unexpected stop_reason: {response.stop_reason}")
            break

    return "Agent reached max iterations without completing."


# ============================================
# STEP 4: Run the agent
# ============================================
if __name__ == "__main__":
    # Example query that might require multiple strategies
    query = """
    Who in my network can help with entering the pharmaceutical market in Singapore?
    I need someone who either:
    - Works in pharma/healthcare in APAC
    - Has connections to Singapore regulators
    - Has done market entry in similar regulated industries

    Show me the most relevant people and explain WHY they could help.
    """

    result = run_agent(query)
    print("\n" + "="*60)
    print("FINAL ANSWER:")
    print("="*60)
    print(result)
