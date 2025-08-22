import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
WEBHOOK_URL = os.getenv("TELEGRAM_WEBHOOK_URL", "").rstrip("/")
WEBHOOK_PATH = os.getenv("TELEGRAM_WEBHOOK_PATH", "/webhook")
WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")
OPENAI_FALLBACK_MODEL = os.getenv("OPENAI_FALLBACK_MODEL", "gpt-4o-mini")
OPENAI_TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "tts-1")
OPENAI_STT_MODEL = os.getenv("OPENAI_STT_MODEL", "whisper-1")

# DB
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Limits / Settings
FREE_MSGS_PER_DAY = int(os.getenv("FREE_MSGS_PER_DAY", "50"))
FREE_IMAGES_PER_DAY = int(os.getenv("FREE_IMAGES_PER_DAY", "10"))
HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "20"))
TZ = os.getenv("TZ", "Europe/Amsterdam")

# Admins
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x.isdigit()]

FULL_WEBHOOK_URL = f"{WEBHOOK_URL}{WEBHOOK_PATH}" if WEBHOOK_URL else ""
