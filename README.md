# Telegram GPT‑4o бот (FastAPI + Railway + Postgres)

## Установка
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # заполни токены/ключи
```

## Локальный старт
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Webhook (после деплоя)
```bash
curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook?url=$TELEGRAM_WEBHOOK_URL$TELEGRAM_WEBHOOK_PATH&secret_token=$TELEGRAM_WEBHOOK_SECRET"
```

## Переменные окружения (Railway → Variables)
- TELEGRAM_BOT_TOKEN
- TELEGRAM_WEBHOOK_URL
- TELEGRAM_WEBHOOK_PATH
- TELEGRAM_WEBHOOK_SECRET
- OPENAI_API_KEY
- OPENAI_MODEL (gpt-4o)
- OPENAI_IMAGE_MODEL (gpt-image-1)
- OPENAI_FALLBACK_MODEL (gpt-4o-mini)
- OPENAI_TTS_MODEL (tts-1)
- OPENAI_STT_MODEL (whisper-1)
- DATABASE_URL (после добавления Postgres)
- FREE_MSGS_PER_DAY (напр. 50)
- FREE_IMAGES_PER_DAY (напр. 10)
- HISTORY_LIMIT (напр. 20)
- ADMIN_IDS (список id через запятую)
- TZ (Europe/Amsterdam)

## Start command (Railway)
`uvicorn main:app --host 0.0.0.0 --port $PORT`

## Возможности
- 💬 Текстовый чат (память диалога, лимиты)
- 🛠 Инструменты (wiki-поиск, погода, калькулятор, напоминания)
- 🎨 Генерация изображений
- 🔊 Голос: распознавание (Whisper) + ответ голосом (TTS)
- ⏰ Фоновые напоминания
```
