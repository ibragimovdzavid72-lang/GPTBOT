"""
Модуль админ-панели для Telegram-бота.

Содержит команды и функции для управления ботом администраторами,
включая статистику, управление пользователями и настройки бота.
"""

from aiogram import types
from aiogram.filters import CommandObject
import asyncpg

from .config import settings


def is_admin(user_id: int) -> bool:
    """
    Проверяет, является ли пользователь администратором бота.

    :param user_id: ID пользователя Telegram
    :return: True, если пользователь является администратором
    """
    return user_id in settings.ADMINS


def is_super_admin(user_id: int) -> bool:
    """
    Проверяет, является ли пользователь супер-администратором с доступом к админ-панели.
    
    Обычные админы могут использовать команды через /,
    но только супер-админ может видеть админ-панель.
    
    Супер-админ определяется как ПЕРВЫЙ ID в переменной окружения ADMINS.
    Например, если ADMINS="1752390166,123456789", то супер-админ = 1752390166

    :param user_id: ID пользователя Telegram
    :return: True, если пользователь является супер-администратором
    """
    if settings.ADMINS:
        # Супер-админ - это первый ID в списке ADMINS
        super_admin_id = settings.ADMINS[0]
        return user_id == super_admin_id
    else:
        # Если список ADMINS пуст - отказываем в доступе
        return False


async def is_bot_active(pool: asyncpg.pool.Pool) -> bool:
    """
    Проверяет, активен ли бот.

    :param pool: Пул подключений к базе данных
    :return: True, если бот активен, False otherwise
    """
    if not pool:
        return True  # Если нет подключения к БД, бот считается активным
        
    try:
        async with pool.acquire() as conn:
            # Проверяем существование таблицы bot_status
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'bot_status'
                )
            """)
            
            if not table_exists:
                # Если таблицы нет, бот активен по умолчанию
                return True
                
            row = await conn.fetchrow("SELECT is_active FROM bot_status ORDER BY id DESC LIMIT 1")
            if row is None:
                # Если записей нет, бот активен по умолчанию
                return True
            return row["is_active"]
    except Exception:
        # В случае ошибки считаем бот активным
        return True


async def cmd_admin_stats(message: types.Message, pool: asyncpg.pool.Pool):
    """
    Обработчик команды /admin_stats - показывает статистику для администраторов.

    :param message: Сообщение от пользователя
    :param pool: Пул подключений к базе данных
    """
    if not pool:
        await message.answer("⛔ Нет подключения к базе данных.")
        return

    try:
        async with pool.acquire() as conn:
            # Получаем количество уникальных пользователей
            count_users = await conn.fetchval("SELECT COUNT(DISTINCT username) FROM logs WHERE username IS NOT NULL")
            # Получаем общее количество сообщений
            count_msgs = await conn.fetchval("SELECT COUNT(*) FROM logs")
            # Получаем количество ошибок (сообщений с ошибками)
            count_errors = await conn.fetchval("SELECT COUNT(*) FROM logs WHERE answer LIKE '❌%'")

        await message.answer(
            f"👑 Админ-панель:\n"
            f"📊 Пользователей: {count_users}\n"
            f"💬 Сообщений в базе: {count_msgs}\n"
            f"💥 Ошибок: {count_errors}"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка при получении статистики: {e}")


async def cmd_errors(message: types.Message, pool: asyncpg.pool.Pool):
    """
    Обработчик команды /errors - показывает последние ошибки.

    :param message: Сообщение от пользователя
    :param pool: Пул подключений к базе данных
    """
    if not pool:
        await message.answer("⛔ Нет подключения к базе данных.")
        return

    try:
        async with pool.acquire() as conn:
            # Получаем последние 10 записей с ошибками
            rows = await conn.fetch("SELECT * FROM logs WHERE answer LIKE '❌%' ORDER BY id DESC LIMIT 10")

        if not rows:
            await message.answer("✅ Ошибок не найдено.")
            return

        text = "\n\n".join(
            [f"👤 {r['username'] or 'Неизвестный'}\n🕒 {r['created_at']}\n❓ {r['command']} {r['args']}\n💬 {r['answer']}" for r in rows]
        )
        await message.answer("📋 Последние ошибки:\n\n" + text)
    except Exception as e:
        await message.answer(f"❌ Ошибка при получении логов: {e}")


async def cmd_bot_on(message: types.Message, pool: asyncpg.pool.Pool):
    """
    Обработчик команды /bot_on - включает бота.

    :param message: Сообщение от пользователя
    :param pool: Пул подключений к базе данных
    """
    if not pool:
        await message.answer("⛔ Нет подключения к базе данных.")
        return

    try:
        async with pool.acquire() as conn:
            # Проверяем существование таблицы bot_status
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'bot_status'
                )
            """)
            
            if not table_exists:
                # Создаем таблицу, если её нет
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS bot_status (
                        id SERIAL PRIMARY KEY,
                        is_active BOOLEAN DEFAULT TRUE
                    )
                """)
            
            await conn.execute("INSERT INTO bot_status (is_active) VALUES (TRUE)")
        await message.answer("✅ Бот включён!")
    except Exception as e:
        await message.answer(f"❌ Ошибка при включении бота: {e}")


async def cmd_bot_off(message: types.Message, pool: asyncpg.pool.Pool):
    """
    Обработчик команды /bot_off - выключает бота.

    :param message: Сообщение от пользователя
    :param pool: Пул подключений к базе данных
    """
    if not pool:
        await message.answer("⛔ Нет подключения к базе данных.")
        return

    try:
        async with pool.acquire() as conn:
            # Проверяем существование таблицы bot_status
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'bot_status'
                )
            """)
            
            if not table_exists:
                # Создаем таблицу, если её нет
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS bot_status (
                        id SERIAL PRIMARY KEY,
                        is_active BOOLEAN DEFAULT TRUE
                    )
                """)
            
            await conn.execute("INSERT INTO bot_status (is_active) VALUES (FALSE)")
        await message.answer("🛑 Бот выключен!")
    except Exception as e:
        await message.answer(f"❌ Ошибка при выключении бота: {e}")
