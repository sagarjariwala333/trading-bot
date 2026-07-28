import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy import (
    create_engine, Column, String, Float, Integer, Boolean,
    DateTime, JSON, Text, select, func, or_, case
)
from sqlalchemy.orm import declarative_base, Session
from app.core.config import settings

logger = logging.getLogger("ha_alma_bot")

# Resolve database URL:
# 1. Local environment (DATABASE_URL empty): automatically uses SQLite (data/tradingbot.db)
# 2. Production environment (Render / Cloud): uses PostgreSQL via DATABASE_URL env var
db_url = settings.DATABASE_URL or os.environ.get("DATABASE_URL", "").strip()

if not db_url:
    # Local fallback: SQLite
    db_dir = os.path.abspath(settings.DATA_DIR)
    os.makedirs(db_dir, exist_ok=True)
    sqlite_path = os.path.join(db_dir, "tradingbot.db")
    db_url = f"sqlite:///{sqlite_path}"
    logger.info(f"Database Engine: Running locally using SQLite ({sqlite_path})")
else:
    # Render and PostgreSQL providers use "postgres://", but SQLAlchemy requires "postgresql://"
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    logger.info("Database Engine: Running in Production using PostgreSQL (Render / Cloud)")

# Create engine
engine = create_engine(
    db_url,
    pool_pre_ping=True,
    **({"pool_size": 5, "max_overflow": 10} if not db_url.startswith("sqlite") else {})
)

# Declarative Base for ORM Models
Base = declarative_base()


# ---- ORM MODELS ---------------------------------------------------

