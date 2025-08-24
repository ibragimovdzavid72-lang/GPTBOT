"""Модуль конфигурации для Telegram AI Bot."""

import os
from typing import Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
import dotenv

# Загружаем .env файл перед импортами (согласно памяти о Pydantic)
dotenv.load_dotenv()


class БазаДанныхНастройки(BaseModel):
    """Настройки базы данных."""
    ссылка: str = Field(..., env="DATABASE_URL")


class Настройки(BaseSettings):
    """Настройки приложения."""
    
    # Настройки Telegram Bot
    telegram_bot_token: str = Field(..., env="TELEGRAM_BOT_TOKEN")
    webhook_base_url: Optional[str] = Field(None, env="WEBHOOK_BASE_URL")
    webhook_path: str = Field("/webhook", env="WEBHOOK_PATH")
    webhook_secret_token: Optional[str] = Field(None, env="WEBHOOK_SECRET_TOKEN")
    
    # Настройки OpenAI
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")
    openai_model: str = Field("gpt-4o", env="OPENAI_MODEL")
    openai_image_model: str = Field("dall-e-3", env="OPENAI_IMAGE_MODEL")
    openai_tts_model: str = Field("tts-1", env="OPENAI_TTS_MODEL")
    openai_whisper_model: str = Field("whisper-1", env="OPENAI_WHISPER_MODEL")
    
    # Настройки базы данных (согласно памяти о Database Configuration)
    база_данных: БазаДанныхНастройки = БазаДанныхНастройки(ссылка=os.getenv("DATABASE_URL", ""))
    
    # Настройки администратора
    super_admin_id: int = Field(..., env="SUPER_ADMIN_ID")
    
    # Настройки платежей
    payment_provider_token: Optional[str] = Field(None, env="PAYMENT_PROVIDER_TOKEN")
    
    # Настройки ограничений скорости и использования
    max_history_messages: int = Field(16, env="MAX_HISTORY_MESSAGES")
    
    # Лимиты уровня FREE
    free_daily_messages: int = Field(20, env="FREE_DAILY_MESSAGES")
    free_daily_images: int = Field(5, env="FREE_DAILY_IMAGES")
    free_daily_voice: int = Field(10, env="FREE_DAILY_VOICE")
    
    # Лимиты уровня PRO (согласно памяти о Monetization - 199₽)
    pro_daily_messages: int = Field(200, env="PRO_DAILY_MESSAGES")
    pro_daily_images: int = Field(50, env="PRO_DAILY_IMAGES")
    pro_daily_voice: int = Field(100, env="PRO_DAILY_VOICE")
    pro_price_rub: int = Field(199, env="PRO_PRICE_RUB")
    
    # Лимиты уровня TEAM (согласно памяти о Monetization - 799₽)
    team_daily_messages: int = Field(1000, env="TEAM_DAILY_MESSAGES")
    team_daily_images: int = Field(200, env="TEAM_DAILY_IMAGES")
    team_daily_voice: int = Field(500, env="TEAM_DAILY_VOICE")
    team_price_rub: int = Field(799, env="TEAM_PRICE_RUB")
    
    # Среда выполнения
    environment: str = Field("production", env="ENVIRONMENT")
    debug: bool = Field(False, env="DEBUG")
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }
    
    def __init__(self, **kwargs):
        """Инициализация с обработкой ошибок (согласно памяти о graceful-deployment-failure)."""
        try:
            super().__init__(**kwargs)
            # Проверка формата DATABASE_URL (согласно памяти)
            if self.база_данных.ссылка.startswith("postgresql+asyncpg:"):
                raise ValueError("Неверный формат DATABASE_URL. Используйте 'postgresql://' вместо 'postgresql+asyncpg:'")
        except Exception as e:
            print(f"""
❌ Ошибка конфигурации: {e}

📋 Инструкции по настройке:
1. Скопируйте .env.example в .env
2. Заполните обязательные переменные:
   - TELEGRAM_BOT_TOKEN (от @BotFather)
   - OPENAI_API_KEY (от OpenAI)
   - DATABASE_URL (формат: postgresql://user:pass@host:port/db)
   - SUPER_ADMIN_ID (ваш Telegram ID)

🔧 Пример DATABASE_URL:
   postgresql://postgres:password@localhost:5432/russian_bot_db

📚 Подробнее см. QUICK_START.md
            """)
            raise


# Глобальный экземпляр настроек
настройки = Настройки()