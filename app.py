import os
import logging
from fastapi import FastAPI
import uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("gptbot")

# FastAPI app for health check
api = FastAPI()

@api.get("/health")
async def health():
    return {"status": "ok"}

@api.get("/")
async def root():
    return {"message": "Telegram Bot with FastAPI Health Check"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    log.info(f"Starting server on port {port}")
    uvicorn.run(api, host="0.0.0.0", port=port, log_level="info")
