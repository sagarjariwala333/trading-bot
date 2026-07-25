from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from app.schemas.market import MarketDownloadRequestSchema, DownloadResponseSchema, RawKlineSchema
from app.services.market_data_service import MarketDataService
from typing import List

router = APIRouter()


@router.post("/download", response_model=DownloadResponseSchema)
def download_historical_data(payload: MarketDownloadRequestSchema):
    try:
        result = MarketDataService.download_historical_klines(
            symbol=payload.symbol,
            interval=payload.interval,
            months=payload.months,
            custom_filename=payload.filename,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download historical data: {e}")


@router.get("/klines", response_model=List[RawKlineSchema])
def get_klines(
    symbol: str = Query("BTCUSDT", description="Symbol to fetch klines for"),
    interval: str = Query("12h", description="Timeframe interval"),
    limit: int = Query(100, ge=1, le=1500, description="Number of candles to fetch")
):
    try:
        # Fetch directly from Binance API for visualization in the UI
        df = MarketDataService.fetch_klines_raw(symbol, interval, limit)
        return df
    except Exception as e:
        # Fallback to local indicator fetch
        try:
            from app.services.indicator_service import IndicatorService
            df = IndicatorService.fetch_live_klines(symbol, interval, limit)
            klines = []
            for ts, r in df.iterrows():
                klines.append(
                    RawKlineSchema(
                        open_time=int(r["open_time"]),
                        open=r["open"],
                        high=r["high"],
                        low=r["low"],
                        close=r["close"],
                        close_time=int(r["close_time"])
                    )
                )
            return klines
        except Exception as inner_err:
            raise HTTPException(status_code=500, detail=f"Error fetching klines: {inner_err}")

# Add helper fetch_klines_raw to MarketDataService or locally
