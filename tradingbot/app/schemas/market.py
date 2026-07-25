from pydantic import BaseModel, Field
from typing import List, Optional


class MarketDownloadRequestSchema(BaseModel):
    symbol: str = Field("BTCUSDT", description="Binance Futures trading pair, e.g., BTCUSDT")
    interval: str = Field("12h", description="Candle interval, e.g., 1h, 4h, 12h, 1d")
    months: int = Field(12, ge=1, le=60, description="Number of months of historical data to fetch")
    filename: Optional[str] = Field(None, description="Output filename (will default to symbol_interval.csv if not provided)")


class DatasetFileSchema(BaseModel):
    name: str
    size_bytes: int
    last_modified: str
    filepath: str


class DownloadResponseSchema(BaseModel):
    success: bool
    message: str
    filename: str
    filepath: str
    rows_count: int


class RawKlineSchema(BaseModel):
    open_time: int
    open: float
    high: float
    low: float
    close: float
    close_time: int
