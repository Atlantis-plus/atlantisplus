"""
Proactive Notifications Service.

Sends proactive messages to users via Telegram when:
- Duplicates are detected
- There are important questions about contacts
- After extraction, summarizes what was saved
"""

from typing import Optional
from uuid import UUID
from datetime import datetime, timezone

from app.supabase_client import get_supabase_admin
from app.services.dedup import get_dedup_service

# Note: telegram_bot imports are done lazily inside methods to avoid circular imports


class ProactiveNotificationService:
    """Service for sending proactive notifications to users."""

    def __init__(self):
        self.supabase = get_supabase_admin()
        self.dedup_service = get_dedup_service()

    async def check_and_notify_duplicates(
        self,
        user_id: str,
        person_ids: list[str]
    ) -> int:
        """
        Check if any of the newly created people have duplicates.
        Send Telegram notification if found.

        Returns: Number of notifications sent
        """
        from app.telegram_bot.telegram_api import (
            get_telegram_id_for_user,
            send_message_with_buttons
        )

        telegram_id = await get_telegram_id_for_user(user_id)
        if not telegram_id:
            return 0

        notifications_sent = 0

        for person_id in person_ids:
            candidates = await self.dedup_service.find_duplicates_for_person(
                UUID(user_id),
                UUID(person_id),
                name_threshold=0.5,
                embedding_threshold=0.8
            )

            # Only notify for high-confidence matches
            high_confidence = [c for c in candidates if c.match_score >= 0.6]

            for candidate in high_confidence[:1]:  # Max 1 notification per person
                # Get the person name
                person_result = self.supabase.table("person").select(
                    "display_name"
                ).eq("person_id", person_id).single().execute()

                if not person_result.data:
                    continue

                person_name = person_result.data["display_name"]

                # Create inline keyboard buttons
                buttons = [[
                    {"text": "Merge", "callback_data": f"merge:{person_id}:{candidate.person_id}"},
                    {"text": "Different", "callback_data": f"reject:{person_id}:{candidate.person_id}"},
                ]]

                message = (
                    f"Possible duplicate found:\n\n"
                    f"**{person_name}** and **{candidate.display_name}**\n"
                    f"Match type: {candidate.match_type}\n"
                    f"Confidence: {int(candidate.match_score * 100)}%\n\n"
                    f"Are they the same person?"
                )

                try:
                    await send_message_with_buttons(
                        telegram_id,
                        message,
                        buttons,
                        parse_mode="Markdown"
                    )
                    notifications_sent += 1

                    # Create a proactive question record
                    await self.dedup_service.create_dedup_question(
                        UUID(user_id),
                        UUID(person_id),
                        person_name,
                        candidate.person_id,
                        candidate.display_name,
                        candidate.match_score
                    )

                except Exception as e:
                    print(f"[PROACTIVE] Failed to send notification: {e}")

        return notifications_sent

    async def notify_extraction_summary(
        self,
        user_id: str,
        people_names: list[str],
        assertions_count: int
    ) -> bool:
        """
        Send a summary of what was extracted (optional, for rich notes).
        Currently handled in handlers.py directly.
        """
        # This is a placeholder for more sophisticated summaries
        # For now, handlers.py sends the summary directly
        return True

    async def send_import_report(
        self,
        user_id: str,
        import_type: str,
        batch_id: str,
        new_people: int,
        updated_people: int,
        analytics: dict,
        dedup_result: Optional[dict] = None
    ) -> bool:
        """
        Send import completion report to Telegram.

        Args:
            user_id: Supabase user ID
            import_type: 'linkedin' or 'calendar'
            batch_id: Import batch ID for reference
            new_people: Number of new contacts created
            updated_people: Number of existing contacts updated
            analytics: Analytics dict with import stats
            dedup_result: Optional dedup results

        Returns:
            True if sent successfully
        """
        from app.telegram_bot.telegram_api import (
            get_telegram_id_for_user,
            send_message
        )

        telegram_id = await get_telegram_id_for_user(user_id)
        if not telegram_id:
            print(f"[PROACTIVE] No telegram_id found for user {user_id}")
            return False

        # Build message
        source_name = "LinkedIn" if import_type == "linkedin" else "Google Calendar"
        message_lines = [
            f"**Import Complete** ({source_name})",
            "",
            f"New contacts: {new_people}",
            f"Updated: {updated_people}",
        ]

        # Add analytics based on import type
        if import_type == "linkedin" and analytics:
            by_year = analytics.get("by_year", {})
            if by_year:
                years_str = ", ".join([f"{y}: {c}" for y, c in list(by_year.items())[:3]])
                message_lines.append(f"By year: {years_str}")

            by_company = analytics.get("by_company", {})
            if by_company:
                companies = list(by_company.keys())[:3]
                message_lines.append(f"Top companies: {', '.join(companies)}")

        elif import_type == "calendar" and analytics:
            by_freq = analytics.get("by_frequency", {})
            if by_freq:
                freq_str = ", ".join([f"{k}: {v}" for k, v in by_freq.items()])
                message_lines.append(f"By frequency: {freq_str}")

            date_range = analytics.get("date_range")
            if date_range:
                message_lines.append(f"Period: {date_range}")

        # Add dedup info
        if dedup_result and dedup_result.get("duplicates_found", 0) > 0:
            message_lines.append("")
            message_lines.append(f"Potential duplicates: {dedup_result['duplicates_found']}")
            message_lines.append("Review them in the app")

        message = "\n".join(message_lines)

        try:
            await send_message(telegram_id, message, parse_mode="Markdown")
            return True
        except Exception as e:
            print(f"[PROACTIVE] Failed to send import report: {e}")
            return False

    async def send_proactive_question(
        self,
        user_id: str,
        force: bool = False
    ) -> Optional[dict]:
        """
        Check if there's a proactive question to ask and send it.

        Args:
            user_id: Supabase user ID
            force: If True, ignore rate limits

        Returns:
            Question dict if sent, None otherwise
        """
        from app.telegram_bot.telegram_api import (
            get_telegram_id_for_user,
            send_message
        )

        telegram_id = await get_telegram_id_for_user(user_id)
        if not telegram_id:
            return None

        # Check rate limits
        if not force:
            rate_result = self.supabase.from_("question_rate_limit").select("*").eq(
                "owner_id", user_id
            ).execute()

            if rate_result.data:
                rate = rate_result.data[0]
                now = datetime.now(timezone.utc)

                # Check if paused
                if rate.get("paused_until"):
                    paused_until = datetime.fromisoformat(
                        rate["paused_until"].replace("Z", "+00:00")
                    )
                    if now < paused_until:
                        return None

                # Check daily limit
                from app.config import get_settings
                settings = get_settings()

                if rate.get("questions_shown_today", 0) >= settings.questions_max_per_day:
                    return None

        # Find pending question
        now = datetime.now(timezone.utc)
        result = self.supabase.from_("proactive_question").select(
            "question_id, person_id, question_type, question_text_ru, question_text, "
            "person:person_id(display_name)"
        ).eq("owner_id", user_id).eq("status", "pending").gt(
            "expires_at", now.isoformat()
        ).order("priority", desc=True).limit(1).execute()

        if not result.data:
            return None

        question = result.data[0]
        person_name = ""
        if question.get("person") and question["person"]:
            person_name = question["person"].get("display_name", "")

        question_text = question.get("question_text_ru") or question["question_text"]

        # Format message based on question type
        if question["question_type"] == "dedup_confirm":
            # Already handled with buttons in check_and_notify_duplicates
            return None

        # For regular questions, send as plain message
        message = f"About **{person_name}**:\n\n{question_text}"

        try:
            await send_message(telegram_id, message, parse_mode="Markdown")

            # Mark as shown
            self.supabase.from_("proactive_question").update({
                "status": "shown",
                "shown_at": now.isoformat()
            }).eq("question_id", question["question_id"]).execute()

            return question

        except Exception as e:
            print(f"[PROACTIVE] Failed to send question: {e}")
            return None

    async def handle_callback(
        self,
        user_id: str,
        callback_data: str,
        message_id: int,
        chat_id: int
    ) -> str:
        """
        Handle inline keyboard callback.

        Args:
            user_id: Supabase user ID
            callback_data: Data from button (e.g., "merge:uuid1:uuid2")
            message_id: ID of message with the buttons
            chat_id: Telegram chat ID

        Returns:
            Response message
        """
        from app.telegram_bot.telegram_api import edit_message_text

        parts = callback_data.split(":")

        if len(parts) < 3:
            return "Invalid callback data"

        action = parts[0]
        person_a_id = parts[1]
        person_b_id = parts[2]

        if action == "merge":
            try:
                result = await self.dedup_service.merge_persons(
                    UUID(user_id),
                    UUID(person_a_id),
                    UUID(person_b_id)
                )

                # Get the kept person name
                person_result = self.supabase.table("person").select(
                    "display_name"
                ).eq("person_id", person_a_id).single().execute()

                kept_name = person_result.data["display_name"] if person_result.data else "Unknown"

                response = (
                    f"Merged successfully!\n\n"
                    f"Kept: {kept_name}\n"
                    f"Facts moved: {result.assertions_moved}"
                )

                # Edit the original message
                await edit_message_text(chat_id, message_id, response)

                return response

            except Exception as e:
                return f"Merge failed: {str(e)[:100]}"

        elif action == "reject":
            try:
                await self.dedup_service.reject_duplicate(
                    UUID(user_id),
                    UUID(person_a_id),
                    UUID(person_b_id)
                )

                response = "Marked as different people."

                # Edit the original message
                await edit_message_text(chat_id, message_id, response)

                return response

            except Exception as e:
                return f"Reject failed: {str(e)[:100]}"

        return "Unknown action"


# Singleton instance
_proactive_service: Optional[ProactiveNotificationService] = None


def get_proactive_service() -> ProactiveNotificationService:
    global _proactive_service
    if _proactive_service is None:
        _proactive_service = ProactiveNotificationService()
    return _proactive_service
