from typing import Optional
from datetime import datetime, timedelta
from uuid import UUID

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
            "description": "Search the COMMUNITY network for people matching a query. Searches both user's own contacts AND shared contacts from other users. Results include 'is_own' and 'source' fields.",
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
            "description": "List all people in the COMMUNITY network. Returns two groups: 'own_people' (user's contacts) and 'shared_people' (from other users).",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of people to return per group",
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
            "description": "Add a new note or fact about a person. ONLY works for user's own contacts, not shared ones. If person doesn't exist, creates a new one.",
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
            "description": "Merge two people who are actually the same person. Moves all facts and connections from person_b to person_a.",
            "parameters": {
                "type": "object",
                "properties": {
                    "person_a_name": {
                        "type": "string",
                        "description": "Name of the person to KEEP (canonical)"
                    },
                    "person_b_name": {
                        "type": "string",
                        "description": "Name of the person to MERGE INTO person_a (will be marked as merged)"
                    }
                },
                "required": ["person_a_name", "person_b_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_merge_candidates",
            "description": "Find potential duplicate people in the network who might be the same person. Returns pairs with similarity scores.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of candidates to return",
                        "default": 5
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_person",
            "description": "Delete a person from the network (soft delete). ONLY works for user's own contacts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "person_name": {
                        "type": "string",
                        "description": "Name of the person to delete"
                    }
                },
                "required": ["person_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_person",
            "description": "Edit a person's display name. ONLY works for user's own contacts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "current_name": {
                        "type": "string",
                        "description": "Current name of the person"
                    },
                    "new_name": {
                        "type": "string",
                        "description": "New display name"
                    }
                },
                "required": ["current_name", "new_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "reject_merge",
            "description": "Mark two people as definitely NOT the same person (reject duplicate suggestion).",
            "parameters": {
                "type": "object",
                "properties": {
                    "person_a_name": {
                        "type": "string",
                        "description": "Name of first person"
                    },
                    "person_b_name": {
                        "type": "string",
                        "description": "Name of second person"
                    }
                },
                "required": ["person_a_name", "person_b_name"]
            }
        }
    },
]

