"""
Message dispatcher - classifies incoming messages.

Phase 1: Placeholder
Phase 2: Full implementation with GPT-4o-mini classifier
"""

import openai
from app.config import get_settings


async def classify_message(text: str, context: dict) -> str:
    """
    Classify message type using GPT-4o-mini.

    Args:
        text: Message text
        context: Dialog context (contains active_chat_session, etc.)

    Returns:
        "note" - fact/note about people (→ extraction pipeline)
        "query" - question for chat agent
        "dialog" - continuation of active dialog
    """

    # If there's an active chat session, this is dialog continuation
    if context.get("chat_session_id"):
        return "dialog"

    # Phase 2: GPT-4o-mini classification
    settings = get_settings()
    client = openai.OpenAI(api_key=settings.openai_api_key)

    prompt = f'''Classify this user message into ONE category:

Message: "{text}"

Categories:
- "note": User is SHARING or ADDING facts about people they know
  Examples: "Вася работает в Google", "Познакомился с Петей", "add a note: Leo is a lawyer", "запомни: Маша из Яндекса"
- "query": User is ASKING a question or SEARCHING their network
  Examples: "Кто работает в Google?", "Найди эксперта", "who can help with X?"

If the message CONTAINS facts about a person (name + info), it's a "note", even if phrased as a command.

Return ONLY one word: "note" or "query"
'''

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=10
    )

    classification = response.choices[0].message.content.strip().lower()

    # Default to query if unclear
    if classification not in ["note", "query"]:
        return "query"

    return classification
