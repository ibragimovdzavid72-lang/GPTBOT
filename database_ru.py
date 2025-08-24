"""Модуль базы данных с моделями PostgreSQL и миграциями."""

import asyncio
import asyncpg
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from config_ru import настройки
import logging

logger = logging.getLogger(__name__)

# SQL миграций базы данных (согласно памяти о Database Configuration)
MIGRATIONS_SQL = """
-- Таблица пользователей
CREATE TABLE IF NOT EXISTS пользователи (
    id BIGINT PRIMARY KEY,
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    language_code VARCHAR(10) DEFAULT 'ru',
    is_admin BOOLEAN DEFAULT FALSE,
    plan VARCHAR(20) DEFAULT 'FREE',
    plan_expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица разговоров для контекста разговора
CREATE TABLE IF NOT EXISTS разговоры (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES пользователи(id) ON DELETE CASCADE,
    session_data JSONB DEFAULT '{}',
    persona VARCHAR(50) DEFAULT 'default',
    language VARCHAR(10) DEFAULT 'ru',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица сообщений для истории чата
CREATE TABLE IF NOT EXISTS сообщения (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES пользователи(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    message_type VARCHAR(20) DEFAULT 'text',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица статистики использования
CREATE TABLE IF NOT EXISTS статистика_использования (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES пользователи(id) ON DELETE CASCADE,
    action VARCHAR(50) NOT NULL,
    duration_ms INTEGER,
    status VARCHAR(20) DEFAULT 'success',
    metadata JSONB DEFAULT '{}',
    cost_tokens INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица платежей
CREATE TABLE IF NOT EXISTS платежи (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES пользователи(id) ON DELETE CASCADE,
    telegram_payment_charge_id VARCHAR(255) UNIQUE,
    provider_payment_charge_id VARCHAR(255),
    amount INTEGER NOT NULL,
    currency VARCHAR(10) DEFAULT 'RUB',
    plan VARCHAR(20) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица напоминаний
CREATE TABLE IF NOT EXISTS напоминания (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES пользователи(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    remind_at TIMESTAMP NOT NULL,
    sent BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание индексов для лучшей производительности
CREATE INDEX IF NOT EXISTS idx_пользователи_plan ON пользователи(plan);
CREATE INDEX IF NOT EXISTS idx_сообщения_user_id ON сообщения(user_id);
CREATE INDEX IF NOT EXISTS idx_сообщения_created_at ON сообщения(created_at);
CREATE INDEX IF NOT EXISTS idx_статистика_использования_user_id ON статистика_использования(user_id);
CREATE INDEX IF NOT EXISTS idx_статистика_использования_created_at ON статистика_использования(created_at);
CREATE INDEX IF NOT EXISTS idx_статистика_использования_action ON статистика_использования(action);
CREATE INDEX IF NOT EXISTS idx_платежи_user_id ON платежи(user_id);
CREATE INDEX IF NOT EXISTS idx_напоминания_user_id ON напоминания(user_id);
CREATE INDEX IF NOT EXISTS idx_напоминания_remind_at ON напоминания(remind_at);
CREATE INDEX IF NOT EXISTS idx_напоминания_sent ON напоминания(sent);
"""


