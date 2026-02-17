# Project Structure Analysis Report
**Date**: 2026-02-16

## Executive Summary

Проект в целом хорошо организован, но есть проблемы с **документацией** (34 файла без структуры) и **тестовыми данными** (смешаны с кодом).

---

## Critical Issues

### 1. QA Script in Project Root
- **File**: `/qa_company_search.py`
- **Problem**: Testing script в корне проекта
- **Action**: Move to `service/tests/qa/`

### 2. Test Data Mixed with Test Code
- **Location**: `service/tests/`
- **Problem**: 7 .ics файлов и zip рядом с test_*.py
- **Action**: Create `service/tests/fixtures/calendars/`

### 3. Hardcoded API Key in QA Script
- **File**: `qa_company_search.py:11-12`
- **Problem**: Service role key в plaintext (файл в gitignore, но риск при шаринге)
- **Action**: Delete file or use env vars

---

## Warning Issues

### 4. Documentation Directory Chaos
- **Location**: `/docs/` — 34 files
- **Problems**:
  - No structure (все в одной папке)
  - Inconsistent naming (snake_case vs kebab-case)
  - Multiple similar reports (3 QA summary files)
  - HTML exports that should be markdown
- **Recommended structure**:
```
docs/
├── README.md              # Index
├── qa/                    # All QA reports
├── planning/              # Architecture, plans
├── code-reviews/          # Code review docs
├── guides/                # How-to guides
└── reference/             # Examples, specs
```

### 5. Duplicate Docs in service/docs/
- **Files**:
  - `service/docs/qa_report_chat_claude_endpoint.md`
  - `service/docs/qa-person-search-comparison.md`
- **Action**: Move to `/docs/qa/`, delete `service/docs/`

---

## Suggestions

| Issue | Location | Action |
|-------|----------|--------|
| Missing docs index | `/docs/` | Create README.md with TOC |
| Shell test script | `service/tests/company_search_test.sh` | Convert to pytest or move to scripts/ |
| E2E seed data | `e2e/seed-test-data.sql` | Move to `supabase/seeds/` |
| Undocumented .claude/ | `/.claude/` | Add README explaining purpose |

---

## Quick Wins (Priority Order)

1. **Create `/docs/README.md`** — 15 min, immediate navigation improvement
2. **Move QA script** — `qa_company_search.py` → `service/tests/qa/`
3. **Reorganize docs/** — Create subdirectories for qa/, planning/, guides/
4. **Create test fixtures/** — Separate test data from test code
5. **Consolidate service/docs/** — Move to main docs/

---

## What's Good

- ✅ Proper `.gitignore` configuration
- ✅ Clear separation: service/ frontend/ e2e/ supabase/
- ✅ Standard directory names
- ✅ Tests in separate directories
- ✅ .env.example files exist
- ✅ Supabase migrations organized
