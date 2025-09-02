"""
Конфигурация приложения. Этот модуль собирает настройки из переменных окружения.

Объект `settings` предоставляет доступ к этим настройкам. Если некоторые
переменные окружения не определены, используются значения по умолчанию.
"""

import os


class Settings:
    """Класс настроек, читающий значения из переменных окружения."""

    # Токен Telegram‑бота
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    # Ключ доступа к OpenAI API
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    # Модель OpenAI для генерации ответов (по умолчанию gpt-4o)
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    # Параметр temperature для OpenAI (степень креативности ответа)
    TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0.8"))
    # Тайм‑аут запросов к OpenAI, секунды
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "30"))
    # Максимальная длина ответа, который бот может отправить в Telegram
    MAX_TG_REPLY: int = int(os.getenv("MAX_TG_REPLY", "3500"))
    # Строка подключения к базе данных PostgreSQL
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    # Список администраторов бота (через запятую)
    ADMINS: list = [int(x) for x in os.getenv("ADMINS", "").split(",") if x.strip().isdigit()] or []


settings = Settings()
