"""
Telegram message and command handlers.

ARCHITECTURE: Direct function calls - NO HTTP overhead!
- Handlers call business logic functions directly
- Use Supabase with service_role_key
- API endpoints remain for Mini App

PROGRESSIVE SEARCH ENHANCEMENT:
===============================
Search uses two tiers for optimal UX:

Tier 1 (Fast, ~3 sec): OpenAI single-shot semantic search
- Returns results immediately
- Shows "Dig deeper" button if results found

Tier 2 (Deep, ~15 sec): Claude agent multi-shot search
- Triggered by "Dig deeper" button callback
- Re-runs Tier 1 to get fresh context
- Uses low-level tools to find name variations, company spellings
- Finds non-obvious connections

The PENDING_DIG_DEEPER_QUERIES dict stores original queries
temporarily (keyed by hash) for Tier 2 callbacks.

COMMUNITY INTAKE MODE:
======================
Three user types with different UX:
- Atlantis+ members: full access
- Community admins: see own community members
- Community members: only self-profile

Deep link handling:
- join_XXX: community onboarding flow
- person_XXX: open person profile
"""

import asyncio
from telegram import Update
from telegram.ext import ContextTypes

from .auth import get_or_create_user
from .context import load_context, clear_context, get_active_session, set_active_session
from .dispatcher import classify_message
from .telegram_api import (
    send_message, send_chat_action, send_message_with_web_app_buttons,
    send_message_with_dig_deeper, edit_message_text
)
from .logging_config import bot_logger as logger
from .community_handlers import (
    handle_join_deep_link, handle_join_conversation, handle_join_voice,
    handle_join_callback, handle_delete_callback,
    handle_profile_command, handle_edit_command, handle_delete_command,
    handle_new_community_command, handle_community_name_input,
    is_in_join_conversation, get_pending_join, PENDING_COMMUNITY_CREATION
)

# Direct imports of business logic
from app.services.extraction import extract_from_text_simple, process_extraction_result
from app.services.transcription import transcribe_from_storage
from app.services.proactive import get_proactive_service
from app.supabase_client import get_supabase_admin
from app.config import get_settings
from app.api.process import process_pipeline
from app.api.chat import chat_direct, chat_dig_deeper

# Store pending "dig deeper" queries (hash → full query)
# Simple in-memory store, queries expire naturally when bot restarts
# For production, consider Redis with TTL
PENDING_DIG_DEEPER_QUERIES: dict[str, str] = {}


def log_query(user_id: str, query_text: str, tier: int = 1, results_count: int = 0, tg_username: str = None) -> None:
    """Log search query to database. Fire-and-forget, never raises."""
    try:
        supabase = get_supabase_admin()
        data = {
            "user_id": user_id,
            "query_text": query_text,
            "tier": tier,
            "results_count": results_count
        }
        if tg_username:
            data["tg_username"] = tg_username
        supabase.table("query_log").insert(data).execute()
    except Exception as e:
        logger.warning(f"Failed to log query: {e}")


async def handle_start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /start command with deep link support.

    Deep links handled:
    - join_XXX: community onboarding
    - person_XXX: open person profile (redirect to Mini App)
    """
    user = update.effective_user
    args = context.args  # ['join_ABC123'] or []

    # Handle deep links
    if args:
        deep_link = args[0]

        # Community join flow
        if deep_link.startswith('join_'):
            invite_code = deep_link[5:]  # Remove 'join_' prefix
            await handle_join_deep_link(update, context, invite_code)
            return

        # Person profile link (redirect to Mini App)
        if deep_link.startswith('person_'):
            person_id = deep_link[7:]  # Remove 'person_' prefix
            settings = get_settings()
            mini_app_link = f"{settings.mini_app_url}?startapp=person_{person_id}"
            await update.message.reply_text(
                f"Opening profile...\n\n"
                f"<a href=\"{mini_app_link}\">Open in Mini App</a>",
                parse_mode="HTML"
            )
            return

    # Default welcome message
    welcome_text = f"""👋 Hi, {user.first_name}!

I'm Atlantis Plus, your personal assistant for managing your professional network.

<b>What I can do:</b>
• Remember information about people from your notes
• Answer questions about your network
• Find the right people for specific tasks

<b>How to use:</b>
Just text me or send a voice message:
• "Vasya works at Google, met him in Singapore"
• "Who can help with fundraising?"
• "What do I know about Pete?"

I'll automatically figure out what to save and what to answer.

Use the menu button below to access your contact catalog 👇"""

    await update.message.reply_text(welcome_text, parse_mode="HTML")


async def handle_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    help_text = """📖 <b>How to use Atlantis Plus</b>

