"""
Binance USDT-M Futures bot — configurable symbol (default BTCUSDT), 12H timeframe by default.

Strategy recap (see README.md "Current full default settings" for the authoritative,
code-verified list of every value - this docstring is a summary, not the source of truth):
  - Heikin Ashi candles, ALMA(9) on HA close, RSI(14)+SMA(14) on real close, ATR(14) on
    real candles, SMA(50) on real close for trend-alignment sizing, optional ADX(14) filter.
  - LONG:  HA close > ALMA  AND  RSI > RSI_SMA  (AND ADX >= threshold, if enabled)
  - SHORT: HA close < ALMA  AND  RSI < RSI_SMA  (AND ADX >= threshold, if enabled)
  - Entry sizing: 25% of futures balance as margin per entry if the trade agrees with the SMA trend regime, 20% if it doesn't.
  - On signal: place TWO limit orders, same side, same chosen margin fraction.
  - Binance nets same-direction fills into ONE position automatically (one-way mode).
  - Initial SL = merged_entryPrice -/+ 1.0x ATR (frozen at signal candle).
  - TP ladder: TP1 at 0.5x ATR, then +0.5x ATR per further level, unbounded.
  - Trend reversal (opposite signal confirmed) market-closes the ENTIRE position immediately and opens the new opposite trade.
"""

import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from decimal import Decimal, ROUND_DOWN
from typing import Optional

# Explicitly attach the temporary REST monitor inside the actual trading subprocess.
# sitecustomize was not reliably visible in Render's subprocess, so this import is
# intentionally before the Binance Client import below. Diagnostic only.
try:
    from tradingbot.sitecustomize import install_binance_rest_monitor
    install_binance_rest_monitor()
except Exception as exc:
    print(f"[BINANCE_REST_MONITOR_ATTACH_ERROR] {exc!r}", flush=True)

import numpy as np
import pandas as pd

QTY_EPSILON = 1e-9
CLIENT_ORDER_ID_PREFIX = "haqbot_"
import requests
from binance.client import Client
try:
    from binance.exceptions import BinanceAPIException, BinanceRequestException
except ImportError:
    BinanceAPIException = None
    BinanceRequestException = None
try:
    from binance.enums import (
        SIDE_BUY, SIDE_SELL,
        ORDER_TYPE_LIMIT, ORDER_TYPE_MARKET, ORDER_TYPE_STOP_MARKET,
        TIME_IN_FORCE_GTC,
    )
except ImportError:
    from binance.enums import (
        SIDE_BUY, SIDE_SELL,
        ORDER_TYPE_LIMIT, ORDER_TYPE_MARKET,
        TIME_IN_FORCE_GTC,
    )
    ORDER_TYPE_STOP_MARKET = "STOP_MARKET"
