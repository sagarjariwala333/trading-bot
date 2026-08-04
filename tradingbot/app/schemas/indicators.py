from pydantic import BaseModel
from typing import List, Optional, Dict


class IndicatorRowSchema(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    ha_open: float
    ha_high: float
    ha_low: float
    ha_close: float
    alma: Optional[float] = None
    rsi: Optional[float] = None
    rsi_sma: Optional[float] = None
    atr: Optional[float] = None
    adx: Optional[float] = None
    trend_sma: Optional[float] = None


class IndicatorCalculateRequestSchema(BaseModel):
    symbol: str = "BTCUSDT"
    interval: Optional[str] = None
    klines_lookback: int = 300


class LatestSignalResponseSchema(BaseModel):
    timestamp: str
    symbol: str
    interval: str
    signal: Optional[str] = None  # "LONG", "SHORT", or None
    close_price: float
    ha_close: float
    alma: Optional[float] = None
    rsi: Optional[float] = None
    rsi_sma: Optional[float] = None
    atr: Optional[float] = None
    adx: Optional[float] = None
    trend_sma: Optional[float] = None
    is_aligned_with_trend: bool
