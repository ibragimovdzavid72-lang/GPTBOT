#!/usr/bin/env python3
"""Simple startup script."""

import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting on port {port}")
    uvicorn.run("app:app", host="0.0.0.0", port=port)
