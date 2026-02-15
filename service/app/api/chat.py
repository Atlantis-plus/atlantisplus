from typing import Optional
from datetime import datetime, timedelta
from uuid import UUID
import re
import html

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
import openai
import json

from app.config import get_settings

# Rate limiter for expensive endpoints
limiter = Limiter(key_func=get_remote_address)
from app.supabase_client import get_supabase_admin
from app.middleware.auth import verify_supabase_token, get_user_id
from app.services.embedding import generate_embedding
from app.services.gap_detection import get_gap_detection_service
from app.services.dedup import get_dedup_service
from app.services.claude_agent_v2 import ClaudeAgentV2
from app.services.sql_tool import handle_sql_tool

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
    # =============================================================================
    # LOW-LEVEL EXPLORATION TOOLS (for agent visibility into data)
    # =============================================================================
    {
        "type": "function",
        "function": {
            "name": "explore_company_names",
            "description": """Show all company name variations in the database with people counts.

Use this BEFORE searching for people at a company to see:
- How the company is spelled in different assertions
- Which spelling has more people
- Cyrillic vs Latin variants

Example: explore_company_names(pattern="%yandex%") reveals:
- "Yandex" (26 people)
- "Яндекс" (2 people)
- "Yandex N.V." (1 person)

Then you know to search for ALL variants, not just one.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "SQL ILIKE pattern (e.g., '%yandex%', '%google%'). Case-insensitive."
                    }
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "count_people_by_filter",
            "description": """Quick count of people matching filters. No details, just total count.

Use to verify before searching:
- count_people_by_filter(company_pattern="%Meta%") → 15
- count_people_by_filter(name_pattern="%John%") → 3

Much faster than find_people when you just need counts.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "company_pattern": {
                        "type": "string",
                        "description": "ILIKE pattern for company (works_at predicate)"
                    },
                    "name_pattern": {
                        "type": "string",
                        "description": "ILIKE pattern for person name"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_by_company_exact",
            "description": """Find people by EXACT company ILIKE pattern. Low-level, no semantic search.

Unlike find_people (which uses embeddings), this is literal string matching:
- search_by_company_exact(pattern="Яндекс") → only Cyrillic spelling
- search_by_company_exact(pattern="%yandex%") → only Latin spelling

Use after explore_company_names to search specific variants.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "SQL ILIKE pattern for company name (e.g., 'Google', '%Meta%')"
                    },
                    "predicate": {
                        "type": "string",
                        "description": "Which predicate to search (default: works_at)",
                        "enum": ["works_at", "met_on", "worked_on", "background"],
                        "default": "works_at"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 50)",
                        "default": 50
                    }
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_by_name_fuzzy",
            "description": """Fuzzy name search using trigram similarity. Finds typos and variations.

Examples:
- "Михаил" finds "Michael", "Misha", "Миша" (similar sounds)
- "John" finds "Jon", "Johny", "Johnny"

Returns similarity score (0.0-1.0). Default threshold 0.4.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name to search (any spelling)"
                    },
                    "threshold": {
                        "type": "number",
                        "description": "Min similarity (0.0-1.0, default 0.4). Lower = more results.",
                        "default": 0.4
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "semantic_search_raw",
            "description": """Direct semantic search on assertions. Returns raw embedding matches.

Unlike find_people (which groups by person and adds motivations), this returns:
- Individual assertions that match
- Raw similarity scores
- No LLM post-processing

Use for debugging or when you need to see exactly what the vector search found.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Semantic query (converted to embedding)"
                    },
                    "threshold": {
                        "type": "number",
                        "description": "Min similarity (0.0-1.0, default 0.4)",
                        "default": 0.4
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 20)",
                        "default": 20
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "report_results",
            "description": "MUST be called at the end of every search to report found people to the user. Extract person_id and name from whatever tools you used.",
            "parameters": {
                "type": "object",
                "properties": {
                    "people": {
                        "type": "array",
                        "description": "All people found, deduplicated by person_id",
                        "items": {
                            "type": "object",
                            "properties": {
                                "person_id": {"type": "string"},
                                "name": {"type": "string"}
                            },
                            "required": ["person_id", "name"]
                        }
                    },
                    "summary": {
                        "type": "string",
                        "description": "Brief summary of search results for the user"
                    }
                },
                "required": ["people", "summary"]
            }
        }
    },
]

SYSTEM_PROMPT = """You are a personal network assistant helping the user manage and query their professional network.

## CRITICAL: USE person_id FOR ALL OPERATIONS

Every find_people result includes `person_id`. ALWAYS use person_id (not names) for subsequent operations.

## CRITICAL: OUTPUT FORMATTING FOR TELEGRAM

You MUST use HTML formatting (NOT Markdown!) for Telegram:
- Bold: <b>text</b> (NOT **text**)
- Italic: <i>text</i> (NOT *text*)
- NO LINKS - do not use <a href="..."> tags, they don't work in this context

When showing search results, format EACH person like this:
👤 <b>Person Name</b>

Use a BLANK LINE between people for readability. Do NOT use numbered lists (1. 2. 3.).

Example output for search results:
👤 <b>Charbel Melhem</b>

👤 <b>Alex Turilin</b>

## WORKFLOW

1. **Search**: find_people(query="...") → returns list with person_id and name
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

CRITICAL RULE: After completing any search, you MUST call report_results with ALL people you found.
- Extract person_id and name from the results of whatever tools you used
- Deduplicate by person_id (same person may appear in multiple tool results)
- The summary field should be a brief description for the user
- If you found no people, call report_results with empty people array
"""


async def execute_tool(tool_name: str, args: dict, user_id: str) -> str:
    """Execute a tool and return the result as a string."""
    settings = get_settings()
    supabase = get_supabase_admin()

    if tool_name == "find_people":
        limit = args.get('limit', 20)
        query = args.get('query')
        name_pattern = args.get('name_pattern')
        shared_mode = settings.shared_database_mode
        print(f"[FIND_PEOPLE] query={query}, name_pattern={name_pattern}, limit={limit}, shared_mode={shared_mode}")

        # Hybrid search: name + semantic
        if query:
            person_scores = {}  # person_id -> best_score (1.0 for name match, similarity for semantic)

            # 1. Name search (exact/partial match gets high score)
            name_query = supabase.table('person').select(
                'person_id, display_name, import_source, owner_id'
            ).eq('status', 'active').ilike('display_name', f'%{query}%').limit(50)
            if not shared_mode:
                name_query = name_query.eq('owner_id', user_id)
            name_result = name_query.execute()

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
                import time as _time
                t0 = _time.time()
                query_embedding = generate_embedding(query)
                t1 = _time.time()
                print(f"[FIND_PEOPLE] Embedding generated in {(t1-t0)*1000:.0f}ms")

                match_result = supabase.rpc(
                    'match_assertions_community',
                    {
                        'query_embedding': query_embedding,
                        'match_threshold': 0.4,  # Balanced: less noise, good recall
                        'match_count': 200
                    }
                ).execute()
                t2 = _time.time()
                print(f"[FIND_PEOPLE] pgvector search in {(t2-t1)*1000:.0f}ms, found {len(match_result.data or [])} assertions")

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
            people_query = supabase.table('person').select(
                'person_id, display_name, import_source, owner_id'
            ).in_('person_id', top_person_ids).eq('status', 'active')
            if not shared_mode:
                people_query = people_query.eq('owner_id', user_id)
            people_result = people_query.execute()

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
                is_own = p.get('owner_id') == user_id
                results.append({
                    'person_id': p['person_id'],
                    'name': p['display_name'],
                    'import_source': p.get('import_source') or 'manual',
                    'has_email': p['person_id'] in has_email_ids,
                    'relevance': round(person_scores[pid], 2),
                    'is_own': is_own
                })

            print(f"[FIND_PEOPLE] Hybrid search found {len(results)} people")

            # NOTE: Removed filter_and_motivate_results() call to speed up Tier 1
            # Tier 1 should be fast (2-3 sec), Tier 2 (Dig Deeper) does the smart reasoning

            # Fix: total should reflect only accessible people (after owner filter)
            # person_scores may include people from other owners (via semantic search)
            accessible_count = len(people_by_id)  # Only people that passed owner filter
            return json.dumps({
                'people': results,
                'total': accessible_count,
                'showing': len(results)
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
        list_query = supabase.table('person').select(
            'person_id, display_name, import_source, owner_id'
        ).eq('status', 'active').limit(limit)
        if not shared_mode:
            list_query = list_query.eq('owner_id', user_id)
        result = list_query.execute()

        results = []
        for p in result.data or []:
            results.append({
                'person_id': p['person_id'],
                'name': p['display_name'],
                'import_source': p.get('import_source') or 'manual',
                'is_own': p.get('owner_id') == user_id
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

    # =============================================================================
    # LOW-LEVEL EXPLORATION TOOLS
    # =============================================================================

    elif tool_name == "explore_company_names":
        pattern = args['pattern']
        shared_mode = settings.shared_database_mode

        # Get assertions matching the pattern
        result = supabase.table('assertion').select(
            'object_value, subject_person_id'
        ).in_('predicate', ['works_at', 'met_on']).ilike(
            'object_value', pattern
        ).limit(500).execute()

        # In non-shared mode, filter to only user's people
        allowed_person_ids = None
        if not shared_mode:
            people_result = supabase.table('person').select('person_id').eq(
                'owner_id', user_id
            ).eq('status', 'active').execute()
            allowed_person_ids = set(p['person_id'] for p in people_result.data or [])

        # Aggregate in Python (simpler than raw SQL via Supabase)
        company_counts: dict[str, set] = {}
        for row in result.data or []:
            # Filter by owner if not shared mode
            if allowed_person_ids is not None and row['subject_person_id'] not in allowed_person_ids:
                continue

            company = row['object_value']
            if company not in company_counts:
                company_counts[company] = set()
            company_counts[company].add(row['subject_person_id'])

        # Sort by count descending
        sorted_companies = sorted(
            [(c, len(pids)) for c, pids in company_counts.items()],
            key=lambda x: x[1],
            reverse=True
        )[:30]  # Top 30

        return json.dumps({
            'pattern': pattern,
            'variants': [
                {'company': html.escape(c), 'people_count': cnt}
                for c, cnt in sorted_companies
            ],
            'total_variants': len(company_counts),
            'hint': 'Use search_by_company_exact with specific variant to get people'
        }, ensure_ascii=False, indent=2)

    elif tool_name == "count_people_by_filter":
        company_pattern = args.get('company_pattern')
        name_pattern = args.get('name_pattern')
        shared_mode = settings.shared_database_mode

        # Start with person query
        query = supabase.table('person').select('person_id', count='exact').eq('status', 'active')

        if not shared_mode:
            query = query.eq('owner_id', user_id)

        if name_pattern:
            query = query.ilike('display_name', name_pattern)

        if company_pattern:
            # Get person IDs from assertions first
            assertion_result = supabase.table('assertion').select(
                'subject_person_id'
            ).eq('predicate', 'works_at').ilike('object_value', company_pattern).execute()

            if not assertion_result.data:
                return json.dumps({'count': 0, 'filters': args}, ensure_ascii=False)

            person_ids = list(set(r['subject_person_id'] for r in assertion_result.data))
            query = query.in_('person_id', person_ids)

        result = query.execute()

        return json.dumps({
            'count': result.count if hasattr(result, 'count') and result.count is not None else len(result.data or []),
            'filters': {k: v for k, v in args.items() if v}
        }, ensure_ascii=False)

    elif tool_name == "search_by_company_exact":
        pattern = args['pattern']
        predicate = args.get('predicate', 'works_at')
        limit = args.get('limit', 50)
        shared_mode = settings.shared_database_mode

        # Get assertions matching the pattern
        result = supabase.table('assertion').select(
            'subject_person_id, predicate, object_value, confidence'
        ).eq('predicate', predicate).ilike('object_value', pattern).limit(limit * 2).execute()

        if not result.data:
            return json.dumps({
                'people': [],
                'total': 0,
                'pattern': pattern,
                'predicate': predicate
            }, ensure_ascii=False)

        # Get person details
        person_ids = list(set(r['subject_person_id'] for r in result.data))

        people_query = supabase.table('person').select(
            'person_id, display_name, owner_id'
        ).in_('person_id', person_ids).eq('status', 'active')

        if not shared_mode:
            people_query = people_query.eq('owner_id', user_id)

        people_result = people_query.limit(limit).execute()
        people_by_id = {p['person_id']: p for p in people_result.data or []}

        # Build results (with HTML escaping for safe display)
        people = []
        for row in result.data:
            pid = row['subject_person_id']
            if pid in people_by_id:
                p = people_by_id[pid]
                people.append({
                    'person_id': pid,
                    'name': html.escape(p['display_name']),
                    'company': html.escape(row['object_value']),
                    'predicate': row['predicate'],
                    'is_own': p.get('owner_id') == user_id
                })

        # Dedupe by person_id
        seen = set()
        unique_people = []
        for p in people:
            if p['person_id'] not in seen:
                seen.add(p['person_id'])
                unique_people.append(p)

        return json.dumps({
            'people': unique_people[:limit],
            'total': len(unique_people),
            'pattern': pattern,
            'predicate': predicate
        }, ensure_ascii=False, indent=2)

    elif tool_name == "search_by_name_fuzzy":
        name = args['name']
        threshold = args.get('threshold', 0.4)
        shared_mode = settings.shared_database_mode

        if shared_mode:
            # Use community version
            result = supabase.rpc('find_similar_names_community', {
                'p_name': name,
                'p_threshold': threshold
            }).execute()
        else:
            result = supabase.rpc('find_similar_names', {
                'p_owner_id': user_id,
                'p_name': name,
                'p_threshold': threshold
            }).execute()

        people = [
            {
                'person_id': r['person_id'],
                'name': html.escape(r['display_name']),
                'similarity': round(r['similarity'], 3)
            }
            for r in result.data or []
        ]

        return json.dumps({
            'people': people,
            'total': len(people),
            'search_name': name,
            'threshold': threshold
        }, ensure_ascii=False, indent=2)

    elif tool_name == "semantic_search_raw":
        query = args['query']
        threshold = args.get('threshold', 0.4)
        limit = args.get('limit', 20)
        shared_mode = settings.shared_database_mode

        # Generate embedding
        query_embedding = generate_embedding(query)

        # Call match_assertions RPC
        if shared_mode:
            result = supabase.rpc('match_assertions_community', {
                'query_embedding': query_embedding,
                'match_threshold': threshold,
                'match_count': limit
            }).execute()
        else:
            result = supabase.rpc('match_assertions', {
                'query_embedding': query_embedding,
                'match_threshold': threshold,
                'match_count': limit,
                'p_owner_id': user_id
            }).execute()

        # Get person names
        person_ids = list(set(r['subject_person_id'] for r in result.data or []))
        if person_ids:
            people_result = supabase.table('person').select(
                'person_id, display_name'
            ).in_('person_id', person_ids).execute()
            name_by_id = {p['person_id']: p['display_name'] for p in people_result.data or []}
        else:
            name_by_id = {}

        assertions = [
            {
                'person_id': r['subject_person_id'],
                'person_name': html.escape(name_by_id.get(r['subject_person_id'], 'Unknown')),
                'predicate': r['predicate'],
                'value': html.escape(r['object_value'] or ''),
                'similarity': round(r['similarity'], 3)
            }
            for r in result.data or []
        ]

        return json.dumps({
            'assertions': assertions,
            'total': len(assertions),
            'query': query,
            'threshold': threshold
        }, ensure_ascii=False, indent=2)

    elif tool_name == "report_results":
        return json.dumps({"status": "reported", "count": len(args.get("people", []))})

    elif tool_name == "execute_sql":
        # SQL tool for agent v2
        return await handle_sql_tool(args, user_id)

    return f"Unknown tool: {tool_name}"


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("20/minute")  # Rate limit: 20 requests per minute per IP
async def chat(
    request: Request,  # Required for rate limiter
    chat_request: ChatRequest,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Chat with the network agent. Maintains conversation history and can use tools.

    Rate limited to 20 requests/minute to prevent API cost abuse.
    """
    settings = get_settings()
    user_id = get_user_id(token_payload)
    supabase = get_supabase_admin()
    client = openai.OpenAI(api_key=settings.openai_api_key)

    # Get or create session
    if chat_request.session_id:
        # Verify session belongs to user
        session_check = supabase.table('chat_session').select('session_id').eq(
            'session_id', chat_request.session_id
        ).eq('owner_id', user_id).execute()

        if not session_check.data:
            raise HTTPException(status_code=404, detail="Session not found")

        session_id = chat_request.session_id
    else:
        # Create new session
        session = supabase.table('chat_session').insert({
            'owner_id': user_id,
            'title': chat_request.message[:50] + ('...' if len(chat_request.message) > 50 else '')
        }).execute()
        session_id = session.data[0]['session_id']

    # Save user message
    supabase.table('chat_message').insert({
        'session_id': session_id,
        'role': 'user',
        'content': chat_request.message
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
    """
    Result from chat_direct with response and extracted people.

    PROGRESSIVE ENHANCEMENT ARCHITECTURE:
    =====================================
    The search system uses a two-tier approach for optimal UX:

    Tier 1 (Fast): OpenAI single-shot search (~2-3 sec)
    - Uses find_people tool with semantic search + filters
    - Returns results immediately
    - Sets can_dig_deeper=True if results found

    Tier 2 (Deep): Claude agent multi-shot search (~10-15 sec)
    - Triggered by "Dig deeper" button
    - Gets Tier 1 results as context
    - Uses low-level tools (explore_company_names, etc.)
    - Finds non-obvious connections and name variations

    WHY THIS ARCHITECTURE:
    - Users get immediate feedback (Tier 1)
    - Agent spends tokens only when needed (Tier 2)
    - Agent is MORE effective with initial context:
      "Initial search found X at Yandex. Let me check Яндекс variants..."
    - Natural UX: show results → option to dig deeper

    The original_query is preserved for Tier 2 to re-run Tier 1 search
    (simpler than caching results, and ensures fresh data).
    """
    def __init__(
        self,
        message: str,
        session_id: str,
        people: list[dict] = None,
        can_dig_deeper: bool = False,
        original_query: str = ""
    ):
        self.message = message
        self.session_id = session_id
        self.people = people or []  # List of {person_id, name} from find_people results
        self.can_dig_deeper = can_dig_deeper  # True if Claude agent could find more
        self.original_query = original_query  # Preserved for "dig deeper" callback


async def chat_direct(message: str, user_id: str, session_id: Optional[str] = None) -> ChatDirectResult:
    """
    TIER 1: Fast, simple search.

    Just calls find_people once, returns results.
    No agentic loop, no multiple tools — that's what Tier 2 (Claude Agent) is for.
    """
    settings = get_settings()
    supabase = get_supabase_admin()
    client = openai.OpenAI(api_key=settings.openai_api_key)

    print(f"[TIER1] Starting fast search for: {message[:50]}...")

    # Get or create session (for history/context)
    if session_id:
        session_check = supabase.table('chat_session').select('session_id').eq(
            'session_id', session_id
        ).eq('owner_id', user_id).execute()
        if not session_check.data:
            session_id = None

    if not session_id:
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

    # === TIER 1: Single call to find_people ===
    search_result = await execute_tool("find_people", {"query": message, "limit": 20}, user_id)

    # Parse results
    found_people = []
    try:
        result_data = json.loads(search_result)
        people_list = result_data.get('people', [])
        for p in people_list:
            if isinstance(p, dict):
                pid = p.get('person_id')
                name = p.get('name')
                motivation = p.get('motivation', '')
                if pid and name:
                    found_people.append({
                        'person_id': pid,
                        'name': name,
                        'motivation': motivation
                    })
        print(f"[TIER1] find_people returned {len(found_people)} people")
    except json.JSONDecodeError as e:
        print(f"[TIER1] ERROR parsing find_people result: {e}")

    # Generate simple response text
    if found_people:
        # Format response with people and their motivations
        response_lines = [f"Found {len(found_people)} people:\n"]
        for p in found_people[:10]:  # Show first 10 in text
            motivation = p.get('motivation', '')
            if motivation:
                response_lines.append(f"👤 **{p['name']}**\n_{motivation}_\n")
            else:
                response_lines.append(f"👤 **{p['name']}**\n")

        if len(found_people) > 10:
            response_lines.append(f"\n...and {len(found_people) - 10} more.")

        response_text = "\n".join(response_lines)
    else:
        response_text = "I couldn't find anyone matching your query. Try 'Dig deeper' for a more thorough search, or rephrase your query."

    # Save assistant response
    supabase.table('chat_message').insert({
        'session_id': session_id,
        'role': 'assistant',
        'content': response_text
    }).execute()

    print(f"[TIER1] Complete in single call, {len(found_people)} people found")

    return ChatDirectResult(
        response_text,
        session_id,
        found_people,
        can_dig_deeper=True,  # Always offer dig deeper, even if Tier 1 found nothing
        original_query=message
    )


# =============================================================================
# CLAUDE AGENT ENDPOINT (experimental)
# =============================================================================

CLAUDE_SYSTEM_PROMPT = """You are a personal network assistant helping the user find people in their professional network.

## YOUR TOOLS

You have multiple tools at different levels:
- **find_people** — semantic search (good for concepts like "AI experts")
- **explore_company_names** — see how company names are actually stored
- **search_by_company_exact** — literal pattern match
- **search_by_name_fuzzy** — fuzzy name matching
- **semantic_search_raw** — raw embedding results
- **count_people_by_filter** — quick counts
- **get_person_details** — full profile

Use whichever tools you need. Explore the data. Don't settle for incomplete results.

## KEY INSIGHT

Data in the database has variations. "Yandex" and "Яндекс" are stored separately.
If results seem incomplete, investigate why. You have the tools to see what's there.

## OUTPUT

Use HTML for Telegram: <b>bold</b>, <i>italic</i>
Format: 👤 <b>Name</b> + reason why relevant
Respond in the user's language.

CRITICAL RULE: After completing any search, you MUST call report_results with ALL people you found.
- Extract person_id and name from the results of whatever tools you used
- Deduplicate by person_id (same person may appear in multiple tool results)
- The summary field should be a brief description for the user
- If you found no people, call report_results with empty people array
"""


async def chat_dig_deeper(
    original_query: str,
    user_id: str
) -> ChatDirectResult:
    """
    TIER 2: Deep search with Claude agent.

    PROGRESSIVE ENHANCEMENT - HOW IT WORKS:
    ========================================
    This function is called when user clicks "Dig deeper" button after Tier 1 results.

    The flow:
    1. User sends query: "кто работает в Яндексе?"
    2. Tier 1 (chat_direct) returns 10 people in ~3 sec, shows "Dig deeper" button
    3. User clicks button → this function is called
    4. We re-run Tier 1 search to get fresh results (simpler than caching)
    5. Claude agent receives: original query + what Tier 1 found
    6. Agent uses low-level tools to find what Tier 1 MISSED:
       - explore_company_names → discovers "Яндекс" vs "Yandex" variations
       - search_by_company_exact → searches each variation
       - semantic_search_raw → finds related people by context

    WHY RE-RUN TIER 1 INSTEAD OF CACHING:
    - Simpler implementation (no Redis/memory cache needed)
    - Ensures fresh data (DB could have changed)
    - Tier 1 is fast anyway (~2-3 sec)
    - Callback_data has 64 byte limit, can't store results there

    AGENT INSTRUCTION:
    The agent is told what was already found, so it can focus on:
    - Name/company spelling variations
    - Non-obvious connections (VCs who know target company)
    - Different predicates (met_on, knows, worked_on)

    Args:
        original_query: The user's original search query
        user_id: Supabase user ID

    Returns:
        ChatDirectResult with agent's deeper findings
    """
    settings = get_settings()

    if not settings.anthropic_api_key:
        return ChatDirectResult(
            "Claude agent not configured. Please contact support.",
            "",
            [],
            can_dig_deeper=False,
            original_query=original_query
        )

    # Step 1: Re-run Tier 1 search to get initial results
    # This is simpler than caching and ensures fresh data
    print(f"[DIG_DEEPER] Re-running Tier 1 search for: {original_query[:50]}")

    tier1_result = await chat_direct(original_query, user_id, session_id=None)
    initial_people = tier1_result.people
    initial_count = len(initial_people)

    print(f"[DIG_DEEPER] Tier 1 found {initial_count} people")

    # Step 2: Build enhanced prompt for Claude agent
    # Tell it what was found and ask to find MORE
    if initial_people:
        people_summary = "\n".join([
            f"- {p.get('name', 'Unknown')}"
            for p in initial_people[:10]  # Show first 10
        ])
        if initial_count > 10:
            people_summary += f"\n... and {initial_count - 10} more"

        enhanced_prompt = f"""User's question: {original_query}

INITIAL SEARCH already found {initial_count} people:
{people_summary}

YOUR TASK: Find people that the initial search MISSED.

The initial search uses simple semantic matching. You have access to low-level tools
that can find more:

1. Use explore_company_names to discover spelling variations
   (e.g., "Yandex" vs "Яндекс" - different people under each)

2. Use search_by_company_exact with EACH variation found

3. Use semantic_search_raw with different phrasings

4. Consider non-obvious connections:
   - VCs who invested in the target company
   - People who "met_on" events related to the company
   - People with "contact_context" mentioning the company

Focus on finding NEW people not in the initial list.
If you find significantly more, explain what the initial search missed."""
    else:
        # No initial results - agent has free reign
        enhanced_prompt = f"""User's question: {original_query}

Initial search found NO results. This might mean:
1. Company/person names are spelled differently in the database
2. The search terms don't match how information is stored
3. The connection is indirect

Use SQL to investigate:
1. Search with object_value_normalized for company variations
2. Try different name spellings with ILIKE
3. Look at related predicates (met_on, knows, contact_context)

Be thorough - the user is counting on you to find what simple search couldn't."""

    # Step 3: Run Claude agent v2 with SQL tool
    print(f"[DIG_DEEPER] Starting Claude agent v2 with SQL tool")

    agent = ClaudeAgentV2(
        user_id=user_id,
        execute_tool_fn=execute_tool,
        model="claude-sonnet-4-20250514"
    )

    result = await agent.run(enhanced_prompt)

    print(f"[DIG_DEEPER] Agent v2 finished: {result.iterations} iterations, {len(result.people)} people")

    return ChatDirectResult(
        result.message,
        "",
        result.people,  # v2 uses .people, not .found_people
        can_dig_deeper=False,  # No further digging after Tier 2
        original_query=original_query
    )
