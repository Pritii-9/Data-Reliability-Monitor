import sys
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routers.snowflake import router as snowflake_router

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(snowflake_router, prefix="/api")

@app.get("/health")
def health():
    return {"status": "ok", "service": "Validata API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.app:app", host="0.0.0.0", port=8000, reload=True)
