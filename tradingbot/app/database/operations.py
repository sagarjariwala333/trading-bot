"""Database operations for trading bot."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, func

from app.models.trading import (
    TradingPair, BotState, HistoricalData, 
    TradeExecution, PerformanceMetrics, SystemLog
)

class DatabaseOperations:
    """High-level database operations for the trading bot."""
    
    def __init__(self, db: Session):
        self.db = db
    
    # Trading Pair Operations
    def get_or_create_trading_pair(self, symbol: str, config_data: Dict[str, Any]) -> TradingPair:
        """Get existing trading pair or create new one."""
        pair = self.db.query(TradingPair).filter(TradingPair.symbol == symbol).first()
        
        if not pair:
            # Extract base and quote from symbol (e.g., BTCUSDT -> BTC, USDT)
            if symbol.endswith('USDT'):
                base_asset = symbol[:-4]
                quote_asset = 'USDT'
            elif symbol.endswith('BTC'):
                base_asset = symbol[:-3] 
                quote_asset = 'BTC'
            else:
                # Default fallback
                base_asset = symbol[:-4] if len(symbol) > 4 else symbol
                quote_asset = 'USDT'
            
            pair = TradingPair(
                symbol=symbol,
                base_asset=base_asset,
                quote_asset=quote_asset,
                config_data=config_data,
                is_active=True
            )
            self.db.add(pair)
            self.db.commit()
            self.db.refresh(pair)
        
        return pair
    
    def update_trading_pair_config(self, symbol: str, config_data: Dict[str, Any]) -> None:
        """Update trading pair configuration."""
        pair = self.db.query(TradingPair).filter(TradingPair.symbol == symbol).first()
        if pair:
            pair.config_data = config_data
            pair.updated_at = datetime.utcnow()
            self.db.commit()
    
    def get_trading_pair_config(self, symbol: str) -> Dict[str, Any]:
        """Get trading pair configuration."""
        pair = self.db.query(TradingPair).filter(TradingPair.symbol == symbol).first()
        return pair.config_data if pair else {}
    
    # Bot State Operations  
    def get_bot_state(self, symbol: str) -> Dict[str, Any]:
        """Get current bot state."""
        state = self.db.query(BotState).filter(BotState.symbol == symbol).first()
        return state.state_data if state else {}
    
    def save_bot_state(self, symbol: str, state_data: Dict[str, Any], 
                      position_size: Decimal = None, entry_price: Decimal = None,
                      unrealized_pnl: Decimal = None) -> None:
        """Save/update bot state."""
        state = self.db.query(BotState).filter(BotState.symbol == symbol).first()
        
        if not state:
            state = BotState(
                symbol=symbol,
                state_data=state_data,
                status=state_data.get('status', 'IDLE'),
                is_running=state_data.get('is_running', False)
            )
            self.db.add(state)
        else:
            state.state_data = state_data
            state.status = state_data.get('status', state.status)
            state.is_running = state_data.get('is_running', state.is_running)
            state.updated_at = datetime.utcnow()
        
        # Update position info if provided
        if position_size is not None:
            state.position_size = position_size
        if entry_price is not None:
            state.entry_price = entry_price
        if unrealized_pnl is not None:
            state.unrealized_pnl = unrealized_pnl
        
        self.db.commit()
    
    def get_active_bots(self) -> List[str]:
        """Get list of active bot symbols."""
        states = self.db.query(BotState).filter(BotState.is_running == True).all()
        return [state.symbol for state in states]
    
    def set_bot_active_status(self, symbol: str, is_running: bool) -> None:
        """Set bot active status."""
        state = self.db.query(BotState).filter(BotState.symbol == symbol).first()
        
        if not state:
            state = BotState(
                symbol=symbol,
                state_data={'status': 'IDLE'},
                is_running=is_running
            )
            self.db.add(state)
        else:
            state.is_running = is_running
            state.updated_at = datetime.utcnow()
        
        self.db.commit()
    
    # Historical Data Operations
    def save_historical_data(self, symbol: str, timeframe: str, 
                           data: List[Dict[str, Any]]) -> None:
        """Save historical price data."""
        for candle in data:
            # Check if data already exists
            existing = self.db.query(HistoricalData).filter(
                and_(
                    HistoricalData.symbol == symbol,
                    HistoricalData.timeframe == timeframe,
                    HistoricalData.timestamp == candle['timestamp']
                )
            ).first()
            
            if not existing:
                hist_data = HistoricalData(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=candle['timestamp'],
                    open_price=Decimal(str(candle['open'])),
                    high_price=Decimal(str(candle['high'])),
                    low_price=Decimal(str(candle['low'])),
                    close_price=Decimal(str(candle['close'])),
                    volume=Decimal(str(candle['volume']))
                )
                self.db.add(hist_data)
        
        self.db.commit()
    
    def get_historical_data(self, symbol: str, timeframe: str, 
                           limit: int = 300) -> List[Dict[str, Any]]:
        """Get historical data for analysis."""
        data = self.db.query(HistoricalData).filter(
            and_(
                HistoricalData.symbol == symbol,
                HistoricalData.timeframe == timeframe
            )
        ).order_by(desc(HistoricalData.timestamp)).limit(limit).all()
        
        return [
            {
                'timestamp': d.timestamp,
                'open': float(d.open_price),
                'high': float(d.high_price),
                'low': float(d.low_price),
                'close': float(d.close_price),
                'volume': float(d.volume)
            }
            for d in reversed(data)  # Return in chronological order
        ]
    
    # Trade Execution Operations
    def record_trade_execution(self, symbol: str, order_id: str, 
                             order_type: str, side: str, quantity: Decimal,
                             price: Decimal, **kwargs) -> None:
        """Record a trade execution."""
        execution = TradeExecution(
            symbol=symbol,
            order_id=order_id,
            order_type=order_type,
            side=side,
            quantity=quantity,
            price=price,
            order_time=kwargs.get('order_time', datetime.utcnow()),
            fill_time=kwargs.get('fill_time'),
            commission=kwargs.get('commission', Decimal('0')),
            commission_asset=kwargs.get('commission_asset'),
            realized_pnl=kwargs.get('realized_pnl'),
            strategy_signal=kwargs.get('strategy_signal'),
            tp_level=kwargs.get('tp_level'),
            client_order_id=kwargs.get('client_order_id')
        )
        
        self.db.add(execution)
        self.db.commit()
    
    def get_trade_history(self, symbol: str, days: int = 30) -> List[TradeExecution]:
        """Get recent trade history."""
        since_date = datetime.utcnow() - timedelta(days=days)
        
        return self.db.query(TradeExecution).filter(
            and_(
                TradeExecution.symbol == symbol,
                TradeExecution.order_time >= since_date
            )
        ).order_by(desc(TradeExecution.order_time)).all()
    
    # Performance Metrics Operations
    def update_performance_metrics(self, symbol: str, date: datetime, 
                                 period_type: str = 'DAILY', **metrics) -> None:
        """Update performance metrics for a period."""
        existing = self.db.query(PerformanceMetrics).filter(
            and_(
                PerformanceMetrics.symbol == symbol,
                PerformanceMetrics.date == date.date(),
                PerformanceMetrics.period_type == period_type
            )
        ).first()
        
        if existing:
            for key, value in metrics.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            existing.updated_at = datetime.utcnow()
        else:
            perf = PerformanceMetrics(
                symbol=symbol,
                date=date,
                period_type=period_type,
                **metrics
            )
            self.db.add(perf)
        
        self.db.commit()
    
    def get_performance_summary(self, symbol: str, days: int = 30) -> Dict[str, Any]:
        """Get performance summary for recent period."""
        since_date = datetime.utcnow() - timedelta(days=days)
        
        metrics = self.db.query(PerformanceMetrics).filter(
            and_(
                PerformanceMetrics.symbol == symbol,
                PerformanceMetrics.date >= since_date.date(),
                PerformanceMetrics.period_type == 'DAILY'
            )
        ).all()
        
        if not metrics:
            return {}
        
        return {
            'total_pnl': sum(m.total_pnl or 0 for m in metrics),
            'total_trades': sum(m.trades_count or 0 for m in metrics),
            'winning_trades': sum(m.winning_trades or 0 for m in metrics),
            'losing_trades': sum(m.losing_trades or 0 for m in metrics),
            'win_rate': sum(m.win_rate or 0 for m in metrics) / len(metrics) if metrics else 0,
            'total_volume': sum(m.total_volume or 0 for m in metrics),
            'total_commission': sum(m.total_commission or 0 for m in metrics),
            'days_active': len(metrics)
        }
    
    # System Logging Operations
    def log_event(self, level: str, message: str, symbol: str = None, 
                  extra_data: Dict[str, Any] = None, logger_name: str = None) -> None:
        """Log a system event."""
        log_entry = SystemLog(
            level=level.upper(),
            message=message,
            symbol=symbol,
            logger_name=logger_name or 'trading_bot',
            extra_data=extra_data
        )
        
        self.db.add(log_entry)
        self.db.commit()
    
    def get_recent_logs(self, level: str = None, symbol: str = None, 
                       hours: int = 24, limit: int = 100) -> List[SystemLog]:
        """Get recent system logs."""
        since_time = datetime.utcnow() - timedelta(hours=hours)
        
        query = self.db.query(SystemLog).filter(SystemLog.created_at >= since_time)
        
        if level:
            query = query.filter(SystemLog.level == level.upper())
        
        if symbol:
            query = query.filter(SystemLog.symbol == symbol)
        
        return query.order_by(desc(SystemLog.created_at)).limit(limit).all()