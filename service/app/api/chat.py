from typing import Optional
from datetime import datetime, timedelta
from uuid import UUID
import re
import html

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import openai
import json

from app.config import get_settings
from app.supabase_client import get_supabase_admin
from app.middleware.auth import verify_supabase_token, get_user_id
from app.services.embedding import generate_embedding
from app.services.gap_detection import get_gap_detection_service
from app.services.dedup import get_dedup_service
from app.agents.prompts import SEARCH_FILTER_PROMPT

router = APIRouter(tags=["chat"])

# =============================================================================
# COMPANY SEARCH: Predicate weights and extraction
# =============================================================================

# Predicate relevance weights for company-related queries
COMPANY_PREDICATES = {
    'works_at': 1.0,       # Direct employment - highest
    'met_on': 0.8,         # Met at meeting/conference (e.g., "ByteDance meeting")
    'knows': 0.7,          # Personal connection (may mention company)
    'contact_context': 0.6,  # How we met (may mention company)
    'worked_on': 0.5,      # Past projects (may mention company)
    'background': 0.4,     # Career history
}


def normalize_company_name(name: str) -> str:
    """
    Normalize company name for matching. Must match SQL function.
    Examples: "Google LLC" → "google", "Yandex N.V." → "yandex n.v"
    """
    if not name:
        return ""

    result = name.lower().strip()

    # Remove common suffixes (must match SQL function)
    result = re.sub(
        r'\s*(inc\.?|llc\.?|ltd\.?|gmbh|corp\.?|corporation|company|co\.?|limited|plc|ag|sa|nv|n\.v\.)$',
        '',
        result,
        flags=re.IGNORECASE
    )

    # Normalize whitespace
    result = re.sub(r'\s+', ' ', result).strip()

    return result


def extract_company_from_query(query: str) -> Optional[str]:
    """
    Extract company name from query for multi-predicate search.

    Examples:
    - "кто из ByteDance" → "ByteDance"
    - "кто работает в Google" → "Google"
    - "интро в Яндекс" → "Яндекс"
    - "who from Meta" → "Meta"
    """
    # Patterns for company extraction (Russian and English)
    patterns = [
        # "из/from/at/в/into + Company"
        r'(?:из|from|at|в|во|into)\s+([A-ZА-Яa-zа-я][A-Za-zА-Яа-я0-9\.\-]+)',
        # "компания/company + Name"
        r'(?:компани[яию]|company)\s+([A-ZА-Яa-zа-я][A-Za-zА-Яа-я0-9\.\-]+)',
        # "работает в/works at + Company"
        r'(?:работает в|works? at|работают в)\s+([A-ZА-Яa-zа-я][A-Za-zА-Яа-я0-9\.\-]+)',
        # Capitalized word with optional suffix (Google, Meta Inc, etc.)
        r'([A-Z][A-Za-z0-9\.]+(?:\s+(?:Inc|LLC|Ltd|Corp|Bank))?)',
    ]

    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            company = match.group(1).strip()
            # Filter out common false positives
            if company.lower() not in ('кто', 'who', 'что', 'where', 'как', 'the', 'a', 'an'):
                return company

    return None


async def search_company_across_predicates(
    company_name: str,
    user_id: str,
    supabase
) -> dict[str, float]:
    """
    Search for company mentions across multiple predicates.
    Returns dict of person_id -> weighted score.
    """
    person_scores: dict[str, float] = {}

    for predicate, weight in COMPANY_PREDICATES.items():
        # Search this predicate for company mention
        try:
            # Note: Results are filtered by owner_id later in find_people
            matches = supabase.table('assertion').select(
                'subject_person_id, predicate, object_value, confidence'
            ).eq('predicate', predicate).ilike(
                'object_value', f'%{company_name}%'
            ).limit(100).execute()  # Limit to prevent overload

            for match in matches.data or []:
                pid = match['subject_person_id']
                confidence = match.get('confidence', 0.5)
                score = weight * confidence

                # Keep best score for each person
                if pid not in person_scores or score > person_scores[pid]:
                    person_scores[pid] = score

        except Exception as e:
            print(f"[COMPANY_SEARCH] Error searching {predicate}: {e}")
            continue

    return person_scores


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
            "name": "find_people",
            "description": """Universal search for people. Returns person_id for each result.

Use query for semantic search (companies, skills, topics, meetings, names).
Use name_pattern for regex cleanup (e.g., "[0-9]" for digits in names).

Examples:
- "who works at Google" → query="Google"
- "AI experts" → query="AI expert"
- "найди Васю" → query="Вася"
- "all with digits in name" → name_pattern="[0-9]"
- "meeting rooms" → query="meeting room conference"

Returns person_id for each result - use these IDs for subsequent operations.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Semantic search - searches ALL facts about people by meaning"
                    },
                    "name_pattern": {
                        "type": "string",
                        "description": "Regex pattern to filter by name (e.g., '[0-9]' for digits, '^Room' for names starting with Room)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results (default 20)",
                        "default": 20
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_person_details",
            "description": "Get detailed information about a person. Use person_id from find_people results.",
            "parameters": {
                "type": "object",
                "properties": {
                    "person_id": {
                        "type": "string",
                        "description": "UUID of the person (preferred - from find_people results)"
                    },
                    "person_name": {
                        "type": "string",
                        "description": "Name to search (fallback if no person_id)"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_note_about_person",
            "description": "Add a note/fact about a person. Use person_id from find_people. Creates new person if name provided and not found.",
            "parameters": {
                "type": "object",
                "properties": {
                    "person_id": {
                        "type": "string",
                        "description": "UUID of the person (preferred)"
                    },
                    "person_name": {
                        "type": "string",
                        "description": "Name (fallback, or to create new person)"
                    },
                    "note": {
                        "type": "string",
                        "description": "The note or fact to add"
                    }
                },
                "required": ["note"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_pending_question",
            "description": "Get a pending question to ask the user about their network. Use this occasionally to help fill gaps in profiles.",
            "parameters": {
                "type": "object",
                "properties": {
                    "person_name": {
                        "type": "string",
                        "description": "Optional: get question about a specific person"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "merge_people",
            "description": "Merge two people (same person). Use person_id from find_people. Can also rename result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "person_a_id": {
                        "type": "string",
                        "description": "UUID of person to KEEP (preferred)"
                    },
                    "person_b_id": {
                        "type": "string",
                        "description": "UUID of person to MERGE INTO person_a (preferred)"
                    },
                    "person_a_name": {
                        "type": "string",
                        "description": "Name fallback for person_a"
                    },
                    "person_b_name": {
                        "type": "string",
                        "description": "Name fallback for person_b"
                    },
                    "new_display_name": {
                        "type": "string",
                        "description": "Optional: rename merged person to this"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_merge_candidates",
            "description": "Find potential duplicates. Returns person_id pairs with similarity scores.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum candidates to return",
                        "default": 5
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_person",
            "description": "Rename a person. Use person_id from find_people.",
            "parameters": {
                "type": "object",
                "properties": {
                    "person_id": {
                        "type": "string",
                        "description": "UUID of person to edit (preferred)"
                    },
                    "current_name": {
                        "type": "string",
                        "description": "Name fallback to find person"
                    },
                    "new_name": {
                        "type": "string",
                        "description": "New display name"
                    }
                },
                "required": ["new_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "reject_merge",
            "description": "Mark two people as NOT the same (reject duplicate). Use person_id from find_people.",
            "parameters": {
                "type": "object",
                "properties": {
                    "person_a_id": {
                        "type": "string",
                        "description": "UUID of first person (preferred)"
                    },
                    "person_b_id": {
                        "type": "string",
                        "description": "UUID of second person (preferred)"
                    },
                    "person_a_name": {
                        "type": "string",
                        "description": "Name fallback"
                    },
                    "person_b_name": {
                        "type": "string",
                        "description": "Name fallback"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_people",
            "description": """Delete multiple people by their IDs. Use person_ids from find_people results.

