# Community Feature — Bugs Found During Testing

## Bug #1: Edit flow loses previous extraction context

**Severity**: Medium

**Steps to reproduce**:
1. User joins community via deep link
2. User provides introduction: "Джирик, политик и создатель мемов"
3. System extracts: `name="Джирик"`, `current_role="политик и создатель мемов"`
4. User clicks "✏️ Edit" button
5. User sends correction: "Меня зовут Жирик, а не Джирик"
6. System shows: `name="Жирик"` — WITHOUT the role field

**Expected**: System should merge correction with existing extraction (name corrected, role preserved)

**Actual**: System completely replaces old extraction, losing all fields not in correction

**Root cause** (`community_handlers.py` lines 267-271):

```python
# When user sends correction, new extraction OVERWRITES previous:
extraction = extract_self_intro(text)  # Only extracts from correction text
update_pending_join(
    user.id,
    state="awaiting_confirmation",
    extraction=extraction,  # Replaces, doesn't merge!
    raw_text=text
)
```

The GPT prompt says "If something isn't mentioned, OMIT it" — so correction text only yields corrected fields, and previous fields are lost.

**Suggested fix** (simple merge):
```python
# After new_extraction = extract_self_intro(text)
previous_extraction = conversation.get("extraction", {})
merged_extraction = {**previous_extraction, **new_extraction}
# Save merged_extraction instead
```

---

## Bug #2: UX — unclear message in Edit mode

**Severity**: Low (UX improvement)

**Problem**: When user clicks Edit, bot says "Tell us about yourself again" — this might confuse users into thinking they need to repeat everything.

**Suggested fix**: Change message to:
```
✏️ Edit your profile

Send a correction (you only need to mention what you want to change):
```

---

## Bug #3: Owner cannot see Communities in Mini App

**Severity**: High

**Steps to reproduce**:
1. Owner creates community via `/newcommunity`
2. Owner opens Mini App
3. Owner looks for Communities tab or page

**Expected**: Owner sees "Groups" tab with their communities and member lists

**Actual**:
- Communities tab may exist (for `atlantis_plus` or `community_admin`)
- But CommunitiesPage shows empty list or no data

**Root cause**:
1. `App.tsx:175` shows Communities tab for `atlantis_plus` or `community_admin` ✅
2. `CommunitiesPage.tsx:23` calls `api.getCommunities()`
3. But `/communities` endpoint may return empty or fail
4. Alternatively: `userInfo.communities_owned` from `/auth/me` already has data, but CommunitiesPage doesn't use it

**Suggested fix**:
- Verify `/communities` endpoint returns owned communities
- Or refactor CommunitiesPage to use `userInfo.communities_owned` from useUserType()

---

## Bug #4: Community Member sees full Shared Network (Security Issue)

**Severity**: CRITICAL (Security)

**Steps to reproduce**:
1. User joins community as member (not Atlantis+ member)
2. User opens Mini App
3. Observe what data is visible

**Expected**:
- Community member sees ONLY `SelfProfilePage` with their own profile
- No access to other people, notes, chat, or Shared Network

**Actual**:
- Frontend routing correctly shows only SelfProfilePage ✅
- BUT: RLS policy on `person` table allows unconditional SELECT
- Community member can access ALL people via direct API calls

**Root cause** (`20260224120000_add_community.sql:79-84`):
```sql
CREATE POLICY "Users see all people or own by telegram" ON person
    FOR SELECT USING (
        true  -- ← ALLOWS ANYONE TO READ ANYONE
    );
```

This RLS policy defeats data isolation.

**Security impact**:
- Direct API calls can read all person records
- Supabase direct queries bypass intended isolation
- Deeplinks to other users' profiles work

**Suggested fix**:
```sql
CREATE POLICY "Users see own people or community members" ON person
    FOR SELECT USING (
        owner_id = auth.uid()
        OR community_id IN (
            SELECT community_id FROM person
            WHERE telegram_id = (auth.jwt() -> 'user_metadata' ->> 'telegram_id')::bigint
        )
    );
```

---

## Bug #5: /profile shows empty profile after Edit bug

**Severity**: Medium (consequence of Bug #1)

**Steps to reproduce**:
1. User joins community, provides intro
2. User clicks Edit, sends correction
3. Profile data is lost (Bug #1)
4. User runs `/profile`

**Actual**: Profile shows only name, no role or other info

**Root cause**: Same as Bug #1 — Edit flow loses extraction context

---

---

## Bug #6: /edit creates NEW profile instead of updating existing

**Severity**: High

**Steps to reproduce**:
1. User joins community, creates profile
2. User runs `/edit`
3. User provides new intro, confirms

**Expected**: Existing profile is updated with new assertions

**Actual**:
- NEW person record created (duplicate telegram_id + community_id)
- Assertions saved to NEW record
- /profile shows OLD empty record

**Evidence from DB**:
```
person_id 8b54dab5 (old, 06:31) → assertions = NULL
person_id ae357d42 (new, 06:48) → self_role = "политик, активист и мемолог"
```

**Root cause**: `create_community_profile()` always creates new person instead of checking for existing and updating.

**Suggested fix**:
```python
# In create_community_profile():
# 1. Check if person with telegram_id + community_id exists
# 2. If yes: UPDATE person + add new assertions
# 3. If no: CREATE new person + assertions
```

---

## Bug #7: Duplicate profiles allowed (same telegram_id + community_id)

**Severity**: Medium

**Related to**: Bug #6

**Problem**: Database allows multiple person records with same `telegram_id` and `community_id`. Should have unique constraint.

**Suggested fix**:
```sql
ALTER TABLE person ADD CONSTRAINT unique_telegram_community
    UNIQUE (telegram_id, community_id) WHERE telegram_id IS NOT NULL;
```

---

---

## Bug #8: Deep link sent as text is treated as query

**Severity**: Medium

**Steps to reproduce**:
1. User sends deep link as TEXT message (copy-paste): `https://t.me/atlantisplus_bot?start=join_INVALID123`
2. Instead of clicking the link

**Expected**: Bot should recognize deep link format and handle it (or say "click the link")

**Actual**: Bot treats it as a search query → "I couldn't find anyone matching your query"

**Root cause**: `handle_text_message()` doesn't check if message is a deep link URL before classifying as query.

**Suggested fix**:
```python
# In handle_text_message(), before classification:
if message_text.startswith('https://t.me/') and 'start=join_' in message_text:
    await send_message(chat_id, "Please click the link instead of pasting it.")
    return
```

---

## Bug #9: Community members can access search/query (should be restricted)

**Severity**: High

**Problem**: Community members (non-Atlantis+ users) can send queries and use search functionality. By design, they should only be able to manage their own profile.

**Root cause**: `handle_text_message()` doesn't check user_type before processing queries. All users are treated as full Atlantis+ members.

**Suggested fix**:
1. Check user_type at start of `handle_text_message()`
2. If `community_member` → only allow profile-related commands
3. For any other text → "You can only manage your profile. Use /profile, /edit, or /delete"

---

## Observation: /delete fixed duplicate issue

After `/delete`, the empty duplicate profile was removed, and `/profile` now correctly shows:
- Name: Жирик
- Role: политик, активист и мемолог

This confirms Bug #6 (duplicate creation) and shows that `/delete` works correctly.

---

## Testing Session: 2026-02-19

**Tester**: @evgenyq
**Environment**: Production (Railway + Cloudflare Pages)