class BotConfig(Base):
    __tablename__ = "bot_configs"
    symbol = Column(String(20), primary_key=True)
    config_data = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class BotState(Base):
    __tablename__ = "bot_states"
    symbol = Column(String(20), primary_key=True)
    state_data = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class ActiveBot(Base):
    __tablename__ = "active_bots"
    symbol = Column(String(20), primary_key=True)
    is_running = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class LiveStatus(Base):
    __tablename__ = "live_statuses"
    symbol = Column(String(20), primary_key=True)
    status_data = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class OrderModel(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    trade_id = Column(String(50))
    order_id = Column(String(50), index=True)
    algo_id = Column(String(50), index=True)
    client_order_id = Column(String(50), index=True)
    client_algo_id = Column(String(50), index=True)
    side = Column(String(10))
    order_type = Column(String(20))
    purpose = Column(String(30))
    price = Column(Float)
    stop_price = Column(Float)
    quantity = Column(Float)
    executed_qty = Column(Float, default=0.0)
    status = Column(String(20), default="NEW")
    reduce_only = Column(Boolean, default=False)
    working_type = Column(String(20))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    order_data = Column(JSON)


class TradeModel(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(String(50), unique=True, nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    direction = Column(String(10), nullable=False)
    entry_time = Column(DateTime)
    exit_time = Column(DateTime)
    entry_price = Column(Float)
    exit_price = Column(Float)
    quantity = Column(Float)
    leverage = Column(Integer)
    margin_used = Column(Float)
    trend_aligned = Column(Boolean)
    atr_at_signal = Column(Float)
    tp_levels_hit = Column(Integer, default=0)
    gross_pnl = Column(Float, default=0.0)
    estimated_fees = Column(Float, default=0.0)
    realized_pnl = Column(Float, default=0.0)
    return_pct = Column(Float, default=0.0)
    close_reason = Column(String(50))
    created_at = Column(DateTime, default=func.now())
    trade_data = Column(JSON)


class SignalHistoryModel(Base):
    __tablename__ = "signals_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    candle_time = Column(DateTime)
    ha_open = Column(Float)
    ha_close = Column(Float)
    ha_high = Column(Float)
    ha_low = Column(Float)
    alma = Column(Float)
    rsi = Column(Float)
    rsi_sma = Column(Float)
    atr = Column(Float)
    adx = Column(Float)
    trend_sma = Column(Float)
    signal = Column(String(10))
    decision = Column(String(50))
    executed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())


class BotLogModel(Base):
    __tablename__ = "bot_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    timestamp = Column(DateTime, default=func.now())
    level = Column(String(10), nullable=False)
    message = Column(Text, nullable=False)


from sqlalchemy import text

def init_db():
    """Create all required database tables via SQLAlchemy ORM Metadata."""
    Base.metadata.create_all(bind=engine)
    
    # Ensure missing columns in pre-existing tables are added safely
    for tbl in ["bot_configs", "bot_states", "active_bots", "live_statuses"]:
        try:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN updated_at TIMESTAMP"))
        except Exception:
            pass

    logger.info("SQLAlchemy ORM models & database tables initialized successfully.")


# ---- CONFIG & STATE HELPERS ---------------------------------------

def get_db_config(symbol: str) -> dict:
    symbol_clean = symbol.strip().upper()
    with Session(engine) as session:
        item = session.get(BotConfig, symbol_clean)
        if item and item.config_data:
            val = item.config_data
            return json.loads(val) if isinstance(val, str) else val
    return {}


def save_db_config(symbol: str, config_data: dict) -> None:
    symbol_clean = symbol.strip().upper()
    with Session(engine) as session:
        item = session.get(BotConfig, symbol_clean)
        if not item:
            item = BotConfig(symbol=symbol_clean, config_data=config_data)
            session.add(item)
        else:
            item.config_data = config_data
        session.commit()


def get_db_state(symbol: str) -> dict:
    symbol_clean = symbol.strip().upper()
    with Session(engine) as session:
        item = session.get(BotState, symbol_clean)
        if item and item.state_data:
            val = item.state_data
            return json.loads(val) if isinstance(val, str) else val
    return {}


def save_db_state(symbol: str, state_data: dict) -> None:
    symbol_clean = symbol.strip().upper()
    with Session(engine) as session:
        item = session.get(BotState, symbol_clean)
        if not item:
            item = BotState(symbol=symbol_clean, state_data=state_data)
            session.add(item)
        else:
            item.state_data = state_data
        session.commit()


def get_active_bots() -> list:
    with Session(engine) as session:
        stmt = select(ActiveBot.symbol).where(ActiveBot.is_running == True)
        return list(session.scalars(stmt).all())


def set_bot_active_status(symbol: str, is_running: bool) -> None:
    symbol_clean = symbol.strip().upper()
    with Session(engine) as session:
        item = session.get(ActiveBot, symbol_clean)
        if not item:
            item = ActiveBot(symbol=symbol_clean, is_running=is_running)
            session.add(item)
        else:
            item.is_running = is_running
        session.commit()


# ---- LIVE STATUS HELPERS -------------------------------------------

def save_db_live_status(symbol: str, status_data: dict) -> None:
    symbol_clean = symbol.strip().upper()
    with Session(engine) as session:
        item = session.get(LiveStatus, symbol_clean)
        if not item:
            item = LiveStatus(symbol=symbol_clean, status_data=status_data)
            session.add(item)
        else:
            item.status_data = status_data
        session.commit()


def get_db_live_status(symbol: str) -> dict:
    symbol_clean = symbol.strip().upper()
    with Session(engine) as session:
        item = session.get(LiveStatus, symbol_clean)
        if item and item.status_data:
            val = item.status_data
            return json.loads(val) if isinstance(val, str) else val
    return {}


# ---- ORDERS HELPERS ------------------------------------------------

def record_db_order(symbol: str, order_info: dict) -> None:
    symbol_clean = symbol.strip().upper()
    order_obj = OrderModel(
        symbol=symbol_clean,
        trade_id=str(order_info.get("trade_id", "")),
        order_id=str(order_info.get("order_id") or "") if order_info.get("order_id") else None,
        algo_id=str(order_info.get("algo_id") or "") if order_info.get("algo_id") else None,
        client_order_id=str(order_info.get("client_order_id") or ""),
        client_algo_id=str(order_info.get("client_algo_id") or ""),
        side=order_info.get("side"),
        order_type=order_info.get("order_type"),
        purpose=order_info.get("purpose", "ORDER"),
        price=float(order_info.get("price", 0.0) or 0.0),
        stop_price=float(order_info.get("stop_price", 0.0) or 0.0),
        quantity=float(order_info.get("quantity", 0.0) or 0.0),
        executed_qty=float(order_info.get("executed_qty", 0.0) or 0.0),
        status=str(order_info.get("status", "NEW")),
        reduce_only=bool(order_info.get("reduce_only", False)),
        working_type=str(order_info.get("working_type", "CONTRACT_PRICE")),
        order_data=order_info.get("order_data", order_info)
    )

    with Session(engine) as session:
        session.add(order_obj)
        session.commit()


def update_db_order_status(order_ref: str, status: str, executed_qty: Optional[float] = None) -> None:
    ref_str = str(order_ref)
    with Session(engine) as session:
        stmt = select(OrderModel).where(
            or_(
                OrderModel.order_id == ref_str,
                OrderModel.algo_id == ref_str,
                OrderModel.client_order_id == ref_str,
                OrderModel.client_algo_id == ref_str
            )
        )
        orders = session.scalars(stmt).all()
        for o in orders:
            o.status = status
            if executed_qty is not None:
                o.executed_qty = float(executed_qty)
        session.commit()


def get_db_orders(symbol: str, limit: int = 100) -> List[dict]:
    symbol_clean = symbol.strip().upper()
    with Session(engine) as session:
        stmt = select(OrderModel).where(OrderModel.symbol == symbol_clean).order_by(OrderModel.id.desc()).limit(limit)
        results = session.scalars(stmt).all()

        orders = []
        for r in results:
            orders.append({
                "id": r.id, "symbol": r.symbol, "trade_id": r.trade_id, "order_id": r.order_id,
                "algo_id": r.algo_id, "client_order_id": r.client_order_id, "side": r.side,
                "order_type": r.order_type, "purpose": r.purpose, "price": r.price,
                "stop_price": r.stop_price, "quantity": r.quantity, "executed_qty": r.executed_qty,
                "status": r.status, "reduce_only": r.reduce_only,
                "created_at": str(r.created_at), "updated_at": str(r.updated_at)
            })
        return orders


# ---- TRADES HELPERS ------------------------------------------------

def record_db_trade(symbol: str, trade_info: dict) -> None:
    symbol_clean = symbol.strip().upper()
    tid = str(trade_info.get("trade_id"))

    with Session(engine) as session:
        stmt = select(TradeModel).where(TradeModel.trade_id == tid)
        trade_obj = session.scalars(stmt).first()

        entry_t = trade_info.get("entry_time")
        exit_t = trade_info.get("exit_time")

        if not trade_obj:
            trade_obj = TradeModel(
                trade_id=tid,
                symbol=symbol_clean,
                direction=str(trade_info.get("direction")),
                entry_time=entry_t if isinstance(entry_t, datetime) else None,
                exit_time=exit_t if isinstance(exit_t, datetime) else None,
                entry_price=float(trade_info.get("entry_price", 0.0) or 0.0),
                exit_price=float(trade_info.get("exit_price", 0.0) or 0.0),
                quantity=float(trade_info.get("quantity", 0.0) or 0.0),
                leverage=int(trade_info.get("leverage", 10)),
                margin_used=float(trade_info.get("margin_used", 0.0) or 0.0),
                trend_aligned=bool(trade_info.get("trend_aligned", True)),
                atr_at_signal=float(trade_info.get("atr_at_signal", 0.0) or 0.0),
                tp_levels_hit=int(trade_info.get("tp_levels_hit", 0)),
                gross_pnl=float(trade_info.get("gross_pnl", 0.0) or 0.0),
                estimated_fees=float(trade_info.get("estimated_fees", 0.0) or 0.0),
                realized_pnl=float(trade_info.get("realized_pnl", 0.0) or 0.0),
                return_pct=float(trade_info.get("return_pct", 0.0) or 0.0),
                close_reason=str(trade_info.get("close_reason", "IN_PROGRESS")),
                trade_data=trade_info.get("trade_data", trade_info)
            )
            session.add(trade_obj)
        else:
            if exit_t:
                trade_obj.exit_time = exit_t if isinstance(exit_t, datetime) else None
            trade_obj.exit_price = float(trade_info.get("exit_price", trade_obj.exit_price or 0.0))
            trade_obj.quantity = float(trade_info.get("quantity", trade_obj.quantity or 0.0))
            trade_obj.tp_levels_hit = int(trade_info.get("tp_levels_hit", trade_obj.tp_levels_hit or 0))
            trade_obj.gross_pnl = float(trade_info.get("gross_pnl", trade_obj.gross_pnl or 0.0))
            trade_obj.estimated_fees = float(trade_info.get("estimated_fees", trade_obj.estimated_fees or 0.0))
            trade_obj.realized_pnl = float(trade_info.get("realized_pnl", trade_obj.realized_pnl or 0.0))
            trade_obj.return_pct = float(trade_info.get("return_pct", trade_obj.return_pct or 0.0))
            trade_obj.close_reason = str(trade_info.get("close_reason", trade_obj.close_reason))
            trade_obj.trade_data = trade_info.get("trade_data", trade_obj.trade_data)

        session.commit()


def get_db_trades(symbol: str, limit: int = 100) -> List[dict]:
    symbol_clean = symbol.strip().upper()
    with Session(engine) as session:
        stmt = select(TradeModel).where(TradeModel.symbol == symbol_clean).order_by(TradeModel.id.desc()).limit(limit)
        results = session.scalars(stmt).all()

        trades = []
        for r in results:
            trades.append({
                "trade_id": r.trade_id, "symbol": r.symbol, "direction": r.direction,
                "entry_time": str(r.entry_time) if r.entry_time else None,
                "exit_time": str(r.exit_time) if r.exit_time else None,
                "entry_price": r.entry_price, "exit_price": r.exit_price, "quantity": r.quantity,
                "leverage": r.leverage, "margin_used": r.margin_used, "trend_aligned": r.trend_aligned,
                "atr_at_signal": r.atr_at_signal, "tp_levels_hit": r.tp_levels_hit, "gross_pnl": r.gross_pnl,
                "estimated_fees": r.estimated_fees, "realized_pnl": r.realized_pnl, "return_pct": r.return_pct,
                "close_reason": r.close_reason
            })
        return trades


def get_db_trade_summary(symbol: str) -> dict:
    symbol_clean = symbol.strip().upper()
    with Session(engine) as session:
        stmt = select(
            func.count(TradeModel.id),
            func.sum(case((TradeModel.realized_pnl > 0, 1), else_=0)),
            func.sum(case((TradeModel.realized_pnl <= 0, 1), else_=0)),
            func.sum(TradeModel.realized_pnl),
            func.sum(TradeModel.estimated_fees),
            func.avg(TradeModel.realized_pnl)
        ).where((TradeModel.symbol == symbol_clean) & (TradeModel.close_reason != "IN_PROGRESS"))
        
        res = session.execute(stmt).fetchone()

        if not res or res[0] == 0:
            return {"total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "total_pnl": 0.0, "total_fees": 0.0, "avg_pnl": 0.0}

        total = res[0] or 0
        wins = res[1] or 0
        losses = res[2] or 0
        win_rate = round((wins / total) * 100.0, 2) if total > 0 else 0.0
        return {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "total_pnl": round(float(res[3] or 0.0), 4),
            "total_fees": round(float(res[4] or 0.0), 4),
            "avg_pnl": round(float(res[5] or 0.0), 4)
        }


# ---- SIGNALS HELPERS -----------------------------------------------

def record_db_signal(symbol: str, signal_info: dict) -> None:
    symbol_clean = symbol.strip().upper()
    ctime = signal_info.get("candle_time")
    
    sig_obj = SignalHistoryModel(
        symbol=symbol_clean,
        candle_time=ctime if isinstance(ctime, datetime) else None,
        ha_open=float(signal_info.get("ha_open", 0.0) or 0.0),
        ha_close=float(signal_info.get("ha_close", 0.0) or 0.0),
        ha_high=float(signal_info.get("ha_high", 0.0) or 0.0),
        ha_low=float(signal_info.get("ha_low", 0.0) or 0.0),
        alma=float(signal_info.get("alma", 0.0) or 0.0),
        rsi=float(signal_info.get("rsi", 0.0) or 0.0),
        rsi_sma=float(signal_info.get("rsi_sma", 0.0) or 0.0),
        atr=float(signal_info.get("atr", 0.0) or 0.0),
        adx=float(signal_info.get("adx", 0.0) or 0.0) if signal_info.get("adx") is not None else None,
        trend_sma=float(signal_info.get("trend_sma", 0.0) or 0.0),
        signal=str(signal_info.get("signal", "NONE")),
        decision=str(signal_info.get("decision", "NONE")),
        executed=bool(signal_info.get("executed", False))
    )

    with Session(engine) as session:
        session.add(sig_obj)
        session.commit()


def get_db_signals(symbol: str, limit: int = 100) -> List[dict]:
    symbol_clean = symbol.strip().upper()
    with Session(engine) as session:
        stmt = select(SignalHistoryModel).where(SignalHistoryModel.symbol == symbol_clean).order_by(SignalHistoryModel.id.desc()).limit(limit)
        results = session.scalars(stmt).all()

        signals = []
        for r in results:
            signals.append({
                "candle_time": str(r.candle_time) if r.candle_time else None,
                "ha_open": r.ha_open, "ha_close": r.ha_close,
                "alma": r.alma, "rsi": r.rsi, "rsi_sma": r.rsi_sma, "atr": r.atr,
                "adx": r.adx, "trend_sma": r.trend_sma, "signal": r.signal,
                "decision": r.decision, "executed": bool(r.executed), "created_at": str(r.created_at)
            })
        return signals


# ---- LOGS HELPERS --------------------------------------------------

def insert_db_log(symbol: str, level: str, message: str) -> None:
    symbol_clean = symbol.strip().upper()
    log_obj = BotLogModel(
        symbol=symbol_clean,
        level=level.upper(),
        message=message
    )
    with Session(engine) as session:
        session.add(log_obj)
        session.commit()


def get_db_logs(symbol: str, limit: int = 200) -> List[str]:
    symbol_clean = symbol.strip().upper()
    with Session(engine) as session:
        stmt = select(BotLogModel).where(BotLogModel.symbol == symbol_clean).order_by(BotLogModel.id.desc()).limit(limit)
        results = session.scalars(stmt).all()

        logs = []
        for r in reversed(results):  # return chronological order
            ts_str = str(r.timestamp).split('.')[0] if r.timestamp else ""
            logs.append(f"{ts_str} | {r.level} | {r.message}")
        return logs


# Auto-initialize database tables on import via SQLAlchemy ORM
try:
    init_db()
except Exception as e:
    logger.error(f"Failed to auto-initialize database tables via ORM: {e}")