Workflow:
1. find_people(query="meeting rooms") → get list with person_id
2. User says "delete first and third" → delete_people(person_ids=[id1, id3], confirm=true)

REQUIRES confirm=true to actually delete.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "person_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of person_id UUIDs to delete (from find_people results)"
                    },
                    "confirm": {
                        "type": "boolean",
                        "description": "MUST be true to delete. false = preview only."
                    }
                },
                "required": ["person_ids", "confirm"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_import_stats",
            "description": "Show statistics about imported contacts: counts by source, by year, top companies, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "import_source": {
                        "type": "string",
                        "description": "Optional: filter by source 'linkedin' or 'calendar'",
                        "enum": ["linkedin", "calendar"]
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rollback_import",
            "description": "Undo an entire import batch. Soft-deletes all people from that batch.",
            "parameters": {
                "type": "object",
                "properties": {
                    "batch_id": {
                        "type": "string",
                        "description": "The batch_id to rollback (from import result or get_import_stats)"
                    }
                },
                "required": ["batch_id"]
            }
        }
    },
]

SYSTEM_PROMPT = """You are a personal network assistant helping the user manage and query their professional network.

## CRITICAL: USE person_id FOR ALL OPERATIONS

Every find_people result includes `person_id`. ALWAYS use person_id (not names) for subsequent operations.

## CRITICAL: USE MOTIVATIONS FROM SEARCH RESULTS

When find_people returns results, each person has a "motivation" field with a specific reason why they match the query.

YOU MUST USE THESE MOTIVATIONS EXACTLY AS PROVIDED - do not paraphrase or make up your own!

Example tool response:
{
  "people": [
    {"person_id": "abc", "name": "John Doe", "motivation": "worked at Boston Dynamics, knows robotics ecosystem"}
  ]
}

Your formatted response MUST use the motivation verbatim:
👤 <b>John Doe</b>
<i>worked at Boston Dynamics, knows robotics ecosystem</i>

The motivation comes from the tool response - use it word-for-word!

## CRITICAL: OUTPUT FORMATTING FOR TELEGRAM

You MUST use HTML formatting (NOT Markdown!) for Telegram:
- Bold: <b>text</b> (NOT **text**)
- Italic: <i>text</i> (NOT *text*)
- NO LINKS - do not use <a href="..."> tags, they don't work in this context

When showing search results with people, format EACH person like this:
👤 <b>Person Name</b>
<i>motivation from tool response</i>

Use a BLANK LINE between people for readability. Do NOT use numbered lists (1. 2. 3.).

Example output for search results:
👤 <b>Charbel Melhem</b>
<i>worked at Boston Dynamics, knows US robotics ecosystem</i>

👤 <b>Alex Turilin</b>
<i>YC network, knows robotics founders</i>

The motivation in italics MUST come from the find_people tool response, not be generated by you.

## WORKFLOW

1. **Search**: find_people(query="...") → returns list with person_id, name, and motivation
2. **Operations**: Use person_id from results:
   - merge_people(person_a_id=..., person_b_id=...)
   - edit_person(person_id=..., new_name=...)
   - delete_people(person_ids=[...], confirm=true)
   - add_note_about_person(person_id=..., note=...)

## FIND_PEOPLE EXAMPLES
| User says | Use |
|-----------|-----|
| "кто эксперт в AI" | find_people(query="AI expert") |
| "кто работает в Google" | find_people(query="Google") |
| "найди Васю" | find_people(query="Вася") |
| "все с цифрой в имени" | find_people(name_pattern="[0-9]") |
| "переговорки и комнаты" | find_people(query="meeting room conference") |

## MERGE & EDIT WORKFLOW
Example: User says "объедини Daliya227 и daliya227@yahoo.com, назови Daliya Safiullina"

1. find_people(query="Daliya") → get person_ids
2. merge_people(person_a_id="...", person_b_id="...", new_display_name="Daliya Safiullina")

## DELETE WORKFLOW
Example: User says "найди переговорки" → you show list → "удали первую и третью"

1. find_people(query="meeting rooms") → returns [{person_id: "abc", name: "Room1"}, {person_id: "def", name: "Room2"}, ...]
2. User selects which to delete
3. delete_people(person_ids=["abc", "xyz"], confirm=true) ← use IDs from step 1

Guidelines:
- Be concise but helpful
- Respond in the same language as the user
- User can ONLY modify their own contacts (is_own=true, editable=true)
- ALWAYS use HTML formatting, NEVER use Markdown stars

PROACTIVE QUESTIONS — IMPORTANT:
- After EVERY successful action (adding note, searching, showing person info), call get_pending_question
- If a question is returned, ask it naturally at the END of your response
- Example flow: user asks "что знаешь о Васе?" → you show info → then add "Кстати, где вы познакомились с Васей?"
- When showing a person with few facts (1-2), ALWAYS mention that the profile is incomplete and ask a question
- Phrase questions naturally in Russian: "Кстати, ...", "А где работает ...?", "Как вы познакомились с ...?"

WHEN USER ANSWERS A QUESTION:
- If you asked "Где познакомились с X?" and user replies with an answer, use add_note_about_person to save it
- Example: you asked about Вася, user says "В Сингапуре" → call add_note_about_person(person_name="Вася", note="Познакомились в Сингапуре")
- Always convert short answers into full notes with context
- If the user answers a proactive question, use answer_question to record it
- Don't ask more than 1-2 questions per conversation
- Don't interrupt important tasks with questions
- Good moments to ask: after completing a task, during casual conversation, when discussing a person

IMPORTANT - IGNORING PROACTIVE QUESTIONS:
- If you asked a proactive question but user asks a NEW unrelated question → simply ignore your question and answer the new one
- Example: you asked "Where did you meet Vasya?" but user asks "Who works in tech?" → just search for tech people, don't mention Vasya
- User is NOT obligated to answer your questions - they control the conversation
- If user changes topic, follow their lead immediately without mentioning the unanswered question

You help the user answer questions like:
- "Who can help me with X?"
- "What do I know about [person]?"
- "Who works at [company]?"
- "Find me someone who knows about [topic]"
"""