SYSTEM_PROMPT = """You are a personal network assistant helping the user manage and query their professional network.

You have access to COMMUNITY DATA - people added by the user AND by other users in the community.
When showing results, indicate whether a person is "Мой контакт" (user's own) or "Shared" (from others).

Your capabilities:
1. Search for people based on skills, expertise, companies, or any criteria (searches ALL community data)
2. Look up detailed information about specific people (from any community member)
3. List people in the network (shows both own and shared)
4. Add new notes about people (ONLY for user's own contacts, not shared ones)
5. Ask proactive questions to help fill gaps in profiles
6. MERGE duplicate people (when two entries are the same person)
7. FIND potential duplicates (suggest_merge_candidates)
8. DELETE people from the network
9. EDIT person names
10. REJECT merge suggestions (mark as different people)

## MERGE & DEDUP COMMANDS
When user says things like:
- "объедини X и Y" / "merge X and Y" → use merge_people
- "X и Y это один человек" / "X and Y are the same person" → use merge_people
- "найди дубликаты" / "find duplicates" → use suggest_merge_candidates
- "X и Y это разные люди" / "X and Y are different" → use reject_merge
- "удали X" / "delete X" → use delete_person
- "переименуй X в Y" / "rename X to Y" → use edit_person

Guidelines:
- Be concise but helpful
- When searching, explain WHY certain people might be relevant
- ALWAYS mention if a person is from shared data vs user's own
- If the user mentions someone new, offer to add them
- For ambiguous names, ask for clarification
- Suggest non-obvious connections when relevant
- Respond in the same language as the user
- User can ONLY modify their own contacts (is_own=true, editable=true)

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


async def execute_tool(tool_name: str, args: dict, user_id: str) -> str:
    """Execute a tool and return the result as a string."""
    settings = get_settings()
    supabase = get_supabase_admin()

    if tool_name == "search_network":
        # Generate embedding for query
        query_embedding = generate_embedding(args["query"])

        # Semantic search across ALL users (community sharing)
        match_result = supabase.rpc(
            'match_assertions_community',
            {
                'query_embedding': query_embedding,
                'match_threshold': 0.25,  # Lowered from 0.3 to catch more variations
                'match_count': 20
            }
        ).execute()

        print(f"[SEARCH] Query: {args['query']}")
        print(f"[SEARCH] Found {len(match_result.data) if match_result.data else 0} matching assertions")
        if match_result.data:
            for i, match in enumerate(match_result.data[:5]):
                print(f"[SEARCH] Match {i+1}: person_id={match['subject_person_id']}, similarity={match['similarity']:.3f}, predicate={match['predicate']}, value={match['object_value'][:50]}")

        if not match_result.data:
            return "No relevant people found for this query."

        # Group by person
        person_facts = {}
        person_ids = set()
        person_owners = {}  # Track owner of each person
        for match in match_result.data:
            pid = match['subject_person_id']
            person_ids.add(pid)
            person_owners[pid] = match.get('owner_id')
            if pid not in person_facts:
                person_facts[pid] = []
            person_facts[pid].append({
                'fact': f"{match['predicate']}: {match['object_value']}",
                'similarity': match['similarity']
            })

        # Get person names and owner info
        people = supabase.table('person').select('person_id, display_name, owner_id').in_(
            'person_id', list(person_ids)
        ).execute()

        name_map = {p['person_id']: p['display_name'] for p in people.data}
        owner_map = {p['person_id']: p['owner_id'] for p in people.data}

        results = []
        for pid, facts in person_facts.items():
            name = name_map.get(pid, 'Unknown')
            avg_sim = sum(f['similarity'] for f in facts) / len(facts)
            fact_list = [f['fact'] for f in facts[:5]]
            owner_id_of_person = owner_map.get(pid)
            is_own = owner_id_of_person == user_id
            results.append({
                'name': name,
                'relevance': round(avg_sim, 2),
                'facts': fact_list,
                'is_own': is_own,
                'source': 'Мой контакт' if is_own else 'Shared'
            })

        results.sort(key=lambda x: x['relevance'], reverse=True)
        return json.dumps(results[:10], ensure_ascii=False, indent=2)

    elif tool_name == "get_person_details":
        search_name = args['person_name']

        # Russian name synonyms (diminutives ↔ full names)
        NAME_SYNONYMS = {
            'вася': ['василий', 'васёк', 'васька'],
            'василий': ['вася', 'васёк', 'васька'],
            'петя': ['пётр', 'петр', 'петька'],
            'пётр': ['петя', 'петька'],
            'петр': ['петя', 'петька'],
            'саша': ['александр', 'александра', 'сашка', 'шура'],
            'александр': ['саша', 'сашка', 'шура'],
            'коля': ['николай', 'колян'],
            'николай': ['коля', 'колян'],
            'миша': ['михаил', 'мишка'],
            'михаил': ['миша', 'мишка'],
            'дима': ['дмитрий', 'димка', 'митя'],
            'дмитрий': ['дима', 'димка', 'митя'],
            'женя': ['евгений', 'евгения'],
            'евгений': ['женя'],
            'лёша': ['алексей', 'лёха', 'леша', 'леха'],
            'алексей': ['лёша', 'лёха', 'леша', 'леха'],
            'серёжа': ['сергей', 'серёга', 'сережа'],
            'сергей': ['серёжа', 'серёга', 'сережа'],
            'андрей': ['андрюша', 'андрюха'],
            'наташа': ['наталья', 'наталия', 'ната'],
            'наталья': ['наташа', 'ната'],
            'маша': ['мария', 'машка'],
            'мария': ['маша', 'машка'],
            'катя': ['екатерина', 'катюша'],
            'екатерина': ['катя', 'катюша'],
            'оля': ['ольга'],
            'ольга': ['оля'],
            'таня': ['татьяна'],
            'татьяна': ['таня'],
        }

        # Get all name variants to search
        search_lower = search_name.lower()
        name_variants = [search_name]
        if search_lower in NAME_SYNONYMS:
            name_variants.extend(NAME_SYNONYMS[search_lower])

        # Strategy 1: Exact substring match on display_name (with synonyms) - across ALL users
        person_result = None
        for name_variant in name_variants:
            person_result = supabase.table('person').select(
                'person_id, display_name, summary, owner_id'
            ).ilike(
                'display_name', f"%{name_variant}%"
            ).eq('status', 'active').execute()
            if person_result.data:
                break

        # Strategy 2: Fuzzy match using pg_trgm - across ALL users
        if not person_result or not person_result.data:
            fuzzy_result = supabase.rpc(
                'find_similar_names_community',
                {
                    'p_name': search_name,
                    'p_threshold': 0.3
                }
            ).execute()

            if fuzzy_result.data:
                person_ids = [r['person_id'] for r in fuzzy_result.data]
                person_result = supabase.table('person').select(
                    'person_id, display_name, summary, owner_id'
                ).in_('person_id', person_ids).eq('status', 'active').execute()

        # Strategy 3: Search in identities (freeform_name variations)
        if not person_result or not person_result.data:
            identity_result = supabase.table('identity').select(
                'person_id'
            ).eq('namespace', 'freeform_name').ilike(
                'value', f"%{search_name}%"
            ).execute()

            if identity_result.data:
                person_ids = list(set(i['person_id'] for i in identity_result.data))
                person_result = supabase.table('person').select(
                    'person_id, display_name, summary, owner_id'
                ).in_('person_id', person_ids).eq('status', 'active').execute()

        if not person_result or not person_result.data:
            return f"Person '{search_name}' not found. Try a different spelling or add them first."

        if len(person_result.data) > 1:
            names = [p['display_name'] for p in person_result.data]
            return f"Multiple people match '{args['person_name']}': {', '.join(names)}. Please be more specific."

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

    elif tool_name == "list_people":
        limit = args.get('limit', 20)

        # Get ALL people (community sharing)
        people = supabase.table('person').select(
            'person_id, display_name, summary, owner_id'
        ).eq('status', 'active').limit(limit * 2).execute()  # Get more to split

        if not people.data:
            return "No people in the network yet. Start by adding notes about people you know."

        # Split into own and shared
        own_people = []
        shared_people = []
        for p in people.data:
            person_info = {
                'name': p['display_name'],
                'summary': p.get('summary', ''),
                'is_own': p['owner_id'] == user_id,
                'source': 'Мой контакт' if p['owner_id'] == user_id else 'Shared'
            }
            if p['owner_id'] == user_id:
                own_people.append(person_info)
            else:
                shared_people.append(person_info)

        result = {
            'own_people': own_people[:limit],
            'shared_people': shared_people[:limit],
            'total_own': len(own_people),
            'total_shared': len(shared_people)
        }
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

        # Find person A (to keep)
        person_a_result = supabase.table('person').select('person_id, display_name').eq(
            'owner_id', user_id
        ).ilike('display_name', f"%{args['person_a_name']}%").eq('status', 'active').execute()

        if not person_a_result.data:
            return f"Person '{args['person_a_name']}' not found in your contacts."
        if len(person_a_result.data) > 1:
            names = [p['display_name'] for p in person_a_result.data]
            return f"Multiple people match '{args['person_a_name']}': {', '.join(names)}. Please be more specific."

        # Find person B (to merge)
        person_b_result = supabase.table('person').select('person_id, display_name').eq(
            'owner_id', user_id
        ).ilike('display_name', f"%{args['person_b_name']}%").eq('status', 'active').execute()

        if not person_b_result.data:
            return f"Person '{args['person_b_name']}' not found in your contacts."
        if len(person_b_result.data) > 1:
            names = [p['display_name'] for p in person_b_result.data]
            return f"Multiple people match '{args['person_b_name']}': {', '.join(names)}. Please be more specific."

        person_a = person_a_result.data[0]
        person_b = person_b_result.data[0]

        if person_a['person_id'] == person_b['person_id']:
            return "These are the same person already."

        # Perform merge
        result = await dedup_service.merge_persons(
            UUID(user_id),
            UUID(person_a['person_id']),
            UUID(person_b['person_id'])
        )

        return json.dumps({
            "success": True,
            "kept_person": person_a['display_name'],
            "merged_person": person_b['display_name'],
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

    elif tool_name == "delete_person":
        # Find person
        person_result = supabase.table('person').select('person_id, display_name').eq(
            'owner_id', user_id
        ).ilike('display_name', f"%{args['person_name']}%").eq('status', 'active').execute()

        if not person_result.data:
            return f"Person '{args['person_name']}' not found in your contacts."
        if len(person_result.data) > 1:
            names = [p['display_name'] for p in person_result.data]
            return f"Multiple people match '{args['person_name']}': {', '.join(names)}. Please be more specific."

        person = person_result.data[0]

        # Soft delete
        supabase.table('person').update({
            'status': 'deleted',
            'updated_at': datetime.utcnow().isoformat()
        }).eq('person_id', person['person_id']).execute()

        return f"Deleted '{person['display_name']}' from your network."

    elif tool_name == "edit_person":
        # Find person
        person_result = supabase.table('person').select('person_id, display_name').eq(
            'owner_id', user_id
        ).ilike('display_name', f"%{args['current_name']}%").eq('status', 'active').execute()

        if not person_result.data:
            return f"Person '{args['current_name']}' not found in your contacts."
        if len(person_result.data) > 1:
            names = [p['display_name'] for p in person_result.data]
            return f"Multiple people match '{args['current_name']}': {', '.join(names)}. Please be more specific."

        person = person_result.data[0]
        old_name = person['display_name']

        # Update name
        supabase.table('person').update({
            'display_name': args['new_name'],
            'updated_at': datetime.utcnow().isoformat()
        }).eq('person_id', person['person_id']).execute()

        return f"Renamed '{old_name}' to '{args['new_name']}'."

    elif tool_name == "reject_merge":
        dedup_service = get_dedup_service()

        # Find person A
        person_a_result = supabase.table('person').select('person_id, display_name').eq(
            'owner_id', user_id
        ).ilike('display_name', f"%{args['person_a_name']}%").eq('status', 'active').execute()

        if not person_a_result.data:
            return f"Person '{args['person_a_name']}' not found."
        if len(person_a_result.data) > 1:
            names = [p['display_name'] for p in person_a_result.data]
            return f"Multiple people match '{args['person_a_name']}': {', '.join(names)}. Please be more specific."

        # Find person B
        person_b_result = supabase.table('person').select('person_id, display_name').eq(
            'owner_id', user_id
        ).ilike('display_name', f"%{args['person_b_name']}%").eq('status', 'active').execute()

        if not person_b_result.data:
            return f"Person '{args['person_b_name']}' not found."
        if len(person_b_result.data) > 1:
            names = [p['display_name'] for p in person_b_result.data]
            return f"Multiple people match '{args['person_b_name']}': {', '.join(names)}. Please be more specific."

        person_a = person_a_result.data[0]
        person_b = person_b_result.data[0]

        await dedup_service.reject_duplicate(
            UUID(user_id),
            UUID(person_a['person_id']),
            UUID(person_b['person_id'])
        )

        return f"Marked '{person_a['display_name']}' and '{person_b['display_name']}' as different people."

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


async def chat_direct(message: str, user_id: str, session_id: Optional[str] = None) -> tuple[str, str]:
    """
    Direct chat function for Telegram bot (no HTTP overhead).

    Returns: (response_message, session_id)
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

            return (final_content, session_id)

    # If we hit max iterations
    return ("I apologize, but I'm having trouble completing this request. Please try again.", session_id)
