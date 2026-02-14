# Company Search Test Results

**Test Date:** Sat Feb 14 14:06:42 MSK 2026
**Server:** http://localhost:8000

---


## Query: "кто работает в Google?"

### OpenAI (/chat)
```json
jq: parse error: Invalid numeric literal at line 1, column 8
Testing: OpenAI with query: кто работает в Google?
{"session_id":"4af6e44b-666e-4901-ac7a-2b5ae583a3ee","message":"Кажется, что в вашей сети нет людей, работающих в Google. Если у вас есть другая информация или запрос, пожалуйста, дайте знать!","tool_results":[{"tool":"find_people","args":{"query":"Google"},"result":"{\n  \"people\": [],\n  \"total\": 63,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"}]}
```

### Claude (/chat/claude)
```json
jq: parse error: Invalid numeric literal at line 1, column 8
Testing: Claude with query: кто работает в Google?
{"message":"К сожалению, поиск не находит людей с информацией о работе в Google в вашей базе контактов. Это может означать, что:\n\n1. В вашей сети пока нет контактов, работающих в Google\n2. Информация о работе в Google не была указана в их профилях\n3. Данные могут быть записаны в другом формате\n\nХотите, чтобы я попробовал поискать по другим терминам (например, \"инженер\", \"разработчик\", \"технологии\") или у вас есть конкретные имена людей, которые могут работать в Google?","tool_calls":[{"tool":"find_people","args":{"query":"Google"},"result_preview":"{\n  \"people\": [],\n  \"total\": 63,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"},{"tool":"find_people","args":{"query":"Google работает компания"},"result_preview":"{\n  \"people\": [],\n  \"total\": 81,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"},{"tool":"find_people","args":{"query":"Google company works"},"result_preview":"{\n  \"people\": [],\n  \"total\": 42,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"}],"iterations":4,"found_people":[]}
```

---


## Query: "кто из Yandex?"

### OpenAI (/chat)
```json
jq: parse error: Invalid numeric literal at line 1, column 8
Testing: OpenAI with query: кто из Yandex?
{"session_id":"6fa66dfc-e24c-4419-8805-d4de53de3adf","message":"Похоже, что у меня нет информации о людях из Yandex в вашей сети. Если у вас есть более конкретные критерии поиска, пожалуйста, дайте знать!","tool_results":[{"tool":"find_people","args":{"query":"Yandex"},"result":"{\n  \"people\": [],\n  \"total\": 107,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"}]}
```

### Claude (/chat/claude)
```json
jq: parse error: Invalid numeric literal at line 1, column 8
Testing: Claude with query: кто из Yandex?
{"message":"Система показывает, что в базе есть люди связанные с Yandex (от 37 до 109 в зависимости от запроса), но по какой-то причине не возвращает конкретные результаты. \n\nВозможно, есть техническая проблема с отображением результатов поиска по Yandex. Могу попробовать найти людей другими способами - например, если вы помните имена или другие детали о сотрудниках Yandex, которых ищете?","tool_calls":[{"tool":"find_people","args":{"query":"Yandex"},"result_preview":"{\n  \"people\": [],\n  \"total\": 107,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"},{"tool":"find_people","args":{"query":"Yandex Яндекс","limit":20},"result_preview":"{\n  \"people\": [],\n  \"total\": 109,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"},{"tool":"find_people","args":{"query":"Яндекс"},"result_preview":"{\n  \"people\": [],\n  \"total\": 39,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"},{"tool":"find_people","args":{"query":"работает Яндекс"},"result_preview":"{\n  \"people\": [],\n  \"total\": 37,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"}],"iterations":5,"found_people":[]}
```

---


## Query: "найди людей из ByteDance"

### OpenAI (/chat)
```json
jq: parse error: Invalid numeric literal at line 1, column 8
Testing: OpenAI with query: найди людей из ByteDance
{"session_id":"21e25102-3932-4ca4-aae9-697b233a5789","message":"Извините, но я не смог найти людей, связанных с ByteDance. Возможно, у вас нет информации о них в вашей сети. Если у вас есть другие запросы, дайте знать!","tool_results":[{"tool":"find_people","args":{"query":"ByteDance"},"result":"{\n  \"people\": [],\n  \"total\": 13,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"}]}
```

### Claude (/chat/claude)
```json
jq: parse error: Invalid numeric literal at line 1, column 8
Testing: Claude with query: найди людей из ByteDance
{"message":"К сожалению, в вашей базе контактов не найдено людей, связанных с ByteDance или TikTok. \n\nВозможные причины:\n- В базе нет контактов из этой компании\n- Информация о работе в ByteDance не была импортирована\n- Компания указана под другим названием в профилях\n\nХотите:\n1. Добавить информацию о ком-то из ByteDance?\n2. Попробовать поиск по другим критериям (например, по имени конкретного человека)?\n3. Посмотреть статистику импорта контактов, чтобы понять, какие источники данных у вас есть?","tool_calls":[{"tool":"find_people","args":{"query":"ByteDance"},"result_preview":"{\n  \"people\": [],\n  \"total\": 13,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"},{"tool":"find_people","args":{"query":"ByteDance TikTok Douyin китайская технологическая компания"},"result_preview":"{\n  \"people\": [],\n  \"total\": 12,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"},{"tool":"find_people","args":{"query":"TikTok"},"result_preview":"{\"people\": [], \"total\": 0, \"message\": \"No people match the query\"}"}],"iterations":4,"found_people":[]}
```

---


## Query: "кто из Тинькофф?"

### OpenAI (/chat)
```json
jq: parse error: Invalid numeric literal at line 1, column 8
Testing: OpenAI with query: кто из Тинькофф?
{"session_id":"842ac38d-ffc6-4f81-8df0-c6495516e374","message":"У меня нет информации о людях из \"Тинькофф\" в вашей сети. Если у вас есть другие вопросы или запросы, дайте знать!","tool_results":[{"tool":"find_people","args":{"query":"Тинькофф"},"result":"{\n  \"people\": [],\n  \"total\": 6,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"}]}
```

### Claude (/chat/claude)
```json
jq: parse error: Invalid numeric literal at line 1, column 8
Testing: Claude with query: кто из Тинькофф?
{"message":"Кажется, в вашей базе контактов нет людей из Тинькофф банка или они не помечены соответствующим образом. Возможно, они записаны под другими названиями компании или без указания места работы.\n\nПопробуете поискать по конкретным именам сотрудников Тинькофф, которых вы знаете?","tool_calls":[{"tool":"find_people","args":{"query":"Тинькофф Tinkoff"},"result_preview":"{\n  \"people\": [],\n  \"total\": 24,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"},{"tool":"find_people","args":{"query":"Tinkoff банк","limit":30},"result_preview":"{\n  \"people\": [],\n  \"total\": 41,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"},{"tool":"find_people","args":{"query":"банк финтех","limit":30},"result_preview":"{\n  \"people\": [],\n  \"total\": 19,\n  \"showing\": 0,\n  \"is_semantic\": false\n}"}],"iterations":4,"found_people":[]}
```

---

