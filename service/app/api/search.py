from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import openai

from app.config import get_settings
from app.supabase_client import get_supabase_admin
from app.middleware.auth import verify_supabase_token, get_user_id
from app.services.embedding import generate_embedding

router = APIRouter(tags=["search"])


class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query in natural language")


class SearchResultItem(BaseModel):
    person_id: str
    display_name: str
    relevance_score: float
    reasoning: str
    matching_facts: list[str]


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultItem]
    reasoning_summary: str


@router.post("/search", response_model=SearchResponse)
async def search_network(
    request: SearchRequest,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Search the user's network using semantic search and AI reasoning.
    """
    settings = get_settings()
    user_id = get_user_id(token_payload)
    supabase = get_supabase_admin()

    # 1. Generate embedding for the query
    query_embedding = generate_embedding(request.query)

    # 2. Semantic search using pgvector
    # Call the match_assertions function
    match_result = supabase.rpc(
        'match_assertions',
        {
            'query_embedding': query_embedding,
            'match_threshold': 0.3,
            'match_count': 20,
            'p_owner_id': user_id
        }
    ).execute()

    if not match_result.data:
        return SearchResponse(
            query=request.query,
            results=[],
            reasoning_summary="No relevant information found in your network."
        )

    # 3. Group assertions by person
    person_assertions: dict[str, list[dict]] = {}
    person_ids = set()

    for match in match_result.data:
        person_id = match['subject_person_id']
        person_ids.add(person_id)
        if person_id not in person_assertions:
            person_assertions[person_id] = []
        person_assertions[person_id].append({
            'predicate': match['predicate'],
            'value': match['object_value'],
            'similarity': match['similarity']
        })

    # 4. Fetch person details
    people_result = supabase.table('person').select(
        'person_id, display_name, summary'
    ).in_('person_id', list(person_ids)).execute()

    person_map = {p['person_id']: p for p in people_result.data}

    # 5. Build context for GPT-4o reasoning
    context_parts = []
    for person_id, assertions in person_assertions.items():
        person = person_map.get(person_id, {})
        name = person.get('display_name', 'Unknown')
        facts = [f"- {a['predicate']}: {a['value']}" for a in assertions]
        context_parts.append(f"**{name}**:\n" + "\n".join(facts))

    context = "\n\n".join(context_parts)

    # 6. Use GPT-4o for reasoning
    client = openai.OpenAI(api_key=settings.openai_api_key)

    reasoning_prompt = f"""You are a personal network advisor helping find relevant people.

User's question: "{request.query}"

People and facts from their network:
{context}

Based on this information, analyze which people are most relevant to the user's question.
For each relevant person, explain WHY they might be helpful - be specific and reference the facts.
Think about non-obvious connections too.

Respond in JSON format:
{{
  "reasoning_summary": "Brief summary of your analysis (1-2 sentences)",
  "results": [
    {{
      "person_id": "...",
      "display_name": "...",
      "relevance_score": 0.0-1.0,
      "reasoning": "Why this person is relevant (be specific)",
      "matching_facts": ["fact1", "fact2"]
    }}
  ]
}}

Only include people who are actually relevant. Sort by relevance.
Respond in the same language as the user's question.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that analyzes professional networks."},
                {"role": "user", "content": reasoning_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.3
        )

        result_json = response.choices[0].message.content
        import json
        result_data = json.loads(result_json)

        # Map person names back to IDs
        name_to_id = {p['display_name']: p['person_id'] for p in people_result.data}

        results = []
        for r in result_data.get('results', []):
            person_id = r.get('person_id') or name_to_id.get(r.get('display_name'))
            if person_id:
                results.append(SearchResultItem(
                    person_id=person_id,
                    display_name=r.get('display_name', ''),
                    relevance_score=float(r.get('relevance_score', 0.5)),
                    reasoning=r.get('reasoning', ''),
                    matching_facts=r.get('matching_facts', [])
                ))

        return SearchResponse(
            query=request.query,
            results=results,
            reasoning_summary=result_data.get('reasoning_summary', '')
        )

    except Exception as e:
        print(f"[SEARCH] GPT-4o error: {e}")
        # Fallback: return raw matches without reasoning
        results = []
        for person_id, assertions in person_assertions.items():
            person = person_map.get(person_id, {})
            avg_similarity = sum(a['similarity'] for a in assertions) / len(assertions)
            results.append(SearchResultItem(
                person_id=person_id,
                display_name=person.get('display_name', 'Unknown'),
                relevance_score=avg_similarity,
                reasoning=f"Found {len(assertions)} matching facts",
                matching_facts=[a['value'][:50] for a in assertions[:3]]
            ))

        results.sort(key=lambda x: x.relevance_score, reverse=True)

        return SearchResponse(
            query=request.query,
            results=results[:5],
            reasoning_summary="Search completed (AI reasoning unavailable)"
        )
