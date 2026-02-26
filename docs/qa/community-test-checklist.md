# Community Feature — Quick Test Checklist

## Owner Flow
1. `/newcommunity` → создаёт community → получает invite link ✅
2. Mini App → Groups tab → видит свою community + member count ✅
3. Клик на community → видит список участников ✅

## Member Join Flow
4. Клик по invite link `t.me/bot?start=join_XXX` → бот приветствует ✅
5. Отправка intro → extraction → показ карточки для подтверждения ✅
6. Confirm → профиль создан → `/profile` показывает данные ✅

## Member Edit Flow
7. `/edit` → отправка коррекции → merge с предыдущими данными ✅
8. `/profile` → показывает обновлённые + сохранённые поля ✅

## Access Control
9. Member отправляет query текстом → "You can only manage your profile" ✅
10. Member вставляет deep link как текст → "Please click the link" ✅

## Security (RLS)
11. Member не видит людей из других communities (direct API) ✅
12. Owner видит только свои person records ✅

## Edge Cases
13. Повторный join → upsert существующего профиля ✅
14. `/delete` → удаляет профиль, можно re-join ✅
