import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
PUBLIC_URL = os.getenv("PUBLIC_URL", "").rstrip("/")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_FALLBACK_MODEL = os.getenv("OPENAI_FALLBACK_MODEL", "gpt-4o-mini")
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "dall-e-3")
OPENAI_TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "tts-1")
OPENAI_STT_MODEL = os.getenv("OPENAI_STT_MODEL", "whisper-1")

DATABASE_URL = os.getenv("DATABASE_URL", "")

FREE_MSGS_PER_DAY = int(os.getenv("FREE_MSGS_PER_DAY", "50"))
FREE_IMAGES_PER_DAY = int(os.getenv("FREE_IMAGES_PER_DAY", "10"))
HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "20"))
RATE_PER_MIN = int(os.getenv("RATE_PER_MIN", "20"))

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")

ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x.isdigit()]
TZ = os.getenv("TZ", "Europe/Amsterdam")
