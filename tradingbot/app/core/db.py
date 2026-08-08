import logging
import os
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Double,
    Float,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    delete,
    inspect,
    insert,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import settings, PROJECT_ROOT

logger = logging.getLogger("ha_alma_bot")

# Resolve database URL. Relative sqlite paths are anchored at the project root so the
# API process and the bot subprocess always open the SAME database file regardless of CWD.
db_url = settings.DATABASE_URL
if db_url:
    if db_url.startswith("sqlite:///"):
        path_part = db_url[len("sqlite:///"):]
        if not os.path.isabs(path_part):
            db_url = f"sqlite:///{os.path.abspath(os.path.join(PROJECT_ROOT, path_part))}"
    elif db_url.startswith("postgres://"):
        # Render and some providers use "postgres://", but SQLAlchemy requires "postgresql://"
        db_url = db_url.replace("postgres://", "postgresql://", 1)
else:
    # No DATABASE_URL configured: use a sqlite file in DATA_DIR
    os.makedirs(settings.DATA_DIR, exist_ok=True)
    sqlite_path = os.path.join(settings.DATA_DIR, "tradingbot.db")
    db_url = f"sqlite:///{sqlite_path}"

# Create engine
engine = create_engine(
    db_url,
    pool_pre_ping=True,
    # SQLite doesn't support pool size or overflow parameters
    **({"pool_size": 5, "max_overflow": 10} if not db_url.startswith("sqlite") else {})
)

# JSON columns use JSONB on PostgreSQL and plain JSON (TEXT affinity) on SQLite.
JsonType = JSON().with_variant(JSONB(), "postgresql")
# Real-valued columns: DOUBLE PRECISION on PostgreSQL, REAL-affinity float on SQLite.
FloatType = Float().with_variant(Double(), "postgresql")


class Base(DeclarativeBase):
    pass


class BotConfig(Base):
    __tablename__ = "bot_configs"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    config_data: Mapped[dict] = mapped_column(JsonType, nullable=False)


class BotState(Base):
    __tablename__ = "bot_states"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    state_data: Mapped[dict] = mapped_column(JsonType, nullable=False)


