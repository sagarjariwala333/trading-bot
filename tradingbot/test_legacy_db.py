#!/usr/bin/env python3
"""Test the legacy database structure."""

import sys
sys.path.append('.')

from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv
import json

def test_legacy_database():
    load_dotenv()
    db_url = os.environ.get('DATABASE_URL')
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)

    engine = create_engine(db_url)

    print('🔍 Testing database operations...')

    with engine.connect() as conn:
        # Test reading configs
        result = conn.execute(text("SELECT symbol, config_data FROM bot_configs WHERE symbol = 'BTCUSDT'"))
        row = result.fetchone()
        if row:
            symbol, config_data = row
            config = json.loads(config_data) if isinstance(config_data, str) else config_data
            print(f'✅ Found config for {symbol}: leverage={config.get("leverage", "N/A")}')
        
        # Test reading states
        result = conn.execute(text("SELECT symbol, state_data FROM bot_states WHERE symbol = 'BTCUSDT'"))
        row = result.fetchone()
        if row:
            symbol, state_data = row
            state = json.loads(state_data) if isinstance(state_data, str) else state_data
            print(f'✅ Found state for {symbol}: status={state.get("status", "N/A")}')
        
        # List all symbols
        result = conn.execute(text('SELECT symbol FROM bot_configs ORDER BY symbol'))
        symbols = [row[0] for row in result.fetchall()]
        print(f'📊 Available symbols: {symbols}')
        
        # Test inserting new data
        print('\n🧪 Testing data operations...')
        test_config = {"symbol": "TESTUSDT", "leverage": 20, "testnet": True}
        conn.execute(text("""
            INSERT INTO bot_configs (symbol, config_data, updated_at)
            VALUES (:symbol, :config, CURRENT_TIMESTAMP)
            ON CONFLICT (symbol) DO UPDATE SET
                config_data = EXCLUDED.config_data,
                updated_at = CURRENT_TIMESTAMP
        """), {"symbol": "TESTUSDT", "config": json.dumps(test_config)})
        conn.commit()
        
        # Read it back
        result = conn.execute(text("SELECT config_data FROM bot_configs WHERE symbol = 'TESTUSDT'"))
        row = result.fetchone()
        if row:
            retrieved_config = row[0]  # Already a dict in PostgreSQL JSONB
            print(f'✅ Test config saved and retrieved: leverage={retrieved_config.get("leverage")}')

    print('🎉 Database operations working correctly!')

if __name__ == "__main__":
    test_legacy_database()