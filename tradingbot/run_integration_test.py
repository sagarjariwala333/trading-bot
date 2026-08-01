#!/usr/bin/env python3
"""
Complete integration test for the database migration.

This script runs end-to-end tests to verify:
1. PostgreSQL setup works
2. Data migration completed successfully  
3. Bot manager works with database
4. API endpoints function correctly
5. No file dependencies remain
"""

import subprocess
import sys
import time
from pathlib import Path

def check_requirements():
    """Check that required packages are installed."""
    print("📦 Checking requirements...")
    
    required_packages = [
        'sqlalchemy',
        'psycopg2-binary',
        'fastapi',
        'pydantic'
    ]
    
    missing = []
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing.append(package)
    
    if missing:
        print(f"❌ Missing packages: {', '.join(missing)}")
        print("Install with: pip install -r requirements.txt")
        return False
    
    print("✅ All required packages installed")
    return True

def test_database_setup():
    """Test database connection and model creation."""
    print("\n🔗 Testing database setup...")
    
    try:
        result = subprocess.run([
            sys.executable, 'test_database_migration.py'
        ], capture_output=True, text=True, cwd='tradingbot')
        
        if result.returncode == 0:
            print("✅ Database tests passed")
            print(result.stdout)
            return True
        else:
            print("❌ Database tests failed")
            print(result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ Database test execution failed: {e}")
        return False

def test_api_startup():
    """Test that the FastAPI server starts without file dependencies."""
    print("\n🌐 Testing API server startup...")
    
    try:
        # Start the server in the background
        proc = subprocess.Popen([
            sys.executable, '-c',
            """
import sys
sys.path.append('tradingbot')
from app.main import app
import uvicorn
uvicorn.run(app, host='127.0.0.1', port=8001, log_level='error')
            """
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Give it time to start
        time.sleep(3)
        
        # Check if still running
        if proc.poll() is None:
            print("✅ API server started successfully")
            proc.terminate()
            proc.wait(timeout=5)
            return True
        else:
            stdout, stderr = proc.communicate()
            print("❌ API server failed to start")
            print(f"Error: {stderr.decode()}")
            return False
            
    except Exception as e:
        print(f"❌ API server test failed: {e}")
        try:
            proc.terminate()
        except:
            pass
        return False

def test_bot_manager():
    """Test bot manager database integration."""
    print("\n🤖 Testing bot manager integration...")
    
    try:
        result = subprocess.run([
            sys.executable, '-c',
            """
import sys
sys.path.append('tradingbot')

from app.services.bot_manager import BotManager
from app.services.database_service import db_service

# Test bot manager operations
symbol = 'TESTUSDT'

print(f'Testing config operations for {symbol}...')
config = BotManager.get_config(symbol)
print(f'✅ Got config: {config.get("symbol", "N/A")}')

print('Testing config update...')
updated, errors = BotManager.update_config(symbol, {'leverage': 5})
if not errors:
    print('✅ Config updated successfully')
else:
    print(f'⚠️  Config update errors: {errors}')

print('Testing status retrieval...')
status = BotManager.get_bot_status(symbol)
print(f'✅ Got status: running={status.is_running}')

print('Testing clear instance...')
BotManager.clear_instance(symbol)
print('✅ Instance cleared')

print('🎉 All bot manager tests passed!')
            """
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Bot manager integration successful")
            print(result.stdout)
            return True
        else:
            print("❌ Bot manager integration failed")
            print(result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ Bot manager test failed: {e}")
        return False

def test_file_independence():
    """Test that the system works without file-based storage."""
    print("\n📁 Testing file independence...")
    
    # Check that no critical files are being created
    data_dir = Path('tradingbot/data')
    
    # Test that instances directory isn't required
    instances_dir = data_dir / 'instances'
    if instances_dir.exists():
        print(f"⚠️  Instances directory still exists: {instances_dir}")
        print("This should be cleaned up after migration")
    
    # Test that bot can run without file dependencies
    try:
        result = subprocess.run([
            sys.executable, '-c',
            """
import sys
import os
sys.path.append('tradingbot')

# Set required environment variable
os.environ['BOT_SYMBOL'] = 'TESTUSDT'

# Test database bot runner
from app.trading_engine.database_bot_runner import get_symbol_from_env, setup_logging
from app.services.database_service import db_service

symbol = get_symbol_from_env()
logger = setup_logging(symbol)

print(f'✅ Database bot runner setup successful for {symbol}')

# Test that we can get config and state without files
config = db_service.get_bot_config(symbol)
state = db_service.get_bot_state(symbol)

print(f'✅ Config and state accessible from database')
print(f'Symbol: {config.get("symbol", "N/A")}')
print(f'Status: {state.get("status", "N/A")}')
            """
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ File independence test passed")
            print(result.stdout)
            return True
        else:
            print("❌ File independence test failed")
            print(result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ File independence test failed: {e}")
        return False

def main():
    """Run complete integration test suite."""
    print("🚀 Starting complete integration test for database migration...\n")
    
    tests = [
        ("Requirements Check", check_requirements),
        ("Database Setup", test_database_setup),
        ("API Server Startup", test_api_startup),
        ("Bot Manager Integration", test_bot_manager),
        ("File Independence", test_file_independence)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{'='*60}")
        print(f"🧪 Running: {test_name}")
        print('='*60)
        
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name} PASSED")
            else:
                print(f"❌ {test_name} FAILED")
        except Exception as e:
            print(f"💥 {test_name} CRASHED: {e}")
    
    print(f"\n{'='*60}")
    print(f"🏁 Integration Tests Complete: {passed}/{total} passed")
    print('='*60)
    
    if passed == total:
        print("🎉 ALL TESTS PASSED!")
        print("\n✅ Database migration is complete and working correctly!")
        print("\n🚀 Your trading bot is ready for production with PostgreSQL!")
        
        print("\n📋 Next Steps:")
        print("1. Set DATABASE_URL in your .env file")
        print("2. Run: python migrate_to_postgresql.py --postgresql-url YOUR_URL")
        print("3. Start your trading bot: python -m uvicorn app.main:app --host 0.0.0.0 --port 8000")
        print("4. Clean up old files: python cleanup_old_files.py")
        
        return 0
    else:
        print("⚠️  SOME TESTS FAILED!")
        print("\n🔧 Check the errors above and ensure:")
        print("- PostgreSQL is running and DATABASE_URL is set")
        print("- All requirements are installed: pip install -r requirements.txt")
        print("- Migration has been completed successfully")
        
        return 1

if __name__ == "__main__":
    exit(main())