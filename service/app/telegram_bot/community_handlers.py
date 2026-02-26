from __future__ import annotations

"""
Community-specific Telegram bot handlers.

Handles:
- Join flow via deep links (join_XXX)
- /newcommunity command for creating communities
- /profile, /edit, /delete commands for community members
"""

import json
from telegram import Update
from telegram.ext import ContextTypes

from .auth import get_or_create_user
from .telegram_api import send_message, send_chat_action, send_message_with_buttons
from .logging_config import bot_logger as logger

from app.supabase_client import get_supabase_admin
from app.services.user_type import (
    UserType, get_user_type_by_telegram_id, get_community_by_invite_code,
    can_create_community
)
from app.services.transcription import transcribe_from_storage
from app.services.embedding import generate_embeddings_batch, create_assertion_text
from app.agents.self_intro_prompt import (
    SELF_INTRO_SYSTEM_PROMPT,
    SELF_INTRO_PREDICATE_MAP
)
from app.config import get_settings


# ============================================
# Persistent Join State (DB-backed)
# ============================================

def get_pending_join(telegram_id: int) -> dict | None:
    """Get pending join state from DB. Returns None if not found or expired."""
    supabase = get_supabase_admin()

    # Cleanup expired entries first (older than 1 hour)
    try:
        supabase.rpc("cleanup_expired_pending_joins").execute()
    except Exception:
        pass  # Non-critical

    result = supabase.table("pending_join").select(
        "telegram_id, community_id, state, extraction, raw_text, existing_person_id, is_edit, created_at"
    ).eq("telegram_id", telegram_id).execute()

    if not result.data:
        return None

    row = result.data[0]

    # Also fetch community info
    community = supabase.table("community").select(
        "community_id, name, owner_id"
    ).eq("community_id", row["community_id"]).single().execute()

    if not community.data:
        # Community deleted, cleanup
        delete_pending_join(telegram_id)
        return None

    return {
        "state": row["state"],
        "community_id": row["community_id"],
        "community_name": community.data["name"],
        "owner_id": community.data["owner_id"],
        "extraction": row.get("extraction"),
        "raw_text": row.get("raw_text"),
        "existing_person_id": row.get("existing_person_id"),
        "is_edit": row.get("is_edit", False),
    }


def set_pending_join(telegram_id: int, community_id: str, state: str = "awaiting_intro",
                     extraction: dict = None, raw_text: str = None,
                     existing_person_id: str = None, is_edit: bool = False) -> None:
    """Create or update pending join state in DB."""
    supabase = get_supabase_admin()

    data = {
        "telegram_id": telegram_id,
        "community_id": community_id,
        "state": state,
        "is_edit": is_edit,
    }
    if extraction is not None:
        data["extraction"] = extraction
    if raw_text is not None:
        data["raw_text"] = raw_text
    if existing_person_id is not None:
        data["existing_person_id"] = existing_person_id

    # Upsert
    supabase.table("pending_join").upsert(data, on_conflict="telegram_id").execute()


def update_pending_join(telegram_id: int, **kwargs) -> None:
    """Update specific fields of pending join state."""
    supabase = get_supabase_admin()
    supabase.table("pending_join").update(kwargs).eq("telegram_id", telegram_id).execute()


def delete_pending_join(telegram_id: int) -> None:
    """Delete pending join state from DB."""
    supabase = get_supabase_admin()
    supabase.table("pending_join").delete().eq("telegram_id", telegram_id).execute()


# In-memory cache for /newcommunity flow (short-lived, OK to lose on redeploy)
PENDING_COMMUNITY_CREATION: dict[int, dict] = {}


def extract_self_intro(text: str) -> dict:
    """Extract structured data from self-introduction using GPT-4o."""
    import openai
    settings = get_settings()
    client = openai.OpenAI(api_key=settings.openai_api_key)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SELF_INTRO_SYSTEM_PROMPT},
            {"role": "user", "content": f"Extract information from this self-introduction:\n\n{text}"}
        ],
        response_format={"type": "json_object"},
        temperature=0.1
    )

    result_json = response.choices[0].message.content
    return json.loads(result_json)


