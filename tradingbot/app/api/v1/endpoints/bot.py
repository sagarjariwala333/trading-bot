from fastapi import APIRouter, Query, HTTPException
from app.schemas.bot import BotStatusResponseSchema, BotControlResponseSchema, LogTailResponseSchema
from app.services.bot_manager import BotManager
from app.core.db import get_log_lines

router = APIRouter()


@router.get("/status", response_model=BotStatusResponseSchema)
def get_bot_status(
    symbol: str = Query("BTCUSDT", description="Symbol of the trading bot"),
    log_lines: int = Query(50, ge=1, le=1000)
):
    try:
        return BotManager.get_bot_status(symbol, log_lines=log_lines)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching bot status: {e}")


@router.post("/start", response_model=BotControlResponseSchema)
def start_bot(symbol: str = Query("BTCUSDT", description="Symbol of the trading bot to start")):
    try:
        success = BotManager.start_bot(symbol)
        if success:
            return BotControlResponseSchema(success=True, message=f"Trading bot for {symbol} started successfully.")
        else:
            return BotControlResponseSchema(success=False, message=f"Failed to start trading bot for {symbol}.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting trading bot: {e}")


@router.post("/stop", response_model=BotControlResponseSchema)
def stop_bot(symbol: str = Query("BTCUSDT", description="Symbol of the trading bot to stop")):
    try:
        success = BotManager.stop_bot(symbol)
        if success:
            return BotControlResponseSchema(success=True, message=f"Trading bot for {symbol} stopped successfully.")
        else:
            return BotControlResponseSchema(success=False, message=f"Failed to stop trading bot for {symbol}.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error stopping trading bot: {e}")


@router.get("/logs", response_model=LogTailResponseSchema)
def get_bot_logs(
    symbol: str = Query("BTCUSDT", description="Symbol of the trading bot"),
    lines: int = Query(100, ge=1, le=2000)
):
    try:
        logs = get_log_lines(symbol, n=lines)
        return LogTailResponseSchema(logs=logs, line_count=len(logs))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching bot logs: {e}")


@router.post("/clear", response_model=BotControlResponseSchema)
def clear_bot_instance(symbol: str = Query("BTCUSDT", description="Symbol of the trading bot to clear")):
    try:
        success = BotManager.clear_instance(symbol)
        if success:
            return BotControlResponseSchema(success=True, message=f"Instance data, state, and logs for {symbol} cleared successfully.")
        else:
            return BotControlResponseSchema(success=False, message=f"Failed to clear instance for {symbol}.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing bot instance: {e}")
