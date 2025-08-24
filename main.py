"""Main FastAPI application with Telegram webhook."""

import os
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.security import HTTPBearer
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from aiogram.webhook.aiohttp_server import SimpleRequestHandler

from config_ru import настройки
from database_ru import база_данных
from telegram_ru import получить_бота, получить_диспетчера
from services.reminders_ru import запустить_службу_напоминаний

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Webhook security
security = HTTPBearer(auto_error=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting application...")
    
    # Initialize database
    await база_данных.инициализировать_бд()
    
    # Initialize bot and setup webhook
    бот = получить_бота()
    
    if настройки.webhook_base_url:
        webhook_url = f"{настройки.webhook_base_url}{настройки.webhook_path}"
        
        webhook_info = await бот.get_webhook_info()
        if webhook_info.url != webhook_url:
            await бот.set_webhook(
                url=webhook_url,
                secret_token=настройки.webhook_secret_token,
                drop_pending_updates=True
            )
            logger.info(f"Webhook set: {webhook_url}")
        else:
            logger.info(f"Webhook already set: {webhook_url}")
    else:
        logger.warning("WEBHOOK_BASE_URL not set, webhook not configured")
    
    # Start background services
    задача_напоминаний = asyncio.create_task(запустить_службу_напоминаний())
    
    logger.info("Application started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down application...")
    
    # Cancel background tasks
    задача_напоминаний.cancel()
    try:
        await задача_напоминаний
    except asyncio.CancelledError:
        pass
    
    # Close database
    await база_данных.закрыть()
    
    # Close bot session
    await бот.session.close()
    
    logger.info("Application shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="Telegram AI Bot",
    description="Advanced AI bot for Telegram with payments, analytics and more",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Telegram AI Bot is running", "status": "ok"}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        # Check database connection
        if база_данных.pool:
            async with база_данных.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")


async def verify_webhook_secret(request: Request):
    """Verify webhook secret token."""
    if not настройки.webhook_secret_token:
        return True  # Secret not configured
    
    secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret_header != настройки.webhook_secret_token:
        logger.warning("Invalid webhook secret token")
        raise HTTPException(status_code=401, detail="Invalid secret token")
    
    return True


@app.post(настройки.webhook_path)
async def webhook_handler(
    request: Request,
    _: bool = Depends(verify_webhook_secret)
):
    """Handle Telegram webhook updates."""
    try:
        # Get update from request
        update_data = await request.json()
        update = Update(**update_data)
        
        # Process update with dispatcher
        бот = получить_бота()
        диспетчер = получить_диспетчера()
        
        await диспетчер.feed_update(бот, update)
        
        return {"status": "ok"}
    
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=настройки.debug
    )