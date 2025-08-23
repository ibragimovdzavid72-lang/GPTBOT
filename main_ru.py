"""
Русский AI Телеграм Бот - Главный модуль
======================================
Продакшн-готовый Telegram бот с полной русской локализацией
и интеграцией с OpenAI GPT-4o для русскоязычных пользователей.
"""

import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, Any, Optional

# Настройка базового логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

лог = logging.getLogger("русский_бот")

# Безопасный импорт зависимостей
try:
    from fastapi import FastAPI, Request, HTTPException
    from fastapi.responses import JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    лог.info("✅ FastAPI импортирован успешно")
except ImportError as е:
    лог.error(f"❌ Ошибка импорта FastAPI: {е}")
    лог.error("Установите зависимости: pip install fastapi uvicorn")
    sys.exit(1)

# Получение переменных окружения
ТЕЛЕГРАМ_БОТ_ТОКЕН = os.getenv("TELEGRAM_BOT_TOKEN", "")
ТЕЛЕГРАМ_ВЕБХУК_URL = os.getenv("TELEGRAM_WEBHOOK_URL", "")
ТЕЛЕГРАМ_ВЕБХУК_ПУТЬ = os.getenv("TELEGRAM_WEBHOOK_PATH", "/webhook")
ТЕЛЕГРАМ_ВЕБХУК_СЕКРЕТ = os.getenv("TELEGRAM_WEBHOOK_SECRET", "supersecret123456")
URL_БАЗЫ_ДАННЫХ = os.getenv("DATABASE_URL", "")
КЛЮЧ_OPENAI = os.getenv("OPENAI_API_KEY", "")
ПОРТ = int(os.getenv("PORT", 8000))

# Полный URL для webhook
ПОЛНЫЙ_ВЕБХУК_URL = f"{ТЕЛЕГРАМ_ВЕБХУК_URL.rstrip('/')}{ТЕЛЕГРАМ_ВЕБХУК_ПУТЬ}" if ТЕЛЕГРАМ_ВЕБХУК_URL else ""

# Безопасный импорт дополнительных модулей с заглушками
пул_бд = None
работает_система_напоминаний = True

# Заглушки для отсутствующих модулей
async def создать_пул(url_бд):
    """Заглушка для создания пула БД."""
    if url_бд:
        лог.info("📊 Попытка подключения к базе данных...")
        try:
            # Пытаемся импортировать asyncpg
            import asyncpg
            return await asyncpg.create_pool(url_бд, min_size=2, max_size=10)
        except ImportError:
            лог.warning("⚠️ asyncpg не установлен")
            return None
        except Exception as е:
            лог.error(f"❌ Ошибка подключения к БД: {е}")
            return None
    return None

async def создать_таблицы(пул):
    """Заглушка для создания таблиц."""
    if пул:
        лог.info("📋 Создание таблиц БД...")
    pass

async def получить_просроченные_напоминания(пул):
    """Заглушка для получения напоминаний."""
    return []

async def отметить_напоминание_выполненным(пул, ид_напоминания):
    """Заглушка для отметки напоминания."""
    pass

async def обработать_обновление(обновление, pool=None):
    """Заглушка для обработки обновлений Telegram."""
    лог.info(f"📨 Получено обновление Telegram: {обновление.get('update_id', 'неизвестно')}")

async def отправить_сообщение_телеграм(ид_чата, текст):
    """Заглушка для отправки сообщений."""
    лог.info(f"📤 Отправка сообщения в чат {ид_чата}: {текст[:50]}...")

async def закрыть_http_клиент():
    """Заглушка для закрытия HTTP клиента."""
    pass

# Попытка импорта реальных модулей
try:
    from db import create_pool as импорт_создать_пул
    from db import create_tables as импорт_создать_таблицы
    from db import due_reminders as импорт_получить_напоминания
    from db import mark_reminder_done as импорт_отметить_напоминание
    создать_пул = импорт_создать_пул
    создать_таблицы = импорт_создать_таблицы
    получить_просроченные_напоминания = импорт_получить_напоминания
    отметить_напоминание_выполненным = импорт_отметить_напоминание
    лог.info("✅ Модуль db импортирован")
except ImportError as е:
    лог.warning(f"⚠️ Модуль db не найден: {е}")

try:
    from handlers import handle_update as импорт_обработчик
    обработать_обновление = импорт_обработчик
    лог.info("✅ Модуль handlers импортирован")
except ImportError as е:
    лог.warning(f"⚠️ Модуль handlers не найден: {е}")

