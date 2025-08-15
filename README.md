# GPTBOT (Railway + Telegram + Python)

Минимальный Telegram-бот на `python-telegram-bot 21.x` + FastAPI `/health`, готовый к деплою на Railway.

## Быстрый старт

1) **Залей этот репозиторий в GitHub.**
2) В Railway:
   - Создай проект (или выбери существующий).
   - Подключи репозиторий из GitHub.
   - В `Variables` задай переменную:
     - `TELEGRAM_BOT_TOKEN` — токен в формате `123456789:AA...` (без пробелов и кавычек).
3) Railway сам поставит зависимости и запустит процесс по `Procfile` → `web: python app.py`.
4) В логах должно быть: `Bot polling started` и `Uvicorn running on ...`.

## Локальный запуск

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN=123456789:AA...   # вставь свой токен
python app.py
```

Открой Telegram и отправь боту `/start`.
