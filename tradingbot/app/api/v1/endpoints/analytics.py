from fastapi import APIRouter, Query, HTTPException
from typing import Dict, Any, List
from app.core.db import (
    get_db_trades, get_db_trade_summary, get_db_orders, get_db_signals
)

router = APIRouter()


@router.get("/trades")
def get_bot_trades(
    symbol: str = Query("BTCUSDT", description="Symbol of the trading bot"),
    limit: int = Query(100, ge=1, le=1000)
) -> Dict[str, Any]:
    try:
        trades = get_db_trades(symbol, limit=limit)
        summary = get_db_trade_summary(symbol)
        return {
            "symbol": symbol.upper(),
            "summary": summary,
            "count": len(trades),
            "trades": trades
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching trades: {e}")


@router.get("/orders")
def get_bot_orders(
    symbol: str = Query("BTCUSDT", description="Symbol of the trading bot"),
    limit: int = Query(100, ge=1, le=1000)
) -> Dict[str, Any]:
    try:
        orders = get_db_orders(symbol, limit=limit)
        return {
            "symbol": symbol.upper(),
            "count": len(orders),
            "orders": orders
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching orders: {e}")


@router.get("/signals")
def get_bot_signals(
    symbol: str = Query("BTCUSDT", description="Symbol of the trading bot"),
    limit: int = Query(100, ge=1, le=1000)
) -> Dict[str, Any]:
    try:
        signals = get_db_signals(symbol, limit=limit)
        return {
            "symbol": symbol.upper(),
            "count": len(signals),
            "signals": signals
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching signal decisions: {e}")


@router.get("/performance")
def get_bot_performance(
    symbol: str = Query("BTCUSDT", description="Symbol of the trading bot")
) -> Dict[str, Any]:
    try:
        summary = get_db_trade_summary(symbol)
        return {
            "symbol": symbol.upper(),
            "performance": summary
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching performance metrics: {e}")