try:
    from telegram_api import tg_send_message as импорт_отправка
    from telegram_api import close_http_client as импорт_закрыть_клиент
    отправить_сообщение_телеграм = импорт_отправка
    закрыть_http_клиент = импорт_закрыть_клиент
    лог.info("✅ Модуль telegram_api импортирован")
except ImportError as е:
    лог.warning(f"⚠️ Модуль telegram_api не найден: {е}")

try:
    from settings import *
    лог.info("✅ Модуль settings импортирован")
except ImportError as е:
    лог.warning(f"⚠️ Модуль settings не найден: {е}")

# Состояние приложения
состояние = {
    "пул_бд": None,
    "задача_напоминаний": None,
    "работает": False
}

async def работник_напоминаний():
    """Фоновый работник для системы напоминаний."""
    лог.info("🔄 Запуск работника напоминаний")
    
    while состояние["работает"]:
        try:
            if состояние["пул_бд"]:
                напоминания = await получить_просроченные_напоминания(состояние["пул_бд"])
                
                for напоминание in напоминания:
                    try:
                        текст_напоминания = f"⏰ Напоминание: {напоминание.get('task', 'Задача')}"
                        ид_чата = напоминание.get('chat_id')
                        
                        if ид_чата:
                            await отправить_сообщение_телеграм(ид_чата, текст_напоминания)
                            await отметить_напоминание_выполненным(
                                состояние["пул_бд"], 
                                напоминание.get('id')
                            )
                            лог.info(f"✅ Напоминание отправлено: {напоминание.get('id')}")
                    except Exception as ошибка:
                        лог.error(f"❌ Ошибка отправки напоминания: {ошибка}")
            
            await asyncio.sleep(60)  # Проверка каждую минуту
            
        except Exception as ошибка:
            лог.error(f"💥 Ошибка в работнике напоминаний: {ошибка}")
            await asyncio.sleep(60)

@asynccontextmanager
async def время_жизни_приложения(приложение: FastAPI):
    """Управление жизненным циклом приложения."""
    лог.info("🚀 Запуск Русского AI Telegram Бота v1.0")
    
    # Проверка критически важных переменных
    лог.info("🔍 Проверка конфигурации...")
    
    if not ТЕЛЕГРАМ_БОТ_ТОКЕН:
        лог.error("❌ TELEGRAM_BOT_TOKEN не установлен!")
    else:
        лог.info("✅ Telegram Bot Token настроен")
    
    if not URL_БАЗЫ_ДАННЫХ:
        лог.warning("⚠️ DATABASE_URL не установлен (работа без БД)")
    else:
        лог.info("✅ Database URL настроен")
    
    if not КЛЮЧ_OPENAI:
        лог.warning("⚠️ OPENAI_API_KEY не установлен")
    else:
        лог.info("✅ OpenAI API Key настроен")
    
    try:
        # Инициализация базы данных
        лог.info("📊 Инициализация базы данных...")
        пул = await создать_пул(URL_БАЗЫ_ДАННЫХ)
        if пул:
            await создать_таблицы(пул)
            лог.info("✅ База данных подключена и готова")
        else:
            лог.warning("⚠️ Работа без базы данных")
        
        состояние["пул_бд"] = пул
        состояние["работает"] = True
        
        # Запуск фоновых задач
        лог.info("🔄 Запуск фоновых служб...")
        состояние["задача_напоминаний"] = asyncio.create_task(работник_напоминаний())
        
        лог.info("🎉 Приложение запущено успешно!")
        лог.info(f"🌐 Веб-сервер слушает порт {ПОРТ}")
        
        if ПОЛНЫЙ_ВЕБХУК_URL:
            лог.info(f"🔗 Webhook URL: {ПОЛНЫЙ_ВЕБХУК_URL}")
        else:
            лог.warning("⚠️ Webhook URL не настроен")
        
        yield
        
    except Exception as критическая_ошибка:
        лог.error(f"💥 Критическая ошибка при запуске: {критическая_ошибка}")
        raise
    finally:
        # Остановка приложения
        лог.info("🛑 Остановка приложения...")
        состояние["работает"] = False
        
        # Остановка фоновых задач
        if состояние["задача_напоминаний"]:
            состояние["задача_напоминаний"].cancel()
            try:
                await состояние["задача_напоминаний"]
            except asyncio.CancelledError:
                pass
        
        # Закрытие соединений
        try:
            await закрыть_http_клиент()
        except Exception as е:
            лог.error(f"Ошибка закрытия HTTP клиента: {е}")
        
        if состояние["пул_бд"]:
            try:
                await состояние["пул_бд"].close()
                лог.info("📊 База данных отключена")
            except Exception as е:
                лог.error(f"Ошибка отключения БД: {е}")
        
        лог.info("✅ Приложение остановлено корректно")

