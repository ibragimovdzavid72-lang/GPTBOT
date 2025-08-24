#!/usr/bin/env python3
"""Startup script for the Russian Telegram bot."""

import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting Russian Telegram bot on port {port}")
    uvicorn.run("main_ru:приложение", host="0.0.0.0", port=port, log_level="info")
