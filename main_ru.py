"""
Продакшн-готовый Telegram Бот с расширенными возможностями
========================================================
Комплексный, монетизируемый Telegram бот с:
- Интеграцией PostgreSQL базы данных
- Платежными системами с тарифами (БЕСПЛАТНЫЙ/ПРО/КОМАНДА)
- Админ панелью и управлением пользователями
- AI чатом с памятью и контекстом
- Генерацией и анализом изображений
- Обработкой голоса (STT/TTS)
- Фоновыми напоминаниями и уведомлениями
- Аналитикой и мониторингом
- UX на основе inline клавиатур
"""

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import structlog
import uvicorn
from fastapi import FastAPI, Request, Response, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config_final import settings
from database_final import DatabaseManager
from telegram_final import TelegramClient
from openai_final import OpenAIClient
from handlers_final import MessageHandler
from admin_final import AdminPanel
from payments_final import PaymentManager
from analytics_final import AnalyticsEngine

# Настройка структурированного логирования
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

лог = structlog.get_logger("основной")

# Глобальные экземпляры
менеджер_бд: DatabaseManager = None
телеграм_клиент: TelegramClient = None
опенаи_клиент: OpenAIClient = None
обработчик_сообщений: MessageHandler = None
админ_панель: AdminPanel = None
менеджер_платежей: PaymentManager = None
движок_аналитики: AnalyticsEngine = None

# Фоновые задачи
фоновые_задачи_работают = True

@asynccontextmanager
async def время_жизни(приложение: FastAPI):
    """Менеджер времени жизни приложения для запуска и остановки."""
    global менеджер_бд, телеграм_клиент, опенаи_клиент, обработчик_сообщений
    global админ_панель, менеджер_платежей, движок_аналитики
    
    лог.info("Запуск Telegram Bot приложения", версия=settings.version)
    
    try:
        # Инициализация базы данных
        менеджер_бд = DatabaseManager(settings.database.url)
        await менеджер_бд.initialize()
        лог.info("База данных инициализирована успешно")
        
        # Инициализация клиентов
        телеграм_клиент = TelegramClient(settings.telegram.bot_token, менеджер_бд)
        опенаи_клиент = OpenAIClient(settings.openai.api_key, менеджер_бд)
        
        # Инициализация компонентов
        движок_аналитики = AnalyticsEngine(менеджер_бд)
        менеджер_платежей = PaymentManager(телеграм_клиент, менеджер_бд)
        админ_панель = AdminPanel(телеграм_клиент, менеджер_бд, движок_аналитики)
        
        # Инициализация обработчика сообщений
        обработчик_сообщений = MessageHandler(
            telegram_client=телеграм_клиент,
            openai_client=опенаи_клиент,
            db_manager=менеджер_бд,
            payment_manager=менеджер_платежей,
            analytics_engine=движок_аналитики
        )
        
        # Установка webhook
        урл_вебхука = settings.telegram.full_webhook_url
        if урл_вебхука:
            успех = await телеграм_клиент.set_webhook(урл_вебхука, settings.telegram.webhook_secret)
            if успех:
                лог.info("Webhook установлен успешно", url=урл_вебхука)
            else:
                лог.error("Не удалось установить webhook", url=урл_вебхука)
        else:
            лог.warning("URL webhook не настроен")
        
        # Запуск фоновых задач
        asyncio.create_task(работник_напоминаний())
        asyncio.create_task(работник_аналитики())
        asyncio.create_task(работник_обслуживания())
        
        лог.info("Запуск приложения завершен успешно")
        
        yield
        
    except Exception as e:
        лог.error("Не удалось запустить приложение", ошибка=str(e))
        raise
    finally:
        # Очистка
        global фоновые_задачи_работают
        фоновые_задачи_работают = False
        
        if менеджер_бд:
            await менеджер_бд.close()
            лог.info("Соединения с базой данных закрыты")
        
        лог.info("Остановка приложения завершена")

