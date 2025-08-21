import os

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "supersecret123456")
TELEGRAM_WEBHOOK_TOKEN = os.getenv("TELEGRAM_WEBHOOK_TOKEN", "")
BOT_USERNAME = os.getenv("BOT_USERNAME", "").lower()  # нужно для групп

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "dall-e-3")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "gpt-4o-mini")

# Database
DATABASE_URL = os.getenv("DATABASE_URL")  

# Лимиты
FREE_MSGS_PER_DAY = int(os.getenv("FREE_MSGS_PER_DAY", "20"))
FREE_IMAGES_PER_DAY = int(os.getenv("FREE_IMAGES_PER_DAY", "5"))

# Админы
ADMIN_IDS_ENV = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x) for x in ADMIN_IDS_ENV.replace(" ", "").split(",") if x.isdigit()]
if 1752390166 not in ADMIN_IDS:
    ADMIN_IDS.append(1752390166)  # твой ID по умолчанию