async def handle_join_deep_link(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    invite_code: str
) -> bool:
    """
    Handle join_XXX deep link for community onboarding.

    Flow:
    1. Parse invite_code, validate community exists
    2. Check if user already has profile in this community
    3. Show welcome message with community name
    4. Ask for self-introduction (voice or text)

    Returns True if handled, False if error.
    """
    user = update.effective_user
    chat_id = update.effective_chat.id

    logger.info(f"Join deep link from telegram_id={user.id}, invite_code={invite_code}")

    # 1. Get community by invite code
    community = get_community_by_invite_code(invite_code)
    if not community:
        await update.message.reply_text(
            "❌ This invite link is invalid or expired.\n"
            "Please ask for a new link from the community owner."
        )
        return False

    supabase = get_supabase_admin()

    # 2. Check if user already has profile in this community
    existing = supabase.table("person").select(
        "person_id, display_name"
    ).eq("telegram_id", user.id).eq("community_id", community["community_id"]).eq(
        "status", "active"
    ).execute()

    if existing.data:
        # Already a member
        person = existing.data[0]
        await update.message.reply_text(
            f"👋 Welcome back to <b>{community['name']}</b>!\n\n"
            f"You already have a profile: <b>{person['display_name']}</b>\n\n"
            "Use /profile to view or edit your profile.",
            parse_mode="HTML"
        )
        return True

    # 3. Start join conversation (persistent in DB)
    set_pending_join(
        telegram_id=user.id,
        community_id=community["community_id"],
        state="awaiting_intro"
    )

    await update.message.reply_text(
        f"👋 Welcome to <b>{community['name']}</b>!\n\n"
        f"{community.get('description') or 'Join our community!'}\n\n"
        "<b>Tell us about yourself</b> — this will help other members find you.\n\n"
        "📝 Write a short intro or send a 🎤 voice message:\n"
        "• Your name and what you do\n"
        "• What you can help with\n"
        "• What you're looking for",
        parse_mode="HTML"
    )

    return True


async def handle_join_conversation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str
) -> bool:
    """
    Handle text message in join conversation flow.

    Returns True if in join conversation, False otherwise.
    """
    user = update.effective_user
    chat_id = update.effective_chat.id

    # Check if user is in join conversation (from DB)
    conversation = get_pending_join(user.id)
    if not conversation:
        return False

    if conversation["state"] != "awaiting_intro":
        return False

    logger.info(f"Processing join intro from telegram_id={user.id}, community={conversation['community_name']}, text_len={len(text)}")

    await send_chat_action(chat_id, "typing")

    await send_message(
        chat_id,
        "🎯 Processing your introduction..."
    )

    try:
        # Extract structured data
        extraction = extract_self_intro(text)

        # Check if talking about themselves (Phase 3: first-person detection)
        is_first_person = extraction.get("is_first_person", True)
        if not is_first_person:
            # User might be sending a note about someone else in join mode
            update_pending_join(
                user.id,
                state="awaiting_first_person_clarification",
                extraction=extraction,
                raw_text=text
            )
            await send_message_with_buttons(
                chat_id,
                "🤔 This looks like a note about <b>someone else</b>, not about yourself.\n\n"
                "In join mode, we need YOUR introduction.\n"
                "Is this actually about you?",
                buttons=[
                    [
                        {"text": "👤 It's about me", "callback_data": f"join_is_me:{user.id}"},
                        {"text": "📝 Save as note", "callback_data": f"join_is_note:{user.id}"}
                    ]
                ],
                parse_mode="HTML"
            )
            return True

        # Store extraction for confirmation (persist to DB)
        # In edit mode, merge with previous extraction to preserve unchanged fields
        if conversation.get("is_edit"):
            previous_extraction = conversation.get("extraction", {})
            # Merge: new values override, but empty lists/None don't replace existing
            merged_extraction = {**previous_extraction}
            for key, value in extraction.items():
                # Only override if new value is meaningful
                if value and (not isinstance(value, list) or len(value) > 0):
                    merged_extraction[key] = value
            extraction = merged_extraction

        update_pending_join(
            user.id,
            state="awaiting_confirmation",
            extraction=extraction,
            raw_text=text
        )

        # Format preview
        name = extraction.get("name", user.first_name)
        role = extraction.get("current_role", "")
        can_help = extraction.get("can_help_with", [])
        looking_for = extraction.get("looking_for", [])

        preview = f"👤 <b>{name}</b>\n"
        if role:
            preview += f"💼 {role}\n"
        if can_help:
            preview += f"🎯 Can help with: {', '.join(can_help)}\n"
        if looking_for:
            preview += f"🔍 Looking for: {', '.join(looking_for)}\n"

        await send_message_with_buttons(
            chat_id,
            f"✅ Here's what I understood:\n\n{preview}\n"
            "Is this correct?",
            buttons=[
                [
                    {"text": "✅ Confirm", "callback_data": f"join_confirm:{user.id}"},
                    {"text": "✏️ Edit", "callback_data": f"join_edit:{user.id}"}
                ]
            ],
            parse_mode="HTML"
        )

        return True

    except Exception as e:
        logger.error(f"Error processing join intro: {e}", exc_info=True)
        await send_message(
            chat_id,
            "❌ Error processing your introduction. Please try again."
        )
        # Keep in awaiting_intro state
        return True


