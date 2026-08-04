import json
import logging
import os
from sqlalchemy import create_engine, text
from app.core.config import settings

logger = logging.getLogger("ha_alma_bot")

# Resolve database URL
db_url = settings.DATABASE_URL
if not db_url:
    # Use SQLite fallback
    db_dir = os.path.abspath(settings.DATA_DIR)
    os.makedirs(db_dir, exist_ok=True)
    sqlite_path = os.path.join(db_dir, "tradingbot.db")
    db_url = f"sqlite:///{sqlite_path}"
else:
    # Render and some providers use "postgres://", but SQLAlchemy requires "postgresql://"
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

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
    
    with engine.begin() as conn:
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

        # Ensure unique index exists on symbol for pre-existing tables missing primary key constraints
        try:
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_bot_configs_symbol ON bot_configs (symbol);"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_bot_states_symbol ON bot_states (symbol);"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_active_bots_symbol ON active_bots (symbol);"))
        except Exception as e:
            logger.warning(f"Could not create unique index on database tables: {e}")

    logger.info("Database tables initialized successfully.")

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

# Auto-initialize database tables on import
try:
    init_db()
except Exception as e:
    logger.error(f"Failed to auto-initialize database tables: {e}")

