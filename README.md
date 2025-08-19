
# GPTBOT — Modern UI + Admin Toggle (Webhook)

Функции:
- Webhook через FastAPI (без polling)
- Современный UI: ReplyKeyboard для пользователей + Inline-кнопки в админ-панели
- Память последних сообщений (MEM_LIMIT)
- Генерация изображений `/image` (поддержка URL и base64)
- Логи в Postgres (таблица `chat_logs`)
- Переключатель бота Включить/Выключить из Telegram: /admin или /on /off
- Настройки хранятся в Postgres (таблица `settings`) — переживают перезапуск

## Переменные окружения (Railway → Variables)
- TELEGRAM_BOT_TOKEN
- OPENAI_API_KEY
- WEBHOOK_BASE  (например, https://your-app.up.railway.app)
- WEBHOOK_SECRET
- ADMIN_IDS     (через запятую: 11111111,22222222)
- DATABASE_URL  (опционально)
- IMAGE_SIZE    (опционально, по умолчанию 1024x1024)
