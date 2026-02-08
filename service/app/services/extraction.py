import json
from openai import OpenAI
from app.config import get_settings
from app.agents.prompts import EXTRACTION_SYSTEM_PROMPT, EXTRACTION_OUTPUT_SCHEMA
from app.agents.schemas import ExtractionResult


def extract_from_text(text: str) -> ExtractionResult:
    """
    Extract people, assertions, and edges from text using GPT-4o.

    Args:
        text: Transcript or note text

    Returns:
        ExtractionResult with people, assertions, edges
    """
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": f"Extract information from this note:\n\n{text}"}
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "extraction_result",
                "strict": True,
                "schema": EXTRACTION_OUTPUT_SCHEMA
            }
        },
        temperature=0.1  # Low temperature for consistent extraction
    )

    result_json = response.choices[0].message.content
    result_dict = json.loads(result_json)

    return ExtractionResult(**result_dict)


def extract_from_text_simple(text: str) -> ExtractionResult:
    """
    Fallback extraction using regular JSON mode (if strict schema fails).
    """
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT + "\n\nRespond with valid JSON matching the schema."},
            {"role": "user", "content": f"""Extract information from this note and return JSON with this structure:
{{
  "people": [{{ "temp_id": "p1", "name": "...", "name_variations": [], "identifiers": {{}} }}],
  "assertions": [{{ "subject": "p1", "predicate": "works_at", "value": "...", "confidence": 0.8 }}],
  "edges": [{{ "source": "p1", "target": "p2", "type": "knows", "context": "..." }}]
}}

Note:
{text}"""}
        ],
        response_format={"type": "json_object"},
        temperature=0.1
    )

    result_json = response.choices[0].message.content
    result_dict = json.loads(result_json)

    # Handle missing fields
    result_dict.setdefault("people", [])
    result_dict.setdefault("assertions", [])
    result_dict.setdefault("edges", [])

    return ExtractionResult(**result_dict)
