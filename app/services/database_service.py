"""
Database service for centralized database operations.
Выделенный сервис для работы с PostgreSQL базой данных.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

import asyncpg

from ..config import settings

logger = logging.getLogger(__name__)


class DatabaseService:
    """Сервис для работы с базой данных PostgreSQL."""
    
    def __init__(self):
        """Инициализация сервиса базы данных."""
        self.pool: Optional[asyncpg.Pool] = None
    
    async def initialize_pool(self) -> bool:
        """Инициализация пула подключений к базе данных."""
        try:
            self.pool = await asyncpg.create_pool(
                settings.DATABASE_URL,
                min_size=2,
                max_size=10,
                command_timeout=30
            )
            logger.info("✅ Database pool initialized successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to initialize database pool: {e}")
            return False
    
    async def close_pool(self) -> None:
        """Закрытие пула подключений."""
        if self.pool:
            await self.pool.close()
            logger.info("📊 Database pool closed")
    
    def is_available(self) -> bool:
        """Проверяет доступность базы данных."""
        return self.pool is not None
    
    async def execute_query(self, query: str, *args) -> bool:
        """Выполняет запрос без возврата данных."""
        if not self.is_available():
            logger.warning("Database pool not available")
            return False
        
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, *args)
                return True
        except Exception as e:
            logger.error(f"Database execute error: {e}")
            return False
    
    async def fetch_one(self, query: str, *args) -> Optional[asyncpg.Record]:
        """Возвращает одну запись."""
        if not self.is_available():
            return None
        
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetchrow(query, *args)
        except Exception as e:
            logger.error(f"Database fetch_one error: {e}")
            return None
    
    async def fetch_many(self, query: str, *args) -> List[asyncpg.Record]:
        """Возвращает несколько записей."""
        if not self.is_available():
            return []
        
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetch(query, *args)
        except Exception as e:
            logger.error(f"Database fetch_many error: {e}")
            return []
    
    # === User Management ===
    
    async def get_user_settings(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получает настройки пользователя."""
        row = await self.fetch_one(
            "SELECT preferred_model, tts_voice, language FROM user_settings WHERE user_id = $1",
            user_id
        )
        if row:
            return {
                "preferred_model": row["preferred_model"],
                "tts_voice": row["tts_voice"],
                "language": row["language"]
            }
        return None
    
    async def save_user_settings(self, user_id: int, settings_data: Dict[str, Any]) -> bool:
        """Сохраняет настройки пользователя."""
        query = """
        INSERT INTO user_settings (user_id, preferred_model, tts_voice, language)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_id) DO UPDATE SET
            preferred_model = EXCLUDED.preferred_model,
            tts_voice = EXCLUDED.tts_voice,
            language = EXCLUDED.language,
            updated_at = NOW()
        """
        return await self.execute_query(
            query,
            user_id,
            settings_data.get("preferred_model"),
            settings_data.get("tts_voice"),
            settings_data.get("language")
        )
    
    # === Dialog History ===
    
    async def get_dialog_history(self, user_id: int, limit: int = 10) -> List[Dict[str, str]]:
        """Получает историю диалога пользователя."""
        rows = await self.fetch_many(
            "SELECT role, content FROM dialog_history WHERE user_id = $1 ORDER BY id DESC LIMIT $2",
            user_id, limit
        )
        return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
    
    async def save_dialog_message(self, user_id: int, role: str, content: str) -> bool:
        """Сохраняет сообщение в истории диалога."""
        return await self.execute_query(
            "INSERT INTO dialog_history (user_id, role, content) VALUES ($1, $2, $3)",
            user_id, role, content
        )
    
    async def clear_dialog_history(self, user_id: int) -> bool:
        """Очищает историю диалога пользователя."""
        return await self.execute_query(
            "DELETE FROM dialog_history WHERE user_id = $1",
            user_id
        )
    
    # === Logging ===
    
    async def log_command(self, username: str, command: str, args: str, answer: str) -> bool:
        """Записывает лог команды."""
        return await self.execute_query(
            "INSERT INTO logs (username, command, args, answer) VALUES ($1, $2, $3, $4)",
            username, command, args, answer
        )
    
    # === Admin Functions ===
    
    async def get_bot_settings(self) -> Optional[Dict[str, Any]]:
        """Получает настройки бота."""
        row = await self.fetch_one("SELECT is_active FROM bot_settings LIMIT 1")
        if row:
            return {"is_active": row["is_active"]}
        return None
    
    async def set_bot_active(self, is_active: bool) -> bool:
        """Устанавливает состояние активности бота."""
        query = """
        INSERT INTO bot_settings (id, is_active)
        VALUES (1, $1)
        ON CONFLICT (id) DO UPDATE SET
            is_active = EXCLUDED.is_active,
            updated_at = NOW()
        """
        return await self.execute_query(query, is_active)
    
    async def get_stats(self) -> Optional[Dict[str, int]]:
        """Получает статистику использования бота."""
        try:
            stats = {}
            
            # Общее количество команд
            row = await self.fetch_one("SELECT COUNT(*) as total FROM logs")
            stats["total_commands"] = row["total"] if row else 0
            
            # Уникальные пользователи
            row = await self.fetch_one("SELECT COUNT(DISTINCT username) as unique_users FROM logs")
            stats["unique_users"] = row["unique_users"] if row else 0
            
            # Команды за сегодня
            row = await self.fetch_one(
                "SELECT COUNT(*) as today FROM logs WHERE DATE(created_at) = CURRENT_DATE"
            )
            stats["today_commands"] = row["today"] if row else 0
            
            return stats
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return None
    
    async def get_recent_errors(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Получает последние ошибки."""
        rows = await self.fetch_many(
            """
            SELECT created_at, username, command, args, answer 
            FROM logs 
            WHERE answer LIKE '%❌%' OR answer LIKE '%error%' 
            ORDER BY created_at DESC 
            LIMIT $1
            """,
            limit
        )
        return [
            {
                "timestamp": row["created_at"],
                "username": row["username"],
                "command": row["command"],
                "args": row["args"],
                "answer": row["answer"]
            }
            for row in rows
        ]


# Глобальный экземпляр сервиса
database_service = DatabaseService()