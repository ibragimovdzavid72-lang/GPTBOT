# GPTBOT — Webhook + Buttons + Memory + Images + Postgres Logs

Функции:
- Webhook (FastAPI) — без polling
- Кнопки под чатом (ReplyKeyboard) и меню команд
- GPT-ответы с контекстом (память последних N сообщений)
- Генерация изображений: `/image <промпт>` или нажми кнопку и затем отправь описание
- Логирование вопросов/ответов в Postgres (если задан `DATABASE_URL`)
- `/reset` — очищает память диалога

## Переменные окружения
- `TELEGRAM_BOT_TOKEN` — токен бота
- `OPENAI_API_KEY` — ключ OpenAI (иначе бот ответит без ИИ)
- `WEBHOOK_BASE` — публичный URL Railway (например, `https://your-app.up.railway.app`)
- `WEBHOOK_SECRET` — секрет (любой сложный текст), должен совпадать с заголовком
- `DATABASE_URL` — (опционально) `postgresql://user:pass@host:port/db`

## Запуск на Railway
1) Залей файлы в GitHub (см. чат-инструкцию).
2) В Railway → Variables задайте переменные выше.
3) Redeploy. В логах увидите `Webhook set: ...`.
