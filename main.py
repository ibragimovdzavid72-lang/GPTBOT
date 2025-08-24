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

from app.config import settings
from app.db import db
from app.bot import get_bot, get_dispatcher
from app.services.reminders import start_reminder_service

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Security for webhook
security = HTTPBearer(auto_error=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting application...")
    
    # Initialize database
    await db.init_db()
    
    # Initialize bot and set webhook
    bot = get_bot()
    
    if settings.webhook_base_url:
        webhook_url = f"{settings.webhook_base_url}{settings.webhook_path}"
        
        webhook_info = await bot.get_webhook_info()
        if webhook_info.url != webhook_url:
            await bot.set_webhook(
                url=webhook_url,
                secret_token=settings.webhook_secret_token,
                drop_pending_updates=True
            )
            logger.info(f"Webhook set: {webhook_url}")
        else:
            logger.info(f"Webhook already set: {webhook_url}")
    else:
        logger.warning("WEBHOOK_BASE_URL not set, webhook not configured")
    
    # Start background services
    reminder_task = asyncio.create_task(start_reminder_service())
    
    logger.info("Application started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down application...")
    
    # Cancel background tasks
    reminder_task.cancel()
    try:
        await reminder_task
    except asyncio.CancelledError:
        pass
    
    # Close database
    await db.close()
    
    # Close bot session
    await bot.session.close()
    
    logger.info("Application shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Telegram AI Bot",
    description="Advanced AI-powered Telegram bot with payments, analytics, and more",
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
        if db.pool:
            async with db.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")


async def verify_webhook_secret(request: Request):
    """Verify webhook secret token."""
    if not settings.webhook_secret_token:
        return True  # No secret configured
    
    secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret_header != settings.webhook_secret_token:
        logger.warning("Invalid webhook secret token")
        raise HTTPException(status_code=401, detail="Invalid secret token")
    
    return True


@app.post(settings.webhook_path)
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
        bot = get_bot()
        dispatcher = get_dispatcher()
        
        await dispatcher.feed_update(bot, update)
        
        return {"status": "ok"}
    
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=settings.debug
    )
