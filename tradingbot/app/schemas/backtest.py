from pydantic import BaseModel, Field
from typing import List, Dict, Optional


class BacktestRequestSchema(BaseModel):
    dataset_name: str = Field(..., description="Name of the historical CSV dataset file in data/ directory")
    starting_balance: float = Field(10000.0, ge=10.0)
    
    # Custom strategy settings (optional, defaults to config if not provided)
    leverage: Optional[int] = Field(None, ge=1, le=125)
    margin_fraction_per_entry: Optional[float] = Field(None, ge=0.01, le=1.0)
    margin_fraction_counter_trend: Optional[float] = Field(None, ge=0.01, le=1.0)
    trend_sma_period: Optional[int] = Field(None, ge=2, le=500)
    alma_window: Optional[int] = Field(None, ge=2, le=200)
    rsi_period: Optional[int] = Field(None, ge=2, le=200)
    rsi_sma_period: Optional[int] = Field(None, ge=2, le=200)
    atr_period: Optional[int] = Field(None, ge=2, le=200)
    sl_atr_multiple: Optional[float] = Field(None, ge=0.1, le=10.0)
    tp_custom_levels: Optional[str] = Field(None, description="Comma-separated ATR multiples")
    tp_step_atr: Optional[float] = Field(None, ge=0.05, le=10.0)
    tp_close_fraction: Optional[float] = Field(None, ge=0.05, le=0.95)
    sl_trail_gap_atr: Optional[float] = Field(None, ge=0.05, le=10.0)


class BacktestTradeSchema(BaseModel):
    direction: str
    signal_time: str
    entry_price: Optional[float] = None
    qty: float
    tp_level: int
    realized_pnl: float
    fees_paid: float
    close_time: Optional[str] = None
    close_reason: Optional[str] = None  # "SL", "TP_FINAL", "REVERSAL"


class EquityPointSchema(BaseModel):
    timestamp: str
    balance: float


class BacktestResponseSchema(BaseModel):
    dataset_name: str
    starting_balance: float
    final_balance: float
    total_return_pct: float
    total_trades: int
    win_rate_pct: float
    wins_count: int
    losses_count: int
    monthly_pnl: Dict[str, float]
    close_reasons: Dict[str, int]
    equity_curve: List[EquityPointSchema]
    trades: List[BacktestTradeSchema]