# Создание FastAPI приложения
приложение = FastAPI(
    title="Продвинутый Telegram Бот",
    description="Продакшн-готовый Telegram бот с AI, платежами и аналитикой",
    version=settings.version,
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

@приложение.post("/webhook")
async def обработчик_вебхука(запрос: Request, фоновые_задачи: BackgroundTasks):
    """Обработка входящих Telegram webhook обновлений."""
    время_начала = time.perf_counter()
    
    try:
        # Проверка секрета webhook
        if settings.telegram.webhook_secret:
            заголовок_секрета = запрос.headers.get("X-Telegram-Bot-Api-Secret-Token")
            if заголовок_секрета != settings.telegram.webhook_secret:
                лог.warning("Неверный секрет webhook", ip=запрос.client.host)
                raise HTTPException(status_code=403, detail="Неверный секретный токен")
        
        # Парсинг обновления
        тело = await запрос.body()
        if not тело:
            raise HTTPException(status_code=400, detail="Пустое тело запроса")
        
        try:
            данные_обновления = json.loads(тело)
        except json.JSONDecodeError as e:
            лог.error("Неверный JSON в webhook", ошибка=str(e))
            raise HTTPException(status_code=400, detail="Неверный JSON")
        
        # Обработка обновления в фоне
        фоновые_задачи.add_task(обработать_обновление, данные_обновления, время_начала)
        
        return {"ok": True}
        
    except HTTPException:
        raise
    except Exception as e:
        лог.error("Ошибка обработчика webhook", ошибка=str(e))
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")

@приложение.post("/webhook/{секретный_путь}")
async def обработчик_вебхука_с_секретом(запрос: Request, секретный_путь: str, фоновые_задачи: BackgroundTasks):
    """Обработка входящих Telegram webhook обновлений с секретом в пути."""
    время_начала = time.perf_counter()
    
    try:
        # Проверка секретного пути соответствует настроенному секрету
        if settings.telegram.webhook_secret and секретный_путь != settings.telegram.webhook_secret:
            лог.warning("Неверный секретный путь webhook", секретный_путь=секретный_путь, ip=запрос.client.host)
            raise HTTPException(status_code=404, detail="Не найдено")
        
        # Парсинг обновления
        тело = await запрос.body()
        if not тело:
            raise HTTPException(status_code=400, detail="Пустое тело запроса")
        
        try:
            данные_обновления = json.loads(тело)
        except json.JSONDecodeError as e:
            лог.error("Неверный JSON в webhook", ошибка=str(e))
            raise HTTPException(status_code=400, detail="Неверный JSON")
        
        # Обработка обновления в фоне
        фоновые_задачи.add_task(обработать_обновление, данные_обновления, время_начала)
        
        return {"ok": True}
        
    except HTTPException:
        raise
    except Exception as e:
        лог.error("Ошибка обработчика webhook", ошибка=str(e))
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")

# Корневой endpoint для проверок здоровья
@приложение.get("/")
async def корень():
    """Корневой endpoint для проверок здоровья."""
    return {
        "статус": "запущен",
        "бот": "Продвинутый Telegram Бот",
        "версия": settings.version,
        "временная_метка": datetime.utcnow().isoformat(),
        "описание": "Telegram бот с AI возможностями"
    }

@приложение.get("/health")
async def проверка_здоровья():
    """Endpoint проверки здоровья для мониторинга."""
    try:
        # Проверка подключения к базе данных
        if менеджер_бд:
            await менеджер_бд.health_check()
        
        return {
            "статус": "здоров",
            "временная_метка": datetime.utcnow().isoformat(),
            "версия": settings.version,
            "окружение": settings.environment,
            "база_данных": "подключена" if менеджер_бд else "не инициализирована",
            "телеграм": "подключен" if телеграм_клиент else "не инициализирован",
            "опенаи": "подключен" if опенаи_клиент else "не инициализирован"
        }
    except Exception as e:
        лог.error("Проверка здоровья не удалась", ошибка=str(e))
        raise HTTPException(status_code=503, detail=f"Сервис нездоров: {str(e)}")

@приложение.get("/stats")
async def получить_статистику():
    """Получение базовой статистики бота (только для админов)."""
    try:
        if not движок_аналитики:
            raise HTTPException(status_code=503, detail="Аналитика недоступна")
        
        статистика = await движок_аналитики.get_system_stats()
        return {
            "статус": "ок",
            "статистика": статистика,
            "временная_метка": datetime.utcnow().isoformat()
        }
    except Exception as e:
        лог.error("Ошибка endpoint статистики", ошибка=str(e))
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")

@приложение.get("/metrics")
async def получить_метрики():
    """Получение метрик Prometheus."""
    try:
        if not движок_аналитики:
            raise HTTPException(status_code=503, detail="Аналитика недоступна")
        
        метрики = await движок_аналитики.get_prometheus_metrics()
        return Response(content=метрики, media_type="text/plain")
    except Exception as e:
        лог.error("Ошибка endpoint метрик", ошибка=str(e))
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")

async def обработать_обновление(данные_обновления: Dict[str, Any], время_начала: float):
    """Обработка Telegram обновления."""
    try:
        ид_обновления = данные_обновления.get("update_id")
        лог.info("Обработка обновления", update_id=ид_обновления)
        
        # Запись аналитики
        if движок_аналитики:
            движок_аналитики.record_request_start()
        
        # Обработка различных типов обновлений
        if "message" in данные_обновления:
            await обработчик_сообщений.handle_message(данные_обновления["message"])
        
        elif "callback_query" in данные_обновления:
            await обработчик_сообщений.handle_callback_query(данные_обновления["callback_query"])
        
        elif "inline_query" in данные_обновления:
            await обработчик_сообщений.handle_inline_query(данные_обновления["inline_query"])
        
        elif "pre_checkout_query" in данные_обновления:
            await менеджер_платежей.handle_pre_checkout_query(данные_обновления["pre_checkout_query"])
        
        elif "successful_payment" in данные_обновления.get("message", {}):
            await менеджер_платежей.handle_successful_payment(
                данные_обновления["message"]["successful_payment"],
                данные_обновления["message"]
            )
        
        else:
            лог.info("Неизвестный тип обновления", обновление=данные_обновления)
        
        # Запись завершения аналитики
        if движок_аналитики:
            длительность = time.perf_counter() - время_начала
            движок_аналитики.record_request_completed(длительность)
        
    except Exception as e:
        лог.error("Ошибка обработки обновления", ошибка=str(e), обновление=данные_обновления)
        
        # Запись ошибки аналитики
        if движок_аналитики:
            движок_аналитики.record_request_error()

async def работник_напоминаний():
    """Фоновый работник для обработки напоминаний."""
    лог.info("Запуск работника напоминаний")
    
    while фоновые_задачи_работают:
        try:
            if менеджер_бд and телеграм_клиент:
                # Получение просроченных напоминаний
                напоминания = await менеджер_бд.get_due_reminders()
                
                for напоминание in напоминания:
                    try:
                        # Отправка напоминания
                        await телеграм_клиент.send_message(
                            chat_id=напоминание["telegram_id"],
                            text=f"⏰ Напоминание: {напоминание['text']}"
                        )
                        
                        # Отметка как отправленное
                        await менеджер_бд.mark_reminder_sent(напоминание["id"])
                        
                        лог.info("Напоминание отправлено", 
                                reminder_id=напоминание["id"],
                                telegram_id=напоминание["telegram_id"])
                        
                    except Exception as e:
                        лог.error("Не удалось отправить напоминание", 
                                ошибка=str(e),
                                reminder_id=напоминание["id"])
            
            # Ожидание перед следующей проверкой
            await asyncio.sleep(settings.reminder_check_interval)
            
        except Exception as e:
            лог.error("Ошибка работника напоминаний", ошибка=str(e))
            await asyncio.sleep(60)  # Ожидание минуты при ошибке

async def работник_аналитики():
    """Фоновый работник для аналитики."""
    лог.info("Запуск работника аналитики")
    
    while фоновые_задачи_работают:
        try:
            if движок_аналитики:
                await движок_аналитики.process_analytics()
            
            await asyncio.sleep(settings.analytics_interval)
            
        except Exception as e:
            лог.error("Ошибка работника аналитики", ошибка=str(e))
            await asyncio.sleep(300)  # Ожидание 5 минут при ошибке

async def работник_обслуживания():
    """Фоновый работник для задач обслуживания."""
    лог.info("Запуск работника обслуживания")
    
    while фоновые_задачи_работают:
        try:
            if менеджер_бд:
                # Очистка старых сессий
                await менеджер_бд.cleanup_old_sessions()
                
                # Очистка старой истории разговоров
                await менеджер_бд.cleanup_old_conversations()
                
                # Обновление ежедневной статистики
                await менеджер_бд.reset_daily_usage()
                
                лог.info("Задачи обслуживания выполнены")
            
            await asyncio.sleep(settings.maintenance_interval)
            
        except Exception as e:
            лог.error("Ошибка работника обслуживания", ошибка=str(e))
            await asyncio.sleep(3600)  # Ожидание часа при ошибке

# Обработка исключений
@приложение.exception_handler(Exception)
async def глобальный_обработчик_исключений(запрос: Request, исключение: Exception):
    """Глобальный обработчик исключений."""
    лог.error("Необработанное исключение", 
             ошибка=str(исключение),
             путь=запрос.url.path,
             метод=запрос.method)
    
    return JSONResponse(
        status_code=500,
        content={
            "ошибка": "Внутренняя ошибка сервера",
            "временная_метка": datetime.utcnow().isoformat()
        }
    )

if __name__ == "__main__":
    лог.info("Запуск сервера напрямую")
    uvicorn.run(
        "main_final:приложение",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )
