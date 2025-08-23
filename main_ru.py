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

# Безопасный импорт FastAPI
try:
    from fastapi import FastAPI, Request, HTTPException
    from fastapi.responses import JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    лог.info("✅ FastAPI импортирован успешно")
except ImportError as е:
    лог.error(f"❌ Ошибка импорта FastAPI: {е}")
    sys.exit(1)

# Получение переменных окружения
ТЕЛЕГРАМ_БОТ_ТОКЕН = os.getenv("TELEGRAM_BOT_TOKEN", "")
ТЕЛЕГРАМ_ВЕБХУК_URL = os.getenv("TELEGRAM_WEBHOOK_URL", "")
ТЕЛЕГРАМ_ВЕБХУК_ПУТЬ = os.getenv("TELEGRAM_WEBHOOK_PATH", "/webhook")
ТЕЛЕГРАМ_ВЕБХУК_СЕКРЕТ = os.getenv("TELEGRAM_WEBHOOK_SECRET", "supersecret123456")
URL_БАЗЫ_ДАННЫХ = os.getenv("DATABASE_URL", "")
КЛЮЧ_OPENAI = os.getenv("OPENAI_API_KEY", "")
ПОРТ = int(os.getenv("PORT", 8000))

# Исправление webhook пути для совместимости
if ТЕЛЕГРАМ_ВЕБХУК_ПУТЬ == "/webhook/supersecret123456":
    # Если путь содержит секрет, разделяем его
    ТЕЛЕГРАМ_ВЕБХУК_ПУТЬ = "/webhook"
    ТЕЛЕГРАМ_ВЕБХУК_СЕКРЕТ = "supersecret123456"
    лог.info("🔧 Исправлен webhook путь и секрет")

# Исправление DATABASE_URL для asyncpg
def исправить_url_бд(url):
    """Исправляет URL базы данных для совместимости с asyncpg."""
    if url and url.startswith('postgresql+asyncpg://'):
        исправленный_url = url.replace('postgresql+asyncpg://', 'postgresql://')
        лог.info("🔧 DATABASE_URL исправлен для asyncpg")
        return исправленный_url
    return url

# Применяем исправление только если URL существует
if URL_БАЗЫ_ДАННЫХ:
    URL_БАЗЫ_ДАННЫХ = исправить_url_бд(URL_БАЗЫ_ДАННЫХ)
# Правильная конструкция webhook URL для совместимости с Railway
if ТЕЛЕГРАМ_ВЕБХУК_URL and ТЕЛЕГРАМ_ВЕБХУК_СЕКРЕТ:
    ПОЛНЫЙ_ВЕБХУК_URL = f"{ТЕЛЕГРАМ_ВЕБХУК_URL.rstrip('/')}/webhook/{ТЕЛЕГРАМ_ВЕБХУК_СЕКРЕТ}"
else:
    ПОЛНЫЙ_ВЕБХУК_URL = f"{ТЕЛЕГРАМ_ВЕБХУК_URL.rstrip('/')}/webhook" if ТЕЛЕГРАМ_ВЕБХУК_URL else ""

# Заглушки для модулей
async def создать_пул_бд(url_бд):
    """Создание пула соединений с базой данных."""
    if not url_бд:
        лог.warning("⚠️ URL базы данных не предоставлен")
        return None
    
    # Дополнительная проверка и исправление URL
    if url_бд.startswith('postgresql+asyncpg://'):
        url_бд = url_бд.replace('postgresql+asyncpg://', 'postgresql://')
        лог.info("🔧 Исправлен URL базы данных внутри функции")
    
    лог.info(f"🔗 Подключение к БД: {url_бд[:50]}...")
    
    try:
        import asyncpg
        пул = await asyncpg.create_pool(url_бд, min_size=2, max_size=10)
        лог.info("✅ Подключение к базе данных успешно")
        return пул
    except ImportError:
        лог.warning("⚠️ asyncpg не установлен")
        return None
    except Exception as е:
        лог.error(f"❌ Ошибка подключения к БД: {е}")
        лог.error(f"URL БД был: {url_бд}")
        return None

