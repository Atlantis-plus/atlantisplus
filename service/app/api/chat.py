from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import openai
import json

from app.config import get_settings
from app.supabase_client import get_supabase_admin
from app.middleware.auth import verify_supabase_token, get_user_id
from app.services.embedding import generate_embedding

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., description="User message")
    session_id: Optional[str] = Field(None, description="Existing session ID to continue")


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatResponse(BaseModel):
    session_id: str
    message: str
    tool_results: Optional[list[dict]] = None


# Tools available to the agent
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_network",
            "description": "Search the user's network for people matching a query. Use this when the user asks about finding someone or who can help with something.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query describing what kind of person or expertise is needed"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_person_details",
            "description": "Get detailed information about a specific person including all known facts and connections.",
            "parameters": {
                "type": "object",
                "properties": {
                    "person_name": {
                        "type": "string",
                        "description": "The name of the person to look up"
                    }
                },
                "required": ["person_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_people",
            "description": "List all people in the user's network, optionally filtered. Use when user asks 'who do I know' or wants to see their contacts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of people to return",
                        "default": 20
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_note_about_person",
            "description": "Add a new note or fact about a person. Use when user provides new information about someone.",
            "parameters": {
                "type": "object",
                "properties": {
                    "person_name": {
                        "type": "string",
                        "description": "Name of the person"
                    },
                    "note": {
                        "type": "string",
                        "description": "The note or fact to add"
                    }
                },
                "required": ["person_name", "note"]
            }
        }
    }
]

SYSTEM_PROMPT = """You are a personal network assistant helping the user manage and query their professional network.

You have access to the user's network data - people they know, facts about those people, and connections between them.

Your capabilities:
1. Search for people based on skills, expertise, companies, or any criteria
2. Look up detailed information about specific people
3. List people in the network
4. Add new notes about people

Guidelines:
- Be concise but helpful
- When searching, explain WHY certain people might be relevant
- If the user mentions someone new, offer to add them
- For ambiguous names, ask for clarification
- Suggest non-obvious connections when relevant
- Respond in the same language as the user

You help the user answer questions like:
- "Who can help me with X?"
- "What do I know about [person]?"
- "Who works at [company]?"
- "Find me someone who knows about [topic]"
"""