def is_semantic_query(query: str) -> bool:
    """
    Determine if a query requires semantic reasoning with motivation.

    Returns True for complex queries like "who can help with X", "intro to Y".
    Returns False for simple name searches like "find John".
    """
    if not query:
        return False

    query_lower = query.lower()

    # Semantic intent keywords (English and Russian)
    semantic_patterns = [
        # Help/expertise
        'help with', 'can help', 'помочь', 'поможет', 'помощь',
        'expert', 'эксперт', 'специалист',
        'knows about', 'знает о', 'разбирается',
        # Introductions
        'intro', 'introduce', 'интро', 'познакомить', 'выйти на',
        'connection to', 'contact at', 'контакт в',
        # Recommendations
        'recommend', 'рекомендовать', 'посоветовать',
        'who should', 'кого стоит', 'кому стоит',
        # Capabilities
        'can do', 'able to', 'способен', 'может',
        'good at', 'strong at', 'силён в', 'хорош в',
        # Work/industry
        'works in', 'работает в',
        'industry', 'сфера', 'область',
        # Investment/business
        'investor', 'инвестор', 'invest', 'funding',
        'startup', 'founder', 'основатель',
    ]

    for pattern in semantic_patterns:
        if pattern in query_lower:
            return True

    # Questions usually need reasoning
    if query_lower.startswith(('who ', 'кто ', 'whom ', 'кому ', 'whose ', 'чей ')):
        # But not simple "who is X" name lookups
        if not any(x in query_lower for x in ['is ', 'это ', 'такой ']):
            return True

    return False


async def filter_and_motivate_results(
    query: str,
    candidates: list[dict],
    user_id: str,
    supabase,
    settings
) -> list[dict]:
    """
    Use LLM to filter candidates and generate one-liner motivations.

    Args:
        query: The user's search query
        candidates: List of dicts with person_id, name, relevance
        user_id: User ID for fetching assertions
        supabase: Supabase client
        settings: App settings

    Returns:
        Filtered list with motivation field added
    """
    if not candidates:
        return candidates

    # Limit to top 15 for LLM processing
    candidates = candidates[:15]
    person_ids = [c['person_id'] for c in candidates]

    # Fetch assertions for all candidates (limit to prevent oversized context)
    assertions_result = supabase.table('assertion').select(
        'subject_person_id, predicate, object_value'
    ).in_('subject_person_id', person_ids).limit(150).execute()

    # Group assertions by person
    person_facts: dict[str, list[str]] = {}
    for a in assertions_result.data or []:
        pid = a['subject_person_id']
        if pid not in person_facts:
            person_facts[pid] = []
        person_facts[pid].append(f"{a['predicate']}: {a['object_value']}")

    # Build context for LLM
    candidates_text = []
    for c in candidates:
        facts = person_facts.get(c['person_id'], ['no facts recorded'])
        facts_str = "; ".join(facts[:10])  # Limit facts per person
        candidates_text.append(f"- {c['name']} (id: {c['person_id']}): {facts_str}")

    prompt = f"""User query: "{query}"

Candidates:
{chr(10).join(candidates_text)}

Filter and add motivations. Return JSON."""

    try:
        client = openai.OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Fast model for filtering
            messages=[
                {"role": "system", "content": SEARCH_FILTER_PROMPT},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=1000,
            timeout=10.0  # 10 seconds max
        )

        result_json = response.choices[0].message.content
        result_data = json.loads(result_json)

        # Build lookup of valid person_ids (use DB names, not LLM names for security)
        valid_ids = {c['person_id'] for c in candidates}
        id_to_name = {c['person_id']: c['name'] for c in candidates}

        # Build result with motivations
        filtered_results = []
        for r in result_data.get('results', []):
            pid = r.get('person_id')
            if pid not in valid_ids:
                print(f"[FIND_PEOPLE] LLM returned invalid person_id: {pid}")
                continue
            filtered_results.append({
                'person_id': pid,
                'name': html.escape(id_to_name[pid]),  # Use ORIGINAL name from DB, escape HTML
                'motivation': html.escape(r.get('motivation', ''))  # Escape motivation too
            })

        print(f"[FIND_PEOPLE] Filtered {len(candidates)} -> {len(filtered_results)} with motivations")
        return filtered_results if filtered_results else candidates

    except Exception as e:
        print(f"[FIND_PEOPLE] LLM filter error: {e}")
        # Fallback: return original candidates with empty motivation
        for c in candidates:
            if 'motivation' not in c:
                c['motivation'] = ''
        return candidates


