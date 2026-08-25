import sys
import os
import asyncio
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Traverse up to locate and load .env file
current_dir = os.path.dirname(os.path.abspath(__file__))
while current_dir != os.path.dirname(current_dir):
    env_path = os.path.join(current_dir, ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)
        break
    current_dir = os.path.dirname(current_dir)

from src.api.routers.snowflake import router as snowflake_router

# Windows event loop policy fix
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

app = FastAPI(
    title="Data Reliability Control Center API",
    description="Backend engine for live Snowflake ledger reconciliation and AI analytics.",
    version="1.0.0"
)

# Enable CORS for frontend API calls
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register endpoints under /api prefix
app.include_router(snowflake_router, prefix="/api")

@app.get("/health")
def health():
    return {"status": "ok", "service": "Validata API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.app:app", host="0.0.0.0", port=8000, reload=True)
