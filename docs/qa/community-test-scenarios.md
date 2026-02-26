# Community E2E Test Scenarios

> Manual E2E testing scenarios for Community Intake Mode.
> Use with 2 accounts: **Owner** (@atlantisplus_bot creator) and **Member** (external account).

**Bot**: @atlantisplus_bot
**Mini App**: https://atlantisplus.pages.dev

---

## Prerequisites

### Accounts Setup
- **Owner Account**: Telegram account with Atlantis+ membership (can create communities)
- **Member Account**: Secondary Telegram account (external user joining community)

### Test Environment
- Both accounts should have access to @atlantisplus_bot
- Mini App should be accessible: https://atlantisplus.pages.dev
- Backend service running and healthy

---

## Scenario 1: Create New Community

**Role**: Owner
**Preconditions**:
- Owner is logged into Telegram
- Owner has Atlantis+ membership (can create communities)

**Steps**:
1. Open @atlantisplus_bot
2. Send `/newcommunity` command
3. Bot responds: "What's the name of your community?"
4. Send community name: "Test Community QA"
5. Bot responds with confirmation and invite link

**Expected Result**:
- Bot shows success message:
  ```
  Community created!

  Test Community QA

  Invite link for members:
  https://t.me/atlantisplus_bot?start=join_XXXXXX
  ```
- Invite code is 12 characters (hex format)
- Link is clickable and valid

**Verification**:
- Open Mini App
- Navigate to Communities page
- Verify "Test Community QA" appears in the list
- Member count shows 0

---

## Scenario 2: Get Invite Link from Mini App

**Role**: Owner
**Preconditions**:
- Community "Test Community QA" exists
- Owner logged into Mini App

**Steps**:
1. Open Mini App: https://atlantisplus.pages.dev
2. Navigate to Communities tab/page
3. Click on "Test Community QA"
4. Find and copy invite link

**Expected Result**:
- Community detail page shows:
  - Community name
  - Description (if set)
  - Member count
  - Invite link: `https://t.me/atlantisplus_bot?start=join_XXXXXX`
- Copy button works correctly
- Link format is valid

---

## Scenario 3: Member Join Flow - Basic (Deep Link)

**Role**: Member
**Preconditions**:
- Member has invite link from Scenario 1/2
- Member has NOT joined this community before

**Steps**:
1. Click invite link: `https://t.me/atlantisplus_bot?start=join_XXXXXX`
2. Telegram opens @atlantisplus_bot with START button
3. Click START
4. Bot shows welcome message with community name
5. Bot asks for self-introduction

**Expected Result**:
- Bot message:
  ```
  Welcome to Test Community QA!

  [Community description if exists]

  Tell us about yourself - this will help other members find you.

  Write a short intro or send a voice message:
  - Your name and what you do
  - What you can help with
  - What you're looking for
  ```
- User is in "awaiting_intro" state (persisted in DB)

---

## Scenario 4: Text Input Profile Creation

**Role**: Member
**Preconditions**:
- Member completed Scenario 3 (saw welcome message)
- Member is in awaiting_intro state

**Steps**:
1. Type self-introduction: "Hi, I'm Alex, a product manager at Google. I can help with product strategy and user research. Looking for connections in AI/ML space."
2. Wait for extraction processing
3. Review extracted profile
4. Click "Confirm" button

**Expected Result**:

After sending text:
- Bot shows "Processing your introduction..."
- Bot shows extracted profile:
  ```
  Here's what I understood:

  Alex
  Product Manager at Google
  Can help with: product strategy, user research
  Looking for: connections in AI/ML space

  Is this correct?
  [Confirm] [Edit]
  ```

After clicking Confirm:
- Bot shows welcome confirmation:
  ```
  Welcome to Test Community QA!

  Your profile has been created:
  Alex

  Commands:
  /profile - view your profile
  /edit - update your profile
  /delete - remove your profile
  ```
- Profile is saved in database (person + assertions)

---

## Scenario 5: Voice Input Profile Creation

**Role**: Member
**Preconditions**:
- Member clicked invite link and saw welcome message
- Member is in awaiting_intro state

