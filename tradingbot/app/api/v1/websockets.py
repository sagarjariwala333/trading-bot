import asyncio
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from starlette.websockets import WebSocketState
from app.services.bot_manager import BotManager
import logging
from app.services.binance_ws_service import BinanceWebSocketService
from app.services.mark_price_service import get_mark_price, get_mark_price_updated_at

router = APIRouter()
logger = logging.getLogger("fastapi")

# How many seconds of telemetry age before we flag data as stale.
# The bot writes telemetry every poll_seconds (default 15s), so 30s
# gives ~2 missed writes of headroom.
TELEMETRY_STALE_THRESHOLD_SECONDS = 30


@router.websocket("/live")
async def websocket_live_status(
    websocket: WebSocket,
    symbol: str = Query("BTCUSDT", description="Symbol of the bot to monitor"),
    interval_seconds: int = Query(2, ge=1, le=10, description="Status update polling interval")
):
    await websocket.accept()
    logger.info(f"WebSocket client connected to stream status for {symbol}")
    
    try:
        while True:
            if websocket.client_state != WebSocketState.CONNECTED:
                break

            # Gather bot status and DB logs
            status_data = BotManager.get_bot_status(symbol, log_lines=30)
            from app.services.database_service import db_service
            db_logs = db_service.get_recent_logs(symbol=symbol, limit=50)

            # ── Always-fresh mark price ─────────────────────────────────
            live_mark_price = get_mark_price(symbol)
            mark_price_updated_at = get_mark_price_updated_at(symbol)

            # ── Staleness detection on bot telemetry ─────────────────────
            telemetry = status_data.live_status or {}
            telemetry_ts = telemetry.get("timestamp")
            now = time.time()
            data_stale = True  # Assume stale unless proven fresh
            if telemetry_ts:
                age = now - float(telemetry_ts)
                data_stale = age > TELEMETRY_STALE_THRESHOLD_SECONDS

            # Serialize status data to a dict
            payload = {
                "is_running": status_data.is_running,
                "bot_state": status_data.bot_state.model_dump() if status_data.bot_state else None,
                "live_status": status_data.live_status,
                "logs": status_data.logs,
                "structured_logs": db_logs,
                "mark_price": live_mark_price,
                "mark_price_updated_at": mark_price_updated_at,
                "data_stale": data_stale,
            }
            
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_json(payload)
            await asyncio.sleep(interval_seconds)
            
    except (WebSocketDisconnect, asyncio.CancelledError):
        logger.info(f"WebSocket client disconnected/cancelled for {symbol}")
    except (RuntimeError, ConnectionResetError, OSError) as e:
        logger.info(f"WebSocket closed transport for {symbol}: {e}")
    except Exception as e:
        logger.error(f"Error in live status websocket for {symbol}: {e}")
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.close()
        except Exception:
            pass

@router.websocket("/kline/live")
async def websocket_kline_live(
    websocket: WebSocket,
    symbol: str = Query("BTCUSDT", description="Symbol for kline stream"),
    interval: str = Query("1m", description="Kline interval, e.g., 1m,5m,1h"),
    interval_seconds: int = Query(2, ge=1, le=10, description="Client poll interval")
):
    await websocket.accept()
    try:
        async for kline in BinanceWebSocketService.stream_klines(symbol, interval):
            if websocket.client_state != WebSocketState.CONNECTED:
                break
            await websocket.send_json(kline)
            await asyncio.sleep(interval_seconds)
    except (WebSocketDisconnect, asyncio.CancelledError):
        logger.info(f"WebSocket client disconnected/cancelled for kline {symbol}")
    except (RuntimeError, ConnectionResetError, OSError) as e:
        logger.info(f"WebSocket closed transport for kline {symbol}: {e}")
    except Exception as e:
        logger.error(f"Error in kline websocket for {symbol}: {e}")
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.close()
        except Exception:
            pass
