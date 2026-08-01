"""Enhanced database service for trading bot operations."""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any

from sqlalchemy.orm import Session
from app.database import SessionLocal, DatabaseOperations
from app.models.trading import TradingPair, BotState, TradeExecution

logger = logging.getLogger("ha_alma_bot")

class TradingDatabaseService:
    """Service layer for all trading bot database operations."""
    
    def __init__(self):
        self.session_factory = SessionLocal
    
    def get_session(self) -> Session:
        """Get a new database session."""
        return self.session_factory()
    
    # Configuration Management
    def get_bot_config(self, symbol: str) -> Dict[str, Any]:
        """Get bot configuration with defaults."""
        with self.get_session() as db:
            ops = DatabaseOperations(db)
            config = ops.get_trading_pair_config(symbol)
            
            # Ensure trading pair exists with defaults if not found
            if not config:
                default_config = self._get_default_config(symbol)
                ops.get_or_create_trading_pair(symbol, default_config)
                config = default_config
            
            return config
    
    def save_bot_config(self, symbol: str, config_data: Dict[str, Any]) -> None:
        """Save bot configuration."""
        with self.get_session() as db:
            ops = DatabaseOperations(db)
            
            # Ensure trading pair exists
            ops.get_or_create_trading_pair(symbol, config_data)
            ops.update_trading_pair_config(symbol, config_data)
            
            logger.debug(f"Saved config for {symbol}")
    
    # State Management
    def get_bot_state(self, symbol: str) -> Dict[str, Any]:
        """Get bot state with defaults."""
        with self.get_session() as db:
            ops = DatabaseOperations(db)
            state = ops.get_bot_state(symbol)
            
            if not state:
                # Return default state if none exists
                return self._get_default_state()
            
            return state
    
    def save_bot_state(self, symbol: str, state_data: Dict[str, Any],
                      position_size: Decimal = None, entry_price: Decimal = None,
                      unrealized_pnl: Decimal = None) -> None:
        """Save bot state with optional position data."""
        with self.get_session() as db:
            ops = DatabaseOperations(db)
            ops.save_bot_state(
                symbol, state_data, position_size, entry_price, unrealized_pnl
            )
            
            logger.debug(f"Saved state for {symbol}: {state_data.get('status', 'UNKNOWN')}")
    
    # Trading Operations
    def record_order_placement(self, symbol: str, order_id: str, order_type: str,
                              side: str, quantity: Decimal, price: Decimal,
                              strategy_signal: str = None) -> None:
        """Record when an order is placed."""
        with self.get_session() as db:
            ops = DatabaseOperations(db)
            ops.record_trade_execution(
                symbol=symbol,
                order_id=order_id,
                order_type=order_type,
                side=side,
                quantity=quantity,
                price=price,
                order_time=datetime.utcnow(),
                strategy_signal=strategy_signal
            )
    
    def record_order_fill(self, symbol: str, order_id: str, fill_time: datetime,
                         actual_price: Decimal, commission: Decimal = None,
                         commission_asset: str = None, realized_pnl: Decimal = None) -> None:
        """Update order record when filled."""
        with self.get_session() as db:
            # Find the existing order record
            execution = db.query(TradeExecution).filter(
                TradeExecution.order_id == order_id
            ).first()
            
            if execution:
                execution.fill_time = fill_time
                execution.price = actual_price  # Update with actual fill price
                if commission is not None:
                    execution.commission = commission
                if commission_asset:
                    execution.commission_asset = commission_asset
                if realized_pnl is not None:
                    execution.realized_pnl = realized_pnl
                
                db.commit()
                logger.debug(f"Updated order fill: {order_id} at {actual_price}")
    
    def record_take_profit(self, symbol: str, tp_level: int, quantity: Decimal,
                          price: Decimal, realized_pnl: Decimal) -> None:
        """Record take profit execution."""
        with self.get_session() as db:
            ops = DatabaseOperations(db)
            ops.record_trade_execution(
                symbol=symbol,
                order_id=f"TP{tp_level}_{int(datetime.utcnow().timestamp())}",
                order_type="TAKE_PROFIT",
                side="SELL",  # Assuming long positions for now
                quantity=quantity,
                price=price,
                order_time=datetime.utcnow(),
                fill_time=datetime.utcnow(),
                realized_pnl=realized_pnl,
                strategy_signal="TAKE_PROFIT",
                tp_level=tp_level
            )
    
    # Performance Tracking
    def update_daily_performance(self, symbol: str, **metrics) -> None:
        """Update daily performance metrics."""
        with self.get_session() as db:
            ops = DatabaseOperations(db)
            ops.update_performance_metrics(
                symbol=symbol,
                date=datetime.utcnow(),
                period_type="DAILY",
                **metrics
            )
    
    def get_performance_summary(self, symbol: str, days: int = 30) -> Dict[str, Any]:
        """Get performance summary."""
        with self.get_session() as db:
            ops = DatabaseOperations(db)
            return ops.get_performance_summary(symbol, days)
    
    # Historical Data
    def save_price_data(self, symbol: str, timeframe: str, 
                       candles: List[Dict[str, Any]]) -> None:
        """Save historical price data."""
        with self.get_session() as db:
            ops = DatabaseOperations(db)
            ops.save_historical_data(symbol, timeframe, candles)
    
    def get_price_data(self, symbol: str, timeframe: str, limit: int = 300) -> List[Dict]:
        """Get historical price data."""
        with self.get_session() as db:
            ops = DatabaseOperations(db)
            return ops.get_historical_data(symbol, timeframe, limit)
    
    # Bot Management
    def get_active_bots(self) -> List[str]:
        """Get list of active bot symbols."""
        with self.get_session() as db:
            ops = DatabaseOperations(db)
            return ops.get_active_bots()
    
    def set_bot_active(self, symbol: str, is_active: bool) -> None:
        """Set bot active status."""
        with self.get_session() as db:
            ops = DatabaseOperations(db)
            ops.set_bot_active_status(symbol, is_active)
    
    # Logging
    def log_event(self, level: str, message: str, symbol: str = None,
                  extra_data: Dict[str, Any] = None) -> None:
        """Log system event to database."""
        with self.get_session() as db:
            ops = DatabaseOperations(db)
            ops.log_event(level, message, symbol, extra_data)
    
    def get_recent_logs(self, symbol: str = None, level: str = None,
                       hours: int = 24, limit: int = 100) -> List[Dict]:
        """Get recent log entries."""
        with self.get_session() as db:
            ops = DatabaseOperations(db)
            logs = ops.get_recent_logs(level, symbol, hours, limit)
            
            return [
                {
                    'timestamp': log.created_at,
                    'level': log.level,
                    'message': log.message,
                    'symbol': log.symbol,
                    'logger_name': log.logger_name,
                    'extra_data': log.extra_data
                }
                for log in logs
            ]
    
    # Utility Methods
    def _get_default_config(self, symbol: str) -> Dict[str, Any]:
        """Get default configuration for a symbol."""
        return {
            "symbol": symbol,
            "testnet": True,
            "interval": "12h",
            "leverage": 10,
            "adx_period": 14,
            "atr_period": 14,
            "rsi_period": 14,
            "alma_window": 9,
            "tp_step_atr": 0.5,
            "poll_seconds": 15,
            "adx_threshold": 25.0,
            "rsi_sma_period": 14,
            "klines_lookback": 300,
            "sl_atr_multiple": 1.0,
            "sl_trail_gap_atr": 0.5,
            "telegram_enabled": True,
            "tp_custom_levels": "0.5",
            "trend_sma_period": 50,
            "tp_close_fraction": 0.3,
            "adx_filter_enabled": False,
            "margin_fraction_per_entry": 0.25,
            "margin_fraction_counter_trend": 0.2
        }
    
    def _get_default_state(self) -> Dict[str, Any]:
        """Get default bot state."""
        return {
            "status": "IDLE",
            "direction": None,
            "entry1_order_id": None,
            "entry2_order_id": None,
            "sl_order_id": None,
            "tp_order_id": None,
            "atr_at_signal": None,
            "signal_candle_time": None,
            "tp_level": 0,
            "last_resized_qty": None,
            "realized_pnl": 0.0
        }
    
    # Analytics and Reporting
    def get_trading_statistics(self, symbol: str) -> Dict[str, Any]:
        """Get comprehensive trading statistics."""
        with self.get_session() as db:
            # Get recent trades
            trades = db.query(TradeExecution).filter(
                TradeExecution.symbol == symbol
            ).order_by(TradeExecution.order_time.desc()).limit(100).all()
            
            if not trades:
                return {"message": "No trading history found"}
            
            # Calculate statistics
            total_trades = len(trades)
            profitable_trades = sum(1 for t in trades if t.realized_pnl and t.realized_pnl > 0)
            total_pnl = sum(t.realized_pnl or 0 for t in trades)
            total_commission = sum(t.commission or 0 for t in trades)
            
            return {
                "total_trades": total_trades,
                "profitable_trades": profitable_trades,
                "win_rate": profitable_trades / total_trades if total_trades > 0 else 0,
                "total_pnl": float(total_pnl),
                "total_commission": float(total_commission),
                "net_pnl": float(total_pnl - total_commission),
                "avg_trade_pnl": float(total_pnl / total_trades) if total_trades > 0 else 0
            }

# Global instance
db_service = TradingDatabaseService()