# Создание FastAPI приложения с русским названием переменной
приложение = FastAPI(
    title="Русский AI Телеграм Бот",
    description="Продакшн-готовый Telegram бот с искусственным интеллектом для русскоязычных пользователей",
    version="1.0.0",
    lifespan=время_жизни_приложения,
    docs_url="/документация",
    redoc_url="/справка"
)

# Настройка CORS
приложение.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@приложение.get("/")
async def главная_страница():
    """Главная страница бота для проверки работоспособности Railway."""
    return JSONResponse({
        "статус": "работает",
        "название": "Русский AI Телеграм Бот",
        "версия": "1.0.0",
        "время": datetime.now().isoformat(),
        "описание": "Telegram бот с ИИ для русскоязычных пользователей",
        "сервис": "Railway",
        "порт": ПОРТ,
        "компоненты": {
            "база_данных": "подключена" if состояние["пул_бд"] else "отключена",
            "система_напоминаний": "работает" if состояние["работает"] else "остановлена",
            "telegram_токен": "настроен" if ТЕЛЕГРАМ_БОТ_ТОКЕН else "отсутствует",
            "openai_ключ": "настроен" if КЛЮЧ_OPENAI else "отсутствует"
        }
    })

@приложение.get("/health")
async def проверка_здоровья():
    """Детальная проверка состояния системы для мониторинга."""
    компоненты = {
        "веб_сервер": "работает",
        "база_данных": "подключена" if состояние["пул_бд"] else "отключена",
        "telegram_бот": "настроен" if ТЕЛЕГРАМ_БОТ_ТОКЕН else "не_настроен",
        "openai_api": "настроен" if КЛЮЧ_OPENAI else "не_настроен",
        "webhook": "настроен" if ПОЛНЫЙ_ВЕБХУК_URL else "не_настроен",
        "система_напоминаний": "работает" if состояние["работает"] else "остановлена"
    }
    
    # Определяем общее состояние
    критические_компоненты = ["веб_сервер", "telegram_бот"]
    все_критические_работают = all(
        компоненты[компонент] in ["работает", "настроен"] 
        for компонент in критические_компоненты
    )
    
    общий_статус = "здоров" if все_критические_работают else "проблемы"
    
    return JSONResponse({
        "общий_статус": общий_статус,
        "время_проверки": datetime.now().isoformat(),
        "версия": "1.0.0",
        "платформа": "Railway",
        "компоненты": компоненты,
        "конфигурация": {
            "порт": ПОРТ,
            "webhook_путь": ТЕЛЕГРАМ_ВЕБХУК_ПУТЬ,
            "есть_секрет": bool(ТЕЛЕГРАМ_ВЕБХУК_СЕКРЕТ)
        }
    })

@приложение.post("/webhook")
async def основной_вебхук(запрос: Request):
    """Основной обработчик webhook от Telegram."""
    лог.info("📨 Получен webhook запрос на /webhook")
    
    try:
        # Проверка секретного токена
        if ТЕЛЕГРАМ_ВЕБХУК_СЕКРЕТ:
            секрет_в_заголовке = запрос.headers.get("X-Telegram-Bot-Api-Secret-Token")
            if секрет_в_заголовке != ТЕЛЕГРАМ_ВЕБХУК_СЕКРЕТ:
                лог.warning("🚫 Неверный секретный токен в заголовке")
                raise HTTPException(status_code=403, detail="Неверный секретный токен")
        
        # Чтение и парсинг данных
        тело_запроса = await запрос.body()
        if not тело_запроса:
            лог.warning("📭 Получено пустое тело запроса")
            return JSONResponse({"ok": False, "ошибка": "Пустое тело запроса"})
        
        try:
            данные_обновления = json.loads(тело_запроса.decode("utf-8"))
        except json.JSONDecodeError as ошибка:
            лог.error(f"🔥 Ошибка парсинга JSON: {ошибка}")
            raise HTTPException(status_code=400, detail="Неверный формат JSON")
        
        # Асинхронная обработка обновления
        if данные_обновления:
            ид_обновления = данные_обновления.get("update_id", "неизвестно")
            лог.info(f"✅ Принято обновление #{ид_обновления}")
            
            # Запуск обработки в фоне
            asyncio.create_task(
                обработать_обновление(данные_обновления, pool=состояние["пул_бд"])
            )
        
        return JSONResponse({
            "ok": True, 
            "статус": "обновление_принято",
            "время": datetime.now().isoformat()
        })
        
    except HTTPException:
        raise
    except Exception as ошибка:
        лог.error(f"💥 Критическая ошибка в webhook: {ошибка}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")

