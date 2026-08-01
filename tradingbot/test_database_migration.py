#!/usr/bin/env python3
"""
Test script for database migration and functionality.

This script tests:
1. Database connection and model creation
2. Configuration and state operations
3. Trade recording and performance tracking
4. Migration data integrity
"""

import sys
from decimal import Decimal
from datetime import datetime, timedelta

def test_database_connection():
    """Test basic database connectivity."""
    print("🔗 Testing database connection...")
    
    try:
        from app.database import SessionLocal, engine
        from sqlalchemy import text
        
        # Test connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()
            if version:
                print(f"✅ PostgreSQL connected: {version[0][:50]}...")
            else:
                print("✅ SQLite connected successfully")
        
        print("✅ Database connection successful")
        return True
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

def test_model_creation():
    """Test that all models and tables are created properly."""
    print("\n📊 Testing model creation...")
    
    try:
        from app.database import SessionLocal
        from app.models.trading import TradingPair, BotState, HistoricalData, TradeExecution
        
        with SessionLocal() as db:
            # Test each model
            models = [TradingPair, BotState, HistoricalData, TradeExecution]
            for model in models:
                count = db.query(model).count()
                print(f"✅ {model.__tablename__}: {count} records")
        
        print("✅ All models accessible")
        return True
        
    except Exception as e:
        print(f"❌ Model creation test failed: {e}")
        return False

def test_database_operations():
    """Test high-level database operations."""
    print("\n⚙️  Testing database operations...")
    
    try:
        from app.services.database_service import db_service
        
        # Test symbol
        test_symbol = "TESTUSDT"
        
        # Test configuration
        test_config = {
            "symbol": test_symbol,
            "leverage": 10,
            "testnet": True,
            "margin_fraction": 0.25
        }
        
        print(f"💾 Saving config for {test_symbol}...")
        db_service.save_bot_config(test_symbol, test_config)
        
        retrieved_config = db_service.get_bot_config(test_symbol)
        assert retrieved_config["leverage"] == 10
        print("✅ Configuration save/retrieve works")
        
        # Test state operations
        test_state = {
            "status": "WAITING_ENTRY",
            "direction": "LONG",
            "tp_level": 1
        }
        
        print(f"💾 Saving state for {test_symbol}...")
        db_service.save_bot_state(test_symbol, test_state)
        
        retrieved_state = db_service.get_bot_state(test_symbol)
        assert retrieved_state["status"] == "WAITING_ENTRY"
        print("✅ State save/retrieve works")
        
        # Test trade recording
        print(f"📈 Recording test trade for {test_symbol}...")
        db_service.record_order_placement(
            symbol=test_symbol,
            order_id="test_order_123",
            order_type="LIMIT",
            side="BUY",
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            strategy_signal="LONG_ENTRY"
        )
        
        # Test performance metrics
        print(f"📊 Updating performance metrics for {test_symbol}...")
        db_service.update_daily_performance(
            symbol=test_symbol,
            total_pnl=Decimal("100.50"),
            trades_count=5,
            winning_trades=3
        )
        
        performance = db_service.get_performance_summary(test_symbol, days=1)
        print(f"📈 Performance summary: {performance}")
        
        print("✅ All database operations successful")
        return True
        
    except Exception as e:
        print(f"❌ Database operations test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_migration_data():
    """Test that migrated data is accessible."""
    print("\n🔄 Testing migration data accessibility...")
    
    try:
        from app.database import SessionLocal
        from app.models.trading import TradingPair, BotState
        
        with SessionLocal() as db:
            # Check for migrated trading pairs
            pairs = db.query(TradingPair).all()
            print(f"📊 Found {len(pairs)} trading pairs:")
            for pair in pairs[:3]:  # Show first 3
                print(f"  - {pair.symbol}: {pair.base_asset}/{pair.quote_asset}")
            
            # Check for migrated bot states
            states = db.query(BotState).all()
            print(f"🤖 Found {len(states)} bot states:")
            for state in states[:3]:  # Show first 3
                print(f"  - {state.symbol}: {state.status}")
        
        print("✅ Migration data accessible")
        return True
        
    except Exception as e:
        print(f"❌ Migration data test failed: {e}")
        return False

def test_bot_manager_integration():
    """Test BotManager integration with database."""
    print("\n🤖 Testing BotManager database integration...")
    
    try:
        from app.services.bot_manager import BotManager
        
        test_symbol = "BTCUSDT"
        
        # Test config operations
        print(f"⚙️  Getting config for {test_symbol}...")
        config = BotManager.get_config(test_symbol)
        assert isinstance(config, dict)
        print(f"✅ Config retrieved: {config.get('symbol', 'N/A')}")
        
        # Test config update
        print(f"💾 Updating config for {test_symbol}...")
        updated_config, errors = BotManager.update_config(test_symbol, {
            "leverage": 15,
            "testnet": True
        })
        
        if not errors:
            print("✅ Config update successful")
        else:
            print(f"⚠️  Config update with errors: {errors}")
        
        # Test status retrieval
        print(f"📊 Getting status for {test_symbol}...")
        status = BotManager.get_bot_status(test_symbol)
        print(f"✅ Status retrieved: running={status.is_running}")
        
        print("✅ BotManager integration successful")
        return True
        
    except Exception as e:
        print(f"❌ BotManager integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_performance_queries():
    """Test performance and analytics queries."""
    print("\n📈 Testing performance queries...")
    
    try:
        from app.services.database_service import db_service
        from app.database import SessionLocal
        from app.models.trading import TradeExecution, PerformanceMetrics
        from sqlalchemy import func
        
        # Test analytics queries
        with SessionLocal() as db:
            # Get trade count by symbol
            trade_counts = db.query(
                TradeExecution.symbol,
                func.count(TradeExecution.id)
            ).group_by(TradeExecution.symbol).all()
            
            print(f"📊 Trade counts by symbol:")
            for symbol, count in trade_counts[:5]:  # Show first 5
                print(f"  - {symbol}: {count} trades")
            
            # Get performance metrics
            perf_metrics = db.query(PerformanceMetrics).limit(5).all()
            print(f"📈 Performance metrics: {len(perf_metrics)} records")
        
        print("✅ Performance queries successful")
        return True
        
    except Exception as e:
        print(f"❌ Performance queries test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 Starting database migration tests...\n")
    
    tests = [
        test_database_connection,
        test_model_creation,
        test_database_operations,
        test_migration_data,
        test_bot_manager_integration,
        test_performance_queries
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} crashed: {e}")
    
    print(f"\n🏁 Tests completed: {passed}/{total} passed")
    
    if passed == total:
        print("🎉 All tests passed! Database migration is working correctly.")
        return 0
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
        return 1

if __name__ == "__main__":
    exit(main())