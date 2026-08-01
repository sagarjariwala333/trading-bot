#!/usr/bin/env python3
"""
Cleanup script to remove old file-based storage after successful PostgreSQL migration.

This script removes:
- Backup instance directories
- Old archive files
- Empty directories

Run this ONLY after confirming the PostgreSQL migration was successful
and the bot is working properly with the new database.
"""

import logging
import shutil
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def cleanup_old_files(data_dir: Path = Path("data")):
    """Remove old file storage artifacts."""
    logger.info("Starting cleanup of old file-based storage")
    
    removed_count = 0
    
    # Remove backup instances
    backup_instances = data_dir / "backup_instances"
    if backup_instances.exists():
        shutil.rmtree(backup_instances)
        logger.info(f"Removed {backup_instances}")
        removed_count += 1
    
    # Remove archive directory if it exists
    archive_dir = data_dir / "archive"
    if archive_dir.exists():
        shutil.rmtree(archive_dir)
        logger.info(f"Removed {archive_dir}")
        removed_count += 1
    
    # Remove empty datasets directory
    datasets_dir = data_dir / "datasets"
    if datasets_dir.exists():
        if not any(datasets_dir.iterdir()):
            datasets_dir.rmdir()
            logger.info(f"Removed empty {datasets_dir}")
            removed_count += 1
        else:
            logger.warning(f"{datasets_dir} not empty, skipping")
    
    # Remove SQLite database if PostgreSQL is now being used
    sqlite_db = data_dir / "tradingbot.db"
    if sqlite_db.exists():
        # Check if DATABASE_URL is set to PostgreSQL
        try:
            from app.core.config import settings
            if settings.DATABASE_URL and settings.DATABASE_URL.startswith("postgresql"):
                sqlite_db.unlink()
                logger.info(f"Removed SQLite database {sqlite_db}")
                removed_count += 1
            else:
                logger.info("SQLite database retained (PostgreSQL not configured)")
        except ImportError:
            logger.warning("Could not check database configuration, keeping SQLite file")
    
    logger.info(f"Cleanup completed. Removed {removed_count} items.")

if __name__ == "__main__":
    cleanup_old_files()