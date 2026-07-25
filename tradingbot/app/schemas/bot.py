from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class BotStateSchema(BaseModel):
    status: str
    direction: Optional[str] = None
    entry1_order_id: Optional[int] = None
    entry2_order_id: Optional[int] = None
    sl_order_id: Optional[int] = None
    tp_order_id: Optional[int] = None
    atr_at_signal: Optional[float] = None
    signal_candle_time: Optional[int] = None
    tp_level: int = 0


class LiveStatusSchema(BaseModel):
    timestamp: float
    symbol: str
    interval: str
    position_amt: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    sl_price: Optional[float] = None
    tp_price: Optional[float] = None
    tp_qty: Optional[float] = None
    tp_level: int
    balance: float
    leverage: int
    testnet: bool
    reconciled_at: Optional[float] = None


class BotStatusResponseSchema(BaseModel):
    is_running: bool
    bot_state: Optional[BotStateSchema] = None
    live_status: Optional[Dict[str, Any]] = None
    logs: List[str] = []


class LogTailResponseSchema(BaseModel):
    logs: List[str]
    line_count: int


class BotControlResponseSchema(BaseModel):
    success: bool
    message: str