async def handle_join_voice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> bool:
    """
    Handle voice message in join conversation flow.

    Returns True if in join conversation, False otherwise.
    """
    user = update.effective_user
    chat_id = update.effective_chat.id
    voice = update.message.voice

    # Check if user is in join conversation (from DB)
    conversation = get_pending_join(user.id)
    if not conversation:
        return False

    if conversation["state"] != "awaiting_intro":
        return False

    logger.info(f"Processing join voice from telegram_id={user.id}, community={conversation['community_name']}, duration={voice.duration}s")

    await send_message(
        chat_id,
        "🎤 Processing your voice message..."
    )

    try:
        # Download voice
        file = await context.bot.get_file(voice.file_id)
        voice_bytes = await file.download_as_bytearray()

        # Upload to storage temporarily
        supabase = get_supabase_admin()
        import time
        storage_path = f"join_temp/{user.id}/voice_{int(time.time())}.ogg"

        supabase.storage.from_("voice-notes").upload(
            storage_path,
            bytes(voice_bytes),
            file_options={"content-type": "audio/ogg"}
        )

        # Transcribe
        transcript = await transcribe_from_storage(storage_path)
        logger.info(f"Transcribed join voice: {transcript[:100]}")

        # Clean up temp file
        try:
            supabase.storage.from_("voice-notes").remove([storage_path])
        except Exception:
            pass

        # Process as text
        return await handle_join_conversation(update, context, transcript)

    except Exception as e:
        logger.error(f"Error processing join voice: {e}", exc_info=True)
        await send_message(
            chat_id,
            "❌ Error processing voice message. Please try again or send as text."
        )
        return True


