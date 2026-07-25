from dotenv import load_dotenv
load_dotenv()  # Load .env into os.environ before any other module reads env vars

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.router import api_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="FastAPI Backend for HA-ALMA-RSI-SMA-ATR Trading Bot on Binance Futures USDT-M",
    version="1.0.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)

@app.on_event("startup")
def startup_db_and_resume_bots():
    from app.core.db import init_db, get_active_bots
    from app.services.bot_manager import BotManager
    import logging
    
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
