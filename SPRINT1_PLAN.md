# Sprint 1: Input Pipeline

## Статус Sprint 0: ЗАВЕРШЁН ✅
- Python service работает (localhost:8000)
- Frontend работает (localhost:5173)
- Supabase схема применена
- Storage bucket создан
- .env файлы заполнены

## Задачи Sprint 1

### Backend (Python service)

1. **Transcription service** (`app/services/transcription.py`)
   - Whisper API интеграция
   - Скачивание аудио из Supabase Storage

2. **Extraction service** (`app/services/extraction.py`)
   - GPT-4o extraction pipeline
   - Промпт из CLAUDE.md
   - Pydantic схемы для output

3. **Embedding service** (`app/services/embedding.py`)
   - text-embedding-3-small
   - Генерация embeddings для assertions

4. **Process endpoints** (`app/api/process.py`)
   - POST /process/voice
   - POST /process/text
   - Background processing с asyncio.create_task

### Frontend

5. **VoiceRecorder component** (`src/components/VoiceRecorder.tsx`)
   - MediaRecorder API
   - Upload в Supabase Storage

6. **NotesPage** (`src/pages/NotesPage.tsx`)
   - Переключение голос/текст
   - Отправка на обработку

7. **Realtime подписка**
   - Статус обработки raw_evidence
   - UI индикаторы

## Команда для продолжения

```
Прочитай SPRINT1_PLAN.md и продолжи реализацию Sprint 1.
Начни с backend services (transcription, extraction, embedding).
```

## Запуск сервисов

```bash
# Python service
cd /Users/evgenyq/Projects/atlantisplus/service
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend (в другом терминале)
cd /Users/evgenyq/Projects/atlantisplus/frontend
npm run dev
```