async def handle_join_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    callback_data: str
) -> bool:
    """
    Handle join confirmation/edit callbacks.

    Returns True if handled, False otherwise.
    """
    query = update.callback_query
    user = update.effective_user
    chat_id = query.message.chat_id

    # Parse callback
    if not callback_data.startswith("join_"):
        return False

    action = callback_data.split(":")[0]  # join_confirm, join_edit, join_is_me, join_is_note
    target_user_id = int(callback_data.split(":")[1]) if ":" in callback_data else 0

    # Verify it's the right user
    if target_user_id != user.id:
        await query.answer("This is not your conversation", show_alert=True)
        return True

    conversation = get_pending_join(user.id)
    if not conversation:
        await query.answer("Session expired, please start again", show_alert=True)
        return True

    await query.answer()

    # Handle first-person clarification (Phase 3)
    if action == "join_is_me":
        # User confirms it's about themselves — proceed to confirmation
        if conversation["state"] != "awaiting_first_person_clarification":
            return True
        update_pending_join(user.id, state="awaiting_confirmation")

        extraction = conversation.get("extraction", {})
        name = extraction.get("name", user.first_name)
        role = extraction.get("current_role", "")
        can_help = extraction.get("can_help_with", [])
        looking_for = extraction.get("looking_for", [])

        preview = f"👤 <b>{name}</b>\n"
        if role:
            preview += f"💼 {role}\n"
        if can_help:
            preview += f"🎯 Can help with: {', '.join(can_help)}\n"
        if looking_for:
            preview += f"🔍 Looking for: {', '.join(looking_for)}\n"

        await query.message.edit_text(
            f"✅ Here's what I understood:\n\n{preview}\n"
            "Is this correct?",
            parse_mode="HTML"
        )
        await send_message_with_buttons(
            chat_id,
            "Confirm your profile:",
            buttons=[
                [
                    {"text": "✅ Confirm", "callback_data": f"join_confirm:{user.id}"},
                    {"text": "✏️ Edit", "callback_data": f"join_edit:{user.id}"}
                ]
            ]
        )
        return True

    elif action == "join_is_note":
        # User wants to save as regular note — exit join flow, save as note
        if conversation["state"] != "awaiting_first_person_clarification":
            return True

        await query.message.edit_text(
            "📝 Got it! This will be saved as a regular note.\n\n"
            "To create your profile, please send a new message about <b>yourself</b>.",
            parse_mode="HTML"
        )

        # Reset to awaiting_intro so they can try again
        update_pending_join(user.id, state="awaiting_intro")

        # TODO: Could save the note through regular extraction pipeline
        # For now, just ask for self-intro again
        return True

    # Handle confirmation flow
    if conversation["state"] != "awaiting_confirmation":
        await query.answer("Session expired, please start again", show_alert=True)
        return True

    if action == "join_confirm":
        # Create profile
        await create_community_profile(user, chat_id, conversation)
        # Clean up
        delete_pending_join(user.id)

    elif action == "join_edit":
        # Go back to awaiting_intro
        update_pending_join(user.id, state="awaiting_intro")
        await send_message(
            chat_id,
            "✏️ Edit your profile\n\n"
            "Send a correction (you only need to mention what you want to change):"
        )

    return True


