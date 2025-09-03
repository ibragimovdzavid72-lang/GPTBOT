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
        
        # Настраиваем обработчик webhook
        handler = SimpleRequestHandler(
            dispatcher=self.dp,
            bot=self.bot,
            secret_token=webhook_secret
        )
        handler.register(app, path=webhook_path)
        
        # Настраиваем приложение
        setup_application(app, self.dp, bot=self.bot)
        
        # Добавляем health check endpoint
        async def health_check(request):
            return web.json_response({"status": "ok", "bot": "telegram_ai_agent_v2"})
        
        app.router.add_get("/health", health_check)
        
        # Если webhook путь не корневой, добавляем health check на корень
        if webhook_path != "/":
            app.router.add_get("/", health_check)
        
        logger.info(f"Webhook app создан с путем: {webhook_path}")
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