class МенеджерБазыДанных:
    """Менеджер базы данных для операций PostgreSQL."""
    
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
    
    async def инициализировать_бд(self):
        """Инициализация пула соединений базы данных."""
        try:
            # Проверка формата DATABASE_URL (согласно памяти)
            database_url = настройки.база_данных.ссылка
            if not database_url:
                raise ValueError("DATABASE_URL не задан")
            
            if database_url.startswith("postgresql+asyncpg:"):
                raise ValueError("Неверный формат DATABASE_URL. Используйте 'postgresql://' вместо 'postgresql+asyncpg:'")
            
            self.pool = await asyncpg.create_pool(
                database_url,
                min_size=5,
                max_size=20,
                command_timeout=60
            )
            logger.info("Пул базы данных успешно создан")
            
            # Запуск миграций (согласно памяти о Database Initialization)
            await self.запустить_миграции()
            
            # Проверка существования столбцов (согласно памяти)
            await self.проверить_столбцы()
            
        except Exception as e:
            logger.error(f"Не удалось инициализировать базу данных: {e}")
            # Graceful error handling (согласно памяти)
            print(f"""
❌ Ошибка подключения к базе данных: {e}

🔧 Проверьте:
1. База данных PostgreSQL запущена
2. Правильность DATABASE_URL: {настройки.база_данных.ссылка}
3. Формат: postgresql://username:password@host:port/database

💡 Для локальной разработки используйте:
   docker-compose up postgres -d
            """)
            raise
    
    async def запустить_миграции(self):
        """Запуск миграций базы данных."""
        if not self.pool:
            raise RuntimeError("Пул базы данных не инициализирован")
        
        async with self.pool.acquire() as conn:
            try:
                await conn.execute(MIGRATIONS_SQL)
                logger.info("Миграции базы данных успешно завершены")
            except Exception as e:
                logger.error(f"Не удалось запустить миграции: {e}")
                raise
    
    async def проверить_столбцы(self):
        """Проверка существования необходимых столбцов (согласно памяти)."""
        required_columns = {
            'пользователи': ['id', 'username', 'plan', 'is_admin'],
            'сообщения': ['id', 'user_id', 'role', 'content'],
            'статистика_использования': ['id', 'user_id', 'action', 'status'],
            'платежи': ['id', 'user_id', 'plan', 'amount'],
            'напоминания': ['id', 'user_id', 'text', 'remind_at', 'sent']
        }
        
        async with self.pool.acquire() as conn:
            for table_name, columns in required_columns.items():
                for column in columns:
                    result = await conn.fetchval("""
                        SELECT column_name FROM information_schema.columns 
                        WHERE table_name = $1 AND column_name = $2
                    """, table_name, column)
                    
                    if not result:
                        logger.warning(f"Столбец {column} не найден в таблице {table_name}")
        
        logger.info("Проверка столбцов завершена")
    
    async def закрыть(self):
        """Закрытие пула соединений базы данных."""
        if self.pool:
            await self.pool.close()
            logger.info("Пул базы данных закрыт")
    
    async def получить_пользователя(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получить пользователя по ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM пользователи WHERE id = $1", user_id
            )
            return dict(row) if row else None
    
    async def создать_или_обновить_пользователя(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Создать или обновить пользователя."""
        async with self.pool.acquire() as conn:
            user_id = user_data['id']
            
            # Проверка существования пользователя
            existing = await conn.fetchrow("SELECT id FROM пользователи WHERE id = $1", user_id)
            
            if existing:
                # Обновление существующего пользователя
                await conn.execute("""
                    UPDATE пользователи SET 
                        username = $2, 
                        first_name = $3, 
                        last_name = $4,
                        language_code = $5,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = $1
                """, user_id, user_data.get('username'), user_data.get('first_name'),
                user_data.get('last_name'), user_data.get('language_code', 'ru'))
            else:
                # Создание нового пользователя
                await conn.execute("""
                    INSERT INTO пользователи (id, username, first_name, last_name, language_code)
                    VALUES ($1, $2, $3, $4, $5)
                """, user_id, user_data.get('username'), user_data.get('first_name'),
                user_data.get('last_name'), user_data.get('language_code', 'ru'))
            
            # Возврат обновленного пользователя
            row = await conn.fetchrow("SELECT * FROM пользователи WHERE id = $1", user_id)
            return dict(row)
    
    async def получить_сессию_пользователя(self, user_id: int) -> Dict[str, Any]:
        """Получить или создать сессию пользователя."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM разговоры WHERE user_id = $1 ORDER BY updated_at DESC LIMIT 1",
                user_id
            )
            
            if row:
                return dict(row)
            else:
                # Создание новой сессии
                new_session = await conn.fetchrow("""
                    INSERT INTO разговоры (user_id, session_data, persona, language)
                    VALUES ($1, '{}', 'default', 'ru')
                    RETURNING *
                """, user_id)
                return dict(new_session)
    
    async def обновить_сессию_пользователя(self, user_id: int, session_data: Dict[str, Any]):
        """Обновить сессию пользователя."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE разговоры SET 
                    session_data = $2,
                    persona = $3,
                    language = $4,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = $1
            """, user_id, session_data.get('session_data', {}),
            session_data.get('persona', 'default'), session_data.get('language', 'ru'))
    
    async def добавить_сообщение(self, user_id: int, role: str, content: str, 
                         message_type: str = 'text', metadata: Dict = None):
        """Добавить сообщение в историю."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO сообщения (user_id, role, content, message_type, metadata)
                VALUES ($1, $2, $3, $4, $5)
            """, user_id, role, content, message_type, metadata or {})
    
    async def получить_последние_сообщения(self, user_id: int, limit: int = None) -> List[Dict[str, Any]]:
        """Получить последние сообщения пользователя."""
        if limit is None:
            limit = настройки.max_history_messages
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT role, content, message_type, metadata, created_at
                FROM сообщения 
                WHERE user_id = $1 
                ORDER BY created_at DESC 
                LIMIT $2
            """, user_id, limit)
            
            # Возврат в хронологическом порядке (старые первые)
            return [dict(row) for row in reversed(rows)]
    
    async def записать_статистику(self, user_id: int, action: str, duration_ms: int = None,
                       status: str = 'success', metadata: Dict = None, cost_tokens: int = 0):
        """Записать статистику использования."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO статистика_использования (user_id, action, duration_ms, status, metadata, cost_tokens)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, user_id, action, duration_ms, status, metadata or {}, cost_tokens)
    
    async def получить_дневную_статистику(self, user_id: int, action: str = None) -> int:
        """Получить количество использований за сегодня."""
        async with self.pool.acquire() as conn:
            if action:
                count = await conn.fetchval("""
                    SELECT COUNT(*) FROM статистика_использования 
                    WHERE user_id = $1 AND action = $2 
                    AND DATE(created_at) = CURRENT_DATE
                    AND status = 'success'
                """, user_id, action)
            else:
                count = await conn.fetchval("""
                    SELECT COUNT(*) FROM статистика_использования 
                    WHERE user_id = $1 
                    AND DATE(created_at) = CURRENT_DATE
                    AND status = 'success'
                """, user_id)
            return count or 0
    
    async def создать_платеж(self, user_id: int, plan: str, amount: int) -> int:
        """Создать запись платежа."""
        async with self.pool.acquire() as conn:
            payment_id = await conn.fetchval("""
                INSERT INTO платежи (user_id, plan, amount, status)
                VALUES ($1, $2, $3, 'pending')
                RETURNING id
            """, user_id, plan, amount)
            return payment_id
    
    async def обновить_платеж(self, payment_id: int, telegram_charge_id: str,
                           provider_charge_id: str, status: str = 'completed'):
        """Обновить платеж с ID зарядов."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE платежи SET 
                    telegram_payment_charge_id = $2,
                    provider_payment_charge_id = $3,
                    status = $4
                WHERE id = $1
            """, payment_id, telegram_charge_id, provider_charge_id, status)
    
    async def обновить_план_пользователя(self, user_id: int, plan: str, expires_at: datetime = None):
        """Обновить план пользователя."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE пользователи SET 
                    plan = $2,
                    plan_expires_at = $3,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
            """, user_id, plan, expires_at)
    
    async def добавить_напоминание(self, user_id: int, text: str, remind_at: datetime) -> int:
        """Добавить напоминание."""
        async with self.pool.acquire() as conn:
            reminder_id = await conn.fetchval("""
                INSERT INTO напоминания (user_id, text, remind_at)
                VALUES ($1, $2, $3)
                RETURNING id
            """, user_id, text, remind_at)
            return reminder_id
    
    async def получить_ожидающие_напоминания(self) -> List[Dict[str, Any]]:
        """Получить напоминания, которые нужно отправить."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM напоминания 
                WHERE sent = FALSE AND remind_at <= CURRENT_TIMESTAMP
                ORDER BY remind_at
            """)
            return [dict(row) for row in rows]
    
    async def отметить_напоминание_отправленным(self, reminder_id: int):
        """Отметить напоминание как отправленное."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE напоминания SET sent = TRUE WHERE id = $1
            """, reminder_id)
    
    async def установить_админа(self, user_id: int, is_admin: bool):
        """Установить статус администратора пользователя."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE пользователи SET is_admin = $2 WHERE id = $1
            """, user_id, is_admin)
    
    async def получить_статистику(self) -> Dict[str, Any]:
        """Получить статистику платформы."""
        async with self.pool.acquire() as conn:
            total_users = await conn.fetchval("SELECT COUNT(*) FROM пользователи")
            
            # Пользователи по планам
            plan_stats = await conn.fetch("""
                SELECT plan, COUNT(*) as count FROM пользователи GROUP BY plan
            """)
            
            # Сегодняшнее использование
            today_usage = await conn.fetch("""
                SELECT action, COUNT(*) as count 
                FROM статистика_использования 
                WHERE DATE(created_at) = CURRENT_DATE 
                GROUP BY action
            """)
            
            # Доход за этот месяц
            monthly_revenue = await conn.fetchval("""
                SELECT COALESCE(SUM(amount), 0) FROM платежи 
                WHERE status = 'completed' 
                AND DATE_TRUNC('month', created_at) = DATE_TRUNC('month', CURRENT_DATE)
            """) or 0
            
            return {
                'total_users': total_users,
                'plan_distribution': {row['plan']: row['count'] for row in plan_stats},
                'today_usage': {row['action']: row['count'] for row in today_usage},
                'monthly_revenue_rub': monthly_revenue
            }


# Глобальный экземпляр менеджера базы данных
база_данных = МенеджерБазыДанных()