async def create_community_profile(user, chat_id: int, conversation: dict) -> None:
    """Create or update person + assertions from confirmed extraction.

    If is_edit=True and existing_person_id is set, updates existing profile.
    Otherwise creates a new profile (with duplicate check).
    """
    supabase = get_supabase_admin()

    extraction = conversation["extraction"]
    raw_text = conversation["raw_text"]
    community_id = conversation["community_id"]
    community_name = conversation["community_name"]
    owner_id = conversation["owner_id"]
    is_edit = conversation.get("is_edit", False)
    existing_person_id = conversation.get("existing_person_id")

    name = extraction.get("name", user.first_name)

    # Determine if we're updating or creating
    if is_edit and existing_person_id:
        logger.info(f"Updating community profile for telegram_id={user.id}, person_id={existing_person_id}, name={name}")
        await send_message(chat_id, "Updating your profile...")
    else:
        logger.info(f"Creating community profile for telegram_id={user.id}, name={name}")
        await send_message(chat_id, "Creating your profile...")

    try:
        # 1. Create raw_evidence
        evidence_result = supabase.table("raw_evidence").insert({
            "owner_id": owner_id,
            "source_type": "text_note",
            "content": raw_text,
            "processing_status": "done",
            "processed": True
        }).execute()

        evidence_id = evidence_result.data[0]["evidence_id"]

        # 2. Create or update person
        if is_edit and existing_person_id:
            # UPDATE existing person
            supabase.table("person").update({
                "display_name": name,
                "updated_at": "now()"
            }).eq("person_id", existing_person_id).execute()

            person_id = existing_person_id
            logger.info(f"Updated existing person_id={person_id}")
        else:
            # Check for existing profile (prevent duplicates at application level)
            existing = supabase.table("person").select(
                "person_id"
            ).eq("telegram_id", user.id).eq("community_id", community_id).eq(
                "status", "active"
            ).execute()

            if existing.data:
                # Profile already exists — update instead of create
                person_id = existing.data[0]["person_id"]
                supabase.table("person").update({
                    "display_name": name,
                    "updated_at": "now()"
                }).eq("person_id", person_id).execute()
                logger.info(f"Found existing profile, updated person_id={person_id}")
            else:
                # CREATE new person
                person_result = supabase.table("person").insert({
                    "owner_id": owner_id,
                    "display_name": name,
                    "telegram_id": user.id,
                    "community_id": community_id,
                    "status": "active"
                }).execute()

                person_id = person_result.data[0]["person_id"]
                logger.info(f"Created new person_id={person_id}")

        # 3. Update identity (for all cases, not just new profiles)
        # Check if freeform_name identity already exists
        existing_identity = supabase.table("identity").select(
            "identity_id"
        ).eq("person_id", person_id).eq("namespace", "freeform_name").execute()

        if existing_identity.data:
            # Update existing identity
            supabase.table("identity").update({
                "value": name
            }).eq("identity_id", existing_identity.data[0]["identity_id"]).execute()
        else:
            supabase.table("identity").insert({
                "person_id": person_id,
                "namespace": "freeform_name",
                "value": name
            }).execute()

        if user.username:
            try:
                # Check if telegram_username identity already exists
                existing_tg = supabase.table("identity").select(
                    "identity_id"
                ).eq("person_id", person_id).eq("namespace", "telegram_username").execute()

                if existing_tg.data:
                    supabase.table("identity").update({
                        "value": user.username
                    }).eq("identity_id", existing_tg.data[0]["identity_id"]).execute()
                else:
                    supabase.table("identity").insert({
                        "person_id": person_id,
                        "namespace": "telegram_username",
                        "value": user.username
                    }).execute()
            except Exception:
                pass

        # 4. Create assertions from extraction (always add new assertions)
        assertions = []

        for field, predicate in SELF_INTRO_PREDICATE_MAP.items():
            value = extraction.get(field)
            if not value:
                continue

            if isinstance(value, list):
                for item in value:
                    if item:
                        assertions.append({
                            "subject_person_id": person_id,
                            "predicate": predicate,
                            "object_value": item,
                            "evidence_id": evidence_id,
                            "scope": "personal",
                            "confidence": 0.9
                        })
            else:
                assertions.append({
                    "subject_person_id": person_id,
                    "predicate": predicate,
                    "object_value": value,
                    "evidence_id": evidence_id,
                    "scope": "personal",
                    "confidence": 0.9
                })

        if assertions:
            # Generate embeddings
            assertion_texts = [
                create_assertion_text(a["predicate"], a["object_value"], name)
                for a in assertions
            ]
            embeddings = generate_embeddings_batch(assertion_texts)

            for i, assertion in enumerate(assertions):
                assertion["embedding"] = embeddings[i] if i < len(embeddings) else None
                supabase.table("assertion").insert(assertion).execute()

        action_word = "Updated" if is_edit else "Created"
        logger.info(f"{action_word} profile: person_id={person_id}, assertions={len(assertions)}")

        # Check profile completeness for follow-up (Phase 2)
        has_role = bool(extraction.get("current_role"))
        has_offers = bool(extraction.get("can_help_with"))
        has_seeks = bool(extraction.get("looking_for"))

        missing_fields = []
        if not has_role:
            missing_fields.append("what you do")
        if not has_offers:
            missing_fields.append("what you can help with")
        if not has_seeks:
            missing_fields.append("what you're looking for")

        if is_edit:
            # Edit mode — simpler success message
            await send_message(
                chat_id,
                f"Done! Your profile has been updated.\n\n"
                f"Name: <b>{name}</b>\n"
                f"New facts added: {len(assertions)}\n\n"
                "/profile - view your profile\n"
                "/edit - make more changes",
                parse_mode="HTML"
            )
        elif missing_fields:
            # Profile incomplete — offer follow-up
            await send_message(
                chat_id,
                f"Welcome to <b>{community_name}</b>!\n\n"
                f"Your profile has been created:\n"
                f"Name: <b>{name}</b>\n\n"
                f"<b>Want to add more?</b>\n"
                f"Your profile would be stronger with: {', '.join(missing_fields)}.\n\n"
                "Send another voice or text message to add more details,\n"
                "or use /profile to see your current profile.",
                parse_mode="HTML"
            )
        else:
            # Profile complete
            await send_message(
                chat_id,
                f"Welcome to <b>{community_name}</b>!\n\n"
                f"Your profile has been created:\n"
                f"Name: <b>{name}</b>\n\n"
                "Commands:\n"
                "/profile - view your profile\n"
                "/edit - update your profile\n"
                "/delete - remove your profile",
                parse_mode="HTML"
            )

    except Exception as e:
        logger.error(f"Error creating/updating profile: {e}", exc_info=True)
        error_action = "updating" if is_edit else "creating"
        await send_message(
            chat_id,
            f"Error {error_action} profile. Please try again."
        )


