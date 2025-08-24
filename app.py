"""Simple FastAPI app for Railway deployment."""
from fastapi import FastAPI

app = FastAPI(title="Telegram AI Bot")

@app.get("/")
def read_root():
    return {"Hello": "World", "status": "running"}

@app.get("/health")  
def health():
    return {"status": "ok"}

@app.get("/ping")
async def ping():
    """Ping endpoint."""
    return {"ping": "pong"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting server on port {port}")
    uvicorn.run("main:приложение", host="0.0.0.0", port=port, log_level="info")
