#!/usr/bin/env python3
"""
Migration script to move from file-based storage to PostgreSQL.

This script:
1. Imports existing instance configs and states to database
2. Archives old CSV data files 
3. Prepares the system for full PostgreSQL usage

Usage:
    python migrate_to_postgresql.py --postgresql-url "postgresql://user:pass@localhost/tradingbot"
"""

import argparse
import json
import logging
import os
import shutil
from pathlib import Path
from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine, text

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def migrate_instance_data(source_dir: Path, engine):
    """Migrate bot instance configs and states to database."""
    logger.info(f"Migrating instance data from {source_dir}")
    
    instances_dir = source_dir / "instances"
    if not instances_dir.exists():
        logger.warning(f"No instances directory found at {instances_dir}")
        return
    
    migrated_count = 0
    for symbol_dir in instances_dir.iterdir():
        if not symbol_dir.is_dir():
            continue
            
        symbol = symbol_dir.name
        logger.info(f"Migrating {symbol}")
        
        # Migrate config
        config_file = symbol_dir / "config.json"
        if config_file.exists():
            with open(config_file, 'r') as f:
                config_data = json.load(f)
            
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO bot_configs (symbol, config_data, created_at, updated_at)
                    VALUES (:symbol, :config, :timestamp, :timestamp)
                    ON CONFLICT(symbol) DO UPDATE SET 
                        config_data = EXCLUDED.config_data,
                        updated_at = EXCLUDED.updated_at
                """), {
                    "symbol": symbol,
                    "config": json.dumps(config_data),
                    "timestamp": datetime.utcnow()
                })
        
        # Migrate state
        state_file = symbol_dir / "bot_state.json"
        if state_file.exists():
            with open(state_file, 'r') as f:
                state_data = json.load(f)
            
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO bot_states (symbol, state_data, created_at, updated_at)
                    VALUES (:symbol, :state, :timestamp, :timestamp)
                    ON CONFLICT(symbol) DO UPDATE SET 
                        state_data = EXCLUDED.state_data,
                        updated_at = EXCLUDED.updated_at
                """), {
                    "symbol": symbol,
                    "state": json.dumps(state_data),
                    "timestamp": datetime.utcnow()
                })
        
        migrated_count += 1
    
    logger.info(f"Successfully migrated {migrated_count} instances")

def migrate_csv_data(source_dir: Path, engine):
    """Migrate CSV historical data to database."""
    logger.info("Migrating CSV data to database")
    
    # Create historical_data table
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS historical_data (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                timeframe VARCHAR(10) NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                open DECIMAL(20,8) NOT NULL,
                high DECIMAL(20,8) NOT NULL,
                low DECIMAL(20,8) NOT NULL,
                close DECIMAL(20,8) NOT NULL,
                volume DECIMAL(20,8) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # Add indexes
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_historical_data_symbol_time ON historical_data(symbol, timestamp)"))
    
    archive_dir = source_dir / "archive"
    if not archive_dir.exists():
        logger.warning(f"No archive directory found at {archive_dir}")
        return
    
    migrated_files = 0
    for csv_file in archive_dir.glob("*.csv"):
        logger.info(f"Processing {csv_file.name}")
        
        try:
            # Parse filename to extract symbol and timeframe
            # Expected format: btcusdt_12h_12m.csv
            parts = csv_file.stem.split('_')
            if len(parts) >= 2:
                symbol = parts[0].upper()
                timeframe = '_'.join(parts[1:])
            else:
                symbol = csv_file.stem.upper()
                timeframe = "unknown"
            
            # Read CSV
            df = pd.read_csv(csv_file)
            
            # Assuming standard OHLCV format
            required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            if not all(col in df.columns for col in required_cols):
                logger.warning(f"Skipping {csv_file.name} - missing required columns")
                continue
            
            # Convert timestamp if needed
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Insert data in batches
            batch_size = 1000
            for i in range(0, len(df), batch_size):
                batch = df.iloc[i:i+batch_size]
                
                with engine.begin() as conn:
                    for _, row in batch.iterrows():
                        conn.execute(text("""
                            INSERT INTO historical_data 
                            (symbol, timeframe, timestamp, open, high, low, close, volume)
                            VALUES (:symbol, :timeframe, :timestamp, :open, :high, :low, :close, :volume)
                            ON CONFLICT DO NOTHING
                        """), {
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "timestamp": row['timestamp'],
                            "open": float(row['open']),
                            "high": float(row['high']),
                            "low": float(row['low']),
                            "close": float(row['close']),
                            "volume": float(row['volume'])
                        })
            
            logger.info(f"Migrated {len(df)} records from {csv_file.name}")
            migrated_files += 1
            
        except Exception as e:
            logger.error(f"Error processing {csv_file.name}: {e}")
    
    logger.info(f"Successfully migrated {migrated_files} CSV files")

def cleanup_old_files(data_dir: Path):
    """Clean up old file-based storage after successful migration."""
    logger.info("Cleaning up old files")
    
    # Move instances to backup
    instances_dir = data_dir / "instances"
    if instances_dir.exists():
        backup_dir = data_dir / "backup_instances"
        shutil.move(str(instances_dir), str(backup_dir))
        logger.info(f"Moved instances to {backup_dir}")
    
    # Remove empty datasets directory
    datasets_dir = data_dir / "datasets"
    if datasets_dir.exists() and not any(datasets_dir.iterdir()):
        datasets_dir.rmdir()
        logger.info("Removed empty datasets directory")

def main():
    parser = argparse.ArgumentParser(description="Migrate trading bot data to PostgreSQL")
    parser.add_argument("--postgresql-url", required=True, 
                       help="PostgreSQL connection URL (e.g., postgresql://user:pass@localhost/tradingbot)")
    parser.add_argument("--data-dir", default="data", 
                       help="Path to data directory (default: data)")
    parser.add_argument("--cleanup", action="store_true", 
                       help="Clean up old files after migration")
    
    args = parser.parse_args()
    
    # Validate PostgreSQL connection
    try:
        engine = create_engine(args.postgresql_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("PostgreSQL connection successful")
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}")
        return 1
    
    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        logger.error(f"Data directory {data_dir} does not exist")
        return 1
    
    # Initialize database tables
    logger.info("Initializing database tables")
    with engine.begin() as conn:
        # Create base tables
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS bot_configs (
                symbol VARCHAR(20) PRIMARY KEY,
                config_data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS bot_states (
                symbol VARCHAR(20) PRIMARY KEY,
                state_data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS active_bots (
                symbol VARCHAR(20) PRIMARY KEY,
                is_running BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
    
    # Run migrations
    try:
        migrate_instance_data(data_dir, engine)
        migrate_csv_data(data_dir, engine)
        
        if args.cleanup:
            cleanup_old_files(data_dir)
        
        logger.info("Migration completed successfully!")
        logger.info("Update your .env file to set DATABASE_URL to your PostgreSQL connection string")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())