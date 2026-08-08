import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import create_engine, text
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


def init_db():
    """Create tables if they do not exist, and ensure unique indexes exist."""
    is_sqlite = db_url.startswith("sqlite")
    json_type = "TEXT" if is_sqlite else "JSONB"
    bigint_type = "BIGINT" if is_sqlite else "BIGINT"
    real_type = "REAL" if is_sqlite else "DOUBLE PRECISION"
    float_type = "FLOAT" if is_sqlite else "DOUBLE PRECISION"
    autoincrement = "INTEGER PRIMARY KEY AUTOINCREMENT" if is_sqlite else "BIGSERIAL PRIMARY KEY"
    timestamp_type = "TIMESTAMP" if is_sqlite else "TIMESTAMP"

    with engine.begin() as conn:
        if is_sqlite:
            conn.execute(text("PRAGMA journal_mode=WAL;"))

        # Create configs table
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS bot_configs (
                symbol VARCHAR(20) PRIMARY KEY,
                config_data {json_type} NOT NULL
            )
        """))

        # Create states table
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS bot_states (
                symbol VARCHAR(20) PRIMARY KEY,
                state_data {json_type} NOT NULL
            )
        """))

        # Create active bots table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS active_bots (
                symbol VARCHAR(20) PRIMARY KEY,
                is_running BOOLEAN NOT NULL DEFAULT FALSE
            )
        """))

        # Live status snapshots written every poll cycle by the running bot
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS bot_live_status (
                symbol VARCHAR(20) PRIMARY KEY,
                status_data {json_type} NOT NULL,
                updated_at {timestamp_type} NOT NULL
            )
        """))

        # Market datasets (one row per symbol+interval pair, name mirrors the old filename)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS datasets (
                name VARCHAR(100) PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                interval VARCHAR(10) NOT NULL,
                rows_count BIGINT NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_datasets_symbol_interval ON datasets (symbol, interval);"
        ))

        # Historical klines stored per symbol+interval, keyed by candle open time
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS kline_data (
                symbol VARCHAR(20) NOT NULL,
                interval VARCHAR(10) NOT NULL,
                open_time {bigint_type} NOT NULL,
                open {float_type} NOT NULL,
                high {float_type} NOT NULL,
                low {float_type} NOT NULL,
                close {float_type} NOT NULL,
                close_time {bigint_type} NOT NULL,
                PRIMARY KEY (symbol, interval, open_time)
            )
        """))

        # Log lines persisted so the dashboard can tail them without any log files
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS bot_logs (
                id {autoincrement},
                symbol VARCHAR(20) NOT NULL,
                ts {real_type} NOT NULL,
                level VARCHAR(10) NOT NULL,
                message TEXT NOT NULL
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_bot_logs_symbol_ts ON bot_logs (symbol, ts);"))

        # Ensure unique index exists on symbol for pre-existing tables missing primary key constraints
        try:
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_bot_configs_symbol ON bot_configs (symbol);"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_bot_states_symbol ON bot_states (symbol);"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_active_bots_symbol ON active_bots (symbol);"))
        except Exception as e:
            logger.warning(f"Could not create unique index on database tables: {e}")

    logger.info("Database tables initialized successfully.")


# ---------------------------------------------------------------------------
# Bot configs
# ---------------------------------------------------------------------------

def get_db_config(symbol: str) -> dict:
    """Fetch bot configuration from the database."""
    symbol_clean = symbol.strip().upper()
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT config_data FROM bot_configs WHERE symbol = :symbol"),
            {"symbol": symbol_clean}
        ).fetchone()
        if result:
            val = result[0]
            return json.loads(val) if isinstance(val, str) else val
    return {}

def save_db_config(symbol: str, config_data: dict) -> None:
    """Save/update bot configuration in the database."""
    symbol_clean = symbol.strip().upper()
    is_sqlite = db_url.startswith("sqlite")
    serialized = json.dumps(config_data)

    with engine.begin() as conn:
        try:
            if is_sqlite:
                conn.execute(text("""
                    INSERT INTO bot_configs (symbol, config_data)
                    VALUES (:symbol, :config)
                    ON CONFLICT(symbol) DO UPDATE SET config_data = :config
                """), {"symbol": symbol_clean, "config": serialized})
            else:
                conn.execute(text("""
                    INSERT INTO bot_configs (symbol, config_data)
                    VALUES (:symbol, :config)
                    ON CONFLICT(symbol) DO UPDATE SET config_data = EXCLUDED.config_data
                """), {"symbol": symbol_clean, "config": serialized})
        except Exception:
            # Fallback if ON CONFLICT fails due to missing constraint
            res = conn.execute(text("""
                UPDATE bot_configs SET config_data = :config WHERE symbol = :symbol
            """), {"symbol": symbol_clean, "config": serialized})
            if res.rowcount == 0:
                conn.execute(text("""
                    INSERT INTO bot_configs (symbol, config_data) VALUES (:symbol, :config)
                """), {"symbol": symbol_clean, "config": serialized})


# ---------------------------------------------------------------------------
# Bot states
# ---------------------------------------------------------------------------

def get_db_state(symbol: str) -> dict:
    """Fetch bot state from the database."""
    symbol_clean = symbol.strip().upper()
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT state_data FROM bot_states WHERE symbol = :symbol"),
            {"symbol": symbol_clean}
        ).fetchone()
        if result:
            val = result[0]
            return json.loads(val) if isinstance(val, str) else val
    return {}

def save_db_state(symbol: str, state_data: dict) -> None:
    """Save/update bot state in the database."""
    symbol_clean = symbol.strip().upper()
    is_sqlite = db_url.startswith("sqlite")
    serialized = json.dumps(state_data)

    with engine.begin() as conn:
        try:
            if is_sqlite:
                conn.execute(text("""
                    INSERT INTO bot_states (symbol, state_data)
                    VALUES (:symbol, :state)
                    ON CONFLICT(symbol) DO UPDATE SET state_data = :state
                """), {"symbol": symbol_clean, "state": serialized})
            else:
                conn.execute(text("""
                    INSERT INTO bot_states (symbol, state_data)
                    VALUES (:symbol, :state)
                    ON CONFLICT(symbol) DO UPDATE SET state_data = EXCLUDED.state_data
                """), {"symbol": symbol_clean, "state": serialized})
        except Exception:
            # Fallback if ON CONFLICT fails due to missing constraint
            res = conn.execute(text("""
                UPDATE bot_states SET state_data = :state WHERE symbol = :symbol
            """), {"symbol": symbol_clean, "state": serialized})
            if res.rowcount == 0:
                conn.execute(text("""
                    INSERT INTO bot_states (symbol, state_data) VALUES (:symbol, :state)
                """), {"symbol": symbol_clean, "state": serialized})


# ---------------------------------------------------------------------------
# Live status snapshots
# ---------------------------------------------------------------------------

def get_db_live_status(symbol: str) -> dict:
    """Fetch the latest live status snapshot for a bot from the database."""
    symbol_clean = symbol.strip().upper()
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT status_data FROM bot_live_status WHERE symbol = :symbol"),
            {"symbol": symbol_clean}
        ).fetchone()
        if result:
            val = result[0]
            return json.loads(val) if isinstance(val, str) else val
    return {}

def save_db_live_status(symbol: str, status_data: dict) -> None:
    """Save/update the live status snapshot for a bot in the database."""
    symbol_clean = symbol.strip().upper()
    is_sqlite = db_url.startswith("sqlite")
    serialized = json.dumps(status_data)
    now = "datetime('now')" if is_sqlite else "CURRENT_TIMESTAMP"

    with engine.begin() as conn:
        try:
            if is_sqlite:
                conn.execute(text(f"""
                    INSERT INTO bot_live_status (symbol, status_data, updated_at)
                    VALUES (:symbol, :status, {now})
                    ON CONFLICT(symbol) DO UPDATE SET status_data = :status, updated_at = {now}
                """), {"symbol": symbol_clean, "status": serialized})
            else:
                conn.execute(text("""
                    INSERT INTO bot_live_status (symbol, status_data, updated_at)
                    VALUES (:symbol, :status, CURRENT_TIMESTAMP)
                    ON CONFLICT(symbol) DO UPDATE SET status_data = EXCLUDED.status_data, updated_at = EXCLUDED.updated_at
                """), {"symbol": symbol_clean, "status": serialized})
        except Exception:
            # Fallback if ON CONFLICT fails due to missing constraint
            res = conn.execute(text(f"""
                UPDATE bot_live_status SET status_data = :status, updated_at = {now} WHERE symbol = :symbol
            """), {"symbol": symbol_clean, "status": serialized})
            if res.rowcount == 0:
                conn.execute(text(f"""
                    INSERT INTO bot_live_status (symbol, status_data, updated_at) VALUES (:symbol, :status, {now})
                """), {"symbol": symbol_clean, "status": serialized})

def delete_db_live_status(symbol: str) -> None:
    """Remove the live status snapshot for a bot."""
    symbol_clean = symbol.strip().upper()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM bot_live_status WHERE symbol = :symbol"), {"symbol": symbol_clean})


# ---------------------------------------------------------------------------
# Active bots registry
# ---------------------------------------------------------------------------

def get_active_bots() -> list:
    """Get list of symbols that should be actively running."""
    with engine.connect() as conn:
        results = conn.execute(
            text("SELECT symbol FROM active_bots WHERE is_running = TRUE")
        ).fetchall()
        return [row[0] for row in results]

def set_bot_active_status(symbol: str, is_running: bool) -> None:
    """Set running status for a bot in active_bots table."""
    symbol_clean = symbol.strip().upper()
    is_sqlite = db_url.startswith("sqlite")
    with engine.begin() as conn:
        try:
            if is_sqlite:
                conn.execute(text("""
                    INSERT INTO active_bots (symbol, is_running)
                    VALUES (:symbol, :is_running)
                    ON CONFLICT(symbol) DO UPDATE SET is_running = :is_running
                """), {"symbol": symbol_clean, "is_running": is_running})
            else:
                conn.execute(text("""
                    INSERT INTO active_bots (symbol, is_running)
                    VALUES (:symbol, :is_running)
                    ON CONFLICT(symbol) DO UPDATE SET is_running = EXCLUDED.is_running
                """), {"symbol": symbol_clean, "is_running": is_running})
        except Exception:
            # Fallback if ON CONFLICT fails due to missing constraint
            res = conn.execute(text("""
                UPDATE active_bots SET is_running = :is_running WHERE symbol = :symbol
            """), {"symbol": symbol_clean, "is_running": is_running})
            if res.rowcount == 0:
                conn.execute(text("""
                    INSERT INTO active_bots (symbol, is_running) VALUES (:symbol, :is_running)
                """), {"symbol": symbol_clean, "is_running": is_running})


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
    is_sqlite = db_url.startswith("sqlite")

    with engine.begin() as conn:
        # Remove any pre-existing rows for this symbol+interval (fresh replace semantics)
        conn.execute(text("DELETE FROM kline_data WHERE symbol = :symbol AND interval = :interval"),
                     {"symbol": symbol_clean, "interval": interval})

        if rows:
            if is_sqlite:
                conn.execute(text("""
                    INSERT INTO kline_data (symbol, interval, open_time, open, high, low, close, close_time)
                    VALUES (:symbol, :interval, :open_time, :open, :high, :low, :close, :close_time)
                    ON CONFLICT(symbol, interval, open_time) DO UPDATE SET
                        open = excluded.open,
                        high = excluded.high,
                        low = excluded.low,
                        close = excluded.close,
                        close_time = excluded.close_time
                """), [{
                    "symbol": symbol_clean,
                    "interval": interval,
                    "open_time": int(r["open_time"]),
                    "open": float(r["open"]),
                    "high": float(r["high"]),
                    "low": float(r["low"]),
                    "close": float(r["close"]),
                    "close_time": int(r["close_time"]),
                } for r in rows])
            else:
                conn.execute(text("""
                    INSERT INTO kline_data (symbol, interval, open_time, open, high, low, close, close_time)
                    VALUES (:symbol, :interval, :open_time, :open, :high, :low, :close, :close_time)
                    ON CONFLICT (symbol, interval, open_time) DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        close_time = EXCLUDED.close_time
                """), [{
                    "symbol": symbol_clean,
                    "interval": interval,
                    "open_time": int(r["open_time"]),
                    "open": float(r["open"]),
                    "high": float(r["high"]),
                    "low": float(r["low"]),
                    "close": float(r["close"]),
                    "close_time": int(r["close_time"]),
                } for r in rows])

        # Upsert the dataset metadata row
        rows_count = len(rows)
        if is_sqlite:
            conn.execute(text("""
                INSERT INTO datasets (name, symbol, interval, rows_count, created_at)
                VALUES (:name, :symbol, :interval, :rows_count, datetime('now'))
                ON CONFLICT(name) DO UPDATE SET
                    symbol = :symbol, interval = :interval, rows_count = :rows_count, created_at = datetime('now')
            """), {"name": name_clean, "symbol": symbol_clean, "interval": interval, "rows_count": rows_count})
        else:
            conn.execute(text("""
                INSERT INTO datasets (name, symbol, interval, rows_count, created_at)
                VALUES (:name, :symbol, :interval, :rows_count, CURRENT_TIMESTAMP)
                ON CONFLICT (name) DO UPDATE SET
                    symbol = EXCLUDED.symbol, interval = EXCLUDED.interval,
                    rows_count = EXCLUDED.rows_count, created_at = EXCLUDED.created_at
            """), {"name": name_clean, "symbol": symbol_clean, "interval": interval, "rows_count": rows_count})

    return rows_count

def get_kline_dataset(symbol: str, interval: str, limit: int = 0) -> List[dict]:
    """Fetch klines for a symbol+interval, oldest first. If limit>0, fetch the last `limit` rows."""
    symbol_clean = symbol.strip().upper()
    with engine.connect() as conn:
        if limit and limit > 0:
            rows = conn.execute(text("""
                SELECT open_time, open, high, low, close, close_time
                FROM kline_data
                WHERE symbol = :symbol AND interval = :interval
                ORDER BY open_time DESC
                LIMIT :limit
            """), {"symbol": symbol_clean, "interval": interval, "limit": limit}).fetchall()
            rows = list(reversed(rows))
        else:
            rows = conn.execute(text("""
                SELECT open_time, open, high, low, close, close_time
                FROM kline_data
                WHERE symbol = :symbol AND interval = :interval
                ORDER BY open_time ASC
            """), {"symbol": symbol_clean, "interval": interval}).fetchall()

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
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM kline_data WHERE symbol = :symbol AND interval = :interval"),
                     {"symbol": symbol_clean, "interval": interval})
        conn.execute(text("DELETE FROM datasets WHERE symbol = :symbol AND interval = :interval"),
                     {"symbol": symbol_clean, "interval": interval})

def list_kline_datasets() -> List[dict]:
    """List all stored datasets with metadata (name, symbol, interval, rows_count, created_at)."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT name, symbol, interval, rows_count, created_at
            FROM datasets
            ORDER BY name ASC
        """)).fetchall()
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
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT name, symbol, interval, rows_count, created_at FROM datasets WHERE name = :name"),
            {"name": name.strip()}
        ).fetchone()
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
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO bot_logs (symbol, ts, level, message) VALUES (:symbol, :ts, :level, :message)"),
            [{"symbol": symbol_clean, "ts": ts, "level": level, "message": msg} for ts, level, msg in lines],
        )
        conn.execute(text("""
            DELETE FROM bot_logs WHERE symbol = :symbol AND id NOT IN (
                SELECT id FROM bot_logs WHERE symbol = :symbol ORDER BY id DESC LIMIT 50000
            )
        """), {"symbol": symbol_clean})

def get_log_lines(symbol: str, n: int = 50) -> List[str]:
    """Return the last `n` log lines for a symbol, formatted like the old file lines."""
    symbol_clean = symbol.strip().upper()
    if n <= 0:
        return []
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT ts, level, message FROM bot_logs
            WHERE symbol = :symbol
            ORDER BY id DESC LIMIT :n
        """), {"symbol": symbol_clean, "n": n}).fetchall()
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
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM bot_logs WHERE symbol = :symbol"), {"symbol": symbol_clean})


# Auto-initialize database tables on import
try:
    init_db()
except Exception as e:
    logger.error(f"Failed to auto-initialize database tables: {e}")