**Steps**:
1. Record voice message: "Hi everyone, my name is Maria. I work as a senior engineer at Meta. I'm strong in distributed systems and can help with system design interviews. I'm looking for startup founders to advise."
2. Send voice message
3. Wait for transcription and extraction
4. Review extracted profile
5. Click "Confirm" button

**Expected Result**:

After sending voice:
- Bot shows "Processing your voice message..."
- Bot shows "Processing your introduction..."
- Bot shows extracted profile with:
  - Name: Maria
  - Role: Senior Engineer at Meta
  - Can help with: distributed systems, system design interviews
  - Looking for: startup founders to advise

After clicking Confirm:
- Profile created successfully
- Member sees welcome message with commands

**Technical Verification**:
- Voice file uploaded to Supabase Storage (join_temp/)
- Transcription completed via Whisper
- Temp file cleaned up after processing

---

## Scenario 6: Confirmation Flow - Edit Option

**Role**: Member
**Preconditions**:
- Member sent intro text/voice
- Bot showing confirmation with [Confirm] [Edit] buttons

**Steps**:
1. Click "Edit" button
2. Bot asks for corrected introduction
3. Send corrected intro: "I'm Alex Chen, Head of Product at Google Cloud. Expert in B2B product strategy."
4. Review new extraction
5. Click "Confirm"

**Expected Result**:

After clicking Edit:
- Bot shows: "Please send your corrected introduction. Tell us about yourself again:"
- User returns to awaiting_intro state

After sending correction:
- Bot shows updated extracted profile:
  ```
  Alex Chen
  Head of Product at Google Cloud
  Can help with: B2B product strategy
  ```
- User can confirm or edit again

---

## Scenario 7: Incomplete Profile - Follow-up Prompt

**Role**: Member
**Preconditions**:
- Member clicked invite link

**Steps**:
1. Send minimal intro: "My name is John"
2. Review extraction (should be minimal)
3. Click "Confirm"

**Expected Result**:

After confirmation:
- Bot shows success but suggests additions:
  ```
  Welcome to Test Community QA!

  Your profile has been created:
  John

  Want to add more?
  Your profile would be stronger with: what you do, what you can help with, what you're looking for.

  Send another voice or text message to add more details,
  or use /profile to see your current profile.
  ```

---

## Scenario 8: First-Person Detection - Note About Someone Else

**Role**: Member
**Preconditions**:
- Member clicked invite link
- Member in awaiting_intro state

**Steps**:
1. Send message about someone else: "My friend Alex works at OpenAI as a researcher. He's great at ML and knows everyone in the AI community."
2. Wait for extraction
3. Bot detects third-person narrative
4. Click "It's about me" or "Save as note"

**Expected Result**:

After sending third-person text:
- Bot shows:
  ```
  This looks like a note about someone else, not about yourself.

  In join mode, we need YOUR introduction.
  Is this actually about you?

  [It's about me] [Save as note]
  ```

If "It's about me" clicked:
- Bot proceeds with confirmation flow for extracted data

If "Save as note" clicked:
- Bot says: "Got it! This will be saved as a regular note. To create your profile, please send a new message about yourself."
- User returns to awaiting_intro state

---

## Scenario 9: /profile Command

**Role**: Member
**Preconditions**:
- Member has completed join flow
- Member has a profile in at least one community

**Steps**:
1. Send `/profile` command to bot

**Expected Result**:
- Bot shows current profile:
  ```
  Your profile in Test Community QA

  Name: Alex Chen
  Role: Head of Product at Google Cloud
  Can help with: B2B product strategy
  Looking for: [not set]

  /edit - update profile
  /delete - remove profile
  ```

---

## Scenario 10: /edit Command

**Role**: Member
**Preconditions**:
- Member has a profile in community

**Steps**:
1. Send `/edit` command
2. Bot prompts for new introduction
3. Send updated intro: "Alex Chen, now VP of Product at Google Cloud. Can help with executive coaching and product leadership."
4. Confirm new profile

**Expected Result**:

After /edit:
- Bot shows:
  ```
  Edit your profile in Test Community QA

  Send me a new introduction (text or voice).
  This will add to your existing profile.
  ```
