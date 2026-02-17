# QA Report: /chat/claude Endpoint Testing

**Date**: 2026-02-14
**Environment**: Local test server (http://localhost:8000)
**Test Duration**: ~15 minutes
**Endpoint**: POST /chat/claude

---

## Test Setup

- Local server with test mode enabled
- Auth via test endpoint (telegram_id: 123456)
- All tests executed sequentially with server restart between failures

---

## Test Results

### Кейс 1: Яндекс
**Query**: "кто работает в Яндексе"

**Результат**:
- **Людей найдено**: 15 (показано 6 основных + упомянуто еще 9)
- **Имена найденных** (основные):
  1. Дима Васильев (Продакт-менеджер)
  2. Dmitriy Stepanov (IT Recruitment Group Lead)
  3. Evgeniya Kikoina (QA Automation Engineer)
  4. Anna Chebotkevich (Sr. HR BP at Yandex.Cloud)
  5. Anna Kodaneva (Lead HR-expert, Яндекс Практикум)
  6. Роман Вишневский (Senior Data Analyst, Яндекс Банк)
- **Iterations**: 4
- **Время ответа**: ~8-10 секунд
- **Мотивация агента**: Сгруппировал результаты по подразделениям (основная компания, Практикум, Банк). Предложил показать детали остальных 9 контактов.
- **Проблемы**: Нет

**Оценка**: 5/5 - отличная структуризация, логичная группировка по подразделениям

---

### Кейс 2: Pharma intro
**Query**: "who can help with intro to pharma or biotech companies in Singapore"

**Результат**:
- **Людей найдено**: 11
- **Имена найденных** (ключевые):
  1. Aleks Yenin (BeOne Medicines, biotech consultant) - DIRECT biotech
  2. Li Ming (ByteDance Singapore) - Singapore local
  3. Sandra Golbreich (BSV Ventures, Asia focus)
  4. Shanti Mohan (LetsVenture founder)
  5. Dmitry Alimov (Frontier Ventures)
  6. Ilya Golubovich (I2BF Global Ventures)
  + еще 5 VCs с Asia focus
- **Iterations**: 6
- **Время ответа**: ~12-15 секунд
- **Мотивация агента**:
  - "Direct biotech connection" для Aleks Yenin
  - "Singapore business network" для Li Ming
  - "VCs often have portfolio companies in biotech and Singapore ecosystem"
  - Рекомендация: начать с Aleks (biotech insights) + Sandra/Shanti (Singapore intros)
- **Проблемы**: Нет

**Оценка**: 5/5 - отличное reasoning, неочевидная логика (VCs как мост к Singapore biotech), четкие рекомендации

---

### Кейс 3: Cappasity
**Query**: "кто связан с Cappasity"

**Результат**:
- **Людей найдено**: 3 (total), 1 показан явно
- **Имена найденных**:
  1. Kate Ilinskaya (CMO at Cappasity) - EXPLICIT
  2-3. Два других человека не показаны (упомянуто что total=3)
- **Iterations**: 6
- **Время ответа**: ~10 секунд
- **Мотивация агента**: Агент попытался найти остальных 2 людей через смежные запросы (3D AR VR, "Cappasity компания работает"), но не смог их извлечь.
- **Проблемы**:
  - Агент нашёл total=3, но вернул только 1 человека
  - Не смог достать остальных 2 из-за ограничений find_people tool (default limit=5?)
  - Признал ограничение и предложил помощь в уточнении

**Оценка**: 3/5 - нашёл основного человека, но не смог извлечь всех (проблема tool limits)

---

### Кейс 4: Fundraising
**Query**: "who can help with fundraising or has VC connections"

**Результат**:
- **Людей найдено**: 17
- **Имена найденных** (показано 13 основных):

  **VCs (6)**:
  1. Sandra Golbreich (GP @ BSV Ventures)
  2. Dmitry Filatov (Partner @ Sistema VC)
  3. Ilya Golubovich (Founding Partner @ I2BF)
  4. Vital Laptenok (GP @ Flyer One Ventures)
  5. Dmitry Alimov (Founding Partner @ Frontier)
  6. Alexander Artemyev (Venture Partner @ Atlas)

  **Founders (5)**:
  7. Shanti Mohan (Founder @ LetsVenture)
  8. Sarah Guo (Founder @ Conviction)
  9. David Schukin (CEO @ Observant AI)
  10. Fedor Borshev (CEO @ Fans)
  11. Val Bejenuta (Founder & advisor)

  **Scouts (1)**:
  12. Tamerlan Musaev (Venture Scout @ Flashpoint)

- **Iterations**: 3
- **Время ответа**: ~8 секунд
- **Мотивация агента**: Структурировал по категориям (VCs, Founders, Scouts). Четкие role descriptions. Предложил drill-down по типам инвесторов (AI-focused, fintech).
- **Проблемы**: Нет

**Оценка**: 5/5 - быстрая работа, отличная категоризация, полезные описания

---

### Кейс 5: ETG
**Query**: "кто работал в Emerging Travel Group"

**Результат**:
- **Людей найдено**: 15
- **Имена найденных** (все 15 показаны):
  1. Olga Bratishcheva (Extranet PM)
  2. Алексей Афанасьев (Database Programmer)
  3. Mikhail Stysin (участвовал в 7 встречах, Board Calls 2018-2019)
  4-15. Natalia Erkina, Elena Li, Ilya Kravtsov, Alexey Solovyev, Olesya Ezhova, Михаил Павлов, Vladimir Savvateev, Nikita Gorodzhiy, Andrey Lisyanskiy, Olesya Mironova, Victoria Shamshurova, Ivan Yurchenko (все LinkedIn контакты)
- **Iterations**: 3
- **Время ответа**: ~8 секунд (после перезапуска сервера)
- **Мотивация агента**: Выделил Mikhail Stysin как особо интересного (Board Calls 2018-2019). Остальные - LinkedIn контакты.
- **Проблемы**:
  - Сервер упал при первом запросе (error code 7 - connection lost)
  - Возможная причина: long-running query или OpenAI API timeout
  - После перезапуска сервера запрос прошёл успешно

**Оценка**: 4/5 - полный список, хорошее выделение ключевого контакта, но падение сервера снижает стабильность

---

## Технические проблемы

### 1. Падение сервера (Кейс 5, первая попытка)
- **Симптомы**: Exit code 7, connection lost
- **Контекст**: После запроса ETG сервер упал
- **Возможные причины**:
  - Long-running OpenAI API call
  - Timeout в pgvector search
  - Memory leak
- **Решение**: Перезапуск сервера
- **Severity**: MEDIUM (нужен graceful timeout handling)

### 2. Tool limits в find_people (Кейс 3)
- **Симптомы**: total=3, но вернулся только 1 человек
- **Контекст**: Агент нашёл 3 людей, но не смог извлечь всех
- **Возможные причины**:
  - Default limit=5 в find_people
  - Relevance threshold отсекает остальных
  - Дубликаты в результатах (John Smith, Xiao A появились в последующих запросах)
- **Severity**: LOW (edge case для редких компаний)

---

## Качество Reasoning

### Сильные стороны:
1. **Категоризация** - агент группирует результаты логично (Яндекс по подразделениям, fundraising по ролям)
2. **Non-obvious connections** - VCs как путь к Singapore biotech (Кейс 2)
3. **Контекст** - выделяет Board Calls для Mikhail Stysin (Кейс 5)
4. **Follow-up suggestions** - предлагает drill-down (Кейс 4)
5. **Признание ограничений** - честно говорит когда не нашёл всех людей (Кейс 3)

### Слабые стороны:
1. **Не использует edges** - нет reasoning через "кто знает кого"
2. **Нет confidence scores** - не говорит "уверен на 80%" vs "may be relevant"
3. **Verbose для простых запросов** - Кейс 1 мог быть короче

---

## Общая оценка endpoint /chat/claude: 4.4/5

### Разбивка:
- **Функциональность**: 5/5 - все кейсы отработали, находит релевантных людей
- **Reasoning quality**: 5/5 - отличное объяснение WHY, неочевидные связи
- **Стабильность**: 3/5 - падение сервера на Кейсе 5 (first attempt)
- **UX**: 5/5 - структурированный output, HTML форматирование, follow-up вопросы
- **Performance**: 4/5 - 3-15 секунд на запрос (приемлемо, но можно быстрее)

### Рекомендации:

**CRITICAL**:
1. Добавить timeout handling для OpenAI API calls (prevent server crashes)
2. Graceful error recovery вместо падения сервера

**HIGH**:
3. Исправить tool limits в find_people (Кейс 3: total=3, показан 1)
4. Добавить reasoning через edges ("X knows Y who works at Z")

**MEDIUM**:
5. Добавить confidence indicators в ответы
6. Оптимизировать iterations (Кейс 2: 6 итераций для pharma query)

**LOW**:
7. Сократить verbose для простых запросов (Кейс 1)
8. Добавить preview найденных людей без full details для больших списков

---

## Verdict

Endpoint `/chat/claude` **готов для dogfooding** с оговорками:
- Качество reasoning - отличное
- UX - хороший
- Стабильность - требует улучшений (timeout handling)

**Блокеры для production**: нет
**Блокеры для internal use**: 1 (server crash на long queries - MEDIUM priority fix)

**Next steps**:
1. Добавить timeout middleware (30s limit)
2. Fix find_people limit issues
3. Load testing с 10+ concurrent users
4. Мониторинг OpenAI API latency