async def handle_profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /profile command for community members."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    supabase = get_supabase_admin()

    # Find user's community profiles
    result = supabase.table("person").select(
        "person_id, display_name, community_id, community:community_id(name)"
    ).eq("telegram_id", user.id).not_.is_("community_id", "null").eq(
        "status", "active"
    ).execute()

    if not result.data:
        await update.message.reply_text(
            "📭 You don't have any community profiles yet.\n\n"
            "Join a community using an invite link to create one!"
        )
        return

    # For simplicity, show first profile (or could list all)
    profile = result.data[0]
    person_id = profile["person_id"]
    community_name = profile["community"]["name"] if profile.get("community") else "Unknown"

    # Get assertions
    assertions_result = supabase.table("assertion").select(
        "predicate, object_value"
    ).eq("subject_person_id", person_id).execute()

    # Format profile
    text = f"👤 <b>Your profile in {community_name}</b>\n\n"
    text += f"<b>Name:</b> {profile['display_name']}\n\n"

    if assertions_result.data:
        # Group by predicate type
        role = []
        offers = []
        seeks = []
        other = []

        for a in assertions_result.data:
            pred = a["predicate"]
            val = a["object_value"]
            if pred == "self_role":
                role.append(val)
            elif pred == "self_offer":
                offers.append(val)
            elif pred == "self_seek":
                seeks.append(val)
            elif not pred.startswith("_"):
                other.append(f"{pred}: {val}")

        if role:
            text += f"<b>Role:</b> {', '.join(role)}\n"
        if offers:
            text += f"<b>Can help with:</b> {', '.join(offers)}\n"
        if seeks:
            text += f"<b>Looking for:</b> {', '.join(seeks)}\n"
        if other:
            text += f"<b>Other:</b> {', '.join(other)}\n"

    text += "\n/edit — update profile\n/delete — remove profile"

    await update.message.reply_text(text, parse_mode="HTML")


async def handle_edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /edit command - start edit flow similar to join."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    supabase = get_supabase_admin()

    # Find user's profile
    result = supabase.table("person").select(
        "person_id, display_name, community_id, community:community_id(name, owner_id)"
    ).eq("telegram_id", user.id).not_.is_("community_id", "null").eq(
        "status", "active"
    ).execute()

    if not result.data:
        await update.message.reply_text(
            "📭 You don't have any community profiles to edit.\n"
            "Join a community first using an invite link!"
        )
        return

    profile = result.data[0]

    # Start edit conversation (persistent in DB)
    set_pending_join(
        telegram_id=user.id,
        community_id=profile["community_id"],
        state="awaiting_intro",
        existing_person_id=profile["person_id"],
        is_edit=True
    )

    await update.message.reply_text(
        f"✏️ <b>Edit your profile in {profile['community']['name']}</b>\n\n"
        "Send me a new introduction (text or voice).\n"
        "This will add to your existing profile.",
        parse_mode="HTML"
    )


async def handle_delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /delete command for community members."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    supabase = get_supabase_admin()

    # Find user's profile
    result = supabase.table("person").select(
        "person_id, display_name, community_id, community:community_id(name)"
    ).eq("telegram_id", user.id).not_.is_("community_id", "null").eq(
        "status", "active"
    ).execute()

    if not result.data:
        await update.message.reply_text(
            "📭 You don't have any community profiles to delete."
        )
        return

    profile = result.data[0]

    # Ask for confirmation
    await send_message_with_buttons(
        chat_id,
        f"⚠️ <b>Delete your profile?</b>\n\n"
        f"This will remove your profile from <b>{profile['community']['name']}</b>.\n\n"
        f"Profile: <b>{profile['display_name']}</b>",
        buttons=[
            [
                {"text": "🗑️ Delete", "callback_data": f"delete_profile:{profile['person_id']}"},
                {"text": "❌ Cancel", "callback_data": "delete_cancel"}
            ]
        ],
        parse_mode="HTML"
    )


