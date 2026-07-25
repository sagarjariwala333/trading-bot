from fastapi import APIRouter, Query, HTTPException
from app.schemas.config import TradingConfigSchema, ConfigResponseSchema
from app.services.bot_manager import BotManager
from app.trading_engine.bot import EDITABLE_FIELD_LIMITS

router = APIRouter()


@router.get("", response_model=ConfigResponseSchema)
def get_config(symbol: str = Query("BTCUSDT", description="Symbol to fetch configuration for")):
    try:
        cfg = BotManager.get_config(symbol)
        # format limits mapping to json safe structure
        limits_dict = {
            k: [lo, hi, typ.__name__]
            for k, (lo, hi, typ) in EDITABLE_FIELD_LIMITS.items()
        }
        return ConfigResponseSchema(config=TradingConfigSchema(**cfg), limits=limits_dict)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting config: {e}")


@router.put("", response_model=ConfigResponseSchema)
def update_config(
    payload: TradingConfigSchema,
    symbol: str = Query("BTCUSDT", description="Symbol to update configuration for")
):
    # Check if symbol/interval changes are attempted while bot is running
    is_running = BotManager.is_running(symbol)
    current_config = BotManager.get_config(symbol)
    
    # If the bot is running, do not allow changing symbol or interval
    if is_running:
        if payload.symbol != current_config.get("symbol") or payload.interval != current_config.get("interval"):
            raise HTTPException(
                status_code=400,
                detail="Cannot change symbol or interval while the bot is active/running. Stop the bot first."
            )

    try:
        # Convert Pydantic schema to dict and apply updates
        payload_dict = payload.model_dump()
        updated_cfg, warnings = BotManager.update_config(symbol, payload_dict)
        
        limits_dict = {
            k: [lo, hi, typ.__name__]
            for k, (lo, hi, typ) in EDITABLE_FIELD_LIMITS.items()
        }
        
        return ConfigResponseSchema(config=TradingConfigSchema(**updated_cfg), limits=limits_dict)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating config: {e}")


@router.post("/reset", response_model=ConfigResponseSchema)
def reset_config(symbol: str = Query("BTCUSDT", description="Symbol to reset configuration for")):
    try:
        is_running = BotManager.is_running(symbol)
        if is_running:
            raise HTTPException(
                status_code=400,
                detail="Cannot reset configuration while the bot is active/running. Stop the bot first."
            )
            
        defaults = BotManager.reset_config(symbol)
        limits_dict = {
            k: [lo, hi, typ.__name__]
            for k, (lo, hi, typ) in EDITABLE_FIELD_LIMITS.items()
        }
        return ConfigResponseSchema(config=TradingConfigSchema(**defaults), limits=limits_dict)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error resetting config: {e}")
