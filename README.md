# GPTBOT (Railway + Telegram + Python) — v2 with extra logging

Минимальный Telegram-бот на `python-telegram-bot 21.x` + FastAPI `/health`, готовый к деплою на Railway.
Эта версия добавляет дополнительные логи, чтобы в Railway было видно каждый этап запуска.

## Переменные окружения (в Railway → Service → Variables)
- `TELEGRAM_BOT_TOKEN` — токен вашего бота **строго** вида `123456789:AA...` (без пробелов, без кавычек).

## Локальный запуск
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN=123456789:AA...   # вставьте ваш токен
python app.py
```