async def создать_таблицы_бд(пул):
    """Создание таблиц базы данных."""
    if not пул:
        return
    
    try:
        async with пул.acquire() as соединение:
            # Создание таблицы пользователей сначала
            await соединение.execute("""
                CREATE TABLE IF NOT EXISTS пользователи (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    имя VARCHAR(255),
                    создан TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Создание таблицы сообщений после таблицы пользователей с правильным foreign key
            await соединение.execute("""
                CREATE TABLE IF NOT EXISTS сообщения (
                    id SERIAL PRIMARY KEY,
                    пользователь_id INTEGER REFERENCES пользователи(id),
                    текст TEXT,
                    создано TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
        лог.info("✅ Таблицы базы данных созданы")
    except Exception as е:
        лог.error(f"❌ Ошибка создания таблиц: {е}")
        лог.warning("⚠️ Продолжаем работу без базы данных")

async def обработать_обновление_телеграм(обновление, pool=None):
    """Обработка обновлений от Telegram."""
    ид_обновления = обновление.get('update_id', 'неизвестно')
    лог.info(f"📨 Обработка обновления: {ид_обновления}")
    
    if "message" in обновление:
        сообщение = обновление["message"]
        if "text" in сообщение:
            текст = сообщение["text"]
            чат_ид = сообщение["chat"]["id"]
            пользователь = сообщение.get("from", {}).get("first_name", "Пользователь")
            лог.info(f"💬 Сообщение от {пользователь}: {текст}")
            
            # Здесь будет логика ответа
            await отправить_ответ_телеграм(чат_ид, f"Привет, {пользователь}! Бот получил: {текст}")
    
    лог.info(f"✅ Обновление {ид_обновления} обработано")

async def отправить_ответ_телеграм(чат_ид, текст):
    """Отправка ответа через Telegram API."""
    if not ТЕЛЕГРАМ_БОТ_ТОКЕН:
        лог.warning("⚠️ Telegram Bot Token не настроен")
        return
    
    try:
        import httpx
        
        url = f"https://api.telegram.org/bot{ТЕЛЕГРАМ_БОТ_ТОКЕН}/sendMessage"
        данные = {
            "chat_id": чат_ид,
            "text": текст,
            "parse_mode": "HTML"
        }
        
        async with httpx.AsyncClient() as клиент:
            ответ = await клиент.post(url, json=данные)
            if ответ.status_code == 200:
                лог.info(f"📤 Сообщение отправлено в чат {чат_ид}")
            else:
                лог.error(f"❌ Ошибка отправки: {ответ.status_code}")
                
    except Exception as е:
        лог.error(f"💥 Ошибка отправки сообщения: {е}")

# Безопасный импорт локальных модулей
try:
    from db import create_pool as импорт_пул, create_tables as импорт_таблицы
    создать_пул_бд = импорт_пул
    создать_таблицы_бд = импорт_таблицы
    лог.info("✅ Модуль db импортирован")
except ImportError:
    лог.warning("⚠️ Модуль db не найден, используются заглушки")

try:
    from handlers import handle_update as импорт_обработчик
    обработать_обновление_телеграм = импорт_обработчик
    лог.info("✅ Модуль handlers импортирован")
except ImportError:
    лог.warning("⚠️ Модуль handlers не найден, используется заглушка")

try:
    from telegram_api import tg_send_message as импорт_отправка
    отправить_ответ_телеграм = импорт_отправка
    лог.info("✅ Модуль telegram_api импортирован")
except ImportError:
    лог.warning("⚠️ Модуль telegram_api не найден, используется заглушка")

# Состояние приложения
состояние = {"пул_бд": None, "работает": False}

@asynccontextmanager
async def время_жизни_приложения(app: FastAPI):
    """Управление жизненным циклом приложения."""
    лог.info("🚀 Запуск Русского AI Telegram Бота v1.0")
    
    # Проверка конфигурации
    лог.info("🔍 Проверка конфигурации...")
    if ТЕЛЕГРАМ_БОТ_ТОКЕН:
        лог.info("✅ Telegram Bot Token настроен")
    else:
        лог.error("❌ TELEGRAM_BOT_TOKEN не установлен!")
    
    if URL_БАЗЫ_ДАННЫХ:
        лог.info("✅ Database URL настроен")
    else:
        лог.warning("⚠️ DATABASE_URL не установлен")
    
    if КЛЮЧ_OPENAI:
        лог.info("✅ OpenAI API Key настроен")
    else:
        лог.warning("⚠️ OPENAI_API_KEY не установлен")
    
    # Дополнительная информация о webhook
    лог.info(f"🔗 TELEGRAM_WEBHOOK_URL: {ТЕЛЕГРАМ_ВЕБХУК_URL or 'НЕ УСТАНОВЛЕН'}")
    лог.info(f"🛤️ TELEGRAM_WEBHOOK_PATH: {ТЕЛЕГРАМ_ВЕБХУК_ПУТЬ}")
    лог.info(f"🔑 TELEGRAM_WEBHOOK_SECRET: {'УСТАНОВЛЕН' if ТЕЛЕГРАМ_ВЕБХУК_СЕКРЕТ else 'НЕ УСТАНОВЛЕН'}")
    
    try:
        # Инициализация базы данных
        лог.info("📊 Инициализация базы данных...")
        пул = await создать_пул_бд(URL_БАЗЫ_ДАННЫХ)
        if пул:
            await создать_таблицы_бд(пул)
        else:
            лог.warning("⚠️ Работа без базы данных")
        
        состояние["пул_бд"] = пул
        состояние["работает"] = True
        
        лог.info("🎉 Приложение запущено успешно!")
        лог.info(f"🌐 Веб-сервер слушает порт {ПОРТ}")
        
        if ПОЛНЫЙ_ВЕБХУК_URL:
            лог.info(f"🔗 Webhook URL: {ПОЛНЫЙ_ВЕБХУК_URL}")
        else:
            лог.warning("⚠️ Webhook URL не настроен")
            лог.warning("💡 Установите переменную TELEGRAM_WEBHOOK_URL в Railway")
            лог.warning("💡 Например: https://ваш-проект.railway.app")
        
        yield
        
    except Exception as е:
        лог.error(f"💥 Ошибка запуска: {е}")
        raise
    finally:
        состояние["работает"] = False
        if состояние["пул_бд"]:
            try:
                await состояние["пул_бд"].close()
                лог.info("📊 База данных отключена")
            except:
                pass
        лог.info("✅ Приложение остановлено")

# Создание FastAPI приложения
приложение = FastAPI(
    title="Русский AI Телеграм Бот",
    description="Telegram бот с ИИ для русскоязычных пользователей",
    version="1.0.0",
    lifespan=время_жизни_приложения
)

приложение.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

@приложение.get("/")
async def главная_страница():
    """Главная страница для проверки работоспособности."""
    return JSONResponse({
        "статус": "работает",
        "название": "Русский AI Телеграм Бот",
        "версия": "1.0.0",
        "время": datetime.now().isoformat(),
        "компоненты": {
            "база_данных": "подключена" if состояние["пул_бд"] else "отключена",
            "telegram_токен": "настроен" if ТЕЛЕГРАМ_БОТ_ТОКЕН else "отсутствует",
            "openai_ключ": "настроен" if КЛЮЧ_OPENAI else "отсутствует"
        }
    })

@приложение.get("/health")
async def проверка_здоровья():
    """Проверка состояния системы."""
    компоненты = {
        "веб_сервер": "работает",
        "база_данных": "подключена" if состояние["пул_бд"] else "отключена",
        "telegram_бот": "настроен" if ТЕЛЕГРАМ_БОТ_ТОКЕН else "не_настроен",
        "openai_api": "настроен" if КЛЮЧ_OPENAI else "не_настроен"
    }
    
    общий_статус = "здоров" if компоненты["telegram_бот"] == "настроен" else "проблемы"
    
    return JSONResponse({
        "общий_статус": общий_статус,
        "время_проверки": datetime.now().isoformat(),
        "компоненты": компоненты
    })

@приложение.get("/debug/webhook")
async def отладка_вебхука():
    """Информация о настройке webhook."""
    return JSONResponse({
        "webhook_конфигурация": {
            "TELEGRAM_WEBHOOK_URL": ТЕЛЕГРАМ_ВЕБХУК_URL or "НЕ_УСТАНОВЛЕН",
            "TELEGRAM_WEBHOOK_PATH": ТЕЛЕГРАМ_ВЕБХУК_ПУТЬ,
            "TELEGRAM_WEBHOOK_SECRET": "УСТАНОВЛЕН" if ТЕЛЕГРАМ_ВЕБХУК_СЕКРЕТ else "НЕ_УСТАНОВЛЕН",
            "полный_webhook_url": ПОЛНЫЙ_ВЕБХУК_URL or "НЕ_НАСТРОЕН"
        },
        "доступные_вебхук_пути": [
            "/webhook",
            "/webhook/supersecret123456",
            f"/webhook/{ТЕЛЕГРАМ_ВЕБХУК_СЕКРЕТ}" if ТЕЛЕГРАМ_ВЕБХУК_СЕКРЕТ != "supersecret123456" else "тот_же_как_выше"
        ],
        "тест_webhook": {
            "url": f"https://ваш-проект.railway.app/webhook/supersecret123456",
            "method": "POST",
            "описание": "Отправьте POST запрос с Telegram обновлением"
        }
    })

@приложение.post("/webhook")
async def основной_вебхук(запрос: Request):
    """Основной обработчик webhook."""
    лог.info("📨 Получен webhook запрос на /webhook")
    
    try:
        if ТЕЛЕГРАМ_ВЕБХУК_СЕКРЕТ:
            секрет = запрос.headers.get("X-Telegram-Bot-Api-Secret-Token")
            if секрет != ТЕЛЕГРАМ_ВЕБХУК_СЕКРЕТ:
                лог.warning("🚫 Неверный секретный токен")
                raise HTTPException(status_code=403, detail="Неверный токен")
        
        тело = await запрос.body()
        if not тело:
            return JSONResponse({"ok": False, "ошибка": "Пустое тело"})
        
        данные = json.loads(тело.decode("utf-8"))
        ид_обновления = данные.get("update_id", "неизвестно")
        лог.info(f"✅ Принято обновление #{ид_обновления}")
        
        asyncio.create_task(обработать_обновление_телеграм(данные, pool=состояние["пул_бд"]))
        
        return JSONResponse({"ok": True, "статус": "принято"})
        
    except json.JSONDecodeError as е:
        лог.error(f"🔥 Ошибка JSON: {е}")
        raise HTTPException(status_code=400, detail="Неверный JSON")
    except Exception as е:
        лог.error(f"💥 Ошибка webhook: {е}")
        raise HTTPException(status_code=500, detail="Ошибка сервера")

@приложение.post("/webhook/{секретный_путь}")
async def вебхук_с_секретом(запрос: Request, секретный_путь: str):
    """Webhook с секретом в пути."""
    лог.info(f"📨 Получен webhook с секретным путем: /{секретный_путь}")
    
    try:
        # Проверяем известные секреты - более строгая проверка
        допустимые_секреты = ["supersecret123456"]
        if ТЕЛЕГРАМ_ВЕБХУК_СЕКРЕТ:
            допустимые_секреты.append(ТЕЛЕГРАМ_ВЕБХУК_СЕКРЕТ)
        
        лог.info(f"🔍 Проверяем секретный путь '{секретный_путь}' против списка: {допустимые_секреты}")
        
        if секретный_путь not in допустимые_секреты:
            лог.warning(f"🚫 Неверный секретный путь: {секретный_путь}")
            лог.warning(f"🚫 Ожидался один из: {допустимые_секреты}")
            raise HTTPException(status_code=404, detail="Не найдено")
        
        лог.info(f"✅ Секретный путь принят: {секретный_путь}")
        
        тело = await запрос.body()
        if not тело:
            лог.warning("📭 Получено пустое тело запроса")
            return JSONResponse({"ok": False, "ошибка": "Пустое тело"})
        
        данные = json.loads(тело.decode("utf-8"))
        ид_обновления = данные.get("update_id", "неизвестно")
        лог.info(f"✅ Обновление #{ид_обновления} через секретный путь {секретный_путь}")
        
        # Показываем детали обновления для отладки
        if "message" in данные:
            сообщение = данные["message"]
            if "from" in сообщение:
                пользователь = сообщение["from"].get("first_name", "Неизвестный")
                лог.info(f"👤 Сообщение от пользователя: {пользователь}")
            if "text" in сообщение:
                текст = сообщение["text"][:50]
                лог.info(f"💬 Текст сообщения: {текст}...")
        
        asyncio.create_task(обработать_обновление_телеграм(данные, pool=состояние["пул_бд"]))
        
        return JSONResponse({
            "ok": True, 
            "статус": "принято_через_секретный_путь",
            "обновление_id": ид_обновления,
            "секретный_путь": секретный_путь
        })
        
    except json.JSONDecodeError as е:
        лог.error(f"🔥 JSON ошибка в секретном пути: {е}")
        raise HTTPException(status_code=400, detail="Неверный JSON")
    except Exception as е:
        лог.error(f"💥 Ошибка секретного webhook: {е}")
        raise HTTPException(status_code=500, detail="Ошибка сервера")

@приложение.exception_handler(Exception)
async def обработчик_исключений(запрос: Request, исключение: Exception):
    """Глобальный обработчик исключений."""
    лог.error(f"💥 Необработанное исключение: {исключение}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "ошибка": "Внутренняя ошибка сервера",
            "время": datetime.now().isoformat()
        }
    )

# Совместимость
app = приложение

if __name__ == "__main__":
    import uvicorn
    лог.info("🔧 Локальный запуск")
    uvicorn.run("main_ru:приложение", host="0.0.0.0", port=ПОРТ, log_level="info")
