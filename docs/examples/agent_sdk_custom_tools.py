"""
Claude Agent SDK - Custom Tools via MCP

This demonstrates:
1. Custom tools defined with @tool decorator
2. SDK handles the agentic loop AUTOMATICALLY
3. Self-correction is BUILT-IN
4. Claude decides what to do next - you just receive results

KEY DIFFERENCE FROM ANTHROPIC SDK:
- Anthropic SDK: YOU write the while loop, YOU handle tool results
- Agent SDK: SDK handles everything, you define tools and receive messages
"""

from claude_agent_sdk import (
    tool,
    create_sdk_mcp_server,
    ClaudeSDKClient,
    ClaudeAgentOptions,
)
from typing import Any
import json
import asyncio


# ============================================
# STEP 1: Define Custom Tools with @tool decorator
# ============================================

@tool(
    "search_people",
    "Search for people in the network by query. Returns list of matching people.",
    {"query": str, "limit": int}
)
async def search_people(args: dict[str, Any]) -> dict[str, Any]:
    """
    Your actual search implementation.
    The SDK will call this automatically when Claude decides to use it.
    """
    query = args["query"]
    limit = args.get("limit", 10)

    print(f"  [Tool executed] search_people(query='{query}', limit={limit})")

    # Simulated search - replace with real implementation
    if "pharma" in query.lower():
        # Simulate empty result to trigger self-correction
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "results": [],
                    "total": 0,
                    "suggestion": "Try 'pharmaceutical', 'healthcare', or specific company names"
                })
            }]
        }

    return {
        "content": [{
            "type": "text",
            "text": json.dumps({
                "results": [
                    {"person_id": "uuid-1", "name": "John Doe", "role": "CEO at BioTech"},
                    {"person_id": "uuid-2", "name": "Jane Smith", "role": "VP Sales, Healthcare"}
                ],
                "total": 2
            })
        }]
    }


@tool(
    "semantic_search",
    "Search using embeddings for semantic similarity. Better for complex queries.",
    {"query": str, "threshold": float}
)
async def semantic_search(args: dict[str, Any]) -> dict[str, Any]:
    """Semantic search with embeddings - use for complex/ambiguous queries."""
    query = args["query"]
    threshold = args.get("threshold", 0.7)

    print(f"  [Tool executed] semantic_search(query='{query}', threshold={threshold})")

    return {
        "content": [{
            "type": "text",
            "text": json.dumps({
                "results": [
                    {
                        "person_id": "uuid-5",
                        "name": "Maria Chen",
                        "relevance": 0.89,
                        "reason": "Has pharmaceutical connections in Singapore"
                    },
                    {
                        "person_id": "uuid-6",
                        "name": "Wei Zhang",
                        "relevance": 0.82,
                        "reason": "Former Singapore health ministry consultant"
                    }
                ]
            })
        }]
    }


@tool(
    "get_person_details",
    "Get detailed information about a specific person by ID.",
    {"person_id": str}
)
async def get_person_details(args: dict[str, Any]) -> dict[str, Any]:
    """Get full details for a person."""
    person_id = args["person_id"]

    print(f"  [Tool executed] get_person_details(person_id='{person_id}')")

    # Simulated person data
    persons = {
        "uuid-1": {
            "name": "John Doe",
            "assertions": [
                {"predicate": "works_at", "value": "BioTech Corp"},
                {"predicate": "can_help_with", "value": "pharma distribution in APAC"},
            ],
            "connections": ["uuid-3", "uuid-4"]
        },
        "uuid-5": {
            "name": "Maria Chen",
            "assertions": [
                {"predicate": "works_at", "value": "PharmaSG"},
                {"predicate": "knows", "value": "Singapore healthcare regulators"},
                {"predicate": "can_help_with", "value": "market entry in regulated industries"},
            ],
            "connections": ["uuid-1", "uuid-6"]
        }
    }

    person = persons.get(person_id, {"error": f"Person {person_id} not found"})

    return {
        "content": [{
            "type": "text",
            "text": json.dumps(person)
        }]
    }


@tool(
    "find_connections",
    "Find connection paths between two people in the network.",
    {"from_person_id": str, "to_person_id": str, "max_hops": int}
)
async def find_connections(args: dict[str, Any]) -> dict[str, Any]:
    """Find paths between two people in the network graph."""
    from_id = args["from_person_id"]
    to_id = args["to_person_id"]
    max_hops = args.get("max_hops", 3)

    print(f"  [Tool executed] find_connections({from_id} -> {to_id}, max_hops={max_hops})")

    return {
        "content": [{
            "type": "text",
            "text": json.dumps({
                "paths": [
                    [from_id, "uuid-3", to_id],
                ],
                "shortest_path_length": 2
            })
        }]
    }


# ============================================
# STEP 2: Create SDK MCP Server
# ============================================

network_search_server = create_sdk_mcp_server(
    name="network-search",
    version="1.0.0",
    tools=[
        search_people,
        semantic_search,
        get_person_details,
        find_connections
    ]
)


# ============================================
# STEP 3: Run Agent (SDK handles the loop!)
# ============================================

async def run_agent(user_query: str):
    """
    Run the agent with automatic loop handling.

    KEY DIFFERENCE: No while loop here!
    The SDK orchestrates everything:
    - Claude decides which tools to call
    - SDK executes them automatically
    - Claude sees results and decides next action
    - SDK streams messages back to you
    """

    # System prompt for search agent behavior
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

    options = ClaudeAgentOptions(
        # Provide our custom MCP server
        mcp_servers={
            "network-search": network_search_server
        },
        # Allow specific tools (MCP tool naming format)
        allowed_tools=[
            "mcp__network-search__search_people",
            "mcp__network-search__semantic_search",
            "mcp__network-search__get_person_details",
            "mcp__network-search__find_connections",
        ],
        # Optional: limit turns to prevent infinite loops
        max_turns=10,
        # System prompt for agent behavior
        system_prompt=system_prompt
    )

    print(f"\n{'='*60}")
    print(f"USER QUERY: {user_query}")
    print(f"{'='*60}\n")

    # The SDK handles the agentic loop automatically!
    async with ClaudeSDKClient(options=options) as client:
        # Send the initial query
        await client.query(user_query)

        # Receive and process all messages (including tool calls)
        async for msg in client.receive_response():
            # Message types you might receive:
            # - assistant: Claude's thinking/response
            # - tool_use: Claude is calling a tool (SDK executes it)
            # - tool_result: Result from tool execution
            # - result: Final result

            if hasattr(msg, 'type'):
                if msg.type == "assistant":
                    print(f"\n[Claude]: {msg.content}")
                elif msg.type == "tool_use":
                    print(f"\n[Tool Call]: {msg.tool_name}")
                elif msg.type == "result":
                    print(f"\n{'='*60}")
                    print("FINAL RESULT:")
                    print(f"{'='*60}")
                    print(msg.result if hasattr(msg, 'result') else msg)


# ============================================
# STEP 4: Example queries demonstrating self-correction
# ============================================

async def main():
    # Query 1: Simple case
    await run_agent("Find people who work in healthcare")

    print("\n" + "="*80 + "\n")

    # Query 2: Complex case that requires self-correction
    # "pharma" returns empty from search_people, Claude should try semantic_search
    await run_agent("""
    Who in my network can help with entering the pharmaceutical market in Singapore?
    I need someone who either:
    - Works in pharma/healthcare in APAC
    - Has connections to Singapore regulators
    - Has done market entry in similar regulated industries
    """)


if __name__ == "__main__":
    asyncio.run(main())