<b>Adding information:</b>
Just write or voice note facts about people:
• "Alex is a partner at Sequoia"
• "Met Maria at a conference"
• "Pete is an AI expert, can help with ML pipeline"

<b>Finding people:</b>
Ask questions in natural language:
• "Who works in pharma?"
• "Find someone who knows blockchain"
• "Who can intro me to YC?"

<b>Dialog:</b>
I remember conversation context, so you can clarify:
• "Where did he work before?"
• "When did we last talk?"

<b>Commands:</b>
/start — bot info
/help — this help
/reset — clear dialog context
/profile — view your community profile
/edit — edit your profile
/delete — delete your profile
/newcommunity — create a community (members only)

<b>Catalog:</b>
Open Mini App via menu button to browse all contacts 👇"""

    await update.message.reply_text(help_text, parse_mode="HTML")


async def handle_reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /reset command - clear dialog context."""
    user_id = str(update.effective_user.id)
    await clear_context(user_id)

    await update.message.reply_text(
        "✅ Dialog context cleared.\n"
        "Let's start fresh!"
    )


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle incoming text message.

    ARCHITECTURE: Direct function calls - NO HTTP!
    1. Check for active community conversation
    2. Authenticate user
    3. Classify message via dispatcher
    4. Call business logic directly (extraction or chat)
    5. Return response
    """
    user = update.effective_user
    message_text = update.message.text
    chat_id = update.effective_chat.id

    logger.info(f"Received message from user_id={user.id}, username={user.username}, text_len={len(message_text)}")

    # Check for active community conversations first
    if is_in_join_conversation(user.id):
        # Check community creation flow (in-memory)
        community_creation = PENDING_COMMUNITY_CREATION.get(user.id, {})
        if community_creation.get("state") == "awaiting_community_name":
            handled = await handle_community_name_input(update, context, message_text)
            if handled:
                return

        # Check join/edit flow (persistent in DB)
        join_conversation = get_pending_join(user.id)
        if join_conversation and join_conversation.get("state") == "awaiting_intro":
            handled = await handle_join_conversation(update, context, message_text)
            if handled:
                return

    # 1. Authenticate: telegram_id → Supabase user
    try:
        supabase_user = await get_or_create_user(
            telegram_id=str(user.id),
            telegram_username=user.username,
            display_name=user.first_name
        )
    except Exception as e:
        logger.error(f"Authentication failed for telegram_id={user.id}: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Authentication error: {str(e)}\n"
            "Try /start"
        )
        return

    # 2. Load context and classify message
    user_context = await load_context(str(user.id))
    msg_type = await classify_message(message_text, user_context)
    logger.info(f"Message classified as: {msg_type}")

    # 3. Route to appropriate handler
    try:
        if msg_type == "note":
            # Direct call to extraction logic
            await handle_note_message_direct(
                chat_id, message_text, supabase_user["user_id"]
            )
        else:  # "query" or "dialog"
            # Direct call to chat logic
            await handle_chat_message_direct(
                chat_id, message_text, supabase_user["user_id"], user_context,
                tg_username=user.username
            )
    except Exception as e:
        logger.error(f"Handler error: {e}", exc_info=True)
        await send_message(
            chat_id,
            "❌ Error processing message.\n"
            "Try again or use /help"
        )


async def handle_note_message_direct(chat_id: int, text: str, user_id: str) -> None:
    """
    Handle note/fact about people.

    Direct extraction - NO HTTP calls!
    """
    logger.info(f"Processing note for user_id={user_id}")

    # Show typing indicator
    await send_chat_action(chat_id, "typing")

    # Send immediate feedback
    await send_message(
        chat_id,
        "🎯 Saving note...\n"
        "Extracting information about people."
    )

    supabase = get_supabase_admin()

    try:
        # 1. Create raw_evidence record
        evidence_result = supabase.table("raw_evidence").insert({
            "owner_id": user_id,
            "source_type": "text_note",
            "content": text,
            "processing_status": "extracting"
        }).execute()

        evidence_id = evidence_result.data[0]["evidence_id"]
        logger.info(f"Created evidence_id={evidence_id}")

        # 2. Extract people and assertions (direct call to extraction service)
        extraction = extract_from_text_simple(text)
        logger.info(f"Extracted {len(extraction.people)} people, {len(extraction.assertions)} assertions")

        # 3. Process extraction: create persons, identities, assertions, edges
        # Uses shared function to avoid code duplication with process.py
        result = process_extraction_result(
            supabase=supabase,
            user_id=user_id,
            evidence_id=evidence_id,
            extraction=extraction,
            logger=logger
        )
        person_map = result.person_map

        # 4. Update evidence status to done
        supabase.table("raw_evidence").update({
            "processed": True,
            "processing_status": "done"
        }).eq("evidence_id", evidence_id).execute()

        logger.info(f"Successfully processed note: {result.people_count} people, {result.assertions_count} assertions")

        # Send success message
        people_names = ", ".join(result.people_names)
        await send_message(
            chat_id,
            f"✅ Done! Extracted:\n"
            f"• People: {people_names}\n"
            f"• Facts: {len(extraction.assertions)}\n\n"
            "View in catalog via menu button 👇"
        )

        # Check for duplicates and send proactive notifications
        if person_map:
            try:
                proactive_service = get_proactive_service()
                notifications = await proactive_service.check_and_notify_duplicates(
                    user_id,
                    list(person_map.values())
                )
                if notifications > 0:
                    logger.info(f"Sent {notifications} duplicate notification(s)")
            except Exception as dedup_error:
                logger.warning(f"Dedup notification failed (non-critical): {dedup_error}")

    except Exception as e:
        logger.error(f"Error processing note: {e}", exc_info=True)

        # Update evidence status to error
        try:
            supabase.table("raw_evidence").update({
                "processing_status": "error",
                "error_message": str(e)[:500]
            }).eq("evidence_id", evidence_id).execute()
        except:
            pass

        await send_message(
            chat_id,
            f"❌ Error processing note: {str(e)[:200]}"
        )


async def handle_chat_message_direct(chat_id: int, text: str, user_id: str, user_context: dict, tg_username: str = None) -> None:
    """
    Handle query/dialog message - TIER 1 (fast search).

    PROGRESSIVE SEARCH:
    - Runs fast OpenAI search (~3 sec)
    - If results found, shows "Dig deeper" button
    - User can trigger Claude agent for deeper search

    Direct call to chat agent with tool use - NO HTTP!
    """
    logger.info(f"Processing chat query for user_id={user_id}, tg_username={tg_username}")

    # Show typing indicator
    await send_chat_action(chat_id, "typing")

    try:
        # Get session_id from context (if continuing dialog)
        session_id = user_context.get("chat_session_id")

        # TIER 1: Fast search via OpenAI
        result = await chat_direct(text, user_id, session_id)

        # Log the query
        log_query(user_id, text, tier=1, results_count=len(result.people) if result.people else 0, tg_username=tg_username)

        # Update context with session_id (use user_id, not chat_id!)
        await set_active_session(user_id, result.session_id)

        # If people found AND dig deeper is available, add the button
        if result.people and result.can_dig_deeper:
            logger.info(f"Tier 1 found {len(result.people)} people, adding Dig deeper button")
            await send_message_with_dig_deeper(
                chat_id,
                result.message,
                result.people,
                original_query=text,  # Store for Tier 2
                parse_mode="HTML",
                max_buttons=5
            )
        elif result.people:
            # People found but no dig deeper (shouldn't happen, but fallback)
            logger.info(f"Found {len(result.people)} people, no dig deeper")
            await send_message_with_web_app_buttons(
                chat_id,
                result.message,
                result.people,
                parse_mode="HTML",
                max_buttons=5
            )
        elif result.can_dig_deeper:
            # No people found, but offer dig deeper
            logger.info("Tier 1 found 0 people, showing Dig deeper button")
            await send_message_with_dig_deeper(
                chat_id,
                result.message,
                [],  # No people buttons
                original_query=text,
                parse_mode="HTML",
                max_buttons=0
            )
        else:
            # No people found, no dig deeper option
            await send_message(chat_id, result.message, parse_mode="HTML")

        logger.info(f"Tier 1 response sent for session_id={result.session_id}")

    except Exception as e:
        logger.error(f"Error in chat handler: {e}", exc_info=True)
        await send_message(
            chat_id,
            f"❌ Error processing query: {str(e)[:200]}\n"
            "Try rephrasing or use /reset to start fresh."
        )


async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle incoming voice message.

    Direct processing: download → upload to Storage → transcribe → extract
    """
    user = update.effective_user
    chat_id = update.effective_chat.id
    voice = update.message.voice

    logger.info(f"Received voice message from user_id={user.id}, duration={voice.duration}s")

    # Check for active join conversation first (persistent in DB)
    if is_in_join_conversation(user.id):
        join_conversation = get_pending_join(user.id)
        if join_conversation and join_conversation.get("state") == "awaiting_intro":
            handled = await handle_join_voice(update, context)
            if handled:
                return

    # 1. Authenticate
    try:
        supabase_user = await get_or_create_user(
            telegram_id=str(user.id),
            telegram_username=user.username,
            display_name=user.first_name
        )
    except Exception as e:
        logger.error(f"Authentication failed: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Authentication error: {str(e)}\n"
            "Try /start"
        )
        return

    # Send immediate feedback
    await send_message(
        chat_id,
        "🎤 Processing voice message...\n"
        "Transcribing and extracting information."
    )

    supabase = get_supabase_admin()

    try:
        # 2. Download voice file from Telegram
        file = await context.bot.get_file(voice.file_id)
        voice_bytes = await file.download_as_bytearray()

        # 3. Upload to Supabase Storage
        import time
        storage_path = f"{supabase_user['user_id']}/voice_{int(time.time())}.ogg"

        supabase.storage.from_("voice-notes").upload(
            storage_path,
            bytes(voice_bytes),
            file_options={"content-type": "audio/ogg"}
        )

        logger.info(f"Uploaded to storage: {storage_path}")

        # 4. Create raw_evidence record
        evidence_result = supabase.table("raw_evidence").insert({
            "owner_id": supabase_user["user_id"],
            "source_type": "voice_note",
            "content": "",  # Will be updated with transcript
            "storage_path": storage_path,
            "processing_status": "transcribing"
        }).execute()

        evidence_id = evidence_result.data[0]["evidence_id"]
        logger.info(f"Created evidence_id={evidence_id}")

        # 5. Transcribe
        transcript = await transcribe_from_storage(storage_path)
        logger.info(f"Transcribed {len(transcript)} chars: {transcript[:100]}")

        # Update evidence with transcript
        supabase.table("raw_evidence").update({
            "content": transcript
        }).eq("evidence_id", evidence_id).execute()

        # 6. Classify transcript (same as text messages)
        user_context = await load_context(str(user.id))
        msg_type = await classify_message(transcript, user_context)
        logger.info(f"Voice transcript classified as: {msg_type}")

        # 7. Route based on classification
        if msg_type == "note":
            # Run extraction pipeline
            await process_pipeline(
                evidence_id,
                supabase_user["user_id"],
                transcript,
                is_voice=True,
                storage_path=storage_path
            )

            # Get extraction results to report back
            assertions_result = supabase.table("assertion").select(
                "assertion_id, person:subject_person_id(person_id, display_name)"
            ).eq("evidence_id", evidence_id).execute()

            # Extract unique people from this evidence
            people_dict = {}
            for assertion in assertions_result.data:
                person = assertion.get("person")
                if person:
                    people_dict[person["person_id"]] = person["display_name"]

            people_names = ", ".join(people_dict.values())

            await send_message(
                chat_id,
                f"✅ Done! Extracted:\n"
                f"• People: {people_names or 'none found'}\n"
                f"• Facts: {len(assertions_result.data)}\n\n"
                "View in catalog via menu button 👇"
            )

            logger.info(f"Successfully processed voice note: {len(people_dict)} people, {len(assertions_result.data)} assertions")

        else:  # "query" or "dialog"
            # Delete the evidence record (not a note)
            supabase.table("raw_evidence").delete().eq("evidence_id", evidence_id).execute()

            # Handle as chat query
            await handle_chat_message_direct(
                chat_id,
                transcript,
                supabase_user["user_id"],
                user_context,
                tg_username=user.username
            )

            logger.info(f"Successfully processed voice query")

    except Exception as e:
        logger.error(f"Error processing voice: {e}", exc_info=True)
        await send_message(
            chat_id,
            f"❌ Error processing voice message: {str(e)[:200]}"
        )


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle inline keyboard button callbacks.

    Callback data format: "action:param1:param2"
    Actions:
    - dig:{query_hash} — Dig deeper with Claude agent (Tier 2 search)
    - merge, reject — Duplicate resolution (proactive_service)
    - join_confirm, join_edit — Community join flow
    - delete_profile, delete_cancel — Profile deletion
    """
    print("[CALLBACK_HANDLER] Entered handle_callback_query")

    query = update.callback_query
    user = update.effective_user
    callback_data = query.data
    message_id = query.message.message_id
    chat_id = query.message.chat_id

    print(f"[CALLBACK_HANDLER] callback_data={callback_data}, user_id={user.id}")
    logger.info(f"Callback from user_id={user.id}: {callback_data}")

    # Handle community join callbacks
    if callback_data.startswith("join_"):
        handled = await handle_join_callback(update, context, callback_data)
        if handled:
            return

    # Handle profile deletion callbacks
    if callback_data.startswith("delete_"):
        handled = await handle_delete_callback(update, context, callback_data)
        if handled:
            return

    # Authenticate user
    try:
        supabase_user = await get_or_create_user(
            telegram_id=str(user.id),
            telegram_username=user.username,
            display_name=user.first_name
        )
    except Exception as e:
        logger.error(f"Callback auth failed: {e}", exc_info=True)
        await query.answer("Authentication error", show_alert=True)
        return

    # Handle "Dig deeper" callback — TIER 2 SEARCH
    if callback_data.startswith("dig:"):
        await handle_dig_deeper_callback(
            query, supabase_user["user_id"], callback_data, chat_id,
            tg_username=user.username
        )
        return

    # Answer the callback to remove loading state (for other callbacks)
    await query.answer()

    # Handle other callbacks (merge, reject, etc.)
    try:
        proactive_service = get_proactive_service()
        response = await proactive_service.handle_callback(
            supabase_user["user_id"],
            callback_data,
            message_id,
            chat_id
        )
        logger.info(f"Callback handled: {response[:50]}")

    except Exception as e:
        logger.error(f"Callback error: {e}", exc_info=True)
        await query.answer(f"Error: {str(e)[:50]}", show_alert=True)


async def handle_dig_deeper_callback(
    query,
    user_id: str,
    callback_data: str,
    chat_id: int,
    tg_username: str = None
) -> None:
    """
    Handle "Dig deeper" button callback — TIER 2 SEARCH.

    PROGRESSIVE ENHANCEMENT FLOW:
    =============================
    1. User searched → Tier 1 found N people → showed "Dig deeper" button
    2. User clicked button → this callback fires
    3. We retrieve original query from PENDING_DIG_DEEPER_QUERIES
    4. Call chat_dig_deeper() which:
       - Re-runs Tier 1 to get fresh context
       - Passes context to Claude agent
       - Agent uses low-level tools to find what Tier 1 missed
    5. Send deeper results back to user

    The button is disabled after click to prevent double-taps.
    """
    print(f"[DIG_DEEPER_CALLBACK] Started with callback_data={callback_data}, chat_id={chat_id}")

    # Answer immediately with loading message
    await query.answer("🔍 Searching deeper... This may take up to 1 minute")
    print("[DIG_DEEPER_CALLBACK] Answered callback query")

    # Parse query hash from callback_data
    query_hash = callback_data.split(":", 1)[1] if ":" in callback_data else ""

    # Retrieve original query
    original_query = PENDING_DIG_DEEPER_QUERIES.get(query_hash)

    if not original_query:
        logger.warning(f"Dig deeper: query not found for hash {query_hash}")
        await send_message(
            chat_id,
            "❌ Query expired. Please search again.",
            parse_mode="HTML"
        )
        return

    logger.info(f"[DIG_DEEPER] Starting Tier 2 for: {original_query[:50]}")

    # Send "searching" message
    await send_message(
        chat_id,
        "🔍 <b>Searching deeper...</b>\n\n"
        "The AI agent is checking:\n"
        "• Company name variations (Яндекс vs Yandex)\n"
        "• Different predicates (works_at, met_on, knows)\n"
        "• Non-obvious connections\n\n"
        "<i>This usually takes up to 1 minute...</i>",
        parse_mode="HTML"
    )

    # Show typing indicator
    await send_chat_action(chat_id, "typing")

    try:
        # TIER 2: Claude agent deep search
        result = await chat_dig_deeper(original_query, user_id)

        # Log the query
        log_query(user_id, original_query, tier=2, results_count=len(result.people) if result.people else 0, tg_username=tg_username)

        # Send results
        if result.people:
            logger.info(f"[DIG_DEEPER] Found {len(result.people)} people")
            await send_message_with_web_app_buttons(
                chat_id,
                result.message,
                result.people,
                parse_mode="HTML",
                max_buttons=5
            )
        else:
            await send_message(chat_id, result.message, parse_mode="HTML")

        # Clean up stored query
        PENDING_DIG_DEEPER_QUERIES.pop(query_hash, None)

        logger.info(f"[DIG_DEEPER] Tier 2 complete")

    except Exception as e:
        logger.error(f"[DIG_DEEPER] Error: {e}", exc_info=True)
        await send_message(
            chat_id,
            f"❌ Error in deep search: {str(e)[:200]}\n"
            "Please try your search again.",
            parse_mode="HTML"
        )


async def handle_error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors in handlers."""
    logger.error(f"Bot error: {context.error}", exc_info=context.error)

    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Error processing message.\n"
            "Try again or use /help"
        )
