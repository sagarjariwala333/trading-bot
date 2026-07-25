"""
Downloads REAL historical klines from Binance's public futures API and saves them as
a CSV in the exact format backtest.py expects. Run this on YOUR machine (needs real
internet access) - no API key required, this only touches Binance's public market-data
endpoint.

USAGE:
    pip install requests pandas
    python download_historical_data.py --symbol BTCUSDT --interval 12h --months 12 --out btcusdt_12h.csv
    python download_historical_data.py --symbol PAXGUSDT --interval 12h --months 12 --out paxgusdt_12h.csv
"""

import argparse
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

BASE_URL = "https://fapi.binance.com/fapi/v1/klines"


def fetch_klines(symbol: str, interval: str, start_ms: int, end_ms: int) -> list:
    """Binance caps each response at 1500 candles, so page through in chunks."""
    all_rows = []
    cursor = start_ms
    while cursor < end_ms:
        resp = requests.get(BASE_URL, params={
            "symbol": symbol, "interval": interval,
            "startTime": cursor, "endTime": end_ms, "limit": 1500,
        }, timeout=15)
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            break
        all_rows.extend(rows)
        cursor = rows[-1][6] + 1  # next candle's start = last candle's close_time + 1ms
        print(f"  fetched {len(rows)} candles, up to {datetime.fromtimestamp(rows[-1][0]/1000, tz=timezone.utc)}")
        time.sleep(0.3)  # be polite to the public API, avoid rate limiting
    return all_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="12h")
    parser.add_argument("--months", type=int, default=12)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.months * 30)
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)

    print(f"Fetching real {args.symbol} {args.interval} klines from Binance "
          f"({start.date()} to {end.date()})...")
    raw = fetch_klines(args.symbol, args.interval, start_ms, end_ms)

    cols = ["open_time", "open", "high", "low", "close", "volume",
            "close_time", "qav", "trades", "tb_base", "tb_quote", "ignore"]
    df = pd.DataFrame(raw, columns=cols)
    for c in ["open", "high", "low", "close"]:
        df[c] = df[c].astype(float)

    df[["open_time", "open", "high", "low", "close", "close_time"]].to_csv(args.out, index=False)
    print(f"\nSaved {len(df)} REAL candles to {args.out}")
    print(f"Run: python backtest.py --data {args.out} --balance <your_balance>")


if __name__ == "__main__":
    main()
