import os

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "supersecret123456")
TELEGRAM_WEBHOOK_TOKEN = os.getenv("TELEGRAM_WEBHOOK_TOKEN", "")
BOT_USERNAME = os.getenv("BOT_USERNAME", "").lower()  # для групп, вида testgpt404_bot

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "dall-e-3")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "gpt-4o-mini")

# Database (опционально)
DATABASE_URL = os.getenv("DATABASE_URL")  # postgresql://USER:PASS@HOST:PORT/DB?sslmode=require

# Limits
FREE_MSGS_PER_DAY = int(os.getenv("FREE_MSGS_PER_DAY", "20"))
FREE_IMAGES_PER_DAY = int(os.getenv("FREE_IMAGES_PER_DAY", "5"))

# Admins
ADMIN_IDS_ENV = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x) for x in ADMIN_IDS_ENV.replace(" ", "").split(",") if x.isdigit()]
if 1752390166 not in ADMIN_IDS:
    ADMIN_IDS.append(1752390166)  # твой ID по умолчанию

# Mini App (опционально)
MINI_APP_URL = os.getenv("MINI_APP_URL", "")  # если укажешь URL — покажем inline-кнопку

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set")