class ActiveBot(Base):
    __tablename__ = "active_bots"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    is_running: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class BotLiveStatus(Base):
    __tablename__ = "bot_live_status"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    status_data: Mapped[dict] = mapped_column(JsonType, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (Index("idx_datasets_symbol_interval", "symbol", "interval"),)

    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    interval: Mapped[str] = mapped_column(String(10), nullable=False)
    rows_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class KlineData(Base):
    __tablename__ = "kline_data"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    interval: Mapped[str] = mapped_column(String(10), primary_key=True)
    open_time: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    open: Mapped[float] = mapped_column(FloatType, nullable=False)
    high: Mapped[float] = mapped_column(FloatType, nullable=False)
    low: Mapped[float] = mapped_column(FloatType, nullable=False)
    close: Mapped[float] = mapped_column(FloatType, nullable=False)
    close_time: Mapped[int] = mapped_column(BigInteger, nullable=False)


class BotLog(Base):
    __tablename__ = "bot_logs"
    __table_args__ = (Index("idx_bot_logs_symbol_ts", "symbol", "ts"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    ts: Mapped[float] = mapped_column(FloatType, nullable=False)
    level: Mapped[str] = mapped_column(String(10), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def _migrate_legacy_schema(conn) -> None:
    """Reconcile pre-existing tables from an older app schema with the current ORM models.

    Base.metadata.create_all() leaves existing tables untouched, so a legacy PostgreSQL
    database created by an earlier version of the app may not match the current column
    layout. The notable drift is bot_logs: it stored log timestamps in a TIMESTAMP column
    named `timestamp` where the current schema expects `ts` (epoch seconds as DOUBLE
    PRECISION). The migration is idempotent and a no-op on fresh databases.
    """
    inspector = inspect(conn)

    # bot_logs: legacy 'timestamp' (TIMESTAMP) -> 'ts' (DOUBLE PRECISION epoch seconds)
    if "bot_logs" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("bot_logs")}
        if "ts" not in cols and "timestamp" in cols:
            conn.execute(text('ALTER TABLE bot_logs RENAME COLUMN "timestamp" TO ts;'))
            # The legacy column carries a CURRENT_TIMESTAMP default that cannot be cast
            # to DOUBLE PRECISION, and the app always supplies `ts` explicitly anyway.
            conn.execute(text("ALTER TABLE bot_logs ALTER COLUMN ts DROP DEFAULT;"))
            conn.execute(text(
                "ALTER TABLE bot_logs ALTER COLUMN ts TYPE DOUBLE PRECISION USING EXTRACT(EPOCH FROM ts);"
            ))
            logger.info("Migrated legacy bot_logs: renamed 'timestamp' to 'ts' (epoch seconds).")

    # Ensure the symbol-keyed tables have a PRIMARY KEY on symbol so ORM merge() works.
    for table in ("bot_configs", "bot_states", "active_bots", "bot_live_status"):
        if table not in inspector.get_table_names():
            continue
        if inspector.get_pk_constraint(table)["constrained_columns"]:
            continue
        cols = {c["name"] for c in inspector.get_columns(table)}
        if "symbol" not in cols:
            continue
        try:
            conn.execute(text(f"ALTER TABLE {table} ADD PRIMARY KEY (symbol);"))
            logger.info(f"Migrated legacy {table}: added PRIMARY KEY (symbol).")
        except Exception as e:
            logger.warning(f"Could not add PRIMARY KEY to {table}: {e}")


def init_db():
    """Create tables if they do not exist, and ensure unique indexes exist."""
    is_sqlite = db_url.startswith("sqlite")

    with engine.begin() as conn:
        if is_sqlite:
            conn.execute(text("PRAGMA journal_mode=WAL;"))
        Base.metadata.create_all(conn)
        if not is_sqlite:
            _migrate_legacy_schema(conn)

    # Ensure unique index exists on symbol for pre-existing tables missing primary key constraints
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_bot_configs_symbol ON bot_configs (symbol);"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_bot_states_symbol ON bot_states (symbol);"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_active_bots_symbol ON active_bots (symbol);"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_bot_logs_symbol_ts ON bot_logs (symbol, ts);"))
    except Exception as e:
        logger.warning(f"Could not create unique index on database tables: {e}")

    logger.info("Database tables initialized successfully.")


# ---------------------------------------------------------------------------
# Bot configs
# ---------------------------------------------------------------------------

def get_db_config(symbol: str) -> dict:
    """Fetch bot configuration from the database."""
    symbol_clean = symbol.strip().upper()
    with SessionLocal() as session:
        row = session.get(BotConfig, symbol_clean)
        if row:
            return row.config_data or {}
    return {}


def save_db_config(symbol: str, config_data: dict) -> None:
    """Save/update bot configuration in the database."""
    symbol_clean = symbol.strip().upper()
    with SessionLocal() as session:
        session.merge(BotConfig(symbol=symbol_clean, config_data=config_data))
        session.commit()


# ---------------------------------------------------------------------------
# Bot states
# ---------------------------------------------------------------------------

def get_db_state(symbol: str) -> dict:
    """Fetch bot state from the database."""
    symbol_clean = symbol.strip().upper()
    with SessionLocal() as session:
        row = session.get(BotState, symbol_clean)
        if row:
            return row.state_data or {}
    return {}


def save_db_state(symbol: str, state_data: dict) -> None:
    """Save/update bot state in the database."""
    symbol_clean = symbol.strip().upper()
    with SessionLocal() as session:
        session.merge(BotState(symbol=symbol_clean, state_data=state_data))
        session.commit()


# ---------------------------------------------------------------------------
# Live status snapshots
# ---------------------------------------------------------------------------

def get_db_live_status(symbol: str) -> dict:
    """Fetch the latest live status snapshot for a bot from the database."""
    symbol_clean = symbol.strip().upper()
    with SessionLocal() as session:
        row = session.get(BotLiveStatus, symbol_clean)
        if row:
            return row.status_data or {}
    return {}


def save_db_live_status(symbol: str, status_data: dict) -> None:
    """Save/update the live status snapshot for a bot in the database."""
    symbol_clean = symbol.strip().upper()
    with SessionLocal() as session:
        session.merge(BotLiveStatus(
            symbol=symbol_clean,
            status_data=status_data,
            updated_at=datetime.now(timezone.utc),
        ))
        session.commit()


def delete_db_live_status(symbol: str) -> None:
    """Remove the live status snapshot for a bot."""
    symbol_clean = symbol.strip().upper()
    with SessionLocal() as session:
        session.execute(delete(BotLiveStatus).where(BotLiveStatus.symbol == symbol_clean))
        session.commit()


# ---------------------------------------------------------------------------
# Active bots registry
# ---------------------------------------------------------------------------

def get_active_bots() -> list:
    """Get list of symbols that should be actively running."""
    with SessionLocal() as session:
        rows = session.execute(
            select(ActiveBot.symbol).where(ActiveBot.is_running == True)  # noqa: E712
        ).scalars().all()
        return list(rows)


def set_bot_active_status(symbol: str, is_running: bool) -> None:
    """Set running status for a bot in active_bots table."""
    symbol_clean = symbol.strip().upper()
    with SessionLocal() as session:
        session.merge(ActiveBot(symbol=symbol_clean, is_running=is_running))
        session.commit()


# ---------------------------------------------------------------------------
# Market datasets & klines
# ---------------------------------------------------------------------------

def save_kline_dataset(name: str, symbol: str, interval: str, rows: List[dict]) -> int:
    """
    Persist a full market dataset. Replaces any previously stored klines for the same
    (symbol, interval) so a re-download always reflects the latest data. Returns the
    number of rows stored.
    """
    symbol_clean = symbol.strip().upper()
    name_clean = name.strip()

    with SessionLocal() as session:
        # Remove any pre-existing rows for this symbol+interval (fresh replace semantics)
        session.execute(delete(KlineData).where(
            KlineData.symbol == symbol_clean,
            KlineData.interval == interval,
        ))

        if rows:
            session.execute(
                insert(KlineData),
                [{
                    "symbol": symbol_clean,
                    "interval": interval,
                    "open_time": int(r["open_time"]),
                    "open": float(r["open"]),
                    "high": float(r["high"]),
                    "low": float(r["low"]),
                    "close": float(r["close"]),
                    "close_time": int(r["close_time"]),
                } for r in rows],
            )

        # Upsert the dataset metadata row
        rows_count = len(rows)
        session.merge(Dataset(
            name=name_clean,
            symbol=symbol_clean,
            interval=interval,
            rows_count=rows_count,
            created_at=datetime.now(timezone.utc),
        ))
        session.commit()

    return rows_count


def get_kline_dataset(symbol: str, interval: str, limit: int = 0) -> List[dict]:
    """Fetch klines for a symbol+interval, oldest first. If limit>0, fetch the last `limit` rows."""
    symbol_clean = symbol.strip().upper()

    stmt = select(
        KlineData.open_time, KlineData.open, KlineData.high,
        KlineData.low, KlineData.close, KlineData.close_time,
    ).where(
        KlineData.symbol == symbol_clean,
        KlineData.interval == interval,
    )
    if limit and limit > 0:
        stmt = stmt.order_by(KlineData.open_time.desc()).limit(limit)
    else:
        stmt = stmt.order_by(KlineData.open_time.asc())

    with SessionLocal() as session:
        rows = session.execute(stmt).all()

    if limit and limit > 0:
        rows = list(reversed(rows))

    return [
        {
            "open_time": r[0],
            "open": float(r[1]),
            "high": float(r[2]),
            "low": float(r[3]),
            "close": float(r[4]),
            "close_time": r[5],
        }
        for r in rows
    ]


def delete_kline_dataset(symbol: str, interval: str) -> None:
    """Remove a dataset and all its stored klines."""
    symbol_clean = symbol.strip().upper()
    with SessionLocal() as session:
        session.execute(delete(KlineData).where(
            KlineData.symbol == symbol_clean,
            KlineData.interval == interval,
        ))
        session.execute(delete(Dataset).where(
            Dataset.symbol == symbol_clean,
            Dataset.interval == interval,
        ))
        session.commit()


def list_kline_datasets() -> List[dict]:
    """List all stored datasets with metadata (name, symbol, interval, rows_count, created_at)."""
    with SessionLocal() as session:
        rows = session.execute(
            select(Dataset.name, Dataset.symbol, Dataset.interval,
                   Dataset.rows_count, Dataset.created_at)
            .order_by(Dataset.name.asc())
        ).all()
    return [
        {
            "name": r[0],
            "symbol": r[1],
            "interval": r[2],
            "rows_count": r[3],
            "created_at": r[4].isoformat() if hasattr(r[4], "isoformat") else str(r[4]),
        }
        for r in rows
    ]


def get_kline_dataset_meta(name: str) -> Optional[dict]:
    """Look up a single dataset by name, or return None if it does not exist."""
    with SessionLocal() as session:
        row = session.execute(
            select(Dataset.name, Dataset.symbol, Dataset.interval,
                   Dataset.rows_count, Dataset.created_at)
            .where(Dataset.name == name.strip())
        ).first()
    if not row:
        return None
    return {
        "name": row[0],
        "symbol": row[1],
        "interval": row[2],
        "rows_count": row[3],
        "created_at": row[4].isoformat() if hasattr(row[4], "isoformat") else str(row[4]),
    }


# ---------------------------------------------------------------------------
# Log lines
# ---------------------------------------------------------------------------

def append_log_lines(symbol: str, lines: List[Tuple[float, str, str]]) -> None:
    """Append log lines. Each line is a tuple of (ts_epoch_float, level, message)."""
    symbol_clean = symbol.strip().upper()
    if not lines:
        return

    with SessionLocal() as session:
        session.execute(
            insert(BotLog),
            [{"symbol": symbol_clean, "ts": ts, "level": level, "message": msg}
             for ts, level, msg in lines],
        )

        keep_ids = (
            select(BotLog.id)
            .where(BotLog.symbol == symbol_clean)
            .order_by(BotLog.id.desc())
            .limit(50000)
        )
        session.execute(delete(BotLog).where(
            BotLog.symbol == symbol_clean,
            BotLog.id.not_in(keep_ids),
        ))
        session.commit()


def get_log_lines(symbol: str, n: int = 50) -> List[str]:
    """Return the last `n` log lines for a symbol, formatted like the old file lines."""
    symbol_clean = symbol.strip().upper()
    if n <= 0:
        return []

    with SessionLocal() as session:
        rows = session.execute(
            select(BotLog.ts, BotLog.level, BotLog.message)
            .where(BotLog.symbol == symbol_clean)
            .order_by(BotLog.id.desc())
            .limit(n)
        ).all()

    lines = []
    for ts, level, message in reversed(rows):
        try:
            ts_str = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            ts_str = ""
        lines.append(f"{ts_str} | {level} | {message}")
    return lines


def clear_log_lines(symbol: str) -> None:
    """Delete all stored log lines for a symbol."""
    symbol_clean = symbol.strip().upper()
    with SessionLocal() as session:
        session.execute(delete(BotLog).where(BotLog.symbol == symbol_clean))
        session.commit()


# Auto-initialize database tables on import
try:
    init_db()
except Exception as e:
    logger.error(f"Failed to auto-initialize database tables: {e}")
