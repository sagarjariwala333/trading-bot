from fastapi import APIRouter, Query, HTTPException
from typing import List
from app.schemas.indicators import LatestSignalResponseSchema, IndicatorRowSchema, IndicatorCalculateRequestSchema
from app.services.indicator_service import IndicatorService
from app.services.bot_manager import BotManager

router = APIRouter()


@router.get("/latest", response_model=LatestSignalResponseSchema)
def get_latest_signal(
    symbol: str = Query("BTCUSDT", description="Symbol to evaluate signal for"),
    interval: str = Query("12h", description="Candle interval")
):
    try:
        # Load custom periods from symbol configuration if they exist
        cfg = BotManager.get_config(symbol)
        
        return IndicatorService.evaluate_latest_signal(
            symbol=symbol,
            interval=interval,
            alma_window=cfg.get("alma_window", 9),
            rsi_period=cfg.get("rsi_period", 14),
            rsi_sma_period=cfg.get("rsi_sma_period", 14),
            atr_period=cfg.get("atr_period", 14),
            adx_period=cfg.get("adx_period", 14),
            trend_sma_period=cfg.get("trend_sma_period", 50),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compute latest indicators: {e}")


@router.post("/calculate", response_model=List[IndicatorRowSchema])
def calculate_indicators(payload: IndicatorCalculateRequestSchema):
    try:
        cfg = BotManager.get_config(payload.symbol)
        df = IndicatorService.fetch_live_klines(payload.symbol, payload.interval, payload.klines_lookback)
        df_ind = IndicatorService.calculate_indicators(
            df,
            alma_window=cfg.get("alma_window", 9),
            rsi_period=cfg.get("rsi_period", 14),
            rsi_sma_period=cfg.get("rsi_sma_period", 14),
            atr_period=cfg.get("atr_period", 14),
            adx_period=cfg.get("adx_period", 14),
            trend_sma_period=cfg.get("trend_sma_period", 50),
        )
        return IndicatorService.get_indicator_rows(df_ind)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to calculate indicators: {e}")
