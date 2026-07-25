import os
import time
from datetime import datetime, timedelta, timezone
import pandas as pd
import requests
from typing import List, Dict, Any, Optional
from app.core.config import settings
from app.schemas.market import DatasetFileSchema, DownloadResponseSchema

BASE_URL = "https://fapi.binance.com/fapi/v1/klines"


class MarketDataService:
    @staticmethod
    def get_datasets_dir() -> str:
        datasets_dir = os.path.join(settings.DATA_DIR, "datasets")
        os.makedirs(datasets_dir, exist_ok=True)
        return datasets_dir

    @classmethod
    def list_datasets(cls) -> List[DatasetFileSchema]:
        datasets_dir = cls.get_datasets_dir()
        files = []
        for f in os.listdir(datasets_dir):
            if f.endswith(".csv"):
                filepath = os.path.join(datasets_dir, f)
                stat = os.stat(filepath)
                files.append(
                    DatasetFileSchema(
                        name=f,
                        size_bytes=stat.st_size,
                        last_modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                        filepath=os.path.abspath(filepath),
                    )
                )
        return sorted(files, key=lambda x: x.name)

    @classmethod
    def get_dataset_path(cls, filename: str) -> str:
        datasets_dir = cls.get_datasets_dir()
        # Prevent directory traversal attacks by taking the basename
        safe_filename = os.path.basename(filename)
        return os.path.join(datasets_dir, safe_filename)

    @classmethod
    def download_historical_klines(
        cls, symbol: str, interval: str, months: int, custom_filename: Optional[str] = None
    ) -> DownloadResponseSchema:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=months * 30)
        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)

        filename = custom_filename or f"{symbol.lower()}_{interval}_{months}m.csv"
        if not filename.endswith(".csv"):
            filename += ".csv"
        
        filepath = cls.get_dataset_path(filename)
        
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

        # Convert and save
        cols = [
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "qav", "trades", "tb_base", "tb_quote", "ignore"
        ]
        df = pd.DataFrame(all_rows, columns=cols)
        for c in ["open", "high", "low", "close"]:
            df[c] = df[c].astype(float)

        cleaned_df = df[["open_time", "open", "high", "low", "close", "close_time"]]
        cleaned_df.to_csv(filepath, index=False)

        return DownloadResponseSchema(
            success=True,
            message=f"Successfully downloaded {len(cleaned_df)} candles for {symbol} ({interval})",
            filename=filename,
            filepath=os.path.abspath(filepath),
            rows_count=len(cleaned_df),
        )

    @classmethod
    def load_kline_dataframe(cls, filepath: str) -> pd.DataFrame:
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Dataset file not found: {filepath}")
        raw = pd.read_csv(filepath)
        # Parse timestamp from ms if necessary
        raw["open_time"] = pd.to_datetime(
            raw["open_time"],
            unit="ms" if raw["open_time"].iloc[0] > 1e12 else None,
            utc=True
        )
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
