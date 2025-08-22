import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

FREE_MSGS_PER_DAY = int(os.getenv("FREE_MSGS_PER_DAY", 20))
FREE_IMAGES_PER_DAY = int(os.getenv("FREE_IMAGES_PER_DAY", 5))

WHISPER_MODEL = "gpt-4o-mini-transcribe"
TTS_VOICE = "alloy"
