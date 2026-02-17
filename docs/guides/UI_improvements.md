# UI/UX Improvements Plan

## Overview

This document outlines planned UI/UX improvements for Atlantis Plus Mini App, focusing on business logic enhancements that require backend changes or significant architectural decisions.

---

## Design System: Neobrutalism

### Core Principles
- **Bold borders**: 3px solid black (white in dark mode)
- **Hard shadows**: 4px 4px 0 offset, no blur
- **High-contrast colors**: Cream (#FEF3E2) base, bold accents
- **Blocky typography**: Space Grotesk for headings, Inter for body
- **Snappy animations**: 100-200ms, ease-out, transform-based

### Color Palette
| Role | Light Mode | Dark Mode |
|------|------------|-----------|
| Background | #FEF3E2 (cream) | #1A1A1A |
| Card | #FFFFFF | #2D2D2D |
| Primary | #0066FF | #4D9FFF |
| Success | #8FFFB0 (mint) | #6BFFB0 |
| Warning | #FFE566 (yellow) | #FFE566 |
| Danger | #FF6B6B (coral) | #FF8080 |
| Accent | #C4B5FD (lavender) | #C4B5FD |

---

## Business Logic Improvements (Requires Backend)

### 1. Clickable Predicate Values for Cross-Navigation

**Current:** Predicates show static text values
**Proposed:** Certain predicate values become interactive links

#### Implementation Plan

**Predicates that should be clickable:**

| Predicate | Action on Click | Backend Change |
|-----------|-----------------|----------------|
| `works_at` (company) | Search people at same company | Add `/search?company=X` filter |
| `located_in` (city) | Search people in same city | Add `/search?location=X` filter |
| `worked_on` (project/event) | Search people from same event | Add `/search?event=X` filter |
| `contact_context` (meeting) | Search people from same meeting | Parse meeting context, match |
| `knows` (person reference) | Navigate to that person | Resolve person_id from name |

**Backend API Changes:**
```python
# GET /search?filter_type=company&filter_value=Google
# GET /search?filter_type=location&filter_value=Moscow
# GET /search?filter_type=event&filter_value=TechConf%202024

@router.get("/search/filtered")
async def search_filtered(
    filter_type: str,  # company, location, event, meeting
    filter_value: str,
    user_id: str
):
    """Search people by specific attribute value."""
    # Query assertions with matching predicate and value
    # Return people with relevance context
```

**Frontend Changes:**
```tsx
// components/AssertionBadge.tsx
interface AssertionBadgeProps {
  predicate: string;
  value: string;
  onClick?: (filterType: string, filterValue: string) => void;
}

const CLICKABLE_PREDICATES = {
  'works_at': 'company',
  'located_in': 'location',
  'worked_on': 'event',
  'contact_context': 'meeting',
};
```

**Priority:** Medium
**Effort:** 3-4 hours backend + 2 hours frontend

---

### 2. Predicate Color Coding System

**Current:** All predicates look the same (gray label)
**Proposed:** Color-coded by category for instant recognition

#### Predicate Categories

| Category | Color | Predicates |
|----------|-------|------------|
| **Role & Work** | Blue (#0066FF) | role, role_is, works_at, worked_on |
| **Skills & Expertise** | Mint (#8FFFB0) | expertise, strong_at, can_help_with |
| **Location** | Peach (#FFCBA4) | location, located_in |
| **Relationship** | Lavender (#C4B5FD) | contact_context, relationship_depth, knows |
| **Reputation** | Yellow (#FFE566) | recommend_for, reputation_note |
| **Anti-recommend** | Coral (#FF6B6B) | not_recommend_for |
| **Other** | Gray (#E5E5E5) | background, note, etc. |

**No backend changes required** - purely frontend styling.

**Priority:** High
**Effort:** 1-2 hours

---

### 3. Meeting/Event Entity Extraction

**Current:** Meetings mentioned in notes are just text in `contact_context`
**Proposed:** Extract meetings as separate entities for cross-referencing

#### Data Model Changes

```sql
-- New table for events/meetings
CREATE TABLE event (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL REFERENCES auth.users(id),
    name TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('meeting', 'conference', 'call', 'other')),
    event_date DATE,
    location TEXT,
    source_evidence_id UUID REFERENCES raw_evidence(evidence_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Link people to events
CREATE TABLE person_event (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id UUID NOT NULL REFERENCES person(person_id),
    event_id UUID NOT NULL REFERENCES event(event_id),
    role TEXT, -- speaker, attendee, organizer
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(person_id, event_id)
);
```

**Extraction Pipeline Changes:**
- Modify GPT-4o extraction prompt to identify events
- Create event records during extraction
- Link people to events via junction table

**Priority:** Low (defer to v2)
**Effort:** 6-8 hours

---

### 4. Smart Deduplication UI

**Current:** System detects duplicates but no UI to resolve
**Proposed:** Merge suggestions card in People view

#### UI Flow

1. Show "Possible duplicates" banner at top of PeoplePage
2. Banner shows: "We found 3 possible duplicate contacts"
3. Click → Modal with side-by-side comparison
4. User picks: "Merge", "Keep Both", "Ignore"

**Backend exists:** `person_match_candidate` table
**Frontend needed:** DuplicateReviewModal component

**Priority:** Medium
**Effort:** 4-5 hours frontend

---

### 5. Enrichment Source Attribution

**Current:** Enriched data shows "External data" label
**Proposed:** Show source (People Data Labs) with confidence

#### UI Changes

```tsx
// In person detail, show enrichment source
<div className="enrichment-source">
  <span className="source-badge">PDL</span>
  <span className="confidence">High confidence</span>
  <span className="enriched-date">Enriched Jan 15, 2024</span>
</div>
```

**Backend Changes:**
- Store `enrichment_source` in assertion metadata
- Store `enrichment_confidence` score

**Priority:** Low
**Effort:** 2 hours

---

### 6. Assertion Voting/Correction System

**Current:** Users can only delete assertions
**Proposed:** Users can mark assertions as correct/incorrect

#### Data Model

```sql
ALTER TABLE assertion ADD COLUMN user_verified BOOLEAN;
ALTER TABLE assertion ADD COLUMN user_correction TEXT;
```

**UI:**
- Each assertion shows thumbs up/down icons
- Thumbs down opens correction modal
- Corrections update the assertion or create override

**Priority:** Medium (v2)
**Effort:** 4-5 hours

---

## Frontend-Only Improvements (No Backend)

### 7. Replace Emojis with Custom Icons

**Status:** In Progress

Create SVG icon set for:
- Navigation: people, notes, chat, import
- Actions: record, stop, search, send, edit, delete
- Status: done, error, processing, pending
- Contact types: email, linkedin, telegram, phone, calendar

**Priority:** Critical
**Effort:** 3-4 hours

---

### 8. Search Query History

**Implementation:**
```typescript
// lib/searchHistory.ts
const STORAGE_KEY = 'atlantis_search_history';
const MAX_HISTORY = 10;

export function addToHistory(query: string) {
  const history = getHistory();
  const filtered = history.filter(q => q !== query);
  const updated = [query, ...filtered].slice(0, MAX_HISTORY);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
}

export function getHistory(): string[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
  } catch {
    return [];
  }
}
```

**Priority:** Low
**Effort:** 1 hour

---

### 9. Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Cmd/Ctrl + K` | Focus search |
| `Cmd/Ctrl + N` | New note |
| `Escape` | Close modal / Go back |
| `Enter` | Submit form |

**Priority:** Low
**Effort:** 2 hours

---

### 10. Pull-to-Refresh

Use `react-pull-to-refresh` or custom implementation for:
- PeoplePage: Refresh contact list
- NotesPage: Refresh evidence list
- ChatPage: Refresh session

**Priority:** Low
**Effort:** 2 hours

---

## Implementation Order

### Phase 1: Visual Overhaul (This Sprint)
1. [x] Neobrutalism design system (colors, typography, shadows)
2. [x] Replace emojis with SVG icons
3. [x] Predicate color coding
4. [x] Button component standardization
5. [x] Improve empty states

### Phase 2: Interaction Polish (Next Sprint)
6. [ ] Clickable predicate values (needs backend)
7. [ ] Loading states and skeletons
8. [ ] Toast notifications
9. [ ] Search history
10. [ ] Keyboard shortcuts

### Phase 3: Advanced Features (Backlog)
11. [ ] Duplicate resolution UI
12. [ ] Meeting/event extraction
13. [ ] Assertion voting
14. [ ] Pull-to-refresh
15. [ ] Data visualizations

---

## Design Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2024-02-12 | Neobrutalism style | Professional yet distinctive; works well with Telegram constraints |
| 2024-02-12 | Space Grotesk + Inter fonts | Blocky headings + readable body text |
| 2024-02-12 | 3px borders standard | Balance between bold and not overwhelming |
| 2024-02-12 | Cream (#FEF3E2) as base | Warm, professional, less harsh than pure white |

---

## References

- [Neobrutalism Design System Guide](internal)
- [Telegram Mini App Design Guidelines](https://core.telegram.org/bots/webapps#design-guidelines)
- [WCAG 2.1 Accessibility Guidelines](https://www.w3.org/WAI/WCAG21/quickref/)
