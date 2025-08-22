# 🤖 ChatGPT-5 Telegram Bot

Бот для Telegram с поддержкой GPT-5 (Responses API), мультимодальности и памяти.

## 🚀 Запуск на Railway

1. Склонируй репозиторий в GitHub.
2. Подключи GitHub к Railway.
3. В Variables добавь переменные:
   - `BOT_TOKEN`
   - `OPENAI_API_KEY`
   - `DATABASE_URL` (Postgres URL)
   - `FREE_MSGS_PER_DAY=20`
   - `FREE_IMAGES_PER_DAY=5`
4. Нажми **Deploy**.

## 📂 Структура проекта

```
main.py
telegram_api.py
handlers.py
openai_api.py
db.py
settings.py
requirements.txt
.env.example
```

## 💡 Подписки и тарифы (в будущем)

- Добавить таблицу users с тарифами.
- Ограничивать количество запросов по тарифу.
- Реализовать оплату через Telegram Payments или Stripe.
