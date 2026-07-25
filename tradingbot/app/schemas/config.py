from pydantic import BaseModel, Field, field_validator
from typing import Optional
from app.trading_engine.bot import parse_tp_custom_levels


class TradingConfigSchema(BaseModel):
    testnet: bool = True
    symbol: str = "BTCUSDT"
    interval: str = "12h"
    leverage: int = Field(10, ge=1, le=125)
    margin_fraction_per_entry: float = Field(0.25, ge=0.01, le=1.0)
    margin_fraction_counter_trend: float = Field(0.20, ge=0.01, le=1.0)
    trend_sma_period: int = Field(50, ge=2, le=500)
    alma_window: int = Field(9, ge=2, le=200)
    rsi_period: int = Field(14, ge=2, le=200)
    rsi_sma_period: int = Field(14, ge=2, le=200)
    atr_period: int = Field(14, ge=2, le=200)
    sl_atr_multiple: float = Field(1.0, ge=0.1, le=10.0)
    tp_custom_levels: str = Field("0.5", description="Comma-separated ATR multiples")
    tp_step_atr: float = Field(0.5, ge=0.05, le=10.0)
    tp_close_fraction: float = Field(0.30, ge=0.05, le=0.95)
    sl_trail_gap_atr: float = Field(0.5, ge=0.05, le=10.0)
    adx_filter_enabled: bool = False
    adx_period: int = Field(14, ge=2, le=200)
    adx_threshold: float = Field(25.0, ge=0.0, le=100.0)
    poll_seconds: int = Field(15, ge=1, le=3600)
    klines_lookback: int = Field(300, ge=50, le=1500)
    telegram_enabled: bool = True

    @field_validator("tp_custom_levels")
    @classmethod
    def validate_custom_levels(cls, v: str) -> str:
        try:
            parse_tp_custom_levels(v)
            return v
        except ValueError as e:
            raise ValueError(f"Invalid tp_custom_levels format: {e}")


class ConfigResponseSchema(BaseModel):
    config: TradingConfigSchema
    limits: dict
