"""Simple FastAPI application for Railway deployment."""

import os
import logging
from fastapi import FastAPI

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI application
app = FastAPI(
    title="Telegram AI Bot",
    description="Telegram AI Bot - Simple Version",
    version="1.0.0"
)

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Telegram AI Bot is running", 
        "status": "ok",
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "telegram-ai-bot"
    }

@app.get("/ping")
async def ping():
    """Ping endpoint."""
    return {"ping": "pong"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting server on port {port}")
    uvicorn.run("app:app", host="0.0.0.0", port=port, log_level="info")
