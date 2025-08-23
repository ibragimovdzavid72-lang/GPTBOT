"""
Продакшн-готовый Telegram Бот с AI возможностями
==============================================
Telegram бот с интеграцией OpenAI GPT-4o, базой данных PostgreSQL
и системой напоминаний для русскоязычных пользователей.
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

from settings import TELEGRAM_BOT_TOKEN, FULL_WEBHOOK_URL, WEBHOOK_PATH, WEBHOOK_SECRET, DATABASE_URL
from db import create_pool, create_tables, due_reminders, mark_reminder_done
from handlers import handle_update
from telegram_api import tg_send_message, close_http_client

# Настройка логирования на русском
лог = logging.getLogger("приложение")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

# Состояние приложения
состояние = {"пул": None, "задача_напоминаний": None}

async def работник_напоминаний():
    """Фоновый работник для обработки напоминаний."""
    лог.info("Запуск работника напоминаний")
    
    while True:
        try:
            if состояние["пул"]:
                элементы = await due_reminders(состояние["пул"])
                for элемент in элементы:
                    try:
                        await tg_send_message(элемент["chat_id"], f"⏰ Напоминание: {элемент['task']}")
                        await mark_reminder_done(состояние["пул"], элемент["id"])
                        лог.info(f"Напоминание отправлено пользователю {элемент['chat_id']}")
                    except Exception as ошибка:
                        лог.error(f"Ошибка отправки напоминания: {ошибка}")
        except Exception as ошибка:
            лог.error(f"Ошибка цикла напоминаний: {ошибка}")
        
        await asyncio.sleep(60)

@asynccontextmanager
async def время_жизни(приложение: FastAPI):
    """Управление временем жизни приложения."""
    лог.info("Инициализация приложения")
    
    # Проверка обязательных переменных окружения
    if not TELEGRAM_BOT_TOKEN:
        лог.error("TELEGRAM_BOT_TOKEN пуст - бот не будет работать")
    
    if not DATABASE_URL:
        лог.warning("DATABASE_URL пуст (история и лимиты не сохранятся)")
    
    пул = None
    
    try:
        # Инициализация базы данных
        if DATABASE_URL:
            лог.info("Подключение к базе данных...")
            пул = await create_pool(DATABASE_URL)
            await create_tables(пул)
            лог.info("База данных инициализирована успешно")
        
        состояние["пул"] = пул
        
        # Запуск фоновой задачи напоминаний
        состояние["задача_напоминаний"] = asyncio.create_task(работник_напоминаний())
        
        лог.info("Приложение запущено успешно")
        yield
        
    except Exception as ошибка:
        лог.error(f"Ошибка при запуске приложения: {ошибка}")
        raise
    finally:
        # Очистка ресурсов при остановке
        лог.info("Остановка приложения...")
        
        if состояние["задача_напоминаний"]:
            состояние["задача_напоминаний"].cancel()
            try:
                await состояние["задача_напоминаний"]
            except asyncio.CancelledError:
                pass
            except Exception as ошибка:
                лог.error(f"Ошибка при остановке задачи напоминаний: {ошибка}")
        
        try:
            await close_http_client()
        except Exception as ошибка:
            лог.error(f"Ошибка закрытия HTTP клиента: {ошибка}")
        
        if пул:
            await пул.close()
            лог.info("Соединения с базой данных закрыты")
        
        лог.info("Приложение остановлено")

# Создание FastAPI приложения
приложение = FastAPI(
    title="Русский AI Телеграм Бот",
    description="Telegram бот с AI возможностями для русскоязычных пользователей",
    version="1.0.0",
    lifespan=время_жизни
)

# Добавление CORS middleware
приложение.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@приложение.get("/")
async def корень():
    """Корневой endpoint для проверок здоровья."""
    return JSONResponse({
        "статус": "работает",
        "сообщение": "Русский AI Телеграм Бот запущен",
        "время": datetime.utcnow().isoformat(),
        "версия": "1.0.0"
    })

@приложение.get("/health")
async def проверка_здоровья():
    """Детальная проверка здоровья системы."""
    статус_бд = "подключена" if состояние["пул"] else "не подключена"
    статус_напоминаний = "работает" if состояние["задача_напоминаний"] and not состояние["задача_напоминаний"].done() else "остановлена"
    
    return JSONResponse({
        "статус": "здоров",
        "время": datetime.utcnow().isoformat(),
        "компоненты": {
            "база_данных": статус_бд,
            "система_напоминаний": статус_напоминаний,
            "telegram_токен": "настроен" if TELEGRAM_BOT_TOKEN else "не настроен"
        }
    })

@приложение.post(WEBHOOK_PATH)
async def вебхук(запрос: Request):
    """Основной обработчик webhook от Telegram."""
    лог.info(f"Получен webhook запрос на путь: {WEBHOOK_PATH}")
    
    # Проверка секретного токена
    if WEBHOOK_SECRET:
        заголовок = запрос.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if заголовок != WEBHOOK_SECRET:
            лог.warning("Неверный секретный токен в webhook")
            raise HTTPException(status_code=403, detail="Неверный секретный токен")
    
    try:
        # Получение и парсинг данных
        сырые_данные = await запрос.body()
        обновление = json.loads(сырые_данные.decode("utf-8")) if сырые_данные else {}
        
        if обновление:
            лог.info(f"Обработка обновления: {обновление.get('update_id', 'неизвестно')}")
            # Обработка в фоновой задаче
            asyncio.create_task(handle_update(обновление, pool=состояние["пул"]))
        
        return JSONResponse({"ok": True})
        
    except json.JSONDecodeError as ошибка:
        лог.error(f"Ошибка парсинга JSON: {ошибка}")
        raise HTTPException(status_code=400, detail="Неверный JSON")
    except Exception as ошибка:
        лог.error(f"Ошибка обработки webhook: {ошибка}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")

@приложение.post("/webhook/{секретный_путь}")
async def вебхук_с_секретом(запрос: Request, секретный_путь: str):
    """Обработчик webhook с секретом в пути (для совместимости)."""
    лог.info(f"Получен webhook запрос с секретным путем: {секретный_путь}")
    
    # Проверка секретного пути
    if WEBHOOK_SECRET and секретный_путь != WEBHOOK_SECRET:
        лог.warning(f"Неверный секретный путь: {секретный_путь}")
        raise HTTPException(status_code=404, detail="Не найдено")
    
    try:
        # Получение и парсинг данных
        сырые_данные = await запрос.body()
        обновление = json.loads(сырые_данные.decode("utf-8")) if сырые_данные else {}
        
        if обновление:
            лог.info(f"Обработка обновления через секретный путь: {обновление.get('update_id', 'неизвестно')}")
            # Обработка в фоновой задаче
            asyncio.create_task(handle_update(обновление, pool=состояние["пул"]))
        
        return JSONResponse({"ok": True})
        
    except json.JSONDecodeError as ошибка:
        лог.error(f"Ошибка парсинга JSON в секретном пути: {ошибка}")
        raise HTTPException(status_code=400, detail="Неверный JSON")
    except Exception as ошибка:
        лог.error(f"Ошибка обработки webhook с секретным путем: {ошибка}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")

# Глобальный обработчик исключений
@приложение.exception_handler(Exception)
async def глобальный_обработчик_исключений(запрос: Request, исключение: Exception):
    """Обработка всех необработанных исключений."""
    лог.error(f"Необработанное исключение: {исключение}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "ошибка": "Внутренняя ошибка сервера",
            "время": datetime.utcnow().isoformat()
        }
    )

# Для совместимости с uvicorn
app = приложение

if __name__ == "__main__":
    import uvicorn
    лог.info("Запуск сервера в режиме разработки")
    uvicorn.run(
        "main:приложение",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
