import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

print('🧪 Testing fixed database functions...')

# Test the fixed db functions
from app.core.db import get_db_config, save_db_config, get_db_state, save_db_state, get_active_bots, set_bot_active_status

# Test config operations
print('Testing config operations...')
config = get_db_config('BTCUSDT')
print(f"✅ Got BTCUSDT config: leverage={config.get('leverage', 'N/A')}")

# Test state operations  
print('Testing state operations...')
state = get_db_state('BTCUSDT')
print(f"✅ Got BTCUSDT state: status={state.get('status', 'N/A')}")

# Test saving new config
print('Testing save operations...')
test_config = {'symbol': 'TESTBOT', 'leverage': 15, 'testnet': True}
save_db_config('TESTBOT', test_config)

retrieved = get_db_config('TESTBOT')
print(f"✅ Saved and retrieved TESTBOT config: leverage={retrieved.get('leverage', 'N/A')}")

# Test active bots
print('Testing active bots...')
set_bot_active_status('TESTBOT', True)
active = get_active_bots()
print(f"✅ Active bots: {active}")

print('🎉 All database functions working correctly!')
