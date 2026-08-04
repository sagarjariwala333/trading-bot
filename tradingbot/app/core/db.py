import json
import logging
from typing import Dict, Any
from sqlalchemy import create_engine, text
from app.core.config import settings

logger = logging.getLogger("ha_alma_bot")

def get_database_url() -> str:
    """Get the database URL, with fallback to SQLite for development."""
    db_url = settings.DATABASE_URL
    if not db_url:
        # SQLite fallback for development only
        import os
        db_dir = os.path.abspath(settings.DATA_DIR)
        os.makedirs(db_dir, exist_ok=True)
        sqlite_path = os.path.join(db_dir, "tradingbot.db")
        db_url = f"sqlite:///{sqlite_path}"
        logger.warning("Using SQLite fallback - not recommended for production")
    else:
        # Normalize postgres:// to postgresql://
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
    
    return db_url

# Create engine with optimized settings
db_url = get_database_url()
is_sqlite = db_url.startswith("sqlite")

engine_kwargs = {"pool_pre_ping": True}
if not is_sqlite:
    engine_kwargs.update({
        "pool_size": 10,
        "max_overflow": 20,
        "pool_recycle": 3600,  # Recycle connections every hour
    })

engine = create_engine(db_url, **engine_kwargs)

def init_db():
    """Initialize database tables for legacy structure."""
    json_type = "TEXT" if is_sqlite else "JSONB"
    
    with engine.begin() as conn:
        # Bot configurations table (legacy structure)
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS bot_configs (
                symbol VARCHAR(20) PRIMARY KEY,
                config_data {json_type} NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # Bot states table (legacy structure)
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS bot_states (
                symbol VARCHAR(20) PRIMARY KEY,
                state_data {json_type} NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # Active bots tracking (legacy structure)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS active_bots (
                symbol VARCHAR(20) PRIMARY KEY,
                is_running BOOLEAN NOT NULL DEFAULT FALSE,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # Add indexes for better performance (PostgreSQL only)
        if not is_sqlite:
            try:
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_bot_configs_symbol ON bot_configs(symbol)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_bot_states_symbol ON bot_states(symbol)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_active_bots_running ON active_bots(is_running)"))
            except Exception:
                pass  # Indexes might already exist
    
    logger.info("Database tables initialized successfully.")

def get_db_config(symbol: str) -> Dict[str, Any]:
    """Fetch bot configuration from the database."""
    symbol_clean = symbol.strip().upper()
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT config_data FROM bot_configs WHERE symbol = :symbol"),
            {"symbol": symbol_clean}
        ).fetchone()
        if result:
            val = result[0]
            # Handle both JSON string (SQLite) and dict (PostgreSQL JSONB)
            if isinstance(val, str):
                return json.loads(val)
            else:
                return val or {}
    return {}

def save_db_config(symbol: str, config_data: Dict[str, Any]) -> None:
    """Save/update bot configuration in the database."""
    symbol_clean = symbol.strip().upper()
    
    # Always serialize to JSON string (raw text queries require this)
    serialized = json.dumps(config_data)
    
    with engine.begin() as conn:
        res = conn.execute(text("""
            UPDATE bot_configs 
            SET config_data = :config, updated_at = CURRENT_TIMESTAMP 
            WHERE symbol = :symbol
        """), {"symbol": symbol_clean, "config": serialized})
        
        if res.rowcount == 0:
            conn.execute(text("""
                INSERT INTO bot_configs (symbol, config_data, updated_at)
                VALUES (:symbol, :config, CURRENT_TIMESTAMP)
            """), {"symbol": symbol_clean, "config": serialized})

def get_db_state(symbol: str) -> Dict[str, Any]:
    """Fetch bot state from the database."""
    symbol_clean = symbol.strip().upper()
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT state_data FROM bot_states WHERE symbol = :symbol"),
            {"symbol": symbol_clean}
        ).fetchone()
        if result:
            val = result[0]
            # Handle both JSON string (SQLite) and dict (PostgreSQL JSONB)
            if isinstance(val, str):
                return json.loads(val)
            else:
                return val or {}
    return {}

def save_db_state(symbol: str, state_data: Dict[str, Any]) -> None:
    """Save/update bot state in the database."""
    symbol_clean = symbol.strip().upper()
    
    # Always serialize to JSON string (raw text queries require this)
    serialized = json.dumps(state_data)
    status_val = state_data.get("status", "IDLE") if isinstance(state_data, dict) else "IDLE"
    
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT 1 FROM bot_states WHERE symbol = :symbol"),
            {"symbol": symbol_clean}
        ).fetchone()

        if existing:
            conn.execute(text("""
                UPDATE bot_states 
                SET state_data = :state, status = :status, updated_at = CURRENT_TIMESTAMP 
                WHERE symbol = :symbol
            """), {"symbol": symbol_clean, "state": serialized, "status": status_val})
        else:
            # Ensure foreign key requirement in PostgreSQL is met without triggering transaction aborts
            if not is_sqlite:
                has_pair = conn.execute(
                    text("SELECT 1 FROM trading_pairs WHERE symbol = :symbol"),
                    {"symbol": symbol_clean}
                ).fetchone()
                if not has_pair:
                    conn.execute(text("""
                        INSERT INTO trading_pairs (symbol, base_asset, quote_asset, is_active, created_at, updated_at)
                        VALUES (:symbol, :base, 'USDT', TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """), {"symbol": symbol_clean, "base": symbol_clean.replace("USDT", "")})

            conn.execute(text("""
                INSERT INTO bot_states (symbol, status, is_running, state_data, created_at, updated_at)
                VALUES (:symbol, :status, TRUE, :state, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """), {"symbol": symbol_clean, "status": status_val, "state": serialized})

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
    with engine.begin() as conn:
        res = conn.execute(text("""
            UPDATE active_bots 
            SET is_running = :is_running, updated_at = CURRENT_TIMESTAMP 
            WHERE symbol = :symbol
        """), {"symbol": symbol_clean, "is_running": is_running})
        
        if res.rowcount == 0:
            conn.execute(text("""
                INSERT INTO active_bots (symbol, is_running, updated_at)
                VALUES (:symbol, :is_running, CURRENT_TIMESTAMP)
            """), {"symbol": symbol_clean, "is_running": is_running})

# Auto-initialize database tables on import
try:
    init_db()
except Exception as e:
    logger.error(f"Failed to auto-initialize database tables: {e}")

