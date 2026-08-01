# PostgreSQL Migration Guide

This guide covers the complete migration from file-based storage to PostgreSQL database.

## 🚀 Quick Start

### Option 1: Local PostgreSQL Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Set up local PostgreSQL database
python setup_postgresql.py --local

# Migrate existing data
python migrate_to_postgresql.py --postgresql-url "postgresql://tradingbot:tradingbot123@localhost/tradingbot"
```

### Option 2: Cloud PostgreSQL (Recommended for Production)
```bash
# Test connection to your cloud database
python setup_postgresql.py --url "postgresql://username:password@your-host:5432/database"

# Migrate existing data  
python migrate_to_postgresql.py --postgresql-url "your-postgresql-url"
```

## 📊 New Database Schema

The new PostgreSQL schema includes these tables:

### Core Tables
- **trading_pairs**: Symbol configurations and exchange metadata
- **bot_states**: Real-time bot state and position tracking
- **historical_data**: OHLCV price data (replaces CSV files)
- **trade_executions**: Complete order and fill history
- **performance_metrics**: Daily/hourly P&L and trading statistics
- **system_logs**: Structured logging (replaces log files)

### Key Improvements
✅ **Proper relationships** between tables  
✅ **Optimized indexes** for fast queries  
✅ **Timestamp tracking** (created_at, updated_at)  
✅ **DECIMAL precision** for financial data  
✅ **JSONB support** for flexible configuration storage  

## 🛠 Configuration

### Environment Variables
Update your `.env` file:
```env
# PostgreSQL (Required for production)
DATABASE_URL=postgresql://username:password@localhost:5432/tradingbot

# Keep existing settings
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret
# ... etc
```

### Database Connection
The application automatically:
- Uses PostgreSQL when `DATABASE_URL` is set
- Falls back to SQLite for development (with warning)
- Handles connection pooling and optimization

## 📈 Benefits of PostgreSQL Migration

### Performance
- **Faster queries** with proper indexing
- **Concurrent access** support
- **Connection pooling** for efficiency
- **Query optimization** capabilities

### Scalability
- **Multi-bot instances** can share database
- **Historical data analysis** with SQL queries
- **Backup and replication** strategies
- **Monitoring and alerting** integration

### Data Integrity
- **ACID transactions** for consistency
- **Foreign key constraints** prevent orphaned data
- **Proper data types** for financial precision
- **Structured logging** for debugging

## 🔄 Migration Process

### 1. Backup Current Data
Your existing files are automatically backed up during migration:
```
data/
├── backup_instances/     # Original instance configs
├── archive/             # Original CSV files  
└── tradingbot.db       # Original SQLite (kept until migration verified)
```

### 2. Database Schema Creation
All tables and indexes are created automatically with proper:
- Primary keys and foreign keys
- Optimized indexes for query performance  
- Timestamp columns for audit trails
- JSON/JSONB columns for flexible data

### 3. Data Import
The migration script imports:
- Instance configurations → `trading_pairs` table
- Bot states → `bot_states` table
- CSV historical data → `historical_data` table
- Log files → `system_logs` table (optional)

### 4. Verification
After migration, verify:
```bash
# Check database connection
python -c "from app.database import SessionLocal; print('✅ Database connected')"

# Verify data migration
python -c "
from app.database import SessionLocal, DatabaseOperations
with SessionLocal() as db:
    ops = DatabaseOperations(db)
    symbols = ops.get_active_bots()
    print(f'✅ Found {len(symbols)} migrated bot configurations')
"
```

## 🧹 Cleanup

After successful migration and verification:
```bash
# Remove old file storage (ONLY after verifying PostgreSQL works)
python cleanup_old_files.py
```

This removes:
- `backup_instances/` directory
- `archive/` directory  
- Empty `datasets/` directory
- SQLite database (if PostgreSQL is configured)

## 🔧 Advanced Usage

### Using DatabaseOperations Directly
```python
from app.database import SessionLocal, DatabaseOperations
from decimal import Decimal

with SessionLocal() as db:
    ops = DatabaseOperations(db)
    
    # Save configuration
    config = {"leverage": 10, "margin_fraction": 0.25}
    ops.update_trading_pair_config("BTCUSDT", config)
    
    # Record trade execution
    ops.record_trade_execution(
        symbol="BTCUSDT",
        order_id="12345",
        order_type="LIMIT",
        side="BUY", 
        quantity=Decimal("0.1"),
        price=Decimal("45000"),
        strategy_signal="LONG_ENTRY"
    )
    
    # Get performance metrics
    performance = ops.get_performance_summary("BTCUSDT", days=30)
    print(f"30-day P&L: {performance['total_pnl']}")
```

### Custom Queries
```python
from app.database import SessionLocal
from app.models.trading import TradeExecution, PerformanceMetrics

with SessionLocal() as db:
    # Complex queries using SQLAlchemy ORM
    recent_trades = db.query(TradeExecution).filter(
        TradeExecution.symbol == "BTCUSDT",
        TradeExecution.strategy_signal.in_(["TAKE_PROFIT", "STOP_LOSS"])
    ).limit(10).all()
    
    # Aggregate queries
    from sqlalchemy import func
    daily_pnl = db.query(
        func.sum(PerformanceMetrics.total_pnl)
    ).filter(
        PerformanceMetrics.symbol == "BTCUSDT",
        PerformanceMetrics.period_type == "DAILY"
    ).scalar()
```

## 🚨 Troubleshooting

### Connection Issues
```bash
# Test PostgreSQL connection manually
python -c "
import psycopg2
conn = psycopg2.connect('postgresql://user:pass@host:port/db')
print('✅ Connection successful')
"
```

### Migration Issues
```bash
# Run migration with verbose logging
python migrate_to_postgresql.py --postgresql-url "your-url" --verbose

# Check migration status
python -c "
from app.database import SessionLocal
from app.models.trading import TradingPair
with SessionLocal() as db:
    count = db.query(TradingPair).count()
    print(f'Migrated {count} trading pairs')
"
```

### Performance Issues
- Ensure proper indexes are created
- Check connection pool settings
- Monitor query performance with EXPLAIN
- Consider read replicas for heavy analytics

## 🔐 Security Considerations

### Database Access
- Use dedicated database user with minimal permissions
- Enable SSL/TLS for remote connections
- Regularly rotate database passwords
- Monitor database access logs

### Connection Strings
- Store `DATABASE_URL` in environment variables only
- Never commit connection strings to version control
- Use connection pooling to prevent connection exhaustion
- Set appropriate timeouts and retry policies

## 📚 Next Steps

After completing the PostgreSQL migration:

1. **Update monitoring** to track database performance
2. **Set up backups** for your PostgreSQL database  
3. **Configure alerts** for database connectivity issues
4. **Consider read replicas** for analytics workloads
5. **Review query performance** and optimize as needed

The trading bot now has a robust, scalable database foundation ready for production use! 🚀