async def execute_tool(tool_name: str, args: dict, user_id: str) -> str:
    """Execute a tool and return the result as a string."""
    settings = get_settings()
    supabase = get_supabase_admin()

    if tool_name == "search_network":
        # Generate embedding for query
        query_embedding = generate_embedding(args["query"])

        # Semantic search
        match_result = supabase.rpc(
            'match_assertions',
            {
                'query_embedding': query_embedding,
                'match_threshold': 0.3,
                'match_count': 15,
                'p_owner_id': user_id
            }
        ).execute()

        if not match_result.data:
            return "No relevant people found for this query."

        # Group by person
        person_facts = {}
        person_ids = set()
        for match in match_result.data:
            pid = match['subject_person_id']
            person_ids.add(pid)
            if pid not in person_facts:
                person_facts[pid] = []
            person_facts[pid].append({
                'fact': f"{match['predicate']}: {match['object_value']}",
                'similarity': match['similarity']
            })

        # Get person names
        people = supabase.table('person').select('person_id, display_name').in_(
            'person_id', list(person_ids)
        ).execute()

        name_map = {p['person_id']: p['display_name'] for p in people.data}

        results = []
        for pid, facts in person_facts.items():
            name = name_map.get(pid, 'Unknown')
            avg_sim = sum(f['similarity'] for f in facts) / len(facts)
            fact_list = [f['fact'] for f in facts[:5]]
            results.append({
                'name': name,
                'relevance': round(avg_sim, 2),
                'facts': fact_list
            })

        results.sort(key=lambda x: x['relevance'], reverse=True)
        return json.dumps(results[:10], ensure_ascii=False, indent=2)

    elif tool_name == "get_person_details":
        # Find person by name (case-insensitive partial match)
        person_result = supabase.table('person').select(
            'person_id, display_name, summary'
        ).eq('owner_id', user_id).ilike(
            'display_name', f"%{args['person_name']}%"
        ).eq('status', 'active').execute()

        if not person_result.data:
            return f"Person '{args['person_name']}' not found in your network."

        if len(person_result.data) > 1:
            names = [p['display_name'] for p in person_result.data]
            return f"Multiple people match '{args['person_name']}': {', '.join(names)}. Please be more specific."

        person = person_result.data[0]

        # Get all assertions about this person
        assertions = supabase.table('assertion').select(
            'predicate, object_value, confidence'
        ).eq('subject_person_id', person['person_id']).execute()

        facts = [f"- {a['predicate']}: {a['object_value']}" for a in assertions.data]

        result = {
            'name': person['display_name'],
            'summary': person.get('summary', 'No summary yet'),
            'facts': facts if facts else ['No facts recorded yet']
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    elif tool_name == "list_people":
        limit = args.get('limit', 20)

        people = supabase.table('person').select(
            'person_id, display_name, summary'
        ).eq('owner_id', user_id).eq('status', 'active').limit(limit).execute()

        if not people.data:
            return "Your network is empty. Start by adding notes about people you know."

        result = [{'name': p['display_name'], 'summary': p.get('summary', '')} for p in people.data]
        return json.dumps(result, ensure_ascii=False, indent=2)

    elif tool_name == "add_note_about_person":
        # Find or create person
        person_result = supabase.table('person').select('person_id, display_name').eq(
            'owner_id', user_id
        ).ilike('display_name', f"%{args['person_name']}%").eq('status', 'active').execute()

        if not person_result.data:
            # Create new person
            new_person = supabase.table('person').insert({
                'owner_id': user_id,
                'display_name': args['person_name']
            }).execute()
            person_id = new_person.data[0]['person_id']
            person_name = args['person_name']
            created_new = True
        elif len(person_result.data) > 1:
            names = [p['display_name'] for p in person_result.data]
            return f"Multiple people match '{args['person_name']}': {', '.join(names)}. Please be more specific."
        else:
            person_id = person_result.data[0]['person_id']
            person_name = person_result.data[0]['display_name']
            created_new = False

        # Create raw evidence
        evidence = supabase.table('raw_evidence').insert({
            'owner_id': user_id,
            'source_type': 'chat_message',
            'content': f"About {person_name}: {args['note']}",
            'processed': True,
            'processing_status': 'done'
        }).execute()

        # Add assertion
        embedding = generate_embedding(args['note'])
        supabase.table('assertion').insert({
            'subject_person_id': person_id,
            'predicate': 'note',
            'object_value': args['note'],
            'evidence_id': evidence.data[0]['evidence_id'],
            'embedding': embedding,
            'confidence': 0.9
        }).execute()

        if created_new:
            return f"Created new person '{person_name}' and added the note."
        else:
            return f"Added note about {person_name}."

    return f"Unknown tool: {tool_name}"


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Chat with the network agent. Maintains conversation history and can use tools.
    """
    settings = get_settings()
    user_id = get_user_id(token_payload)
    supabase = get_supabase_admin()
    client = openai.OpenAI(api_key=settings.openai_api_key)

    # Get or create session
    if request.session_id:
        # Verify session belongs to user
        session_check = supabase.table('chat_session').select('session_id').eq(
            'session_id', request.session_id
        ).eq('owner_id', user_id).execute()

        if not session_check.data:
            raise HTTPException(status_code=404, detail="Session not found")

        session_id = request.session_id
    else:
        # Create new session
        session = supabase.table('chat_session').insert({
            'owner_id': user_id,
            'title': request.message[:50] + ('...' if len(request.message) > 50 else '')
        }).execute()
        session_id = session.data[0]['session_id']

    # Save user message
    supabase.table('chat_message').insert({
        'session_id': session_id,
        'role': 'user',
        'content': request.message
    }).execute()

    # Load conversation history
    history = supabase.table('chat_message').select(
        'role, content, tool_calls, tool_call_id'
    ).eq('session_id', session_id).order('created_at').execute()

    # Build messages for OpenAI
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    for msg in history.data:
        if msg['role'] == 'tool':
            messages.append({
                "role": "tool",
                "content": msg['content'],
                "tool_call_id": msg['tool_call_id']
            })
        elif msg['role'] == 'assistant' and msg.get('tool_calls'):
            messages.append({
                "role": "assistant",
                "content": msg['content'] or "",
                "tool_calls": msg['tool_calls']
            })
        else:
            messages.append({
                "role": msg['role'],
                "content": msg['content']
            })

    tool_results = []
    max_iterations = 5  # Prevent infinite loops

    for _ in range(max_iterations):
        # Call OpenAI
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.7
        )

        assistant_message = response.choices[0].message

        # Check if we need to call tools
        if assistant_message.tool_calls:
            # Save assistant message with tool calls
            tool_calls_json = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                }
                for tc in assistant_message.tool_calls
            ]

            supabase.table('chat_message').insert({
                'session_id': session_id,
                'role': 'assistant',
                'content': assistant_message.content or '',
                'tool_calls': tool_calls_json
            }).execute()

            messages.append({
                "role": "assistant",
                "content": assistant_message.content or "",
                "tool_calls": tool_calls_json
            })

            # Execute each tool
            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)

                print(f"[CHAT] Executing tool: {tool_name} with args: {tool_args}")

                result = await execute_tool(tool_name, tool_args, user_id)
                tool_results.append({
                    "tool": tool_name,
                    "args": tool_args,
                    "result": result
                })

                # Save tool response
                supabase.table('chat_message').insert({
                    'session_id': session_id,
                    'role': 'tool',
                    'content': result,
                    'tool_call_id': tool_call.id
                }).execute()

                messages.append({
                    "role": "tool",
                    "content": result,
                    "tool_call_id": tool_call.id
                })
        else:
            # No more tool calls, save final response
            final_content = assistant_message.content or ""

            supabase.table('chat_message').insert({
                'session_id': session_id,
                'role': 'assistant',
                'content': final_content
            }).execute()

            # Update session timestamp
            supabase.table('chat_session').update({
                'updated_at': 'now()'
            }).eq('session_id', session_id).execute()

            return ChatResponse(
                session_id=session_id,
                message=final_content,
                tool_results=tool_results if tool_results else None
            )

    # If we hit max iterations, return what we have
    return ChatResponse(
        session_id=session_id,
        message="I apologize, but I'm having trouble completing this request. Please try again.",
        tool_results=tool_results if tool_results else None
    )


@router.get("/chat/sessions")
async def list_sessions(
    token_payload: dict = Depends(verify_supabase_token)
):
    """List all chat sessions for the user."""
    user_id = get_user_id(token_payload)
    supabase = get_supabase_admin()

    sessions = supabase.table('chat_session').select(
        'session_id, title, created_at, updated_at'
    ).eq('owner_id', user_id).order('updated_at', desc=True).limit(20).execute()

    return {"sessions": sessions.data}


@router.get("/chat/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    token_payload: dict = Depends(verify_supabase_token)
):
    """Get all messages in a chat session."""
    user_id = get_user_id(token_payload)
    supabase = get_supabase_admin()

    # Verify session belongs to user
    session_check = supabase.table('chat_session').select('session_id').eq(
        'session_id', session_id
    ).eq('owner_id', user_id).execute()

    if not session_check.data:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = supabase.table('chat_message').select(
        'message_id, role, content, created_at'
    ).eq('session_id', session_id).neq('role', 'tool').order('created_at').execute()

    return {"messages": messages.data}
