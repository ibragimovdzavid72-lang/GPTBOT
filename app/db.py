"""Database module with PostgreSQL models and migrations."""

import asyncio
import asyncpg
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from app.config import settings
import logging

logger = logging.getLogger(__name__)

# Database migrations SQL
MIGRATIONS_SQL = """
-- Users table
CREATE TABLE IF NOT EXISTS users (
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

-- Sessions table for conversation context
CREATE TABLE IF NOT EXISTS sessions (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    session_data JSONB DEFAULT '{}',
    persona VARCHAR(50) DEFAULT 'default',
    language VARCHAR(10) DEFAULT 'ru',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Messages table for chat history
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    message_type VARCHAR(20) DEFAULT 'text',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Usage analytics table
CREATE TABLE IF NOT EXISTS usage (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    action VARCHAR(50) NOT NULL,
    duration_ms INTEGER,
    status VARCHAR(20) DEFAULT 'success',
    metadata JSONB DEFAULT '{}',
    cost_tokens INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Payments table
CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    telegram_payment_charge_id VARCHAR(255) UNIQUE,
    provider_payment_charge_id VARCHAR(255),
    amount INTEGER NOT NULL,
    currency VARCHAR(10) DEFAULT 'RUB',
    plan VARCHAR(20) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Reminders table
CREATE TABLE IF NOT EXISTS reminders (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    remind_at TIMESTAMP NOT NULL,
    sent BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_users_plan ON users(plan);
CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_usage_user_id ON usage(user_id);
CREATE INDEX IF NOT EXISTS idx_usage_created_at ON usage(created_at);
CREATE INDEX IF NOT EXISTS idx_usage_action ON usage(action);
CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id);
CREATE INDEX IF NOT EXISTS idx_reminders_user_id ON reminders(user_id);
CREATE INDEX IF NOT EXISTS idx_reminders_remind_at ON reminders(remind_at);
CREATE INDEX IF NOT EXISTS idx_reminders_sent ON reminders(sent);
"""


