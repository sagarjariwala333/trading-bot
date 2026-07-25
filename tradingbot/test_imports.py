import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    print("Testing imports...")
    from app.core.config import settings
    print("[OK] app.core.config imported successfully")
    
    from app.schemas.config import TradingConfigSchema
    from app.schemas.bot import BotStatusResponseSchema
    from app.schemas.backtest import BacktestRequestSchema
    from app.schemas.market import MarketDownloadRequestSchema
    from app.schemas.indicators import LatestSignalResponseSchema
    print("[OK] app.schemas imported successfully")
    
    from app.trading_engine.indicators import build_indicator_frame
    from app.trading_engine.bot import Config, TradingBot
    from app.trading_engine.backtest import run_backtest
    print("[OK] app.trading_engine imported successfully")
    
    from app.services.market_data_service import MarketDataService
    from app.services.indicator_service import IndicatorService
    from app.services.backtest_service import BacktestService
    from app.services.bot_manager import BotManager
    print("[OK] app.services imported successfully")
    
    from app.main import app
    print("[OK] app.main (FastAPI app) imported successfully")
    
    print("\nALL IMPORTS PASSED! Backend structure is syntactically correct and loadable.")
    sys.exit(0)
except Exception as e:
    print(f"\n[ERROR] IMPORT ERROR DETECTED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
