from fastapi import APIRouter, HTTPException, Depends
from typing import List
from app.schemas.backtest import BacktestRequestSchema, BacktestResponseSchema
from app.schemas.market import DatasetFileSchema
from app.services.backtest_service import BacktestService
from app.services.market_data_service import MarketDataService
from app.services.bot_manager import BotManager
from app.trading_engine.bot import Config

router = APIRouter()


@router.post("/run", response_model=BacktestResponseSchema)
def run_backtest(payload: BacktestRequestSchema):
    try:
        # Load global config parameters for the symbol as defaults if they exist
        symbol_cfg = BotManager.get_config(payload.dataset_name.split("_")[0].upper())
        cfg = Config()
        for k, v in symbol_cfg.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
                
        result = BacktestService.run_strategy_backtest(payload, cfg)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest execution failed: {e}")


@router.get("/datasets", response_model=List[DatasetFileSchema])
def list_datasets():
    try:
        return MarketDataService.list_datasets()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list datasets: {e}")
