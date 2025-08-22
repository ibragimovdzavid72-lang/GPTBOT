# 🤖 ChatGPT‑5 Telegram PRO (быстрый старт)

Режимы: 💬 Текст, 🧰 Инструменты (поиск/погода/калькулятор/вики), 🖼 Картинка (DALL·E 3), 🎙 Голос (Whisper→TTS), 🧠 Память.

## 1) GitHub + Railway
- Залей файлы в новый репозиторий.
- Railway → New Project → Deploy from GitHub.

## 2) Variables (Railway)
BOT_TOKEN=твой_бот_токен
OPENAI_API_KEY=твоя_ключ_OpenAI
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db
OPENAI_MODEL=gpt-4o
OPENAI_IMAGE_MODEL=dall-e-3
OPENAI_TTS_MODEL=tts-1
OPENAI_STT_MODEL=whisper-1
FREE_MSGS_PER_DAY=50
FREE_IMAGES_PER_DAY=10
HISTORY_LIMIT=20
RATE_PER_MIN=20
ADMIN_IDS=123456789
TZ=Europe/Amsterdam

## 3) Запуск
Start Command: `python main.py`

## 4) Проверка
- `/start` → появится клавиатура.
- 🖼 В режиме «Картинка» напиши промпт — придёт изображение.
- 🎙 Пришли voice — бот распознает и ответит аудио.
- 🧰 В инструментах спроси погоду/поиск/калькулятор — модель вызовет tool автоматически.
