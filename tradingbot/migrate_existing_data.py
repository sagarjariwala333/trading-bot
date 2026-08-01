#!/usr/bin/env python3
"""
Simple data migration using legacy database functions.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path

# Use the legacy database functions directly
import sys
sys.path.append('.')
from app.core.db import save_db_config, save_db_state, get_db_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_from_sqlite():
    """Migrate data from SQLite to PostgreSQL using legacy functions."""
    
    # Check if SQLite database exists
    sqlite_path = Path("data/tradingbot.db")
    if not sqlite_path.exists():
        logger.info("No SQLite database found to migrate from")
        return
    
    logger.info(f"Migrating data from {sqlite_path}")
    
    # Connect to SQLite
    sqlite_conn = sqlite3.connect(sqlite_path)
    
    try:
        # Migrate bot configs
        cursor = sqlite_conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bot_configs'")
        if cursor.fetchone():
            logger.info("Migrating bot configurations...")
            
            cursor = sqlite_conn.execute("SELECT symbol, config_data FROM bot_configs")
            config_rows = cursor.fetchall()
            
            for symbol, config_data in config_rows:
                if isinstance(config_data, str):
                    config_dict = json.loads(config_data)
                else:
                    config_dict = config_data
                
                logger.info(f"Migrating config for {symbol}")
                save_db_config(symbol, config_dict)
            
            logger.info(f"Migrated {len(config_rows)} bot configurations")
        
        # Migrate bot states  
        cursor = sqlite_conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bot_states'")
        if cursor.fetchone():
            logger.info("Migrating bot states...")
            
            cursor = sqlite_conn.execute("SELECT symbol, state_data FROM bot_states")
            state_rows = cursor.fetchall()
            
            for symbol, state_data in state_rows:
                if isinstance(state_data, str):
                    state_dict = json.loads(state_data)
                else:
                    state_dict = state_data
                
                logger.info(f"Migrating state for {symbol}")
                save_db_state(symbol, state_dict)
            
            logger.info(f"Migrated {len(state_rows)} bot states")
    
    except Exception as e:
        logger.error(f"Migration error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        sqlite_conn.close()

def migrate_from_instances():
    """Migrate data from instance files using legacy functions."""
    
    instances_dir = Path("data/instances")
    if not instances_dir.exists():
        logger.info("No instances directory found")
        return
    
    logger.info(f"Migrating data from {instances_dir}")
    
    migrated_count = 0
    for symbol_dir in instances_dir.iterdir():
        if not symbol_dir.is_dir():
            continue
            
        symbol = symbol_dir.name
        logger.info(f"Checking instance data for {symbol}")
        
        try:
            # Check if config already exists in database
            existing_config = get_db_config(symbol)
            
            # Migrate config if file exists and database is empty
            config_file = symbol_dir / "config.json"
            if config_file.exists():
                with open(config_file, 'r') as f:
                    config_data = json.load(f)
                
                if not existing_config or existing_config == {}:
                    logger.info(f"Migrating config for {symbol}")
                    save_db_config(symbol, config_data)
                else:
                    logger.info(f"Config for {symbol} already exists, skipping")
            
            # Migrate state
            state_file = symbol_dir / "bot_state.json"
            if state_file.exists():
                with open(state_file, 'r') as f:
                    state_data = json.load(f)
                
                logger.info(f"Migrating state for {symbol}")
                save_db_state(symbol, state_data)
            
            migrated_count += 1
            
        except Exception as e:
            logger.error(f"Error migrating {symbol}: {e}")
            import traceback
            traceback.print_exc()
    
    logger.info(f"Processed {migrated_count} instances")

def main():
    """Run the migration."""
    logger.info("🚀 Starting data migration to PostgreSQL using legacy functions...")
    
    try:
        # Migrate from SQLite if available
        migrate_from_sqlite()
        
        # Migrate from instance files if available
        migrate_from_instances()
        
        logger.info("🎉 Migration completed successfully!")
        
        # Test that data was migrated
        logger.info("🔍 Verifying migrated data...")
        from app.core.db import get_active_bots
        active_bots = get_active_bots()
        logger.info(f"Active bots in database: {active_bots}")
        
        # Check a specific config
        test_config = get_db_config("BTCUSDT")
        if test_config:
            logger.info(f"✅ BTCUSDT config found: {test_config.get('symbol', 'N/A')}")
        else:
            logger.info("⚠️  No BTCUSDT config found")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())