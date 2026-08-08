import os
import time
from datetime import datetime, timedelta, timezone
import pandas as pd
import requests
from typing import List, Dict, Any, Optional
from app.core.db import (
    save_kline_dataset, get_kline_dataset, get_kline_dataset_meta, list_kline_datasets,
)
from app.schemas.market import DatasetFileSchema, DownloadResponseSchema

BASE_URL = "https://fapi.binance.com/fapi/v1/klines"

# Rough byte-size estimate for a stored candle, used to preserve the DatasetFileSchema
# size_bytes field for the frontend without any file on disk.
_BYTES_PER_KLINE = 45


class MarketDataService:
    @classmethod
    def list_datasets(cls) -> List[DatasetFileSchema]:
        rows = list_kline_datasets()
        files = []
        for r in rows:
            files.append(
                DatasetFileSchema(
                    name=r["name"],
                    size_bytes=r["rows_count"] * _BYTES_PER_KLINE,
                    last_modified=r["created_at"],
                    filepath=f"db://{r['symbol'].lower()}/{r['interval']}",
                )
            )
        return files

    @classmethod
    def download_historical_klines(
        cls, symbol: str, interval: str, months: int, custom_filename: Optional[str] = None
    ) -> DownloadResponseSchema:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=months * 30)
        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)

        name = custom_filename or f"{symbol.lower()}_{interval}_{months}m"
        if name.endswith(".csv"):
            name = name[:-4]

        # Download logic
        all_rows = []
        cursor = start_ms
        while cursor < end_ms:
            resp = requests.get(
                BASE_URL,
                params={
                    "symbol": symbol.upper(),
                    "interval": interval,
                    "startTime": cursor,
                    "endTime": end_ms,
                    "limit": 1500,
                },
                timeout=15,
            )
            resp.raise_for_status()
            rows = resp.json()
            if not rows:
                break
            all_rows.extend(rows)
            cursor = rows[-1][6] + 1  # next candle's start = last candle's close_time + 1ms
            time.sleep(0.1)  # be polite to public API

        cleaned_rows = [
            {
                "open_time": int(r[0]),
                "open": float(r[1]),
                "high": float(r[2]),
                "low": float(r[3]),
                "close": float(r[4]),
                "close_time": int(r[6]),
            }
            for r in all_rows
        ]

        stored = save_kline_dataset(name, symbol, interval, cleaned_rows)

        return DownloadResponseSchema(
            success=True,
            message=f"Successfully downloaded {stored} candles for {symbol} ({interval})",
            filename=name,
            filepath=f"db://{symbol.lower()}/{interval}",
            rows_count=stored,
        )

    @classmethod
    def load_kline_dataframe(cls, dataset_name: str) -> pd.DataFrame:
        """Load a stored dataset by name into a DataFrame indexed by open_time."""
        meta = get_kline_dataset_meta(dataset_name)
        if not meta:
            raise FileNotFoundError(f"Dataset not found: {dataset_name}")
        rows = get_kline_dataset(meta["symbol"], meta["interval"])

        if not rows:
            raise FileNotFoundError(f"Dataset is empty: {dataset_name}")

        raw = pd.DataFrame(rows)
        raw["open_time"] = pd.to_datetime(raw["open_time"], unit="ms", utc=True)
        return raw.set_index("open_time")

    @classmethod
    def fetch_klines_raw(cls, symbol: str, interval: str, limit: int = 100) -> List[Any]:
        resp = requests.get(
            BASE_URL,
            params={"symbol": symbol.upper(), "interval": interval, "limit": limit},
            timeout=10,
        )
        resp.raise_for_status()
        raw = resp.json()
        klines = []
        for r in raw:
            klines.append({
                "open_time": int(r[0]),
                "open": float(r[1]),
                "high": float(r[2]),
                "low": float(r[3]),
                "close": float(r[4]),
                "close_time": int(r[6]),
            })
        return klines