- User enters awaiting_intro state with is_edit=true

After sending new intro:
- Bot shows updated extraction for confirmation
- After confirm, profile updated with new assertions

---

## Scenario 11: /delete Command

**Role**: Member
**Preconditions**:
- Member has a profile in community

**Steps**:
1. Send `/delete` command
2. Bot asks for confirmation
3. Click "Delete" button

**Expected Result**:

After /delete:
- Bot shows:
  ```
  Delete your profile?

  This will remove your profile from Test Community QA.

  Profile: Alex Chen

  [Delete] [Cancel]
  ```

After clicking Delete:
- Bot confirms: "Your profile has been deleted. You can rejoin the community anytime using the invite link."
- Person status set to "deleted" in database

After clicking Cancel:
- Bot shows: "Deletion cancelled."
- No changes made

---

## Scenario 12: View Members in Mini App (Owner)

**Role**: Owner
**Preconditions**:
- Community has at least one member
- Owner logged into Mini App

**Steps**:
1. Open Mini App: https://atlantisplus.pages.dev
2. Navigate to Communities page
3. Click on "Test Community QA"
4. View members list

**Expected Result**:
- Community detail page shows:
  - Community name and description
  - Invite link (with copy button)
  - Member count (accurate)
  - List of members with:
    - Display name
    - Join date
    - Quick view of profile assertions

---

## Scenario 13: Member Mini App View (Community Member)

**Role**: Member
**Preconditions**:
- Member has completed join flow
- Member has profile in community

**Steps**:
1. Member opens Mini App: https://atlantisplus.pages.dev

**Expected Result**:
- Member sees SelfProfilePage (not full Atlantis+ UI)
- Shows their own profile:
  - Name
  - Role
  - Can help with
  - Looking for
- Edit button available
- NO access to:
  - People tab
  - Notes tab
  - Chat tab
  - Communities management

---

## Edge Cases

---

## Scenario 14: Repeat Join - Already a Member

**Role**: Member
**Preconditions**:
- Member already joined "Test Community QA"
- Member has active profile

**Steps**:
1. Click same invite link again
2. Telegram opens bot with START

**Expected Result**:
- Bot shows:
  ```
  Welcome back to Test Community QA!

  You already have a profile: Alex Chen

  Use /profile to view or edit your profile.
  ```
- No duplicate profile created
- User NOT put into awaiting_intro state

---

## Scenario 15: Invalid Invite Code

**Role**: Member
**Preconditions**:
- Have invalid/expired invite code

**Steps**:
1. Click link with invalid code: `https://t.me/atlantisplus_bot?start=join_invalidcode`
2. Telegram opens bot

**Expected Result**:
- Bot shows:
  ```
  This invite link is invalid or expired.
  Please ask for a new link from the community owner.
  ```
- No state created
- User can use bot normally

---

## Scenario 16: State Persistence After Bot Restart

**Role**: Member
**Preconditions**:
- Member clicked invite link
- Member is in awaiting_intro state
- **Backend service restarted** (simulating redeploy)

**Steps**:
1. Send intro text after service restart
2. Bot processes introduction

**Expected Result**:
- State is recovered from database (pending_join table)
- Profile creation works normally
- No error messages
- Confirmation flow completes successfully

**Technical Note**: This tests the DB-backed state (not in-memory) persistence.

---

## Scenario 17: Expired Join State (1 hour timeout)

**Role**: Member
**Preconditions**:
- Member clicked invite link more than 1 hour ago
- Did not complete profile

**Steps**:
1. Send intro text after 1+ hour delay

**Expected Result**:
- Join state expired (cleanup_expired_pending_joins RPC)
- Message treated as regular text (not join flow)
- User needs to click invite link again to restart

**Note**: Difficult to test manually, requires DB manipulation or waiting.

---

## Scenario 18: /newcommunity Without Permission

**Role**: External user (NOT Atlantis+ member)
**Preconditions**:
- User does not have can_create_community permission

**Steps**:
1. Send `/newcommunity` command

**Expected Result**:
- Bot shows:
  ```
  Sorry, only Atlantis+ members can create communities.

  Contact the admin to get access.
  ```
