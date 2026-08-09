import time
import logging
from dotenv import load_dotenv
load_dotenv()  # Load .env into os.environ before any other module reads env vars

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.router import api_router
from app.core.telemetry import (
    init_telemetry,
    LangfuseLoggingHandler,
    trace_event,
    flush_telemetry,
)

# Initialize telemetry
init_telemetry()

# Setup logging with Langfuse handler
root_logger = logging.getLogger()
langfuse_handler = LangfuseLoggingHandler()
langfuse_handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s [%(name)s]: %(message)s'))
root_logger.addHandler(langfuse_handler)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="FastAPI Backend for HA-ALMA-RSI-SMA-ATR Trading Bot on Binance Futures USDT-M",
    version="1.0.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)

@app.middleware("http")
async def trace_http_requests(request: Request, call_next):
    start_time = time.time()
    response = None
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        trace_event(
            name=f"HTTP {request.method} {request.url.path}",
            level="DEFAULT" if response.status_code < 400 else "ERROR",
            input={"method": request.method, "path": request.url.path, "query_params": dict(request.query_params)},
            output={"status_code": response.status_code, "duration_ms": round(process_time * 1000, 2)},
            metadata={"client_host": request.client.host if request.client else None}
        )
        return response
    except Exception as e:
        process_time = time.time() - start_time
        trace_event(
            name=f"HTTP Exception {request.method} {request.url.path}",
            level="ERROR",
            input={"method": request.method, "path": request.url.path},
            output={"error": str(e), "duration_ms": round(process_time * 1000, 2)}
        )
        raise e

@app.on_event("startup")
def startup_db_and_resume_bots():
    from app.core.db import init_db, get_active_bots
    from app.services.bot_manager import BotManager
    
    # Initialize DB
    init_db()
    
    # Auto-resume bots
    active_symbols = get_active_bots()
    logger = logging.getLogger("ha_alma_bot")
    logger.info(f"Auto-resuming active bots on startup: {active_symbols}")
    for symbol in active_symbols:
        try:
            BotManager.start_bot(symbol)
            logger.info(f"Successfully auto-resumed bot for {symbol}")
        except Exception as e:
            logger.error(f"Failed to auto-resume bot for {symbol}: {e}")

@app.on_event("shutdown")
def shutdown_telemetry():
    flush_telemetry()

# Set up CORS middleware for React frontend integration
if settings.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Include main API router
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
def read_root():
    return {
        "message": f"Welcome to the {settings.PROJECT_NAME}",
        "docs_url": "/docs",
        "version": "1.0.0",
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
