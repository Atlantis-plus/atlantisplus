# Issues: Dig Deeper Feature (2026-02-14)

## Issue 1: PENDING_DIG_DEEPER_QUERIES lost on restart

**Problem:** Query hashes are stored in in-memory dict. On server restart, all pending queries are lost and "Dig deeper" buttons stop working.

**Error:** `[WARNING] Dig deeper: query not found for hash d7fe55dda372`

**Solutions:**
- A) Store in Supabase table with TTL
- B) Store in Redis
- C) Encode query directly in callback_data (64 byte limit - won't work for long queries)
- D) Re-run classification from the message history in session

**Recommended:** Option D - use session_id from context, load last user message from chat_message table.

## Issue 2: ClaudeAgent doesn't extract people from low-level tools

**Problem:** `ClaudeAgent.found_people` only extracts from `find_people` tool results. But the agent uses `search_by_company_exact`, `explore_company_names`, etc.

**Result:** `[DIG_DEEPER] Agent finished: 10 iterations, 0 people` - buttons not shown even though agent found results.

**Fix:** Update ClaudeAgent to extract people from all people-returning tools (same list as chat_direct).

## Issue 3: Second search in session doesn't show buttons

**Problem:** Message classified as `dialog` instead of `query`. Handler for dialog uses `chat_direct` with session context, but inline buttons might not be sent.

**Investigation needed:** Check if `handle_chat_message_direct` sends buttons for dialog-classified messages.

## Webhook Configuration (IMPORTANT)

When setting webhook, MUST include:
```bash
-d "secret_token=<TELEGRAM_WEBHOOK_SECRET from Railway>"
-d 'allowed_updates=["message","callback_query","edited_message"]'
```

Current secret: `I4it4lKm1z4XydnSSUeFL4Vw5NbRVOcRgmZsNyy0PbE`