- No community creation flow started

---

## Scenario 19: Regenerate Invite Code (API)

**Role**: Owner
**Preconditions**:
- Community exists
- Owner has valid auth token

**Steps**:
1. Call API: `POST /communities/{community_id}/regenerate-invite`
2. Get new invite code

**Expected Result**:
- API returns:
  ```json
  {
    "invite_code": "new_12_char_hex",
    "invite_url": "https://t.me/atlantisplus_bot?start=join_new_12_char_hex"
  }
  ```
- Old invite code immediately invalid
- New code works for joining

---

## Scenario 20: Member Tries to Join Deactivated Community

**Role**: Member
**Preconditions**:
- Community was deactivated by owner
- Member has old invite link

**Steps**:
1. Click old invite link

**Expected Result**:
- Bot shows:
  ```
  This invite link is invalid or expired.
  Please ask for a new link from the community owner.
  ```
- Community lookup fails (is_active = false filter)

---

## API Test Scenarios

---

## Scenario 21: API - List Communities

**Role**: Owner
**Endpoint**: `GET /communities`

**Steps**:
```bash
curl -X GET https://atlantisplus-production.up.railway.app/communities \
  -H "Authorization: Bearer {token}"
```

**Expected Result**:
```json
[
  {
    "community_id": "uuid",
    "name": "Test Community QA",
    "description": null,
    "invite_code": "xxxxxx",
    "telegram_channel_id": null,
    "is_active": true,
    "created_at": "...",
    "updated_at": "...",
    "member_count": 3
  }
]
```

---

## Scenario 22: API - Get Community Members

**Role**: Owner
**Endpoint**: `GET /communities/{community_id}/members`

**Steps**:
```bash
curl -X GET https://atlantisplus-production.up.railway.app/communities/{id}/members \
  -H "Authorization: Bearer {token}"
```

**Expected Result**:
```json
[
  {
    "person_id": "uuid",
    "display_name": "Alex Chen",
    "telegram_id": 123456789,
    "created_at": "..."
  },
  {
    "person_id": "uuid",
    "display_name": "Maria",
    "telegram_id": 987654321,
    "created_at": "..."
  }
]
```

---

## Scenario 23: API - Access Denied for Non-Owner

**Role**: Member (NOT owner)
**Endpoint**: `GET /communities/{community_id}`

**Steps**:
```bash
curl -X GET https://atlantisplus-production.up.railway.app/communities/{other_community_id} \
  -H "Authorization: Bearer {member_token}"
```

**Expected Result**:
- HTTP 403 Forbidden
- Body: `{"detail": "Access denied"}`

---

## Test Data Cleanup

After testing, clean up test data:

```sql
-- Find test community
SELECT community_id, name FROM community WHERE name = 'Test Community QA';

-- Delete test profiles
DELETE FROM person WHERE community_id = '<test_community_id>';

-- Delete test community
DELETE FROM community WHERE name = 'Test Community QA';

-- Clean up pending joins
DELETE FROM pending_join WHERE community_id = '<test_community_id>';
```

---

## Test Results Template

| Scenario | Status | Date | Notes |
|----------|--------|------|-------|
| 1. Create Community | | | |
| 2. Get Invite Link | | | |
| 3. Member Join (Deep Link) | | | |
| 4. Text Input Profile | | | |
| 5. Voice Input Profile | | | |
| 6. Confirmation Edit | | | |
| 7. Incomplete Profile | | | |
| 8. First-Person Detection | | | |
| 9. /profile Command | | | |
| 10. /edit Command | | | |
| 11. /delete Command | | | |
| 12. View Members (Owner) | | | |
| 13. Member Mini App View | | | |
| 14. Repeat Join | | | |
| 15. Invalid Code | | | |
| 16. State Persistence | | | |
| 17. Expired State | | | |
| 18. No Permission | | | |
| 19. Regenerate Code | | | |
| 20. Deactivated Community | | | |
| 21. API List Communities | | | |
| 22. API Get Members | | | |
| 23. API Access Denied | | | |

**Status Legend**: PASS / FAIL / BLOCKED / SKIP
