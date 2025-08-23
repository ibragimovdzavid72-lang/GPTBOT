"""Русский Менеджер Базы Данных"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, date
from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass

import asyncpg
import structlog
from config_ru import настройки, получить_лимиты_тарифа

лог = structlog.get_logger("база_данных")


@dataclass
class Пользователь:
    """Модель пользователя."""
    ид: int
    телеграм_ид: int
    имя_пользователя: Optional[str]
    имя: Optional[str]
    фамилия: Optional[str]
    код_языка: str
    тариф_подписки: str
    подписка_истекает: Optional[datetime]
    это_админ: bool
    заблокирован: bool
    дневных_сообщений: int
    дневных_изображений: int
    дневных_минут_голоса: int
    последняя_активность: datetime
    создан: datetime
    обновлен: datetime


class МенеджерБД:
    """Продвинутый менеджер базы данных с PostgreSQL."""
    
    def __init__(self, ссылка_бд: str):
        self.ссылка_бд = ссылка_бд
        self.пул: Optional[asyncpg.Pool] = None
        self._инициализирован = False
    
    async def инициализировать(self):
        """Инициализировать подключение к БД и запустить миграции."""
        try:
            # Создать пул соединений
            self.пул = await asyncpg.create_pool(
                self.ссылка_бд,
                min_size=настройки.база_данных.мин_соединений,
                max_size=настройки.база_данных.макс_соединений,
                server_settings={
                    'application_name': 'русский_телеграм_бот',
                    'timezone': настройки.часовой_пояс
                }
            )
            
            лог.info("Пул базы данных создан успешно")
            
            # Запустить миграции
            await self._запустить_миграции()
            
            self._инициализирован = True
            лог.info("База данных инициализирована успешно")
            
        except Exception as e:
            лог.error("Не удалось инициализировать базу данных", ошибка=str(e))
            raise
    
    async def закрыть(self):
        """Закрыть соединения с базой данных."""
        if self.пул:
            await self.пул.close()
            лог.info("Соединения с базой данных закрыты")
    
    async def проверка_здоровья(self) -> bool:
        """Проверить состояние базы данных."""
        try:
            async with self.пул.acquire() as соединение:
                await соединение.fetchval("SELECT 1")
            return True
        except Exception as e:
            лог.error("Проверка здоровья БД не удалась", ошибка=str(e))
            return False
    
    async def _запустить_миграции(self):
        """Запустить миграции базы данных."""
        миграции = [
            self._создать_таблицу_пользователей,
            self._создать_таблицу_разговоров,
            self._создать_таблицу_использования,
            self._создать_таблицу_напоминаний,
            self._создать_таблицу_платежей,
            self._создать_индексы,
        ]
        
        async with self.пул.acquire() as соединение:
            for миграция in миграции:
                try:
                    await миграция(соединение)
                    лог.debug(f"Миграция {миграция.__name__} выполнена")
                except Exception as e:
                    лог.error(f"Миграция {миграция.__name__} не удалась", ошибка=str(e))
                    raise
    
    async def _создать_таблицу_пользователей(self, соединение: asyncpg.Connection):
        """Создать таблицу пользователей."""
        await соединение.execute("""
            CREATE TABLE IF NOT EXISTS пользователи (
                ид SERIAL PRIMARY KEY,
                телеграм_ид BIGINT UNIQUE NOT NULL,
                имя_пользователя TEXT,
                имя TEXT,
                фамилия TEXT,
                код_языка TEXT DEFAULT 'ru',
                тариф_подписки TEXT DEFAULT 'БЕСПЛАТНЫЙ',
                подписка_истекает TIMESTAMP WITH TIME ZONE,
                это_админ BOOLEAN DEFAULT FALSE,
                заблокирован BOOLEAN DEFAULT FALSE,
                дневных_сообщений INTEGER DEFAULT 0,
                дневных_изображений INTEGER DEFAULT 0,
                дневных_минут_голоса INTEGER DEFAULT 0,
                последняя_активность TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                создан TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                обновлен TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
    
    async def _создать_таблицу_разговоров(self, соединение: asyncpg.Connection):
        """Создать таблицу разговоров."""
        await соединение.execute("""
            CREATE TABLE IF NOT EXISTS разговоры (
                ид SERIAL PRIMARY KEY,
                ид_пользователя INTEGER REFERENCES пользователи(ид) ON DELETE CASCADE,
                роль TEXT NOT NULL CHECK (роль IN ('пользователь', 'помощник', 'система')),
                содержимое TEXT NOT NULL,
                токены INTEGER DEFAULT 0,
                метаданные JSONB DEFAULT '{}',
                создан TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
    
    async def _создать_таблицу_использования(self, соединение: asyncpg.Connection):
        """Создать таблицу статистики использования."""
        await соединение.execute("""
            CREATE TABLE IF NOT EXISTS статистика_использования (
                ид SERIAL PRIMARY KEY,
                ид_пользователя INTEGER REFERENCES пользователи(ид) ON DELETE CASCADE,
                дата DATE DEFAULT CURRENT_DATE,
                отправлено_сообщений INTEGER DEFAULT 0,
                сгенерировано_изображений INTEGER DEFAULT 0,
                минут_голоса INTEGER DEFAULT 0,
                использовано_токенов INTEGER DEFAULT 0,
                вызовов_апи INTEGER DEFAULT 0,
                создан TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                UNIQUE(ид_пользователя, дата)
            )
        """)
    
    async def _создать_таблицу_напоминаний(self, соединение: asyncpg.Connection):
        """Создать таблицу напоминаний."""
        await соединение.execute("""
            CREATE TABLE IF NOT EXISTS напоминания (
                ид SERIAL PRIMARY KEY,
                ид_пользователя INTEGER REFERENCES пользователи(ид) ON DELETE CASCADE,
                ид_чата BIGINT NOT NULL,
                задача TEXT NOT NULL,
                напомнить_в TIMESTAMP WITH TIME ZONE NOT NULL,
                отправлено BOOLEAN DEFAULT FALSE,
                создан TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
    
    async def _создать_таблицу_платежей(self, соединение: asyncpg.Connection):
        """Создать таблицу платежей."""
        await соединение.execute("""
            CREATE TABLE IF NOT EXISTS платежи (
                ид SERIAL PRIMARY KEY,
                ид_пользователя INTEGER REFERENCES пользователи(ид) ON DELETE CASCADE,
                ид_платежа_телеграм TEXT UNIQUE,
                ид_платежа_провайдера TEXT,
                сумма INTEGER NOT NULL,
                валюта TEXT DEFAULT 'RUB',
                тариф TEXT NOT NULL,
                дней_длительности INTEGER DEFAULT 30,
                статус TEXT DEFAULT 'ожидание' CHECK (статус IN ('ожидание', 'завершен', 'провален', 'возвращен')),
                создан TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
    
    async def _создать_индексы(self, соединение: asyncpg.Connection):
        """Создать индексы базы данных для производительности."""
        индексы = [
            "CREATE INDEX IF NOT EXISTS idx_пользователи_телеграм_ид ON пользователи(телеграм_ид)",
            "CREATE INDEX IF NOT EXISTS idx_разговоры_пользователь ON разговоры(ид_пользователя)",
            "CREATE INDEX IF NOT EXISTS idx_напоминания_время ON напоминания(напомнить_в) WHERE NOT отправлено",
        ]
        
        for индекс_sql in индексы:
            await соединение.execute(индекс_sql)
    
    # Методы управления пользователями
    async def получить_или_создать_пользователя(self, телеграм_ид: int, **kwargs) -> Пользователь:
        """Получить существующего пользователя или создать нового."""
        async with self.пул.acquire() as соединение:
            # Попытаться получить существующего пользователя
            строка = await соединение.fetchrow(
                "SELECT * FROM пользователи WHERE телеграм_ид = $1", телеграм_ид
            )
            
            if строка:
                # Обновить последнюю активность
                await соединение.execute(
                    "UPDATE пользователи SET последняя_активность = NOW() WHERE телеграм_ид = $1",
                    телеграм_ид
                )
                return Пользователь(**dict(строка))
            
            # Создать нового пользователя
            данные_пользователя = {
                'телеграм_ид': телеграм_ид,
                'имя_пользователя': kwargs.get('имя_пользователя'),
                'имя': kwargs.get('имя'),
                'фамилия': kwargs.get('фамилия'),
                'код_языка': kwargs.get('код_языка', 'ru')
            }
            
            строка = await соединение.fetchrow("""
                INSERT INTO пользователи (телеграм_ид, имя_пользователя, имя, фамилия, код_языка)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING *
            """, телеграм_ид, данные_пользователя['имя_пользователя'], данные_пользователя['имя'],
                данные_пользователя['фамилия'], данные_пользователя['код_языка'])
            
            лог.info("Новый пользователь создан", телеграм_ид=телеграм_ид)
            return Пользователь(**dict(строка))
    
    async def проверить_лимиты_пользователя(self, телеграм_ид: int) -> Dict[str, Any]:
        """Проверить лимиты использования пользователя."""
        async with self.пул.acquire() as соединение:
            пользователь = await соединение.fetchrow(
                "SELECT тариф_подписки, дневных_сообщений, дневных_изображений, дневных_минут_голоса FROM пользователи WHERE телеграм_ид=$1",
                телеграм_ид
            )
            
            if not пользователь:
                return {"разрешено": False, "причина": "Пользователь не найден"}
            
            лимиты = получить_лимиты_тарифа(пользователь['тариф_подписки'])
            
            return {
                "разрешено": True,
                "тариф": пользователь['тариф_подписки'],
                "лимиты": {
                    "сообщения": {"использовано": пользователь['дневных_сообщений'], "лимит": лимиты.сообщений_в_день},
                    "изображения": {"использовано": пользователь['дневных_изображений'], "лимит": лимиты.изображений_в_день},
                    "голос": {"использовано": пользователь['дневных_минут_голоса'], "лимит": лимиты.минут_голоса_в_день}
                },
                "может_отправить_сообщение": пользователь['дневных_сообщений'] < лимиты.сообщений_в_день,
                "может_создать_изображение": пользователь['дневных_изображений'] < лимиты.изображений_в_день,
                "может_использовать_голос": пользователь['дневных_минут_голоса'] < лимиты.минут_голоса_в_день
            }
    
    async def увеличить_использование(self, телеграм_ид: int, тип_использования: str, количество: int = 1):
        """Увеличить счетчики использования пользователя."""
        async with self.пул.acquire() as соединение:
            if тип_использования == "сообщения":
                await соединение.execute(
                    "UPDATE пользователи SET дневных_сообщений = дневных_сообщений + $1 WHERE телеграм_ид = $2",
                    количество, телеграм_ид
                )
            elif тип_использования == "изображения":
                await соединение.execute(
                    "UPDATE пользователи SET дневных_изображений = дневных_изображений + $1 WHERE телеграм_ид = $2",
                    количество, телеграм_ид
                )
            elif тип_использования == "голос":
                await соединение.execute(
                    "UPDATE пользователи SET дневных_минут_голоса = дневных_минут_голоса + $1 WHERE телеграм_ид = $2",
                    количество, телеграм_ид
                )
    
    async def получить_просроченные_напоминания(self) -> List[Dict[str, Any]]:
        """Получить все просроченные напоминания."""
        async with self.пул.acquire() as соединение:
            строки = await соединение.fetch("""
                SELECT н.*, п.телеграм_ид 
                FROM напоминания н
                JOIN пользователи п ON н.ид_пользователя = п.ид
                WHERE н.напомнить_в <= NOW() AND NOT н.отправлено
                ORDER BY н.напомнить_в
            """)
            
            return [dict(строка) for строка in строки]
    
    async def отметить_напоминание_отправленным(self, ид_напоминания: int):
        """Отметить напоминание как отправленное."""
        async with self.пул.acquire() as соединение:
            await соединение.execute(
                "UPDATE напоминания SET отправлено = TRUE WHERE ид = $1", ид_напоминания
            )
    
    async def получить_системную_статистику(self) -> Dict[str, Any]:
        """Получить системную статистику."""
        async with self.пул.acquire() as соединение:
            # Статистика пользователей
            всего_пользователей = await соединение.fetchval("SELECT COUNT(*) FROM пользователи")
            активных_пользователей_сегодня = await соединение.fetchval("""
                SELECT COUNT(*) FROM пользователи 
                WHERE последняя_активность::date = CURRENT_DATE
            """)
            
            # Статистика использования
            статистика_сегодня = await соединение.fetchrow("""
                SELECT 
                    COALESCE(SUM(отправлено_сообщений), 0) as сообщений_сегодня,
                    COALESCE(SUM(сгенерировано_изображений), 0) as изображений_сегодня,
                    COALESCE(SUM(минут_голоса), 0) as голоса_сегодня
                FROM статистика_использования 
                WHERE дата = CURRENT_DATE
            """)
            
            return {
                "всего_пользователей": всего_пользователей,
                "активных_пользователей_сегодня": активных_пользователей_сегодня,
                "сообщений_сегодня": статистика_сегодня['сообщений_сегодня'],
                "изображений_сегодня": статистика_сегодня['изображений_сегодня'],
                "минут_голоса_сегодня": статистика_сегодня['голоса_сегодня'],
                "время": datetime.utcnow().isoformat()
            }
    
    async def очистить_старые_сессии(self, часов: int = 24):
        """Очистить старые сессии."""
        # Реализация очистки сессий
        pass
    
    async def очистить_старые_разговоры(self, дней: int = 30):
        """Очистить старую историю разговоров."""
        # Реализация очистки разговоров
        pass
    
    async def вакуум_базы_данных(self):
        """Вакуум базы данных для оптимизации."""
        async with self.пул.acquire() as соединение:
            await соединение.execute("VACUUM ANALYZE")
            лог.info("Вакуум базы данных завершен")