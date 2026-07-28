import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.services.bot_manager import BotManager
import logging

router = APIRouter()
logger = logging.getLogger("fastapi")


@router.websocket("/live")
async def websocket_live_status(
    websocket: WebSocket,
    symbol: str = Query("BTCUSDT", description="Symbol of the bot to monitor"),
    interval_seconds: int = Query(2, ge=1, le=10, description="Status update polling interval")
):
    await websocket.accept()
    logger.info(f"WebSocket client connected to stream status for {symbol}")
    
    # Track the last logs we sent to avoid duplicate spam over WS if logs haven't changed
    last_logs_hash = None
    
    try:
        while True:
            # Gather bot status and DB analytics for 100% socket-driven live updates
            status_data = BotManager.get_bot_status(symbol, log_lines=30)
            
            from app.core.db import (
                get_db_trades, get_db_trade_summary, get_db_orders, get_db_signals
            )
            
            trades = get_db_trades(symbol, limit=50)
            summary = get_db_trade_summary(symbol)
            orders = get_db_orders(symbol, limit=50)
            signals = get_db_signals(symbol, limit=50)

            # Serialize full live telemetry & analytics to WebSocket payload
            payload = {
                "is_running": status_data.is_running,
                "bot_state": status_data.bot_state.model_dump() if status_data.bot_state else None,
                "live_status": status_data.live_status,
                "logs": status_data.logs,
                "trades": trades,
                "summary": summary,
                "orders": orders,
                "signals": signals,
            }
            
            await websocket.send_json(payload)
            await asyncio.sleep(interval_seconds)
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected for {symbol}")
    except RuntimeError as e:
        if "closed" in str(e).lower() or "handler is closed" in str(e).lower():
            logger.info(f"WebSocket client disconnected (closed transport) for {symbol}")
        else:
            logger.error(f"RuntimeError in live status websocket for {symbol}: {e}")
    except Exception as e:
        logger.error(f"Error in live status websocket for {symbol}: {e}")
        try:
            await websocket.close()
        except Exception:
            pass