class DatabaseManager:
    """Database manager for PostgreSQL operations."""
    
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
    
    async def init_db(self):
        """Initialize database connection pool."""
        try:
            self.pool = await asyncpg.create_pool(
                settings.database_url,
                min_size=5,
                max_size=20,
                command_timeout=60
            )
            logger.info("Database pool created successfully")
            
            # Run migrations
            await self.run_migrations()
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    async def run_migrations(self):
        """Run database migrations."""
        if not self.pool:
            raise RuntimeError("Database pool not initialized")
        
        async with self.pool.acquire() as conn:
            try:
                await conn.execute(MIGRATIONS_SQL)
                logger.info("Database migrations completed successfully")
            except Exception as e:
                logger.error(f"Failed to run migrations: {e}")
                raise
    
    async def close(self):
        """Close database connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("Database pool closed")
    
    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE id = $1", user_id
            )
            return dict(row) if row else None
    
    async def create_or_update_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create or update user."""
        async with self.pool.acquire() as conn:
            user_id = user_data['id']
            
            # Check if user exists
            existing = await conn.fetchrow("SELECT id FROM users WHERE id = $1", user_id)
            
            if existing:
                # Update existing user
                await conn.execute("""
                    UPDATE users SET 
                        username = $2, 
                        first_name = $3, 
                        last_name = $4,
                        language_code = $5,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = $1
                """, user_id, user_data.get('username'), user_data.get('first_name'),
                user_data.get('last_name'), user_data.get('language_code', 'ru'))
            else:
                # Create new user
                await conn.execute("""
                    INSERT INTO users (id, username, first_name, last_name, language_code)
                    VALUES ($1, $2, $3, $4, $5)
                """, user_id, user_data.get('username'), user_data.get('first_name'),
                user_data.get('last_name'), user_data.get('language_code', 'ru'))
            
            # Return updated user
            row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
            return dict(row)
    
    async def get_user_session(self, user_id: int) -> Dict[str, Any]:
        """Get or create user session."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM sessions WHERE user_id = $1 ORDER BY updated_at DESC LIMIT 1",
                user_id
            )
            
            if row:
                return dict(row)
            else:
                # Create new session
                new_session = await conn.fetchrow("""
                    INSERT INTO sessions (user_id, session_data, persona, language)
                    VALUES ($1, '{}', 'default', 'ru')
                    RETURNING *
                """, user_id)
                return dict(new_session)
    
    async def update_user_session(self, user_id: int, session_data: Dict[str, Any]):
        """Update user session."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE sessions SET 
                    session_data = $2,
                    persona = $3,
                    language = $4,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = $1
            """, user_id, session_data.get('session_data', {}),
            session_data.get('persona', 'default'), session_data.get('language', 'ru'))
    
    async def add_message(self, user_id: int, role: str, content: str, 
                         message_type: str = 'text', metadata: Dict = None):
        """Add message to history."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO messages (user_id, role, content, message_type, metadata)
                VALUES ($1, $2, $3, $4, $5)
            """, user_id, role, content, message_type, metadata or {})
    
    async def get_recent_messages(self, user_id: int, limit: int = None) -> List[Dict[str, Any]]:
        """Get recent messages for user."""
        if limit is None:
            limit = settings.max_history_messages
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT role, content, message_type, metadata, created_at
                FROM messages 
                WHERE user_id = $1 
                ORDER BY created_at DESC 
                LIMIT $2
            """, user_id, limit)
            
            # Return in chronological order (oldest first)
            return [dict(row) for row in reversed(rows)]
    
    async def log_usage(self, user_id: int, action: str, duration_ms: int = None,
                       status: str = 'success', metadata: Dict = None, cost_tokens: int = 0):
        """Log usage analytics."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO usage (user_id, action, duration_ms, status, metadata, cost_tokens)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, user_id, action, duration_ms, status, metadata or {}, cost_tokens)
    
    async def get_daily_usage(self, user_id: int, action: str = None) -> int:
        """Get today's usage count for user."""
        async with self.pool.acquire() as conn:
            if action:
                count = await conn.fetchval("""
                    SELECT COUNT(*) FROM usage 
                    WHERE user_id = $1 AND action = $2 
                    AND DATE(created_at) = CURRENT_DATE
                    AND status = 'success'
                """, user_id, action)
            else:
                count = await conn.fetchval("""
                    SELECT COUNT(*) FROM usage 
                    WHERE user_id = $1 
                    AND DATE(created_at) = CURRENT_DATE
                    AND status = 'success'
                """, user_id)
            return count or 0
    
    async def create_payment(self, user_id: int, plan: str, amount: int) -> int:
        """Create payment record."""
        async with self.pool.acquire() as conn:
            payment_id = await conn.fetchval("""
                INSERT INTO payments (user_id, plan, amount, status)
                VALUES ($1, $2, $3, 'pending')
                RETURNING id
            """, user_id, plan, amount)
            return payment_id
    
    async def update_payment(self, payment_id: int, telegram_charge_id: str,
                           provider_charge_id: str, status: str = 'completed'):
        """Update payment with charge IDs."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE payments SET 
                    telegram_payment_charge_id = $2,
                    provider_payment_charge_id = $3,
                    status = $4
                WHERE id = $1
            """, payment_id, telegram_charge_id, provider_charge_id, status)
    
    async def upgrade_user_plan(self, user_id: int, plan: str, expires_at: datetime = None):
        """Upgrade user plan."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE users SET 
                    plan = $2,
                    plan_expires_at = $3,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
            """, user_id, plan, expires_at)
    
    async def add_reminder(self, user_id: int, text: str, remind_at: datetime) -> int:
        """Add reminder."""
        async with self.pool.acquire() as conn:
            reminder_id = await conn.fetchval("""
                INSERT INTO reminders (user_id, text, remind_at)
                VALUES ($1, $2, $3)
                RETURNING id
            """, user_id, text, remind_at)
            return reminder_id
    
    async def get_pending_reminders(self) -> List[Dict[str, Any]]:
        """Get reminders that need to be sent."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM reminders 
                WHERE sent = FALSE AND remind_at <= CURRENT_TIMESTAMP
                ORDER BY remind_at
            """)
            return [dict(row) for row in rows]
    
    async def mark_reminder_sent(self, reminder_id: int):
        """Mark reminder as sent."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE reminders SET sent = TRUE WHERE id = $1
            """, reminder_id)
    
    async def set_admin(self, user_id: int, is_admin: bool):
        """Set user admin status."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE users SET is_admin = $2 WHERE id = $1
            """, user_id, is_admin)
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get platform statistics."""
        async with self.pool.acquire() as conn:
            total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
            
            # Users by plan
            plan_stats = await conn.fetch("""
                SELECT plan, COUNT(*) as count FROM users GROUP BY plan
            """)
            
            # Today's usage
            today_usage = await conn.fetch("""
                SELECT action, COUNT(*) as count 
                FROM usage 
                WHERE DATE(created_at) = CURRENT_DATE 
                GROUP BY action
            """)
            
            # Revenue this month
            monthly_revenue = await conn.fetchval("""
                SELECT COALESCE(SUM(amount), 0) FROM payments 
                WHERE status = 'completed' 
                AND DATE_TRUNC('month', created_at) = DATE_TRUNC('month', CURRENT_DATE)
            """) or 0
            
            return {
                'total_users': total_users,
                'plan_distribution': {row['plan']: row['count'] for row in plan_stats},
                'today_usage': {row['action']: row['count'] for row in today_usage},
                'monthly_revenue_rub': monthly_revenue
            }


# Global database manager instance
db = DatabaseManager()