async def execute_tool(tool_name: str, args: dict, user_id: str) -> str:
    """Execute a tool and return the result as a string."""
    settings = get_settings()
    supabase = get_supabase_admin()

    if tool_name == "find_people":
        limit = args.get('limit', 20)
        query = args.get('query')
        name_pattern = args.get('name_pattern')
        print(f"[FIND_PEOPLE] query={query}, name_pattern={name_pattern}, limit={limit}")

        # Hybrid search: name + semantic
        if query:
            person_scores = {}  # person_id -> best_score (1.0 for name match, similarity for semantic)

            # 1. Name search (exact/partial match gets high score)
            name_result = supabase.table('person').select(
                'person_id, display_name, import_source'
            ).eq('owner_id', user_id).eq('status', 'active').ilike('display_name', f'%{query}%').limit(50).execute()

            for p in name_result.data or []:
                # Name matches get score 1.0 (highest priority)
                person_scores[p['person_id']] = 1.0

            print(f"[FIND_PEOPLE] Name search found {len(name_result.data or [])} people")

            # 2. Company-specific search (fast, multi-predicate: works_at, met_on, knows, etc.)
            company_name = extract_company_from_query(query)
            company_matched_ids = set()  # Track company matches for boost later
            if company_name:
                print(f"[FIND_PEOPLE] Detected company query: '{company_name}'")
                company_scores = await search_company_across_predicates(
                    company_name, user_id, supabase
                )
                print(f"[FIND_PEOPLE] Company search found {len(company_scores)} people")

                # Merge company results
                for pid, score in company_scores.items():
                    company_matched_ids.add(pid)
                    if pid not in person_scores:
                        person_scores[pid] = score

                print(f"[FIND_PEOPLE] After company search: {len(person_scores)} total people")

            # 3. Semantic search by assertions (slow, may timeout - wrapped in try/except)
            try:
                query_embedding = generate_embedding(query)
                match_result = supabase.rpc(
                    'match_assertions_community',
                    {
                        'query_embedding': query_embedding,
                        'match_threshold': 0.4,  # Balanced: less noise, good recall
                        'match_count': 200
                    }
                ).execute()

                for m in match_result.data or []:
                    pid = m['subject_person_id']
                    sim = m.get('similarity', 0)
                    # Only update if not already found by name (name match = 1.0)
                    if pid not in person_scores or sim > person_scores[pid]:
                        person_scores[pid] = sim
                    # Boost score if also found by company search
                    if pid in company_matched_ids and person_scores[pid] < 1.0:
                        person_scores[pid] = min(1.0, person_scores[pid] + 0.2)

                print(f"[FIND_PEOPLE] After semantic: {len(person_scores)} total people")
            except Exception as e:
                print(f"[FIND_PEOPLE] Semantic search failed (continuing with name+company results): {e}")

            if not person_scores:
                return json.dumps({'people': [], 'total': 0, 'message': 'No people match the query'}, ensure_ascii=False)

            # Sort by score DESC and take top limit
            sorted_people = sorted(person_scores.items(), key=lambda x: x[1], reverse=True)[:limit]
            top_person_ids = [pid for pid, _ in sorted_people]

            print(f"[FIND_PEOPLE] Top scores: {[(pid[:8], round(s, 3)) for pid, s in sorted_people[:5]]}")

            # Fetch person details for those not already fetched
            people_result = supabase.table('person').select(
                'person_id, display_name, import_source, owner_id'
            ).in_('person_id', top_person_ids).eq('owner_id', user_id).eq('status', 'active').execute()

            # Get email status
            email_check = supabase.table('identity').select('person_id').in_(
                'person_id', top_person_ids
            ).eq('namespace', 'email').execute()
            has_email_ids = set(e['person_id'] for e in email_check.data or [])

            # Build results preserving score order
            people_by_id = {p['person_id']: p for p in people_result.data or []}

            # Apply name_pattern filter if provided
            if name_pattern:
                try:
                    pattern = re.compile(name_pattern, re.IGNORECASE)
                    top_person_ids = [pid for pid in top_person_ids
                                     if pid in people_by_id and pattern.search(people_by_id[pid]['display_name'] or '')]
                except re.error:
                    pass

            results = []
            for pid in top_person_ids:
                if pid not in people_by_id:
                    continue
                p = people_by_id[pid]
                results.append({
                    'person_id': p['person_id'],
                    'name': p['display_name'],
                    'import_source': p.get('import_source') or 'manual',
                    'has_email': p['person_id'] in has_email_ids,
                    'relevance': round(person_scores[pid], 2)
                })

            print(f"[FIND_PEOPLE] Hybrid search found {len(results)} people")

            # Always add motivations when we have multiple search results
            # (LLM often simplifies queries like "who can help with robotics" -> "robotics")
            if results and len(results) > 1:
                print(f"[FIND_PEOPLE] Adding motivations for {len(results)} results...")
                results = await filter_and_motivate_results(
                    query, results, user_id, supabase, settings
                )

            return json.dumps({
                'people': results,
                'total': len(person_scores),
                'showing': len(results),
                'is_semantic': len(results) > 1  # Has motivations if multiple results
            }, ensure_ascii=False, indent=2)

        # Name pattern only (regex filter) - use SQL function
        if name_pattern:
            result = supabase.rpc('find_people_filtered', {
                'p_owner_id': user_id,
                'p_name_regex': name_pattern,
                'p_name_contains': None,
                'p_email_domain': None,
                'p_has_email': None,
                'p_import_source': None,
                'p_company_contains': None,
                'p_limit': limit
            }).execute()

            if not result.data:
                return json.dumps({'people': [], 'total': 0, 'message': 'No people match the pattern'}, ensure_ascii=False)

            results = []
            for p in result.data:
                results.append({
                    'person_id': p['person_id'],
                    'name': p['display_name'],
                    'import_source': p.get('import_source') or 'manual',
                    'has_email': p.get('has_email', False)
                })

            return json.dumps({
                'people': results,
                'total': len(result.data),
                'showing': len(results)
            }, ensure_ascii=False, indent=2)

        # No search criteria - list all (limited)
        result = supabase.table('person').select(
            'person_id, display_name, import_source'
        ).eq('owner_id', user_id).eq('status', 'active').limit(limit).execute()

        results = []
        for p in result.data or []:
            results.append({
                'person_id': p['person_id'],
                'name': p['display_name'],
                'import_source': p.get('import_source') or 'manual'
            })

        return json.dumps({
            'people': results,
            'total': len(results),
            'showing': len(results)
        }, ensure_ascii=False, indent=2)

    elif tool_name == "get_person_details":
        # Prefer person_id if provided
        if args.get('person_id'):
            person_result = supabase.table('person').select(
                'person_id, display_name, summary, owner_id'
            ).eq('person_id', args['person_id']).eq('status', 'active').execute()
            if not person_result.data:
                return f"Person with ID {args['person_id']} not found."
        elif args.get('person_name'):
            search_name = args['person_name']
            # Fallback to name search (existing logic below)
            person_result = None
        else:
            return "Please provide person_id or person_name."

        # Name search fallback (only if no person_id)
        if not args.get('person_id'):
            search_name = args['person_name']
            # Russian name synonyms (diminutives ↔ full names)
            NAME_SYNONYMS = {
                'вася': ['василий', 'васёк', 'васька'],
                'василий': ['вася', 'васёк', 'васька'],
                'петя': ['пётр', 'петр', 'петька'],
                'саша': ['александр', 'александра', 'сашка', 'шура'],
                'коля': ['николай', 'колян'],
                'миша': ['михаил', 'мишка'],
                'дима': ['дмитрий', 'димка', 'митя'],
                'женя': ['евгений', 'евгения'],
                'лёша': ['алексей', 'лёха', 'леша'],
                'серёжа': ['сергей', 'серёга'],
                'наташа': ['наталья', 'ната'],
                'маша': ['мария', 'машка'],
                'катя': ['екатерина', 'катюша'],
            }

            search_lower = search_name.lower()
            name_variants = [search_name]
            if search_lower in NAME_SYNONYMS:
                name_variants.extend(NAME_SYNONYMS[search_lower])

            person_result = None
            for name_variant in name_variants:
                person_result = supabase.table('person').select(
                    'person_id, display_name, summary, owner_id'
                ).ilike('display_name', f"%{name_variant}%").eq('status', 'active').execute()
                if person_result.data:
                    break

            if not person_result or not person_result.data:
                return f"Person '{search_name}' not found. Try find_people first to get person_id."

            if len(person_result.data) > 1:
                # Return list with IDs so user can pick
                people_list = [{'person_id': p['person_id'], 'name': p['display_name']} for p in person_result.data]
                return json.dumps({
                    'error': 'multiple_matches',
                    'message': f"Multiple people match '{search_name}'. Use person_id:",
                    'matches': people_list
                }, ensure_ascii=False)

        person = person_result.data[0]
        is_own_person = person.get('owner_id') == user_id

        # Get all assertions about this person
        assertions = supabase.table('assertion').select(
            'predicate, object_value, confidence'
        ).eq('subject_person_id', person['person_id']).execute()

        facts = [f"- {a['predicate']}: {a['object_value']}" for a in assertions.data]

        # Check profile completeness
        predicates = set(a['predicate'] for a in assertions.data)
        missing = []
        if not predicates & {'contact_context', 'background', 'knows'}:
            missing.append("где познакомились")
        if not predicates & {'works_at', 'role_is'}:
            missing.append("где работает")
        if not predicates & {'can_help_with', 'strong_at'}:
            missing.append("в чём силён")

        result = {
            'name': person['display_name'],
            'summary': person.get('summary', 'No summary yet'),
            'facts': facts if facts else ['No facts recorded yet'],
            'profile_incomplete': len(missing) > 0,
            'missing_info': missing if missing else None,
            'is_own': is_own_person,
            'source': 'Мой контакт' if is_own_person else 'Shared',
            'editable': is_own_person
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    elif tool_name == "add_note_about_person":
        # Prefer person_id
        created_new = False
        if args.get('person_id'):
            person_result = supabase.table('person').select('person_id, display_name').eq(
                'person_id', args['person_id']
            ).eq('owner_id', user_id).eq('status', 'active').execute()
            if not person_result.data:
                return f"Person with ID {args['person_id']} not found or not yours."
            person_id = person_result.data[0]['person_id']
            person_name = person_result.data[0]['display_name']
        elif args.get('person_name'):
            # Find or create by name
            person_result = supabase.table('person').select('person_id, display_name').eq(
                'owner_id', user_id
            ).ilike('display_name', f"%{args['person_name']}%").eq('status', 'active').execute()

            if not person_result.data:
                new_person = supabase.table('person').insert({
                    'owner_id': user_id,
                    'display_name': args['person_name']
                }).execute()
                person_id = new_person.data[0]['person_id']
                person_name = args['person_name']
                created_new = True
            elif len(person_result.data) > 1:
                people_list = [{'person_id': p['person_id'], 'name': p['display_name']} for p in person_result.data]
                return json.dumps({
                    'error': 'multiple_matches',
                    'message': 'Multiple matches. Use person_id:',
                    'matches': people_list
                }, ensure_ascii=False)
            else:
                person_id = person_result.data[0]['person_id']
                person_name = person_result.data[0]['display_name']
        else:
            return "Please provide person_id or person_name."

        # Create raw evidence and assertion
        evidence = supabase.table('raw_evidence').insert({
            'owner_id': user_id,
            'source_type': 'chat_message',
            'content': f"About {person_name}: {args['note']}",
            'processed': True,
            'processing_status': 'done'
        }).execute()

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
            return json.dumps({'success': True, 'person_id': person_id, 'message': f"Created '{person_name}' and added note."}, ensure_ascii=False)
        return json.dumps({'success': True, 'person_id': person_id, 'message': f"Added note about {person_name}."}, ensure_ascii=False)

    elif tool_name == "get_pending_question":
        # Check rate limit first
        rate_result = supabase.from_("question_rate_limit").select("*").eq(
            "owner_id", user_id
        ).execute()

        from datetime import timezone
        now = datetime.now(timezone.utc)
        today = now.date()
        settings = get_settings()

        if rate_result.data:
            rate = rate_result.data[0]

            # Check if paused
            if rate.get("paused_until"):
                paused_until = datetime.fromisoformat(rate["paused_until"].replace("Z", "+00:00"))
                if now < paused_until:
                    return "No questions available right now."

            # Reset daily counter if needed
            last_reset = datetime.strptime(rate["last_daily_reset"], "%Y-%m-%d").date()
            if today > last_reset:
                supabase.from_("question_rate_limit").update({
                    "questions_shown_today": 0,
                    "last_daily_reset": str(today)
                }).eq("owner_id", user_id).execute()
            elif rate["questions_shown_today"] >= settings.questions_max_per_day:
                return "Daily question limit reached."

            # Check cooldown
            if rate.get("last_question_at"):
                last_q = datetime.fromisoformat(rate["last_question_at"].replace("Z", "+00:00"))
                if now - last_q < timedelta(hours=settings.questions_cooldown_hours):
                    return "No questions available right now (cooldown)."

        # Find pending question
        query = supabase.from_("proactive_question").select(
            "question_id, person_id, question_type, question_text_ru, question_text, person:person_id(display_name)"
        ).eq("owner_id", user_id).eq("status", "pending").gt(
            "expires_at", now.isoformat()
        ).order("priority", desc=True).limit(1)

        # Filter by person if specified
        if args.get("person_name"):
            # Find person first
            person_match = supabase.from_("person").select("person_id").eq(
                "owner_id", user_id
            ).ilike("display_name", f"%{args['person_name']}%").execute()

            if person_match.data:
                query = query.eq("person_id", person_match.data[0]["person_id"])

        result = query.execute()

        if not result.data:
            # Try generating new questions
            gap_service = get_gap_detection_service()
            await gap_service.generate_questions_batch(UUID(user_id), limit=3)
            result = query.execute()

        if not result.data:
            return "No pending questions."

        question = result.data[0]

        # Mark as shown and update rate limit
        supabase.from_("proactive_question").update({
            "status": "shown",
            "shown_at": now.isoformat()
        }).eq("question_id", question["question_id"]).execute()

        # Update rate limit
        supabase.from_("question_rate_limit").upsert({
            "owner_id": user_id,
            "last_question_at": now.isoformat(),
            "last_daily_reset": str(today)
        }, on_conflict="owner_id").execute()

        # Increment shown count
        if rate_result.data:
            supabase.from_("question_rate_limit").update({
                "questions_shown_today": rate_result.data[0].get("questions_shown_today", 0) + 1
            }).eq("owner_id", user_id).execute()

        person_name = ""
        if question.get("person") and question["person"]:
            person_name = question["person"].get("display_name", "")

        return json.dumps({
            "question_id": question["question_id"],
            "person_name": person_name,
            "question_text": question.get("question_text_ru") or question["question_text"],
            "question_type": question["question_type"]
        }, ensure_ascii=False)

    elif tool_name == "merge_people":
        dedup_service = get_dedup_service()

        # Helper to find person by ID or name
        def find_person(id_key, name_key):
            if args.get(id_key):
                result = supabase.table('person').select('person_id, display_name').eq(
                    'person_id', args[id_key]
                ).eq('owner_id', user_id).eq('status', 'active').execute()
                if not result.data:
                    return None, f"Person with ID {args[id_key]} not found."
                return result.data[0], None
            elif args.get(name_key):
                result = supabase.table('person').select('person_id, display_name').eq(
                    'owner_id', user_id
                ).ilike('display_name', f"%{args[name_key]}%").eq('status', 'active').execute()
                if not result.data:
                    return None, f"Person '{args[name_key]}' not found."
                if len(result.data) > 1:
                    people_list = [{'person_id': p['person_id'], 'name': p['display_name']} for p in result.data]
                    return None, json.dumps({'error': 'multiple_matches', 'matches': people_list}, ensure_ascii=False)
                return result.data[0], None
            return None, "Missing person_id or name"

        person_a, error_a = find_person('person_a_id', 'person_a_name')
        if error_a:
            return error_a

        person_b, error_b = find_person('person_b_id', 'person_b_name')
        if error_b:
            return error_b

        if person_a['person_id'] == person_b['person_id']:
            return "These are the same person already."

        # Perform merge
        result = await dedup_service.merge_persons(
            UUID(user_id),
            UUID(person_a['person_id']),
            UUID(person_b['person_id'])
        )

        # Rename if requested
        final_name = person_a['display_name']
        if args.get('new_display_name'):
            supabase.table('person').update({
                'display_name': args['new_display_name'],
                'updated_at': datetime.utcnow().isoformat()
            }).eq('person_id', person_a['person_id']).execute()
            final_name = args['new_display_name']

        return json.dumps({
            "success": True,
            "person_id": person_a['person_id'],
            "final_name": final_name,
            "merged_from": person_b['display_name'],
            "assertions_moved": result.assertions_moved,
            "edges_moved": result.edges_moved,
            "identities_moved": result.identities_moved
        }, ensure_ascii=False)

    elif tool_name == "suggest_merge_candidates":
        dedup_service = get_dedup_service()
        limit = args.get('limit', 5)

        candidates = await dedup_service.find_all_duplicates(UUID(user_id), limit=limit)

        if not candidates:
            return "No potential duplicates found in your network."

        return json.dumps({
            "candidates": candidates,
            "total": len(candidates)
        }, ensure_ascii=False, indent=2)

    elif tool_name == "edit_person":
        # Prefer person_id
        if args.get('person_id'):
            person_result = supabase.table('person').select('person_id, display_name').eq(
                'person_id', args['person_id']
            ).eq('owner_id', user_id).eq('status', 'active').execute()
            if not person_result.data:
                return f"Person with ID {args['person_id']} not found."
        elif args.get('current_name'):
            person_result = supabase.table('person').select('person_id, display_name').eq(
                'owner_id', user_id
            ).ilike('display_name', f"%{args['current_name']}%").eq('status', 'active').execute()
            if not person_result.data:
                return f"Person '{args['current_name']}' not found."
            if len(person_result.data) > 1:
                people_list = [{'person_id': p['person_id'], 'name': p['display_name']} for p in person_result.data]
                return json.dumps({'error': 'multiple_matches', 'matches': people_list}, ensure_ascii=False)
        else:
            return "Please provide person_id or current_name."

        person = person_result.data[0]
        old_name = person['display_name']

        supabase.table('person').update({
            'display_name': args['new_name'],
            'updated_at': datetime.utcnow().isoformat()
        }).eq('person_id', person['person_id']).execute()

        return json.dumps({'success': True, 'person_id': person['person_id'], 'old_name': old_name, 'new_name': args['new_name']}, ensure_ascii=False)

    elif tool_name == "reject_merge":
        dedup_service = get_dedup_service()

        # Helper to find person
        def find_person(id_key, name_key):
            if args.get(id_key):
                r = supabase.table('person').select('person_id, display_name').eq(
                    'person_id', args[id_key]).eq('owner_id', user_id).eq('status', 'active').execute()
                return (r.data[0], None) if r.data else (None, f"Person with ID {args[id_key]} not found.")
            elif args.get(name_key):
                r = supabase.table('person').select('person_id, display_name').eq(
                    'owner_id', user_id).ilike('display_name', f"%{args[name_key]}%").eq('status', 'active').execute()
                if not r.data:
                    return None, f"Person '{args[name_key]}' not found."
                if len(r.data) > 1:
                    return None, json.dumps({'error': 'multiple_matches', 'matches': [{'person_id': p['person_id'], 'name': p['display_name']} for p in r.data]}, ensure_ascii=False)
                return r.data[0], None
            return None, "Missing person_id or name"

        person_a, error_a = find_person('person_a_id', 'person_a_name')
        if error_a:
            return error_a
        person_b, error_b = find_person('person_b_id', 'person_b_name')
        if error_b:
            return error_b

        await dedup_service.reject_duplicate(
            UUID(user_id),
            UUID(person_a['person_id']),
            UUID(person_b['person_id'])
        )

        return json.dumps({'success': True, 'person_a': person_a['display_name'], 'person_b': person_b['display_name']}, ensure_ascii=False)

    elif tool_name == "delete_people":
        person_ids = args.get('person_ids', [])
        confirm = args.get('confirm', False)

        if not person_ids:
            return "No person_ids provided. Use find_people first to get IDs."

        # Verify all IDs belong to user and are active
        result = supabase.table('person').select(
            'person_id, display_name'
        ).in_('person_id', person_ids).eq('owner_id', user_id).eq('status', 'active').execute()

        if not result.data:
            return "No matching people found. Check that IDs are correct and belong to you."

        found_people = result.data
        found_ids = [p['person_id'] for p in found_people]

        # Check for missing IDs
        missing = set(person_ids) - set(found_ids)
        if missing:
            print(f"[DELETE_PEOPLE] Warning: {len(missing)} IDs not found or not owned by user")

        if not confirm:
            return json.dumps({
                'preview': True,
                'will_delete': len(found_people),
                'people': [{'person_id': p['person_id'], 'name': p['display_name']} for p in found_people],
                'message': f"This will delete {len(found_people)} people. Call with confirm=true to proceed."
            }, ensure_ascii=False, indent=2)

        # Actually delete
        supabase.table('person').update({
            'status': 'deleted',
            'updated_at': datetime.utcnow().isoformat()
        }).in_('person_id', found_ids).execute()

        return json.dumps({
            'deleted': len(found_people),
            'deleted_names': [p['display_name'] for p in found_people],
            'message': f"Deleted {len(found_people)} people."
        }, ensure_ascii=False)

    elif tool_name == "get_import_stats":
        # Get stats by import source
        query = supabase.table('person').select(
            'import_source, import_batch_id'
        ).eq('owner_id', user_id).eq('status', 'active')

        if args.get('import_source'):
            query = query.eq('import_source', args['import_source'])

        people = query.execute()

        if not people.data:
            return "No imported contacts found."

        # Count by source
        by_source = {}
        batch_ids = set()
        for p in people.data:
            source = p.get('import_source') or 'manual'
            by_source[source] = by_source.get(source, 0) + 1
            if p.get('import_batch_id'):
                batch_ids.add(p['import_batch_id'])

        # Get batch details
        batches = []
        if batch_ids:
            batch_result = supabase.table('import_batch').select(
                'batch_id, import_type, status, total_contacts, new_people, analytics, created_at'
            ).in_('batch_id', list(batch_ids)).order('created_at', desc=True).limit(5).execute()

            for b in batch_result.data or []:
                batches.append({
                    'batch_id': b['batch_id'],
                    'type': b['import_type'],
                    'status': b['status'],
                    'imported': b.get('new_people', 0),
                    'date': b['created_at'][:10] if b.get('created_at') else 'unknown',
                    'analytics': b.get('analytics')
                })

        return json.dumps({
            'total_people': len(people.data),
            'by_source': by_source,
            'recent_batches': batches
        }, ensure_ascii=False, indent=2)

    elif tool_name == "rollback_import":
        batch_id = args['batch_id']

        # Verify batch exists and belongs to user
        batch_check = supabase.table('import_batch').select(
            'batch_id, status, import_type, new_people'
        ).eq('batch_id', batch_id).eq('owner_id', user_id).single().execute()

        if not batch_check.data:
            return f"Batch {batch_id} not found or doesn't belong to you."

        if batch_check.data['status'] == 'rolled_back':
            return f"Batch {batch_id} was already rolled back."

        # Soft delete all people from this batch
        delete_result = supabase.table('person').update({
            'status': 'deleted',
            'updated_at': datetime.utcnow().isoformat()
        }).eq('import_batch_id', batch_id).eq('status', 'active').execute()

        deleted_count = len(delete_result.data) if delete_result.data else 0

        # Mark batch as rolled back
        supabase.table('import_batch').update({
            'status': 'rolled_back',
            'rolled_back_at': datetime.utcnow().isoformat()
        }).eq('batch_id', batch_id).execute()

        return json.dumps({
            'success': True,
            'batch_id': batch_id,
            'import_type': batch_check.data['import_type'],
            'deleted_count': deleted_count,
            'message': f"Rolled back {batch_check.data['import_type']} import. Deleted {deleted_count} people."
        }, ensure_ascii=False)

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


class ChatDirectResult:
    """Result from chat_direct with response and extracted people."""
    def __init__(self, message: str, session_id: str, people: list[dict] = None):
        self.message = message
        self.session_id = session_id
        self.people = people or []  # List of {person_id, name} from find_people results


async def chat_direct(message: str, user_id: str, session_id: Optional[str] = None) -> ChatDirectResult:
    """
    Direct chat function for Telegram bot (no HTTP overhead).

    Returns: ChatDirectResult with message, session_id, and found people
    """
    settings = get_settings()
    supabase = get_supabase_admin()
    client = openai.OpenAI(api_key=settings.openai_api_key)

    # Get or create session
    if session_id:
        # Verify session belongs to user
        session_check = supabase.table('chat_session').select('session_id').eq(
            'session_id', session_id
        ).eq('owner_id', user_id).execute()

        if not session_check.data:
            session_id = None  # Create new session

    if not session_id:
        # Create new session
        session = supabase.table('chat_session').insert({
            'owner_id': user_id,
            'title': message[:50] + ('...' if len(message) > 50 else '')
        }).execute()
        session_id = session.data[0]['session_id']

    # Save user message
    supabase.table('chat_message').insert({
        'session_id': session_id,
        'role': 'user',
        'content': message
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

    max_iterations = 5  # Prevent infinite loops
    found_people = []  # Collect people from find_people results

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

                result = await execute_tool(tool_name, tool_args, user_id)

                # Extract people from find_people results for Mini App buttons
                if tool_name == "find_people":
                    try:
                        print(f"[CHAT_DIRECT] find_people raw result (first 500 chars): {result[:500]}")
                        result_data = json.loads(result)
                        print(f"[CHAT_DIRECT] find_people parsed: type={type(result_data).__name__}, keys={list(result_data.keys()) if isinstance(result_data, dict) else 'N/A'}")

                        # Handle different possible formats
                        if isinstance(result_data, list):
                            # Direct array of people
                            people_list = result_data
                        elif isinstance(result_data, dict):
                            # Dict with 'people' or 'results' key
                            people_list = result_data.get('people') or result_data.get('results') or []
                        else:
                            people_list = []

                        print(f"[CHAT_DIRECT] Extracted {len(people_list)} people for buttons")

                        for p in people_list:
                            if not isinstance(p, dict):
                                print(f"[CHAT_DIRECT] Skipping non-dict person: {type(p)}")
                                continue
                            pid = p.get('person_id')
                            name = p.get('name') or p.get('display_name')
                            if pid and name:
                                found_people.append({
                                    'person_id': pid,
                                    'name': name
                                })

                        print(f"[CHAT_DIRECT] Final found_people count: {len(found_people)}")
                    except (json.JSONDecodeError, TypeError, AttributeError) as e:
                        print(f"[CHAT_DIRECT] ERROR parsing find_people result: {e}, result (first 200 chars): {result[:200] if result else 'None'}")

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

            return ChatDirectResult(final_content, session_id, found_people)

    # If we hit max iterations
    return ChatDirectResult(
        "I apologize, but I'm having trouble completing this request. Please try again.",
        session_id,
        found_people
    )
