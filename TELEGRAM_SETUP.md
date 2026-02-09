# Telegram Bot Setup Guide

## Phase 1: Deploy & Configure Webhook

### 1. Deploy to Railway

```bash
cd /Users/evgenyq/Projects/atlantisplus/service
railway up
```

После деплоя получите URL вашего сервиса (например: `https://atlantisplus-production.up.railway.app`)

### 2. Set Environment Variables in Railway

В Railway Dashboard → Variables добавьте:

```env
TELEGRAM_BOT_TOKEN=<your_token_from_botfather>
TELEGRAM_WEBHOOK_SECRET=<random_secret_string>
```

Для генерации случайного secret:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 3. Register Webhook with Telegram

Замените `<BOT_TOKEN>` и `<SECRET>` на ваши значения:

```bash
curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://atlantisplus-production.up.railway.app/telegram/webhook",
    "secret_token": "<SECRET>",
    "allowed_updates": ["message"],
    "drop_pending_updates": true
  }'
```

**Ожидаемый ответ:**
```json
{
  "ok": true,
  "result": true,
  "description": "Webhook was set"
}
```

### 4. Verify Webhook Status

```bash
curl "https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo"
```

**Должно показать:**
- `url`: ваш webhook URL
- `has_custom_certificate`: false
- `pending_update_count`: 0
- `last_error_date`: не должно быть
- `max_connections`: 40 (default)

### 5. Test Bot

Откройте Telegram и найдите вашего бота (@atlantisplus_bot).

Протестируйте команды:
```
/start
/help
Привет, как дела?
```

**Ожидаемое поведение (Phase 1):**
- `/start` → приветственное сообщение
- `/help` → справка
- Любой текст → echo с информацией о user_id (Phase 1 test mode)

### 6. Check Logs

В Railway Dashboard → Deployments → Logs смотрите:
```
[STARTUP] Initializing Telegram bot...
[BOT] Telegram bot application initialized
[STARTUP] Bot ready
```

При получении сообщения:
```
[BOT] Processing update...
[AUTH] User <telegram_id> authenticated as <user_id>
```

---

## Phase 2+: After Dispatcher Implementation

После реализации dispatcher (Phase 2), тестируйте:

**Note classification:**
```
User: Вася работает в Google
Bot: 🎯 Сохраняю заметку...
     Извлекаю информацию о людях.
     ✅ Готово! Извлечено: ...
```

**Query classification:**
```
User: Кто работает в Google?
Bot: 🔍 Ищу в вашей сети...
     Нашёл X человек: ...
```

---

## Configure Bot in BotFather

### 1. Set Commands
```
/setcommands

start - Начать работу с ботом
help - Помощь
reset - Сбросить контекст диалога
```

### 2. Set Description
```
/setdescription

Atlantis Plus — ваша личная память о профессиональной сети.
Надиктовывайте заметки о людях или спрашивайте кого найти.
```

### 3. Set About Text
```
/setabouttext

AI-first Personal Network Memory. Помогает power-коннекторам помнить свой нетворк.
```

### 4. Set Menu Button (Mini App)
```
/setmenubutton

URL: https://evgenyq.github.io/atlantisplus/
Text: 👥 Каталог контактов
```

---

## Troubleshooting

### Webhook not receiving updates

**Check webhook status:**
```bash
curl "https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo"
```

**Common issues:**
- `last_error_message`: SSL certificate error → Railway должен использовать валидный SSL
- `pending_update_count` > 0 → старые обновления в очереди, используйте `drop_pending_updates: true`

**Delete webhook and retry:**
```bash
curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/deleteWebhook?drop_pending_updates=true"
```

### Bot responds slowly

- Проверьте Railway logs для ошибок
- Убедитесь что OpenAI API key валидный
- Проверьте что Supabase доступен

### Authentication errors

Проверьте в Railway logs:
```
[AUTH] Error creating user: ...
```

Убедитесь что `SUPABASE_SERVICE_ROLE_KEY` правильный (не anon key!)

---

## Полезные команды

**Проверить что бот работает:**
```bash
curl "https://api.telegram.org/bot<BOT_TOKEN>/getMe"
```

**Отправить тестовое сообщение через API:**
```bash
curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/sendMessage" \
  -H "Content-Type: application/json" \
  -d '{
    "chat_id": <your_telegram_id>,
    "text": "Test message from curl"
  }'
```

**Получить chat_id:**
Отправьте любое сообщение боту, затем:
```bash
curl "https://api.telegram.org/bot<BOT_TOKEN>/getUpdates"
```

Ваш chat_id будет в `message.chat.id`.