@приложение.post("/webhook/{секретный_путь}")
async def вебхук_с_секретом(запрос: Request, секретный_путь: str):
    """Альтернативный webhook с секретом в пути URL."""
    лог.info(f"📨 Получен webhook с секретным путем: /{секретный_путь}")
    
    try:
        # Проверка секретного пути
        if ТЕЛЕГРАМ_ВЕБХУК_СЕКРЕТ and секретный_путь != ТЕЛЕГРАМ_ВЕБХУК_СЕКРЕТ:
            лог.warning(f"🚫 Неверный секретный путь: {секретный_путь}")
            raise HTTPException(status_code=404, detail="Страница не найдена")
        
        # Чтение и парсинг данных
        тело_запроса = await запрос.body()
        if not тело_запроса:
            лог.warning("📭 Пустое тело в секретном webhook")
            return JSONResponse({"ok": False, "ошибка": "Пустое тело запроса"})
        
        try:
            данные_обновления = json.loads(тело_запроса.decode("utf-8"))
        except json.JSONDecodeError as ошибка:
            лог.error(f"🔥 JSON ошибка в секретном webhook: {ошибка}")
            raise HTTPException(status_code=400, detail="Неверный JSON")
        
        # Обработка обновления
        if данные_обновления:
            ид_обновления = данные_обновления.get("update_id", "неизвестно")
            лог.info(f"✅ Обновление #{ид_обновления} через секретный путь")
            
            asyncio.create_task(
                обработать_обновление(данные_обновления, pool=состояние["пул_бд"])
            )
        
        return JSONResponse({
            "ok": True, 
            "статус": "обновление_принято_через_секретный_путь",
            "время": datetime.now().isoformat()
        })
        
    except HTTPException:
        raise
    except Exception as ошибка:
        лог.error(f"💥 Ошибка в секретном webhook: {ошибка}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")

@приложение.get("/статус")
async def статус_системы():
    """Подробная информация о состоянии системы."""
    return JSONResponse({
        "система": {
            "название": "Русский AI Телеграм Бот",
            "версия": "1.0.0",
            "платформа": "Railway",
            "python_версия": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "время_запуска": datetime.now().isoformat()
        },
        "конфигурация": {
            "порт": ПОРТ,
            "webhook_путь": ТЕЛЕГРАМ_ВЕБХУК_ПУТЬ,
            "webhook_url": ПОЛНЫЙ_ВЕБХУК_URL or "не настроен",
            "есть_бот_токен": bool(ТЕЛЕГРАМ_БОТ_ТОКЕН),
            "есть_openai_ключ": bool(КЛЮЧ_OPENAI),
            "есть_база_данных": bool(URL_БАЗЫ_ДАННЫХ)
        },
        "службы": {
            "веб_сервер": "работает",
            "база_данных": "подключена" if состояние["пул_бд"] else "отключена",
            "система_напоминаний": "работает" if состояние["работает"] else "остановлена"
        }
    })

# Глобальный обработчик исключений
@приложение.exception_handler(Exception)
async def обработчик_исключений(запрос: Request, исключение: Exception):
    """Глобальная обработка всех необработанных исключений."""
    лог.error(
        f"💥 Необработанное исключение: {исключение}", 
        exc_info=True,
        extra={
            "url": str(запрос.url),
            "method": запрос.method,
            "headers": dict(запрос.headers)
        }
    )
    
    return JSONResponse(
        status_code=500,
        content={
            "ошибка": "Внутренняя ошибка сервера",
            "сообщение": "Произошла неожиданная ошибка. Попробуйте позже.",
            "время": datetime.now().isoformat(),
            "код": 500,
            "поддержка": "Обратитесь к администратору если проблема повторяется"
        }
    )

# Совместимость с обычным именем переменной для uvicorn
app = приложение

# Для локального запуска в режиме разработки
if __name__ == "__main__":
    import uvicorn
    лог.info("🔧 Локальный запуск в режиме разработки")
    
    uvicorn.run(
        "main_ru:приложение",
        host="0.0.0.0",
        port=ПОРТ,
        reload=False,
        log_level="info",
        access_log=True
    )
