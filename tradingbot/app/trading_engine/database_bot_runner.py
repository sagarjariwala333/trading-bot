#!/usr/bin/env python3
"""
Database-first trading bot runner.

This version removes all file I/O operations and uses database-only storage.
"""

import os
import logging
import time
from datetime import datetime
from typing import Dict, Any

from app.services.database_service import db_service
from app.core.config import settings

def setup_logging(symbol: str):
    """Set up database logging for the bot."""
    logger = logging.getLogger("ha_alma_bot")
    logger.setLevel(logging.INFO)
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create custom handler that logs to database
    class DatabaseLogHandler(logging.Handler):
        def __init__(self, symbol: str):
            super().__init__()
            self.symbol = symbol
        
        def emit(self, record):
            try:
                message = self.format(record)
                db_service.log_event(
                    level=record.levelname,
                    message=message,
                    symbol=self.symbol,
                    logger_name=record.name
                )
            except:
                pass  # Don't crash on logging errors
    
    handler = DatabaseLogHandler(symbol)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger

def get_symbol_from_env() -> str:
    """Get symbol from environment variable."""
    symbol = os.environ.get("BOT_SYMBOL")
    if not symbol:
        raise ValueError("BOT_SYMBOL environment variable must be set")
    return symbol.strip().upper()

def run_bot_instance():
    """Run a single bot instance using database storage."""
    symbol = get_symbol_from_env()
    logger = setup_logging(symbol)
    
    logger.info(f"🤖 Starting database-first bot for {symbol}")
    
    # Load configuration from database
    config = db_service.get_bot_config(symbol)
    if not config:
        logger.error(f"No configuration found for {symbol}")
        return 1
    
    logger.info(f"📋 Loaded configuration: testnet={config.get('testnet', True)}")
    
    # Load state from database
    state = db_service.get_bot_state(symbol)
    if not state:
        # Create default state
        state = db_service._get_default_state()
        db_service.save_bot_state(symbol, state)
        logger.info("Created default bot state")
    else:
        logger.info(f"📊 Loaded state: {state.get('status', 'UNKNOWN')}")
    
    # Mark bot as active
    db_service.set_bot_active(symbol, True)
    
    try:
        # Main bot loop would go here
        # For now, this is a placeholder that demonstrates database operations
        
        poll_seconds = config.get("poll_seconds", 15)
        logger.info(f"🔄 Starting main loop (poll every {poll_seconds}s)")
        
        iteration = 0
        while True:
            iteration += 1
            
            # Simulate bot activity
            if iteration % 10 == 0:
                logger.info(f"💓 Bot alive - iteration {iteration}")
                
                # Update state periodically
                state["last_heartbeat"] = datetime.utcnow().isoformat()
                db_service.save_bot_state(symbol, state)
            
            # Check if bot should stop (database flag)
            active_bots = db_service.get_active_bots()
            if symbol not in active_bots:
                logger.info("🛑 Bot marked as inactive in database, stopping...")
                break
            
            time.sleep(poll_seconds)
    
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Bot crashed: {e}")
        db_service.log_event("ERROR", f"Bot crashed: {e}", symbol)
        return 1
    
    finally:
        # Mark bot as inactive
        db_service.set_bot_active(symbol, False)
        logger.info("🏁 Bot shutdown complete")
    
    return 0

if __name__ == "__main__":
    exit(run_bot_instance())