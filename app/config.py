"""Configuration module for Telegram AI Bot."""

import os
from typing import Optional
from pydantic import BaseSettings, Field
from pydantic_settings import BaseSettings as PydanticBaseSettings


class Settings(PydanticBaseSettings):
    """Application settings."""
    
    # Telegram Bot settings
    telegram_bot_token: str = Field(..., env="TELEGRAM_BOT_TOKEN")
    webhook_base_url: Optional[str] = Field(None, env="WEBHOOK_BASE_URL")
    webhook_path: str = Field("/webhook", env="WEBHOOK_PATH")
    webhook_secret_token: Optional[str] = Field(None, env="WEBHOOK_SECRET_TOKEN")
    
    # OpenAI settings
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")
    openai_model: str = Field("gpt-4o", env="OPENAI_MODEL")
    openai_image_model: str = Field("dall-e-3", env="OPENAI_IMAGE_MODEL")
    openai_tts_model: str = Field("tts-1", env="OPENAI_TTS_MODEL")
    openai_whisper_model: str = Field("whisper-1", env="OPENAI_WHISPER_MODEL")
    
    # Database settings
    database_url: str = Field(..., env="DATABASE_URL")
    
    # Admin settings
    super_admin_id: int = Field(..., env="SUPER_ADMIN_ID")
    
    # Payment settings
    payment_provider_token: Optional[str] = Field(None, env="PAYMENT_PROVIDER_TOKEN")
    
    # Rate limiting and usage settings
    max_history_messages: int = Field(16, env="MAX_HISTORY_MESSAGES")
    
    # FREE tier limits
    free_daily_messages: int = Field(20, env="FREE_DAILY_MESSAGES")
    free_daily_images: int = Field(5, env="FREE_DAILY_IMAGES")
    free_daily_voice: int = Field(10, env="FREE_DAILY_VOICE")
    
    # PRO tier limits
    pro_daily_messages: int = Field(200, env="PRO_DAILY_MESSAGES")
    pro_daily_images: int = Field(50, env="PRO_DAILY_IMAGES")
    pro_daily_voice: int = Field(100, env="PRO_DAILY_VOICE")
    pro_price_rub: int = Field(199, env="PRO_PRICE_RUB")
    
    # TEAM tier limits
    team_daily_messages: int = Field(1000, env="TEAM_DAILY_MESSAGES")
    team_daily_images: int = Field(200, env="TEAM_DAILY_IMAGES")
    team_daily_voice: int = Field(500, env="TEAM_DAILY_VOICE")
    team_price_rub: int = Field(799, env="TEAM_PRICE_RUB")
    
    # Environment
    environment: str = Field("production", env="ENVIRONMENT")
    debug: bool = Field(False, env="DEBUG")
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }


# Global settings instance
settings = Settings()