"""
Модуль для работы с Webhook для Telegram бота.
Поддерживает как polling, так и webhook режимы работы.
"""

import logging
import os
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

logger = logging.getLogger(__name__)


class WebhookManager:
    """Менеджер для управления webhook настройками."""
    
    def __init__(self, bot, dp):
        self.bot = bot
        self.dp = dp
        
    async def setup_webhook(self) -> bool:
        """
        Настройка webhook для бота.
        
        :return: True если webhook настроен успешно, False если используется polling
        """
        webhook_url = os.getenv("WEBHOOK_URL")
        webhook_secret = os.getenv("WEBHOOK_SECRET", "telegram_webhook_secret")
        
        if not webhook_url:
            logger.info("WEBHOOK_URL не установлен, используется polling режим")
            return False
            
        try:
            # Устанавливаем webhook
            await self.bot.set_webhook(
                url=webhook_url,
                secret_token=webhook_secret,
                allowed_updates=["message", "callback_query", "inline_query"]
            )
            logger.info(f"✅ Webhook установлен: {webhook_url}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка установки webhook: {e}")
            return False
    
    async def remove_webhook(self) -> None:
        """Удаление webhook."""
        try:
            await self.bot.delete_webhook(drop_pending_updates=True)
            logger.info("Webhook удален")
        except Exception as e:
            logger.error(f"Ошибка удаления webhook: {e}")
    
    def create_webhook_app(self) -> web.Application:
        """
        Создание веб-приложения для webhook.
        
        :return: Configured aiohttp application
        """
        webhook_path = os.getenv("WEBHOOK_PATH", "/")
        webhook_secret = os.getenv("WEBHOOK_SECRET", "telegram_webhook_secret")
        
        # Создаем веб-приложение
        app = web.Application()
        
        # Создаем ручной обработчик webhook для гарантии работы
        async def handle_webhook(request):
            """Ручной обработчик webhook запросов с усиленной безопасностью."""
            try:
                logger.info(f"🌐 Получен webhook POST запрос на {request.path} от {request.remote}")
                
                # Проверяем method
                if request.method != 'POST':
                    logger.warning(f"⚠️ Неправильный HTTP method: {request.method}")
                    return web.Response(status=405)  # Method Not Allowed
                
                # Проверяем Content-Type
                content_type = request.headers.get("Content-Type", "")
                if "application/json" not in content_type:
                    logger.warning(f"⚠️ Неправильный Content-Type: {content_type}")
                    return web.Response(status=400)
                
                # Проверяем secret token для безопасности
                if webhook_secret and webhook_secret != "telegram_webhook_secret":
                    secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
                    if secret_header != webhook_secret:
                        logger.warning(f"⚠️ Неверный secret token: expected '{webhook_secret}', got '{secret_header}'")
                        logger.warning(f"🕵️ Подозрительный запрос от {request.remote}")
                        return web.Response(status=401)  # Unauthorized
                
                # Получаем данные обновления
                try:
                    data = await request.json()
                except Exception as e:
                    logger.error(f"❌ Ошибка парсинга JSON: {e}")
                    return web.Response(status=400)
                
                # Проверяем структуру данных
                if not isinstance(data, dict) or 'update_id' not in data:
                    logger.warning(f"⚠️ Неправильная структура данных: {data}")
                    return web.Response(status=400)
                
                logger.info(f"📄 Полученные данные: update_id={data.get('update_id', '?')}")
                
                from aiogram import types
                update = types.Update(**data)
                
                # Обрабатываем обновление через диспетчер
                await self.dp.feed_update(self.bot, update)
                logger.info("✅ Обновление успешно обработано")
                
                return web.Response(status=200)
                
            except Exception as e:
                logger.error(f"❌ Ошибка обработки webhook: {e}")
                import traceback
                logger.error(f"❌ Полная ошибка: {traceback.format_exc()}")
                return web.Response(status=500)
        
        # Регистрируем обработчик на корневом пути И на /webhook для совместимости
        app.router.add_post("/", handle_webhook)
        app.router.add_post("/webhook", handle_webhook)
        
        # Добавляем health check endpoint
        async def health_check(request):
            return web.json_response({"status": "ok", "bot": "telegram_ai_agent_v2", "webhook_path": webhook_path})
        
        # Обработчик favicon для избежания 404
        async def favicon_handler(request):
            return web.Response(status=204)  # No Content
        
        # Логирование всех входящих запросов для диагностики
        async def log_requests(request, handler):
            logger.info(f"📥 Входящий запрос: {request.method} {request.path} от {request.remote}")
            try:
                response = await handler(request)
                logger.info(f"📤 Ответ: {response.status}")
                return response
            except Exception as e:
                logger.error(f"❌ Ошибка обработки запроса {request.path}: {e}")
                return web.Response(status=500)
        
        # Добавляем middleware для логирования
        app.middlewares.append(log_requests)
        
        app.router.add_get("/health", health_check)
        app.router.add_get("/", health_check)  # GET запросы на корень для health check
        app.router.add_get("/favicon.ico", favicon_handler)
        app.router.add_head("/favicon.ico", favicon_handler)  # HEAD запросы тоже
        
        logger.info(f"Webhook app создан с путями: / и /webhook")
        return app
    
    async def run_webhook_server(self, port: int = None) -> None:
        """
        Запуск webhook сервера.
        
        :param port: Порт для сервера (по умолчанию из переменной окружения)
        """
        if port is None:
            port = int(os.getenv("PORT", "8443"))
        
        host = os.getenv("HOST", "0.0.0.0")
        
        # Создаем приложение
        app = self.create_webhook_app()
        
        # Запускаем сервер
        runner = web.AppRunner(app)
        await runner.setup()
        
        site = web.TCPSite(runner, host, port)
        await site.start()
        
        logger.info(f"🌐 Webhook сервер запущен на {host}:{port}")
        
        # Настраиваем webhook
        webhook_set = await self.setup_webhook()
        if not webhook_set:
            logger.warning("⚠️ Webhook не настроен, но сервер работает")
        
        return runner
    
    async def get_telegram_webhook_info(self):
        """Получаем информацию о webhook от Telegram."""
        try:
            webhook_info = await self.bot.get_webhook_info()
            logger.info(f"📊 Webhook статус: {webhook_info}")
            return webhook_info
        except Exception as e:
            logger.error(f"❌ Ошибка получения webhook инфо: {e}")
            return None
    
    @staticmethod
    def get_webhook_info():
        """Получение информации о webhook настройках."""
        return {
            "webhook_url": os.getenv("WEBHOOK_URL"),
            "webhook_path": os.getenv("WEBHOOK_PATH", "/"),
            "webhook_secret": os.getenv("WEBHOOK_SECRET", "telegram_webhook_secret"),
            "port": int(os.getenv("PORT", "8443")),
            "host": os.getenv("HOST", "0.0.0.0")
        }
