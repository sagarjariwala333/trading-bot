"""Trading-related database models."""

from datetime import datetime
from decimal import Decimal
from typing import Dict, Any

from sqlalchemy import (
    Column, String, Boolean, DateTime, Integer, 
    Numeric, Text, Index, ForeignKey
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator, VARCHAR

from .base import Base, TimestampMixin

class JSONType(TypeDecorator):
    """Platform-independent JSON type."""
    impl = VARCHAR
    cache_ok = True
    
    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(JSONB())
        else:
            return dialect.type_descriptor(Text())
    
    def process_bind_param(self, value, dialect):
        if value is not None:
            import json
            return json.dumps(value)
        return value
    
    def process_result_value(self, value, dialect):
        if value is not None:
            import json
            return json.loads(value)
        return value

class TradingPair(Base, TimestampMixin):
    """Trading pair configuration and metadata."""
    __tablename__ = "trading_pairs"
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), unique=True, nullable=False, index=True)
    base_asset = Column(String(10), nullable=False)
    quote_asset = Column(String(10), nullable=False) 
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Trading configuration
    config_data = Column(JSONType, nullable=False)
    
    # Exchange info
    tick_size = Column(Numeric(20, 8))
    step_size = Column(Numeric(20, 8))
    min_notional = Column(Numeric(20, 8))
    
    # Relationships
    bot_states = relationship("BotState", back_populates="trading_pair")
    trade_executions = relationship("TradeExecution", back_populates="trading_pair")
    historical_data = relationship("HistoricalData", back_populates="trading_pair")
    
    __table_args__ = (
        Index('idx_trading_pairs_symbol', 'symbol'),
        Index('idx_trading_pairs_active', 'is_active'),
    )

class BotState(Base, TimestampMixin):
    """Current state of trading bots."""
    __tablename__ = "bot_states"
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), ForeignKey('trading_pairs.symbol'), nullable=False, index=True)
    
    # Bot status
    status = Column(String(20), nullable=False, default="IDLE")  # IDLE, WAITING_ENTRY, POSITION_OPEN, etc.
    is_running = Column(Boolean, default=False, nullable=False)
    
    # State data
    state_data = Column(JSONType, nullable=False)
    
    # Current position info
    position_size = Column(Numeric(20, 8), default=0)
    entry_price = Column(Numeric(20, 8))
    unrealized_pnl = Column(Numeric(20, 8))
    
    # Risk management
    stop_loss_price = Column(Numeric(20, 8))
    take_profit_price = Column(Numeric(20, 8))
    
    # Relationships
    trading_pair = relationship("TradingPair", back_populates="bot_states")
    
    __table_args__ = (
        Index('idx_bot_states_symbol', 'symbol'),
        Index('idx_bot_states_running', 'is_running'),
        Index('idx_bot_states_status', 'status'),
    )

class HistoricalData(Base, TimestampMixin):
    """Historical price and volume data."""
    __tablename__ = "historical_data"
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), ForeignKey('trading_pairs.symbol'), nullable=False)
    timeframe = Column(String(10), nullable=False)  # 1m, 5m, 15m, 1h, 4h, 12h, 1d
    
    timestamp = Column(DateTime, nullable=False, index=True)
    open_price = Column(Numeric(20, 8), nullable=False)
    high_price = Column(Numeric(20, 8), nullable=False)
    low_price = Column(Numeric(20, 8), nullable=False)
    close_price = Column(Numeric(20, 8), nullable=False)
    volume = Column(Numeric(20, 8), nullable=False)
    
    # Relationships
    trading_pair = relationship("TradingPair", back_populates="historical_data")
    
    __table_args__ = (
        Index('idx_historical_data_symbol_time', 'symbol', 'timestamp'),
        Index('idx_historical_data_symbol_timeframe', 'symbol', 'timeframe'),
        # Unique constraint to prevent duplicate data
        Index('idx_historical_data_unique', 'symbol', 'timeframe', 'timestamp', unique=True),
    )

class TradeExecution(Base, TimestampMixin):
    """Record of all trade executions and orders."""
    __tablename__ = "trade_executions"
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), ForeignKey('trading_pairs.symbol'), nullable=False)
    
    # Order details
    order_id = Column(String(50), nullable=False, index=True)
    client_order_id = Column(String(50))
    order_type = Column(String(20), nullable=False)  # MARKET, LIMIT, STOP_MARKET, etc.
    side = Column(String(10), nullable=False)  # BUY, SELL
    
    # Execution details
    quantity = Column(Numeric(20, 8), nullable=False)
    price = Column(Numeric(20, 8), nullable=False)
    commission = Column(Numeric(20, 8), default=0)
    commission_asset = Column(String(10))
    
    # P&L tracking
    realized_pnl = Column(Numeric(20, 8))
    
    # Timing
    order_time = Column(DateTime, nullable=False)
    fill_time = Column(DateTime)
    
    # Strategy context
    strategy_signal = Column(String(20))  # LONG_ENTRY, SHORT_ENTRY, TAKE_PROFIT, STOP_LOSS
    tp_level = Column(Integer)  # For tracking TP ladder levels
    
    # Relationships
    trading_pair = relationship("TradingPair", back_populates="trade_executions")
    
    __table_args__ = (
        Index('idx_trade_executions_symbol', 'symbol'),
        Index('idx_trade_executions_order_id', 'order_id'),
        Index('idx_trade_executions_time', 'order_time'),
        Index('idx_trade_executions_strategy', 'strategy_signal'),
    )

class PerformanceMetrics(Base, TimestampMixin):
    """Daily/hourly performance metrics."""
    __tablename__ = "performance_metrics"
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), ForeignKey('trading_pairs.symbol'), nullable=False)
    
    # Time period
    date = Column(DateTime, nullable=False, index=True)
    period_type = Column(String(10), nullable=False)  # DAILY, HOURLY, WEEKLY
    
    # P&L metrics
    realized_pnl = Column(Numeric(20, 8), default=0)
    unrealized_pnl = Column(Numeric(20, 8), default=0)
    total_pnl = Column(Numeric(20, 8), default=0)
    
    # Trade metrics
    trades_count = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    win_rate = Column(Numeric(5, 4))  # 0.0000 to 1.0000
    
    # Risk metrics
    max_drawdown = Column(Numeric(20, 8))
    sharpe_ratio = Column(Numeric(10, 6))
    
    # Volume metrics
    total_volume = Column(Numeric(20, 8), default=0)
    total_commission = Column(Numeric(20, 8), default=0)
    
    __table_args__ = (
        Index('idx_performance_metrics_symbol_date', 'symbol', 'date'),
        Index('idx_performance_metrics_period', 'period_type'),
        # Unique constraint for one record per symbol/date/period
        Index('idx_performance_metrics_unique', 'symbol', 'date', 'period_type', unique=True),
    )

class SystemLog(Base, TimestampMixin):
    """System logs and events."""
    __tablename__ = "system_logs"
    
    id = Column(Integer, primary_key=True)
    
    # Log details
    level = Column(String(10), nullable=False, index=True)  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    message = Column(Text, nullable=False)
    logger_name = Column(String(50))
    
    # Context
    symbol = Column(String(20), index=True)  # Optional, for trade-specific logs
    bot_instance = Column(String(50))  # For multi-instance setups
    
    # Additional data
    extra_data = Column(JSONType)  # For structured log data
    
    __table_args__ = (
        Index('idx_system_logs_level', 'level'),
        Index('idx_system_logs_time', 'created_at'),
        Index('idx_system_logs_symbol', 'symbol'),
    )