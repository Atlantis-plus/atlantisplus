"""
Telegram message and command handlers.

ARCHITECTURE: Direct function calls - NO HTTP overhead!
- Handlers call business logic functions directly
- Use Supabase with service_role_key
- API endpoints remain for Mini App
"""

import asyncio
from telegram import Update
from telegram.ext import ContextTypes

from .auth import get_or_create_user
from .context import load_context, clear_context, get_active_session, set_active_session
from .dispatcher import classify_message
from .telegram_api import send_message, send_chat_action, send_message_with_web_app_buttons
from .logging_config import bot_logger as logger

# Direct imports of business logic
from app.services.extraction import extract_from_text_simple
from app.services.embedding import generate_embeddings_batch, create_assertion_text
from app.services.transcription import transcribe_from_storage
from app.services.proactive import get_proactive_service
from app.supabase_client import get_supabase_admin
from app.config import get_settings
from app.api.process import process_pipeline
from app.api.chat import chat_direct


async def handle_start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    user = update.effective_user

    welcome_text = f"""👋 Hi, {user.first_name}!

I'm Atlantis Plus, your personal assistant for managing your professional network.

**What I can do:**
• Remember information about people from your notes
• Answer questions about your network
• Find the right people for specific tasks

**How to use:**
Just text me or send a voice message:
• "Vasya works at Google, met him in Singapore"
• "Who can help with fundraising?"
• "What do I know about Pete?"

I'll automatically figure out what to save and what to answer.

Use the menu button below to access your contact catalog 👇"""

    await update.message.reply_text(welcome_text)


async def handle_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    help_text = """📖 **How to use Atlantis Plus**

**Adding information:**
Just write or voice note facts about people:
• "Alex is a partner at Sequoia"
• "Met Maria at a conference"
• "Pete is an AI expert, can help with ML pipeline"

**Finding people:**
Ask questions in natural language:
• "Who works in pharma?"
• "Find someone who knows blockchain"
• "Who can intro me to YC?"

**Dialog:**
I remember conversation context, so you can clarify:
• "Where did he work before?"
• "When did we last talk?"

**Commands:**
/start — bot info
/help — this help
/reset — clear dialog context

**Catalog:**
Open Mini App via menu button to browse all contacts 👇"""

    await update.message.reply_text(help_text, parse_mode="Markdown")


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
    1. Authenticate user
    2. Classify message via dispatcher
    3. Call business logic directly (extraction or chat)
    4. Return response
    """
    user = update.effective_user
    message_text = update.message.text
    chat_id = update.effective_chat.id

    logger.info(f"Received message from user_id={user.id}, username={user.username}, text_len={len(message_text)}")

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
                chat_id, message_text, supabase_user["user_id"], user_context
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

        # 3. Create person records and map temp_ids to real UUIDs
        person_map: dict[str, str] = {}  # temp_id -> person_id

        for person in extraction.people:
            # Create person
            person_result = supabase.table("person").insert({
                "owner_id": user_id,
                "display_name": person.name,
                "status": "active"
            }).execute()

            person_id = person_result.data[0]["person_id"]
            person_map[person.temp_id] = person_id

            # Create identities for name variations
            identities = [{"person_id": person_id, "namespace": "freeform_name", "value": person.name}]

            for variation in person.name_variations:
                if variation and variation != person.name:
                    identities.append({
                        "person_id": person_id,
                        "namespace": "freeform_name",
                        "value": variation
                    })

            # Insert identities
            for identity in identities:
                try:
                    supabase.table("identity").insert(identity).execute()
                except Exception:
                    pass  # Ignore duplicate identities

        # 4. Create assertions with embeddings
        if extraction.assertions:
            # Generate texts for embedding
            assertion_texts = []
            for assertion in extraction.assertions:
                person_name = ""
                for p in extraction.people:
                    if p.temp_id == assertion.subject:
                        person_name = p.name
                        break
                text_for_embedding = create_assertion_text(assertion.predicate, assertion.value, person_name)
                assertion_texts.append(text_for_embedding)

            # Generate embeddings in batch
            embeddings = generate_embeddings_batch(assertion_texts)

            # Insert assertions with embeddings
            for i, assertion in enumerate(extraction.assertions):
                person_id = person_map.get(assertion.subject)
                if not person_id:
                    continue

                supabase.table("assertion").insert({
                    "subject_person_id": person_id,
                    "predicate": assertion.predicate,
                    "object_value": assertion.value,
                    "confidence": assertion.confidence,
                    "evidence_id": evidence_id,
                    "scope": "personal",
                    "embedding": embeddings[i] if i < len(embeddings) else None
                }).execute()

        # 5. Create edges
        for edge in extraction.edges:
            src_id = person_map.get(edge.source)
            dst_id = person_map.get(edge.target)

            if src_id and dst_id and src_id != dst_id:
                try:
                    supabase.table("edge").insert({
                        "src_person_id": src_id,
                        "dst_person_id": dst_id,
                        "edge_type": edge.type,
                        "scope": "personal"
                    }).execute()
                except Exception:
                    pass  # Ignore edge errors

        # 6. Update evidence status to done
        supabase.table("raw_evidence").update({
            "processed": True,
            "processing_status": "done"
        }).eq("evidence_id", evidence_id).execute()

        logger.info(f"Successfully processed note: {len(extraction.people)} people, {len(extraction.assertions)} assertions")

        # Send success message
        people_names = ", ".join([p.name for p in extraction.people])
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


async def handle_chat_message_direct(chat_id: int, text: str, user_id: str, user_context: dict) -> None:
    """
    Handle query/dialog message.

    Direct call to chat agent with tool use - NO HTTP!
    If the response contains found people, adds inline keyboard with Mini App buttons.
    """
    logger.info(f"Processing chat query for user_id={user_id}")

    # Show typing indicator
    await send_chat_action(chat_id, "typing")

    try:
        # Get session_id from context (if continuing dialog)
        session_id = user_context.get("chat_session_id")

        # Call chat agent directly - returns ChatDirectResult with message, session_id, and people
        result = await chat_direct(text, user_id, session_id)

        # Update context with session_id
        await set_active_session(str(chat_id), result.session_id)

        # If people were found in the search, send message with Mini App buttons
        if result.people:
            logger.info(f"Found {len(result.people)} people, adding Mini App buttons")
            await send_message_with_web_app_buttons(
                chat_id,
                result.message,
                result.people,
                parse_mode="HTML",
                max_buttons=5
            )
        else:
            # No people found, send regular message
            await send_message(chat_id, result.message, parse_mode="HTML")

        logger.info(f"Chat response sent for session_id={result.session_id}")

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
                user_context
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
    Actions: merge, reject
    """
    query = update.callback_query
    user = update.effective_user
    callback_data = query.data
    message_id = query.message.message_id
    chat_id = query.message.chat_id

    logger.info(f"Callback from user_id={user.id}: {callback_data}")

    # Answer the callback to remove loading state
    await query.answer()

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

    # Handle the callback
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


async def handle_error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors in handlers."""
    logger.error(f"Bot error: {context.error}", exc_info=context.error)

    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Error processing message.\n"
            "Try again or use /help"
        )
