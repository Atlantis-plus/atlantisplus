"""
Self-Introduction Extraction Prompt.

Used when community members describe themselves.
Different from regular extraction - focused on self-reported info.
"""

SELF_INTRO_SYSTEM_PROMPT = """You are extracting structured information from a person's self-introduction.
They are describing themselves to join a professional community.

Return the result as a JSON object.

Extract these categories:

1. NAME - how they introduce themselves (full name as stated)
2. CURRENT_ROLE - job title, company, what they do professionally
3. CAN_HELP_WITH - skills, expertise, what they can help others with (as a list)
4. LOOKING_FOR - what they're seeking: collaborations, co-founders, advice, opportunities (as a list)
5. BACKGROUND - relevant past experience, education (brief)
6. LOCATION - city/country if mentioned
7. CONTACT - preferred contact method if mentioned (telegram, email, etc.)
8. INTERESTS - hobbies, personal interests if mentioned
9. IS_FIRST_PERSON - boolean: true if the person is talking ABOUT THEMSELVES, false if talking about someone else

CRITICAL RULES:
- Use the SAME LANGUAGE as the input (Russian/English/etc.)
- Don't hallucinate — only extract what's EXPLICITLY mentioned
- If something isn't mentioned, OMIT it entirely (don't set empty string)
- Multiple items for CAN_HELP_WITH and LOOKING_FOR are OK and encouraged
- Keep values concise but complete
- Preserve the person's original phrasing where possible
- IS_FIRST_PERSON detection: "Меня зовут...", "I am...", "Я работаю..." = true; "Это Вася, он...", "My friend John..." = false

EXAMPLES:

Input: "Привет! Меня зовут Вася Пупкин, я product manager в финтехе. Могу помочь с growth и продуктовой стратегией. Ищу кофаундера для AI-проекта."

Output:
{
  "name": "Вася Пупкин",
  "current_role": "Product manager в финтехе",
  "can_help_with": ["growth", "продуктовая стратегия"],
  "looking_for": ["кофаундер для AI-проекта"]
}

Input: "Hi! I'm John, CTO at a seed-stage startup in SF. Previously at Google and Meta. Can help with system design, hiring engineers, and fundraising. Looking for advisors in AI/ML space."

Output:
{
  "name": "John",
  "current_role": "CTO at a seed-stage startup",
  "background": "Previously at Google and Meta",
  "location": "SF",
  "can_help_with": ["system design", "hiring engineers", "fundraising"],
  "looking_for": ["advisors in AI/ML space"]
}"""

SELF_INTRO_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "How the person introduces themselves"
        },
        "current_role": {
            "type": "string",
            "description": "Current job title and company/industry"
        },
        "can_help_with": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Skills and areas where they can help others"
        },
        "looking_for": {
            "type": "array",
            "items": {"type": "string"},
            "description": "What they're seeking from the community"
        },
        "background": {
            "type": "string",
            "description": "Past experience, education"
        },
        "location": {
            "type": "string",
            "description": "City/country"
        },
        "contact_preference": {
            "type": "string",
            "description": "Preferred contact method"
        },
        "interests": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Hobbies and personal interests"
        },
        "is_first_person": {
            "type": "boolean",
            "description": "True if speaker is talking about themselves, false if about someone else"
        }
    },
    "required": ["name", "is_first_person"]
}

# Mapping of extraction fields to assertion predicates
SELF_INTRO_PREDICATE_MAP = {
    "current_role": "self_role",
    "can_help_with": "self_offer",
    "looking_for": "self_seek",
    "background": "background",
    "location": "located_in",
    "contact_preference": "contact_preference",
    "interests": "interested_in"
}
