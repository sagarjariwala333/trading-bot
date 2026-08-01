from fastapi import APIRouter
from app.api.v1.endpoints import bot, config, backtest, market_data, indicators, reports
from app.api.v1 import websockets

api_router = APIRouter()

# Register sub-routers
api_router.include_router(bot.router, prefix="/bot", tags=["Bot Control"])
api_router.include_router(config.router, prefix="/config", tags=["Configuration"])
api_router.include_router(backtest.router, prefix="/backtest", tags=["Backtesting"])
api_router.include_router(market_data.router, prefix="/market", tags=["Market Data"])
api_router.include_router(indicators.router, prefix="/indicators", tags=["Technical Indicators"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
api_router.include_router(websockets.router, prefix="/ws", tags=["WebSockets"])
