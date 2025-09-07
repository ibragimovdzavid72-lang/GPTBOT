"""
User service for user management operations.
Выделенный сервис для работы с пользователями.
"""

import logging
from typing import Dict, Optional, Any
from datetime import datetime

from .database_service import database_service
from ..constants import TTS_VOICES

logger = logging.getLogger(__name__)


class UserService:
    """Сервис для работы с пользователями."""
    
    def __init__(self):
        """Инициализация сервиса пользователей."""
        self.default_settings = {
            "preferred_model": "gpt-4o-mini",
            "tts_voice": "alloy",
            "language": "ru"
        }
    
    async def get_user_language(self, user_id: int) -> str:
        """Получает язык пользователя."""
        settings = await database_service.get_user_settings(user_id)
        if settings and settings.get("language"):
            return settings["language"]
        return self.default_settings["language"]
    
    async def set_user_language(self, user_id: int, language: str) -> bool:
        """Устанавливает язык пользователя."""
        if language not in ["ru", "en"]:
            return False
        
        current_settings = await database_service.get_user_settings(user_id) or {}
        current_settings.update({"language": language})
        
        return await database_service.save_user_settings(user_id, current_settings)
    
    async def get_user_model(self, user_id: int) -> str:
        """Получает предпочитаемую модель пользователя."""
        settings = await database_service.get_user_settings(user_id)
        if settings and settings.get("preferred_model"):
            return settings["preferred_model"]
        return self.default_settings["preferred_model"]
    
    async def set_user_model(self, user_id: int, model: str) -> bool:
        """Устанавливает предпочитаемую модель пользователя."""
        valid_models = [
            "gpt-4o-mini", "gpt-4o", "gpt-4-turbo", 
            "gpt-3.5-turbo", "gpt-4", "o1-preview", "o1-mini"
        ]
        
        if model not in valid_models:
            return False
        
        current_settings = await database_service.get_user_settings(user_id) or {}
        current_settings.update({"preferred_model": model})
        
        return await database_service.save_user_settings(user_id, current_settings)
    
    async def get_user_tts_voice(self, user_id: int) -> str:
        """Получает голос TTS пользователя."""
        settings = await database_service.get_user_settings(user_id)
        if settings and settings.get("tts_voice"):
            return settings["tts_voice"]
        return self.default_settings["tts_voice"]
    
    async def set_user_tts_voice(self, user_id: int, voice: str) -> bool:
        """Устанавливает голос TTS пользователя."""
        if voice not in TTS_VOICES:
            return False
        
        current_settings = await database_service.get_user_settings(user_id) or {}
        current_settings.update({"tts_voice": voice})
        
        return await database_service.save_user_settings(user_id, current_settings)
    
    async def get_user_profile(self, user_id: int) -> Dict[str, Any]:
        """Получает полный профиль пользователя."""
        settings = await database_service.get_user_settings(user_id)
        if settings:
            return settings
        return self.default_settings.copy()
    
    async def update_user_profile(self, user_id: int, updates: Dict[str, Any]) -> bool:
        """Обновляет профиль пользователя."""
        current_settings = await database_service.get_user_settings(user_id) or {}
        
        # Валидация обновлений
        if "language" in updates and updates["language"] not in ["ru", "en"]:
            return False
        
        if "tts_voice" in updates and updates["tts_voice"] not in TTS_VOICES:
            return False
        
        valid_models = [
            "gpt-4o-mini", "gpt-4o", "gpt-4-turbo", 
            "gpt-3.5-turbo", "gpt-4", "o1-preview", "o1-mini"
        ]
        if "preferred_model" in updates and updates["preferred_model"] not in valid_models:
            return False
        
        # Применяем обновления
        current_settings.update(updates)
        
        return await database_service.save_user_settings(user_id, current_settings)
    
    async def initialize_user(self, user_id: int, username: str = None) -> bool:
        """Инициализирует нового пользователя с настройками по умолчанию."""
        existing_settings = await database_service.get_user_settings(user_id)
        if existing_settings:
            return True  # Пользователь уже существует
        
        return await database_service.save_user_settings(user_id, self.default_settings)
    
    async def get_user_statistics(self, user_id: int) -> Dict[str, Any]:
        """Получает статистику использования пользователем."""
        try:
            # Количество команд пользователя
            rows = await database_service.fetch_many(
                "SELECT COUNT(*) as total, command FROM logs WHERE username = $1 GROUP BY command",
                str(user_id)
            )
            
            stats = {
                "total_commands": sum(row["total"] for row in rows),
                "commands_breakdown": {row["command"]: row["total"] for row in rows}
            }
            
            # Последняя активность
            last_activity = await database_service.fetch_one(
                "SELECT MAX(created_at) as last_seen FROM logs WHERE username = $1",
                str(user_id)
            )
            
            if last_activity and last_activity["last_seen"]:
                stats["last_activity"] = last_activity["last_seen"]
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting user statistics: {e}")
            return {"total_commands": 0, "commands_breakdown": {}}


# Глобальный экземпляр сервиса
user_service = UserService()