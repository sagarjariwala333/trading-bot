import pandas as pd
from typing import List, Optional
from datetime import datetime, timezone
import requests
from app.trading_engine.indicators import build_indicator_frame
from app.trading_engine.bot import compute_signal
from app.schemas.indicators import IndicatorRowSchema, LatestSignalResponseSchema

BASE_URL = "https://fapi.binance.com/fapi/v1/klines"


class IndicatorService:
    @staticmethod
    def fetch_live_klines(symbol: str, interval: str, limit: int = 300) -> pd.DataFrame:
        resp = requests.get(
            BASE_URL,
            params={"symbol": symbol.upper(), "interval": interval, "limit": limit},
            timeout=10,
        )
        resp.raise_for_status()
        raw = resp.json()
        
        cols = [
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "qav", "trades", "tb_base", "tb_quote", "ignore"
        ]
        df = pd.DataFrame(raw, columns=cols)
        for c in ["open", "high", "low", "close"]:
            df[c] = df[c].astype(float)
        df["open_time"] = df["open_time"].astype("int64")
        df["close_time"] = df["close_time"].astype("int64")
        
        # Exclude currently forming candle to match bot logic
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        df = df[df["close_time"] < now_ms].reset_index(drop=True)
        df = df.set_index(pd.to_datetime(df["open_time"], unit="ms", utc=True))
        return df

    @classmethod
    def calculate_indicators(
        cls,
        df: pd.DataFrame,
        alma_window: int = 9,
        rsi_period: int = 14,
        rsi_sma_period: int = 14,
        atr_period: int = 14,
        adx_period: int = 14,
        trend_sma_period: int = 50,
    ) -> pd.DataFrame:
        return build_indicator_frame(
            df,
            alma_window=alma_window,
            rsi_period=rsi_period,
            rsi_sma_period=rsi_sma_period,
            atr_period=atr_period,
            adx_period=adx_period,
            trend_sma_period=trend_sma_period,
        )

    @classmethod
    def get_indicator_rows(cls, df_ind: pd.DataFrame) -> List[IndicatorRowSchema]:
        rows = []
        for ts, r in df_ind.iterrows():
            rows.append(
                IndicatorRowSchema(
                    timestamp=ts.isoformat(),
                    open=float(r["open"]),
                    high=float(r["high"]),
                    low=float(r["low"]),
                    close=float(r["close"]),
                    ha_open=float(r["ha_open"]),
                    ha_high=float(r["ha_high"]),
                    ha_low=float(r["ha_low"]),
                    ha_close=float(r["ha_close"]),
                    alma=None if pd.isna(r["alma"]) else float(r["alma"]),
                    rsi=None if pd.isna(r["rsi"]) else float(r["rsi"]),
                    rsi_sma=None if pd.isna(r["rsi_sma"]) else float(r["rsi_sma"]),
                    atr=None if pd.isna(r["atr"]) else float(r["atr"]),
                    adx=None if pd.isna(r["adx"]) else float(r["adx"]),
                    trend_sma=None if pd.isna(r["trend_sma"]) else float(r["trend_sma"]),
                )
            )
        return rows

    @classmethod
    def evaluate_latest_signal(
        cls,
        symbol: str,
        interval: str,
        alma_window: int = 9,
        rsi_period: int = 14,
        rsi_sma_period: int = 14,
        atr_period: int = 14,
        adx_period: int = 14,
        trend_sma_period: int = 50,
    ) -> LatestSignalResponseSchema:
        df = cls.fetch_live_klines(symbol, interval, limit=max(300, trend_sma_period + 50))
        df_ind = cls.calculate_indicators(
            df,
            alma_window=alma_window,
            rsi_period=rsi_period,
            rsi_sma_period=rsi_sma_period,
            atr_period=atr_period,
            adx_period=adx_period,
            trend_sma_period=trend_sma_period,
        )
        
        last_row = df_ind.iloc[-1]
        sig = compute_signal(df_ind)
        
        is_aligned = True
        if sig == "LONG":
            is_aligned = bool(last_row["close"] > last_row["trend_sma"])
        elif sig == "SHORT":
            is_aligned = bool(last_row["close"] < last_row["trend_sma"])
            
        return LatestSignalResponseSchema(
            timestamp=df_ind.index[-1].isoformat(),
            symbol=symbol,
            interval=interval,
            signal=sig,
            close_price=float(last_row["close"]),
            ha_close=float(last_row["ha_close"]),
            alma=None if pd.isna(last_row["alma"]) else float(last_row["alma"]),
            rsi=None if pd.isna(last_row["rsi"]) else float(last_row["rsi"]),
            rsi_sma=None if pd.isna(last_row["rsi_sma"]) else float(last_row["rsi_sma"]),
            atr=None if pd.isna(last_row["atr"]) else float(last_row["atr"]),
            adx=None if pd.isna(last_row["adx"]) else float(last_row["adx"]),
            trend_sma=None if pd.isna(last_row["trend_sma"]) else float(last_row["trend_sma"]),
            is_aligned_with_trend=is_aligned,
        )
