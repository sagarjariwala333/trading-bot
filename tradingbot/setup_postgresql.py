#!/usr/bin/env python3
"""
PostgreSQL setup script for the trading bot.

This script helps set up PostgreSQL database with proper configuration.
Supports both local and cloud PostgreSQL instances.
"""

import argparse
import sys
import subprocess
from pathlib import Path

def check_postgresql_installed():
    """Check if PostgreSQL is installed locally."""
    try:
        result = subprocess.run(['psql', '--version'], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False

def create_local_database(db_name: str, username: str, password: str):
    """Create a local PostgreSQL database."""
    print(f"Creating local PostgreSQL database '{db_name}'...")
    
    # Commands to run
    commands = [
        f"CREATE USER {username} WITH PASSWORD '{password}';",
        f"CREATE DATABASE {db_name} OWNER {username};",
        f"GRANT ALL PRIVILEGES ON DATABASE {db_name} TO {username};"
    ]
    
    try:
        for cmd in commands:
            result = subprocess.run([
                'psql', '-U', 'postgres', '-c', cmd
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"Warning: Command failed (this might be expected if user/db already exists)")
                print(f"Command: {cmd}")
                print(f"Error: {result.stderr}")
        
        print(f"✅ Database '{db_name}' setup completed!")
        return True
        
    except Exception as e:
        print(f"❌ Failed to create database: {e}")
        return False

def test_connection(connection_url: str):
    """Test PostgreSQL connection."""
    print(f"Testing connection to: {connection_url.replace(':password@', ':***@')}")
    
    try:
        from sqlalchemy import create_engine, text
        
        engine = create_engine(connection_url)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            print(f"✅ Connection successful!")
            print(f"PostgreSQL version: {version}")
            
        # Test creating tables
        from app.models.base import Base
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables created successfully!")
        
        return True
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False

def update_env_file(connection_url: str):
    """Update .env file with database URL."""
    env_file = Path(".env")
    
    if not env_file.exists():
        # Copy from .env.example
        example_file = Path(".env.example")
        if example_file.exists():
            content = example_file.read_text()
            env_file.write_text(content)
            print("📋 Created .env file from .env.example")
        else:
            # Create minimal .env
            env_file.write_text(f"DATABASE_URL={connection_url}\n")
            print("📋 Created new .env file")
    
    # Update DATABASE_URL in .env
    content = env_file.read_text()
    lines = content.split('\n')
    
    updated = False
    for i, line in enumerate(lines):
        if line.startswith('DATABASE_URL='):
            lines[i] = f"DATABASE_URL={connection_url}"
            updated = True
            break
    
    if not updated:
        lines.append(f"DATABASE_URL={connection_url}")
    
    env_file.write_text('\n'.join(lines))
    print(f"✅ Updated .env file with database URL")

def main():
    parser = argparse.ArgumentParser(description="Set up PostgreSQL for trading bot")
    parser.add_argument("--local", action="store_true", 
                       help="Set up local PostgreSQL database")
    parser.add_argument("--url", type=str, 
                       help="PostgreSQL connection URL for existing database")
    parser.add_argument("--db-name", default="tradingbot", 
                       help="Database name (default: tradingbot)")
    parser.add_argument("--username", default="tradingbot", 
                       help="Database username (default: tradingbot)")
    parser.add_argument("--password", default="tradingbot123", 
                       help="Database password (default: tradingbot123)")
    parser.add_argument("--host", default="localhost", 
                       help="Database host (default: localhost)")
    parser.add_argument("--port", default="5432", 
                       help="Database port (default: 5432)")
    
    args = parser.parse_args()
    
    if not args.local and not args.url:
        print("❌ You must specify either --local or --url")
        parser.print_help()
        return 1
    
    if args.url:
        # Test existing database
        if test_connection(args.url):
            update_env_file(args.url)
            print("🎉 PostgreSQL setup completed successfully!")
            print("\nNext steps:")
            print("1. Run the migration script: python migrate_to_postgresql.py --postgresql-url YOUR_URL")
            print("2. Start your trading bot")
            return 0
        else:
            return 1
    
    if args.local:
        # Set up local database
        if not check_postgresql_installed():
            print("❌ PostgreSQL is not installed or not in PATH")
            print("\nInstallation options:")
            print("- Windows: Download from https://www.postgresql.org/download/windows/")
            print("- macOS: brew install postgresql")
            print("- Ubuntu: sudo apt-get install postgresql postgresql-contrib")
            return 1
        
        # Create database
        if create_local_database(args.db_name, args.username, args.password):
            connection_url = f"postgresql://{args.username}:{args.password}@{args.host}:{args.port}/{args.db_name}"
            
            if test_connection(connection_url):
                update_env_file(connection_url)
                print("🎉 Local PostgreSQL setup completed successfully!")
                print(f"\nDatabase URL: {connection_url}")
                print("\nNext steps:")
                print("1. Run the migration script: python migrate_to_postgresql.py --postgresql-url YOUR_URL")
                print("2. Start your trading bot")
                return 0
        
        return 1

if __name__ == "__main__":
    exit(main())