async def handle_delete_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    callback_data: str
) -> bool:
    """Handle delete confirmation callbacks."""
    query = update.callback_query
    user = update.effective_user
    chat_id = query.message.chat_id

    if callback_data == "delete_cancel":
        await query.answer("Cancelled")
        await query.message.edit_text("❌ Deletion cancelled.")
        return True

    if not callback_data.startswith("delete_profile:"):
        return False

    person_id = callback_data.split(":")[1]

    await query.answer()

    supabase = get_supabase_admin()

    # Verify ownership
    check = supabase.table("person").select(
        "telegram_id"
    ).eq("person_id", person_id).single().execute()

    if not check.data or check.data["telegram_id"] != user.id:
        await query.message.edit_text("❌ You can only delete your own profile.")
        return True

    # Soft delete
    supabase.table("person").update({
        "status": "deleted"
    }).eq("person_id", person_id).execute()

    await query.message.edit_text(
        "✅ Your profile has been deleted.\n\n"
        "You can rejoin the community anytime using the invite link."
    )

    return True


async def handle_new_community_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /newcommunity command for creating communities."""
    user = update.effective_user
    chat_id = update.effective_chat.id

    # Get or create Supabase user first
    try:
        supabase_user = await get_or_create_user(
            telegram_id=str(user.id),
            telegram_username=user.username,
            display_name=user.first_name
        )
    except Exception as e:
        logger.error(f"Auth error in /newcommunity: {e}")
        await update.message.reply_text(
            "❌ Authentication error. Please try /start first."
        )
        return

    # Check permission
    if not can_create_community(supabase_user["user_id"]):
        await update.message.reply_text(
            "❌ Sorry, only Atlantis+ members can create communities.\n\n"
            "Contact the admin to get access."
        )
        return

    # For simplicity, create with default name
    # Could implement conversation flow for name/description
    await update.message.reply_text(
        "📝 **Create a new community**\n\n"
        "What's the name of your community?\n"
        "(Just send the name as a message)"
    )

    # Store state for next message (in-memory, short-lived flow)
    PENDING_COMMUNITY_CREATION[user.id] = {
        "state": "awaiting_community_name",
        "supabase_user_id": supabase_user["user_id"]
    }


async def handle_community_name_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    name: str
) -> bool:
    """Handle community name input after /newcommunity."""
    user = update.effective_user
    chat_id = update.effective_chat.id

    conversation = PENDING_COMMUNITY_CREATION.get(user.id)
    if not conversation or conversation.get("state") != "awaiting_community_name":
        return False

    supabase = get_supabase_admin()

    try:
        result = supabase.table("community").insert({
            "owner_id": conversation["supabase_user_id"],
            "name": name,
            "settings": {},
            "is_active": True
        }).execute()

        community = result.data[0]
        invite_code = community["invite_code"]

        invite_link = f"https://t.me/atlantisplus_bot?start=join_{invite_code}"
        await update.message.reply_text(
            f"✅ <b>Community created!</b>\n\n"
            f"<b>{name}</b>\n\n"
            f"📎 Invite link for members:\n"
            f"{invite_link}\n\n"
            "Share this link in your channel!\n\n"
            "Members who click it will be asked to introduce themselves.",
            parse_mode="HTML"
        )

        # Clean up
        PENDING_COMMUNITY_CREATION.pop(user.id, None)
        return True

    except Exception as e:
        logger.error(f"Error creating community: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Error creating community. Please try again."
        )
        PENDING_COMMUNITY_CREATION.pop(user.id, None)
        return True


def is_in_join_conversation(telegram_id: int) -> bool:
    """Check if user is in join/edit conversation (from DB) or community creation (in-memory)."""
    # Check persistent join/edit state
    if get_pending_join(telegram_id) is not None:
        return True
    # Check in-memory community creation state
    if telegram_id in PENDING_COMMUNITY_CREATION:
        return True
    return False
