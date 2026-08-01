#!/usr/bin/env python3
"""
Simple migration using raw SQL to work with existing PostgreSQL structure.
"""

import json
import logging
import sqlite3
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

# Load environment
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_postgres_engine():
    """Get PostgreSQL engine."""
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        raise ValueError("DATABASE_URL not set")
    
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    
    return create_engine(db_url)

def migrate_data():
    """Migrate data using raw SQL."""
    
    # Connect to PostgreSQL
    pg_engine = get_postgres_engine()
    
    with pg_engine.connect() as conn:
        # Test connection
        result = conn.execute(text("SELECT version()"))
        version = result.fetchone()[0]
        logger.info(f"Connected to PostgreSQL: {version[:60]}...")
    
    # Check SQLite data
    sqlite_path = Path("data/tradingbot.db")
    if not sqlite_path.exists():
        logger.info("No SQLite database found")
    else:
        logger.info("Migrating from SQLite...")
        sqlite_conn = sqlite3.connect(sqlite_path)
        
        try:
            # Get SQLite data
            cursor = sqlite_conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bot_configs'")
            if cursor.fetchone():
                cursor = sqlite_conn.execute("SELECT symbol, config_data FROM bot_configs")
                rows = cursor.fetchall()
                
                logger.info(f"Found {len(rows)} configs in SQLite")
                
                # Insert into PostgreSQL
                with pg_engine.begin() as conn:
                    for symbol, config_data in rows:
                        conn.execute(text("""
                            INSERT INTO bot_configs (symbol, config_data, updated_at)
                            VALUES (:symbol, :config, CURRENT_TIMESTAMP)
                            ON CONFLICT (symbol) DO UPDATE SET
                                config_data = EXCLUDED.config_data,
                                updated_at = CURRENT_TIMESTAMP
                        """), {"symbol": symbol, "config": config_data})
                
                logger.info(f"Migrated {len(rows)} configs to PostgreSQL")
            
            # Migrate states
            cursor = sqlite_conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bot_states'")
            if cursor.fetchone():
                cursor = sqlite_conn.execute("SELECT symbol, state_data FROM bot_states")
                rows = cursor.fetchall()
                
                logger.info(f"Found {len(rows)} states in SQLite")
                
                # Insert into PostgreSQL
                with pg_engine.begin() as conn:
                    for symbol, state_data in rows:
                        conn.execute(text("""
                            INSERT INTO bot_states (symbol, state_data, updated_at)
                            VALUES (:symbol, :state, CURRENT_TIMESTAMP)
                            ON CONFLICT (symbol) DO UPDATE SET
                                state_data = EXCLUDED.state_data,
                                updated_at = CURRENT_TIMESTAMP
                        """), {"symbol": symbol, "state": state_data})
                
                logger.info(f"Migrated {len(rows)} states to PostgreSQL")
            
        finally:
            sqlite_conn.close()
    
    # Check instance files
    instances_dir = Path("data/instances")
    if instances_dir.exists():
        logger.info("Migrating from instance files...")
        
        migrated = 0
        for symbol_dir in instances_dir.iterdir():
            if not symbol_dir.is_dir():
                continue
                
            symbol = symbol_dir.name
            
            # Migrate config
            config_file = symbol_dir / "config.json"
            if config_file.exists():
                with open(config_file, 'r') as f:
                    config_data = json.load(f)
                
                with pg_engine.begin() as conn:
                    conn.execute(text("""
                        INSERT INTO bot_configs (symbol, config_data, updated_at)
                        VALUES (:symbol, :config, CURRENT_TIMESTAMP)
                        ON CONFLICT (symbol) DO UPDATE SET
                            config_data = EXCLUDED.config_data,
                            updated_at = CURRENT_TIMESTAMP
                    """), {"symbol": symbol, "config": json.dumps(config_data)})
                
                logger.info(f"Migrated config for {symbol}")
            
            # Migrate state
            state_file = symbol_dir / "bot_state.json"
            if state_file.exists():
                with open(state_file, 'r') as f:
                    state_data = json.load(f)
                
                with pg_engine.begin() as conn:
                    conn.execute(text("""
                        INSERT INTO bot_states (symbol, state_data, updated_at)
                        VALUES (:symbol, :state, CURRENT_TIMESTAMP)
                        ON CONFLICT (symbol) DO UPDATE SET
                            state_data = EXCLUDED.state_data,
                            updated_at = CURRENT_TIMESTAMP
                    """), {"symbol": symbol, "state": json.dumps(state_data)})
                
                logger.info(f"Migrated state for {symbol}")
            
            migrated += 1
        
        logger.info(f"Processed {migrated} instances")
    
    # Verify migration
    with pg_engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM bot_configs"))
        config_count = result.fetchone()[0]
        
        result = conn.execute(text("SELECT COUNT(*) FROM bot_states"))  
        state_count = result.fetchone()[0]
        
        logger.info(f"✅ Migration complete! {config_count} configs, {state_count} states")
        
        # Show some data
        result = conn.execute(text("SELECT symbol FROM bot_configs LIMIT 5"))
        symbols = [row[0] for row in result.fetchall()]
        logger.info(f"📊 Migrated symbols: {symbols}")

if __name__ == "__main__":
    migrate_data()