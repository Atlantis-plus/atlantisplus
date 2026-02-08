from openai import OpenAI
from app.config import get_settings


def generate_embedding(text: str) -> list[float]:
    """
    Generate embedding for text using OpenAI text-embedding-3-small.

    Args:
        text: Text to embed

    Returns:
        1536-dimensional embedding vector
    """
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
        dimensions=1536
    )

    return response.data[0].embedding


def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for multiple texts in one API call.

    Args:
        texts: List of texts to embed

    Returns:
        List of 1536-dimensional embedding vectors
    """
    if not texts:
        return []

    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=texts,
        dimensions=1536
    )

    # Sort by index to maintain order
    sorted_data = sorted(response.data, key=lambda x: x.index)
    return [item.embedding for item in sorted_data]


def create_assertion_text(predicate: str, value: str, person_name: str = "") -> str:
    """
    Create searchable text from assertion for embedding.

    Args:
        predicate: Assertion predicate (e.g., "works_at", "can_help_with")
        value: Assertion value
        person_name: Optional person name for context

    Returns:
        Text suitable for embedding
    """
    predicate_templates = {
        "can_help_with": "{name} can help with {value}",
        "works_at": "{name} works at {value}",
        "role_is": "{name} is {value}",
        "strong_at": "{name} is strong at {value}",
        "interested_in": "{name} is interested in {value}",
        "trusted_by": "{name} is trusted by {value}",
        "knows": "{name} knows {value}",
        "intro_path": "{name} intro path: {value}",
        "located_in": "{name} is located in {value}",
        "worked_on": "{name} worked on {value}",
        "speaks_language": "{name} speaks {value}",
        "background": "{name} background: {value}",
        "contact_context": "{name} contact context: {value}",
        "reputation_note": "{name} reputation: {value}",
    }

    template = predicate_templates.get(predicate, "{name}: {value}")
    return template.format(name=person_name or "Person", value=value)
