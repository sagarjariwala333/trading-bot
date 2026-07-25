"""
Binance USDT-M Futures bot — configurable symbol (default BTCUSDT), 12H timeframe by default.

Strategy recap (see README.md "Current full default settings" for the authoritative,
code-verified list of every value - this docstring is a summary, not the source of truth):
  - Heikin Ashi candles, ALMA(9) on HA close, RSI(14)+SMA(14) on real close, ATR(14) on
    real candles, SMA(50) on real close for trend-alignment sizing, optional ADX(14) filter.
  - LONG:  HA close > ALMA  AND  RSI > RSI_SMA  (AND ADX >= threshold, if enabled)
  - SHORT: HA close < ALMA  AND  RSI < RSI_SMA  (AND ADX >= threshold, if enabled)
  - Entry sizing: 25% of futures balance as margin per entry if the trade agrees with
    the SMA(50) trend regime, 20% if it doesn't (see select_margin_fraction()).
  - On signal: place TWO limit orders, same side, same chosen margin fraction:
        Entry 1 = (HA_open + HA_close) / 2
        Entry 2 = HA_close
  - Binance nets same-direction fills into ONE position automatically (one-way mode) —
    we read that merged entryPrice back from the exchange rather than computing it ourselves.
    One-way mode is verified (and required) at startup; the bot refuses to start in Hedge Mode
    or if that check itself can't be completed.
  - Initial SL = merged_entryPrice -/+ 1.0x ATR (frozen at signal candle).
  - TP ladder: TP1 at 0.5x ATR, then +0.5x ATR per further level, unbounded. Each level
    closes 30% of whatever remains. SL ratchets: breakeven after TP1, then a constant
    0.5x ATR trailing gap behind whichever TP just hit, from TP2 onward.
  - Trend reversal (opposite signal confirmed) market-closes the ENTIRE position
    immediately and opens the new opposite trade in the same cycle - never waits for
    SL/TP once a reversal is confirmed.
  - Ladder ends via reversal, or by closing everything at once if the exchange's
    minimum tradable size would otherwise be violated by continued splitting.

IMPORTANT: Test on Binance Futures Testnet before running with real funds.
Requires: pip install -r requirements.txt (see that file for the exact package list)
"""

import json
import logging
import os
import tempfile
import time
import uuid
from dataclasses import dataclass, field, asdict
from decimal import Decimal, ROUND_DOWN
from typing import Optional

import numpy as np
import pandas as pd

# Position/quantity comparisons use this tolerance instead of exact `== 0` or `!=`, since
# floating point representation and exchange-side fee/rounding dust mean a position or
# order quantity is essentially never EXACTLY 0.0 in the IEEE-754 sense even when it is,
# for all practical purposes, flat/closed.
QTY_EPSILON = 1e-9
# Every order this bot places gets a clientOrderId starting with this prefix, so
# reconciliation can tell "an order this bot placed" apart from anything else that
# might be sitting on the same symbol (e.g. a manually-placed order) and never touch
# orders it doesn't own.
CLIENT_ORDER_ID_PREFIX = "haqbot_"
import requests
from binance.client import Client
try:
    from binance.exceptions import BinanceAPIException, BinanceRequestException
except ImportError:
    # Defensive: if a different python-binance version doesn't expose these at this
    # path, fall back to generic exception handling rather than crashing on import.
    BinanceAPIException = None
    BinanceRequestException = None
from binance.enums import (
    SIDE_BUY, SIDE_SELL,
    ORDER_TYPE_LIMIT, ORDER_TYPE_MARKET, ORDER_TYPE_STOP_MARKET,
    TIME_IN_FORCE_GTC,
)

from indicators import build_indicator_frame


def atomic_write_json(path: str, data) -> None:
    """
    Writes JSON to `path` without ever leaving a half-written/corrupted file behind,
    even if the process is killed, the power cuts, or the disk hiccups mid-write.

    Standard safe pattern: write to a temp file in the SAME directory, flush + fsync it
    to disk, then os.replace() it onto the real path. os.replace() is atomic on both
    POSIX and Windows when source and destination are on the same filesystem (which
    they always are here, since the temp file is created in that same directory) - so
    any reader of `path` only ever sees either the complete old content or the complete
    new content, never a partial write in between.
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------

# Set BOT_INSTANCE_DIR to run multiple fully-isolated instances of this SAME codebase
# at once (e.g. one for BTCUSDT, one for PAXGUSDT) - each gets its own config.json,
# bot_state.json, live_status.json, and bot.log in its own directory, so there is zero
# shared mutable state between instances. Example:
#   BOT_INSTANCE_DIR=instances/btc python bot.py
#   BOT_INSTANCE_DIR=instances/gold python bot.py
# Defaults to the current directory, matching the original single-instance behavior.
BOT_INSTANCE_DIR = os.environ.get("BOT_INSTANCE_DIR", ".")
os.makedirs(BOT_INSTANCE_DIR, exist_ok=True)


@dataclass
class Config:
    api_key: str = os.environ.get("BINANCE_API_KEY", "")
    api_secret: str = os.environ.get("BINANCE_API_SECRET", "")
    telegram_bot_token: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")   # secret - env only, never in config.json
    telegram_chat_id: str = os.environ.get("TELEGRAM_CHAT_ID", "")       # env only, never in config.json
    telegram_enabled: bool = True                                        # dashboard-toggleable mute switch
    testnet: bool = True                       # ALWAYS start with testnet=True
    symbol: str = "BTCUSDT"
    interval: str = "12h"
    leverage: int = 10                         # your preference: 10x on BTC
    margin_fraction_per_entry: float = 0.25     # 25% of balance, per entry - used when the trade is ALIGNED with the SMA trend
    margin_fraction_counter_trend: float = 0.20 # 20% of balance, per entry - used when the trade is AGAINST the SMA trend
    trend_sma_period: int = 50                  # real-close SMA used to judge trend alignment for entry sizing
    alma_window: int = 9
    rsi_period: int = 14
    rsi_sma_period: int = 14                   # SMA of RSI now matches RSI period (was 7)
    atr_period: int = 14
    sl_atr_multiple: float = 1.0               # initial stop-loss = entry -/+ this many ATRs
    tp_custom_levels: str = "0.5"              # TP1 = 0.5x ATR; step continues uniformly from here
    tp_step_atr: float = 0.5                   # step (x ATR) for every level AFTER the custom list ends
    tp_close_fraction: float = 0.30            # each TP closes this fraction of whatever remains
    sl_trail_gap_atr: float = 0.5               # constant ATR gap kept between a just-hit TP (level>=2) and the new SL
    adx_filter_enabled: bool = False           # optional entry-strength gate - OFF by default, your judgment rules unless you turn it on
    adx_period: int = 14
    adx_threshold: float = 25.0                # entries only allowed when ADX >= this (25 = "confirmed trend" convention)
    poll_seconds: int = 15
    klines_lookback: int = 300
    config_path: str = os.path.join(BOT_INSTANCE_DIR, "config.json")
    live_status_file: str = os.path.join(BOT_INSTANCE_DIR, "live_status.json")
    state_file: str = os.path.join(BOT_INSTANCE_DIR, "bot_state.json")
    log_file: str = os.path.join(BOT_INSTANCE_DIR, "bot.log")

    # ---- dashboard integration -------------------------------------------
    def to_editable_dict(self) -> dict:
        return {k: getattr(self, k) for k in EDITABLE_FIELDS}

    def save_editable(self):
        """Write the current editable fields to config_path (used to create the file
        on first run, and whenever the dashboard writes a validated update)."""
        atomic_write_json(self.config_path, self.to_editable_dict())

    def reload_editable(self, allow_symbol_interval_change: bool = True):
        """
        Re-read config_path and apply any changes. Called every tick so dashboard edits
        take effect without restarting the bot. `symbol`/`interval` are only applied when
        allow_symbol_interval_change=True (i.e. the bot is IDLE) - changing which market
        or timeframe you're trading out from under an OPEN position would be genuinely
        dangerous, so those two fields are locked while a trade is active.
        """
        if not os.path.exists(self.config_path):
            return
        try:
            with open(self.config_path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return  # dashboard mid-write or file briefly invalid - just skip this cycle
        for k in EDITABLE_FIELDS:
            if k in ("symbol", "interval") and not allow_symbol_interval_change:
                continue
            if k in data:
                clean_value, error = validate_config_field(k, data[k])
                if error is not None:
                    logging.getLogger("ha_alma_bot").error(
                        f"config.json has an invalid value for '{k}' ({data[k]!r}): {error}. "
                        f"Keeping the previous value rather than applying it."
                    )
                    continue
                setattr(self, k, clean_value)

    @classmethod
    def load(cls, config_path: str = None) -> "Config":
        if config_path is None:
            config_path = os.path.join(BOT_INSTANCE_DIR, "config.json")
        cfg = cls(config_path=config_path)
        if os.path.exists(config_path):
            cfg.reload_editable(allow_symbol_interval_change=True)
        else:
            cfg.save_editable()
        return cfg


EDITABLE_FIELDS = [
    "testnet", "symbol", "interval", "leverage", "margin_fraction_per_entry",
    "margin_fraction_counter_trend", "trend_sma_period",
    "alma_window", "rsi_period", "rsi_sma_period", "atr_period",
    "sl_atr_multiple", "tp_custom_levels", "tp_step_atr", "tp_close_fraction",
    "sl_trail_gap_atr", "adx_filter_enabled", "adx_period", "adx_threshold",
    "poll_seconds", "klines_lookback", "telegram_enabled",
]

# Sensible bounds the dashboard's /api/config endpoint enforces before writing config.json.
# tp_custom_levels is a comma-separated string, validated separately (see parse_tp_custom_levels).
EDITABLE_FIELD_LIMITS = {
    "leverage": (1, 125, int),
    "margin_fraction_per_entry": (0.01, 1.0, float),
    "margin_fraction_counter_trend": (0.01, 1.0, float),
    "trend_sma_period": (2, 500, int),
    "alma_window": (2, 200, int),
    "rsi_period": (2, 200, int),
    "rsi_sma_period": (2, 200, int),
    "atr_period": (2, 200, int),
    "sl_atr_multiple": (0.1, 10.0, float),
    "tp_step_atr": (0.05, 10.0, float),
    "tp_close_fraction": (0.05, 0.95, float),
    "sl_trail_gap_atr": (0.05, 10.0, float),
    "adx_period": (2, 200, int),
    "adx_threshold": (0.0, 100.0, float),
    "poll_seconds": (1, 3600, int),
    "klines_lookback": (50, 1500, int),
}


def parse_tp_custom_levels(raw: str) -> list:
    """
    Parses "0.5" -> [0.5] (the current default - a single value, with tp_step_atr
    handling the uniform continuation from there). Also accepts multi-value lists like
    "0.75,1.5,2.5" for a non-uniform start. Must be a strictly increasing list of
    positive ATR multiples - each TP level must sit further out than the last, or the
    ladder logic (and the exchange orders it produces) wouldn't make sense.
    Raises ValueError with a clear message on anything invalid.
    """
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        raise ValueError("tp_custom_levels must contain at least one ATR multiple")
    if len(parts) > 20:
        raise ValueError("tp_custom_levels: too many levels (max 20)")
    values = []
    for p in parts:
        try:
            v = float(p)
        except ValueError:
            raise ValueError(f"tp_custom_levels: '{p}' is not a number")
        if v <= 0:
            raise ValueError(f"tp_custom_levels: '{p}' must be positive")
        values.append(v)
    for i in range(1, len(values)):
        if values[i] <= values[i - 1]:
            raise ValueError("tp_custom_levels must be strictly increasing "
                              f"(got {values[i]} after {values[i-1]})")
    return values


BOOL_FIELDS = ("testnet", "telegram_enabled", "adx_filter_enabled")
STRING_FIELDS = ("symbol", "interval")


def parse_bool(v) -> bool:
    """
    Explicit boolean parsing - Python's bare bool(v) is a trap here: bool("false")
    is True (any non-empty string is truthy), which would silently invert the intent
    of anyone writing "false" into config.json by hand or via a non-JS client.
    """
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes", "on")
    return bool(v)


def validate_config_field(key: str, value):
    """
    The SINGLE source of truth for "is this a legitimate value for this config field",
    used by BOTH the dashboard's /api/config write-path AND the bot's own
    Config.reload_editable() read-path. Having one shared validator (instead of the
    dashboard validating on write while the bot blindly trusts whatever it later reads)
    closes the gap where a hand-edited or corrupted config.json could otherwise inject
    a bad type straight into a live trading parameter.

    Returns (clean_value, error_message_or_None). On failure, clean_value is None and
    the caller should keep whatever value it already had rather than applying this one.
    """
    if key not in EDITABLE_FIELDS:
        return None, f"'{key}' is not an editable field"

    if key in BOOL_FIELDS:
        return parse_bool(value), None

    if key == "tp_custom_levels":
        try:
            parse_tp_custom_levels(str(value))  # validate only; the raw string is what's stored
            return str(value), None
        except ValueError as e:
            return None, str(e)

    if key in STRING_FIELDS:
        s = str(value).strip()
        if not s:
            return None, f"{key}: cannot be empty"
        return s, None

    if key in EDITABLE_FIELD_LIMITS:
        lo, hi, typ = EDITABLE_FIELD_LIMITS[key]
        try:
            v = typ(value)
        except (TypeError, ValueError):
            return None, f"{key}: expected a {typ.__name__}, got {value!r}"
        if not (lo <= v <= hi):
            return None, f"{key}: {v} out of allowed range [{lo}, {hi}]"
        return v, None

    # Editable but has no specific rule (shouldn't happen given the lists above, but
    # fail safe rather than silently accepting an unvalidated value).
    return None, f"{key}: no validation rule defined - rejecting to be safe"



# --------------------------------------------------------------------------
# STATE (persisted to disk so a restart never loses track of an open trade)
# --------------------------------------------------------------------------

@dataclass
class BotState:
    status: str = "IDLE"                # IDLE -> ENTRIES_PLACED -> IN_POSITION -> (loop)
    direction: Optional[str] = None     # "LONG" or "SHORT"
    entry1_order_id: Optional[int] = None
    entry2_order_id: Optional[int] = None
    sl_order_id: Optional[int] = None
    tp_order_id: Optional[int] = None
    atr_at_signal: Optional[float] = None
    signal_candle_time: Optional[int] = None   # ms open_time of the candle that triggered entry
    tp_level: int = 0                   # how many TP levels have been hit so far (0 = none yet)

    def save(self, path: str):
        atomic_write_json(path, asdict(self))

    @classmethod
    def load(cls, path: str) -> "BotState":
        if os.path.exists(path):
            try:
                with open(path) as f:
                    data = json.load(f)
                return cls(**data)
            except (json.JSONDecodeError, TypeError, OSError) as e:
                # Corrupted/truncated/unreadable state file (e.g. power loss mid-write
                # before atomic saves were in place, or disk corruption). Starting fresh
                # here is SAFE specifically because TradingBot.reconcile_on_startup()
                # independently re-derives the true state from Binance itself right
                # after this loads - it does not blindly trust whatever this returns.
                logging.getLogger("ha_alma_bot").error(
                    f"bot_state.json is corrupted or unreadable ({e}). "
                    f"Starting from a blank state - startup reconciliation against "
                    f"Binance will rebuild the real position/order state if one exists."
                )
                return cls()
        return cls()

    def reset(self):
        self.__init__()


# --------------------------------------------------------------------------
# LOGGING
# --------------------------------------------------------------------------

def setup_logger(cfg: Config) -> logging.Logger:
    logger = logging.getLogger("ha_alma_bot")
    if logger.handlers:
        return logger  # already configured - avoid adding duplicate handlers
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    fh = logging.FileHandler(cfg.log_file)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger


# --------------------------------------------------------------------------
# TELEGRAM NOTIFICATIONS
# --------------------------------------------------------------------------

class TelegramNotifier:
    """
    Best-effort push notifications for major trade lifecycle events, so you know what's
    happening even when you're away from a screen (flying, etc.).

    Bot token and chat ID come from environment variables ONLY (TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID) - never stored in config.json, never exposed through the dashboard,
    since the dashboard has no login and shouldn't be trusted with secrets. `telegram_enabled`
    is the one dashboard-editable piece - a simple mute/unmute switch that doesn't touch
    the credentials themselves.

    A failed or unconfigured notification NEVER raises - this must not be able to crash
    the trading loop. Worst case, you just don't get a message.
    """

    def __init__(self, cfg: Config, logger: logging.Logger):
        self.cfg = cfg
        self.log = logger

    def send(self, message: str):
        if not self.cfg.telegram_enabled:
            return
        if not self.cfg.telegram_bot_token or not self.cfg.telegram_chat_id:
            return  # not configured - silently skip, don't spam the log every tick
        try:
            url = f"https://api.telegram.org/bot{self.cfg.telegram_bot_token}/sendMessage"
            requests.post(
                url,
                data={"chat_id": self.cfg.telegram_chat_id, "text": message, "parse_mode": "HTML"},
                timeout=10,
            )
        except Exception as e:
            self.log.warning(f"Telegram notification failed (bot keeps running regardless): {e}")


# --------------------------------------------------------------------------
# EXCHANGE HELPERS
# --------------------------------------------------------------------------

# Binance API error codes that mean "retrying the exact same request will never
# succeed" - these are configuration, permission, or parameter problems. Retrying them
# just burns time and rate-limit budget while delaying the person noticing the real
# issue (bad credentials, insufficient balance, an invalid order parameter, etc.).
NON_RETRYABLE_BINANCE_CODES = {
    -1022,  # invalid signature
    -2015,  # invalid API-key, IP whitelist, or permissions
    -2014,  # bad API-key format
    -2019,  # margin insufficient
    -2010,  # order rejected (commonly insufficient balance / trading rules)
    -1013,  # invalid quantity/price - LOT_SIZE or PRICE_FILTER failure
    -1111,  # precision over the maximum defined for this asset
    -4164,  # order notional smaller than MIN_NOTIONAL
}
# Timestamp outside recvWindow - almost always local clock drift. Worth a resync +
# retry rather than either failing immediately or retrying blindly without fixing
# the actual cause.
CLOCK_DRIFT_BINANCE_CODES = {-1021}
# Too many requests / rate limited - worth retrying, but with meaningfully longer
# backoff than a generic transient network error, to actually give the limit window
# time to clear rather than hammering it again almost immediately.
RATE_LIMIT_BINANCE_CODES = {-1003}


class ExchangeGateway:
    """Thin wrapper around python-binance Futures endpoints with rounding/retry helpers."""

    def __init__(self, cfg: Config, logger: logging.Logger):
        self.cfg = cfg
        self.log = logger
        self.client = Client(cfg.api_key, cfg.api_secret, testnet=cfg.testnet)
        self._symbol_info = None

    # ---- retry wrapper -----------------------------------------------
    def _binance_error_code(self, exc) -> Optional[int]:
        code = getattr(exc, "code", None)
        if code is None:
            return None
        try:
            return int(code)
        except (TypeError, ValueError):
            return None

    def sync_clock(self):
        """
        Resync the signing clock against Binance's own server time. python-binance
        computes this once at Client construction but never revisits it - if the local
        clock drifts afterward (a documented, commonly-reported real-world issue), every
        signed request can start failing with -1021 until this is called again.
        """
        try:
            server_time = self._call(self.client.futures_time, retries=1)["serverTime"]
            local_time = int(time.time() * 1000)
            offset = server_time - local_time
            self.client.timestamp_offset = offset
            self.log.info(f"Clock resynced against Binance - offset now {offset}ms.")
        except Exception as e:
            self.log.error(f"Could not resync clock against Binance: {e}")

    # Exception types that almost always mean a bug in OUR code (wrong argument type,
    # missing dict key, referencing an undefined name) rather than a transient network
    # or exchange-side issue. Retrying these wastes time and delays discovering a real
    # defect - they should surface immediately instead.
    BUG_LIKE_EXCEPTION_TYPES = (TypeError, AttributeError, KeyError, NameError,
                                 IndexError, UnboundLocalError)

    def _call(self, fn, *args, retries: int = 3, delay: float = 2.0, **kwargs):
        last_exc = None
        attempt = 0
        while attempt < retries:
            attempt += 1
            try:
                return fn(*args, **kwargs)
            except self.BUG_LIKE_EXCEPTION_TYPES as e:
                self.log.error(f"{fn.__name__} raised {type(e).__name__} ({e}) - this looks "
                                f"like a bug in our own code (wrong argument, missing key, "
                                f"etc.), not a transient/exchange issue. Not retrying - "
                                f"raising immediately so it's visible right away.")
                raise
            except Exception as e:
                last_exc = e
                code = self._binance_error_code(e)

                if code in NON_RETRYABLE_BINANCE_CODES:
                    self.log.error(f"{fn.__name__} failed with non-retryable error "
                                    f"({code}): {e}. Not retrying - this needs a human "
                                    f"to fix (credentials, balance, or an order parameter).")
                    raise

                if code in CLOCK_DRIFT_BINANCE_CODES:
                    self.log.warning(f"{fn.__name__} failed due to clock drift ({code}): "
                                      f"{e}. Resyncing and retrying.")
                    self.sync_clock()
                    time.sleep(0.5)
                    continue

                if code in RATE_LIMIT_BINANCE_CODES:
                    backoff = delay * (2 ** attempt)
                    self.log.warning(f"{fn.__name__} rate-limited ({code}): {e}. "
                                      f"Backing off {backoff:.1f}s (longer than a normal retry).")
                    time.sleep(backoff)
                    continue

                # Unknown / generic / transient (network blip, temporary API hiccup) -
                # standard fixed-delay retry.
                self.log.warning(f"{fn.__name__} failed (attempt {attempt}/{retries}): {e}")
                time.sleep(delay)
        raise last_exc

    # ---- symbol precision ----------------------------------------------
    def symbol_info(self):
        if self._symbol_info is None:
            info = self._call(self.client.futures_exchange_info)
            for s in info["symbols"]:
                if s["symbol"] == self.cfg.symbol:
                    self._symbol_info = s
                    break
            if self._symbol_info is None:
                raise RuntimeError(f"Symbol {self.cfg.symbol} not found in exchange info")
        return self._symbol_info

    def _filter(self, filter_type: str):
        for f in self.symbol_info()["filters"]:
            if f["filterType"] == filter_type:
                return f
        raise RuntimeError(f"Filter {filter_type} not found for {self.cfg.symbol}")

    def round_price(self, price: float) -> str:
        tick = Decimal(self._filter("PRICE_FILTER")["tickSize"])
        p = Decimal(str(price)).quantize(tick, rounding=ROUND_DOWN)
        return format(p, "f")

    def round_qty(self, qty: float) -> str:
        step = Decimal(self._filter("LOT_SIZE")["stepSize"])
        q = Decimal(str(qty)).quantize(step, rounding=ROUND_DOWN)
        return format(q, "f")

    def min_qty(self) -> Decimal:
        return Decimal(self._filter("LOT_SIZE")["minQty"])

    def qty_step(self) -> Decimal:
        return Decimal(self._filter("LOT_SIZE")["stepSize"])

    def min_notional(self) -> Decimal:
        """
        Binance's MIN_NOTIONAL filter: price x quantity must exceed this or the order
        is rejected outright, independent of the LOT_SIZE (quantity) check. This matters
        more than it might seem once you're not always trading BTC - a symbol with a much
        lower unit price needs a correspondingly larger quantity to clear the same
        notional floor, and gold-pegged instruments in particular can have very different
        minimums than BTCUSDT.
        """
        try:
            return Decimal(self._filter("MIN_NOTIONAL")["notional"])
        except RuntimeError:
            return Decimal("0")  # some symbols may not carry this filter; treat as no floor

    # ---- account / market data ------------------------------------------
    def setup_symbol(self):
        self.verify_one_way_mode()
        try:
            self._call(self.client.futures_change_leverage,
                       symbol=self.cfg.symbol, leverage=self.cfg.leverage)
        except Exception as e:
            self.log.warning(f"Could not set leverage (may already be set): {e}")
        try:
            self._call(self.client.futures_change_margin_type,
                       symbol=self.cfg.symbol, marginType="ISOLATED")
        except Exception as e:
            self.log.info(f"Margin type unchanged (likely already ISOLATED): {e}")

    def verify_one_way_mode(self):
        """
        This bot's entire position model assumes Binance's ONE-WAY position mode,
        where futures_position_information(symbol=...) returns exactly one entry per
        symbol with a signed positionAmt (positive=long, negative=short). In HEDGE
        MODE, the same call instead returns TWO entries per symbol (separate LONG and
        SHORT sides tracked independently) - reading "the first match" in that case
        could silently grab the wrong side, or miss a real position on the other side
        entirely.

        FAILS CLOSED: if this check cannot even be performed (network/API failure),
        the bot refuses to start rather than proceeding on an unconfirmed assumption -
        the earlier version of this function logged a warning and continued trading
        in that case, which is exactly the "fail open" risk a reviewer correctly
        flagged. Trading blind on whether the position model even holds is worse than
        not trading at all.
        """
        try:
            mode = self._call(self.client.futures_get_position_mode)
        except Exception as e:
            raise RuntimeError(
                f"Could not verify Binance position mode (one-way vs hedge): {e}. "
                f"This bot's entire position-tracking model depends on knowing this for "
                f"certain before it ever touches an order - refusing to start rather than "
                f"proceeding on an unconfirmed assumption. Check your API connectivity/"
                f"credentials and restart."
            )
        if mode.get("dualSidePosition", False):
            raise RuntimeError(
                f"Your Binance Futures account is in HEDGE MODE (dualSidePosition=True). "
                f"This bot requires ONE-WAY mode - its entire position-tracking model "
                f"assumes exactly one position per symbol, which hedge mode does not "
                f"guarantee. Switch to One-way mode in Binance (Futures settings > "
                f"Position Mode) - note Binance will only allow this switch while you "
                f"have NO open positions or orders on ANY symbol - then restart the bot."
            )

    def get_available_balance(self) -> float:
        balances = self._call(self.client.futures_account_balance)
        for b in balances:
            if b["asset"] == "USDT":
                return float(b["availableBalance"])
        raise RuntimeError("USDT balance not found")

    def get_closed_klines(self) -> pd.DataFrame:
        raw = self._call(
            self.client.futures_klines,
            symbol=self.cfg.symbol, interval=self.cfg.interval,
            limit=self.cfg.klines_lookback,
        )
        cols = ["open_time", "open", "high", "low", "close", "volume",
                "close_time", "qav", "trades", "tb_base", "tb_quote", "ignore"]
        df = pd.DataFrame(raw, columns=cols)
        for c in ["open", "high", "low", "close"]:
            df[c] = df[c].astype(float)
        df["open_time"] = df["open_time"].astype("int64")
        df["close_time"] = df["close_time"].astype("int64")

        now_ms = int(time.time() * 1000)
        df = df[df["close_time"] < now_ms].reset_index(drop=True)  # drop any still-forming candle
        df = df.set_index(pd.to_datetime(df["open_time"], unit="ms"))
        return df

    def get_current_price(self) -> float:
        t = self._call(self.client.futures_mark_price, symbol=self.cfg.symbol)
        return float(t["markPrice"])

    def get_position_amt(self) -> float:
        positions = self._call(self.client.futures_position_information, symbol=self.cfg.symbol)
        for p in positions:
            if p["symbol"] == self.cfg.symbol:
                return float(p["positionAmt"])
        return 0.0

    def get_position_entry_price(self) -> float:
        positions = self._call(self.client.futures_position_information, symbol=self.cfg.symbol)
        for p in positions:
            if p["symbol"] == self.cfg.symbol:
                return float(p["entryPrice"])
        return 0.0

    def get_order_status(self, order_id: int) -> Optional[dict]:
        try:
            return self._call(self.client.futures_get_order, symbol=self.cfg.symbol, orderId=order_id)
        except Exception as e:
            self.log.warning(f"Could not fetch order {order_id}: {e}")
            return None

    def get_open_orders(self) -> list:
        """
        ALL currently open orders for this symbol, straight from Binance - not just the
        ones bot_state.json happens to reference by ID. This is what makes startup
        reconciliation trustworthy: it looks at exchange ground truth, not just the ids
        the (possibly stale or crashed-mid-write) state file remembers.
        """
        try:
            return self._call(self.client.futures_get_open_orders, symbol=self.cfg.symbol)
        except Exception as e:
            self.log.error(f"Could not fetch open orders during reconciliation: {e}")
            return []

    def cancel_order(self, order_id: int):
        try:
            self._call(self.client.futures_cancel_order, symbol=self.cfg.symbol, orderId=order_id)
        except Exception as e:
            self.log.info(f"Cancel order {order_id} skipped/failed (likely already gone): {e}")

    # ---- order placement --------------------------------------------------
    def _new_client_order_id(self) -> str:
        """
        Every order this bot places is tagged with a distinctive client order ID prefix.
        This is what lets reconciliation (and any cleanup logic) tell "an order THIS BOT
        placed" apart from "an order that happens to be sitting on this symbol for some
        other reason" (e.g. you manually placed something on the same symbol) - so
        cleanup only ever touches orders the bot itself is responsible for.
        """
        suffix = uuid.uuid4().hex[:8]
        return f"{CLIENT_ORDER_ID_PREFIX}{int(time.time() * 1000)}{suffix}"

    def place_entry_limit(self, side: str, price: float, qty: float) -> int:
        order = self._call(
            self.client.futures_create_order,
            symbol=self.cfg.symbol, side=side, type=ORDER_TYPE_LIMIT,
            timeInForce=TIME_IN_FORCE_GTC,
            quantity=self.round_qty(qty), price=self.round_price(price),
            newClientOrderId=self._new_client_order_id(),
        )
        self.log.info("Raw entry order response: %s", order)
        self.log.info("Saving entry orderId=%s clientOrderId=%s", order.get("orderId"), order.get("clientOrderId"))
        return order["orderId"]

    def place_stop_market(self, side: str, stop_price: float, qty: float) -> int:
        order = self._call(
            self.client.futures_create_order,
            symbol=self.cfg.symbol, side=side, type=ORDER_TYPE_STOP_MARKET,
            stopPrice=self.round_price(stop_price),
            quantity=self.round_qty(qty),
            reduceOnly=True,
            newClientOrderId=self._new_client_order_id(),
        )
        return order["orderId"]

    def place_tp_limit(self, side: str, price: float, qty: float) -> int:
        order = self._call(
            self.client.futures_create_order,
            symbol=self.cfg.symbol, side=side, type=ORDER_TYPE_LIMIT,
            timeInForce=TIME_IN_FORCE_GTC,
            price=self.round_price(price), quantity=self.round_qty(qty),
            reduceOnly=True,
            newClientOrderId=self._new_client_order_id(),
        )
        return order["orderId"]

    def place_market_close(self, side: str, qty: float) -> int:
        order = self._call(
            self.client.futures_create_order,
            symbol=self.cfg.symbol, side=side, type=ORDER_TYPE_MARKET,
            quantity=self.round_qty(qty),
            reduceOnly=True,
            newClientOrderId=self._new_client_order_id(),
        )
        return order["orderId"]


# --------------------------------------------------------------------------
# STRATEGY / SIGNAL LOGIC
# --------------------------------------------------------------------------

def compute_signal(df_ind: pd.DataFrame) -> Optional[str]:
    """
    Looks at the LAST fully closed candle only (df_ind's final row, since
    get_closed_klines already stripped any still-forming candle).
    Returns "LONG", "SHORT", or None.
    """
    last = df_ind.iloc[-1]
    if pd.isna(last["alma"]) or pd.isna(last["rsi_sma"]) or pd.isna(last["atr"]):
        return None  # not enough warm-up data yet

    ha_close_above_alma = last["ha_close"] > last["alma"]
    ha_close_below_alma = last["ha_close"] < last["alma"]
    rsi_above_sma = last["rsi"] > last["rsi_sma"]
    rsi_below_sma = last["rsi"] < last["rsi_sma"]

    if ha_close_above_alma and rsi_above_sma:
        return "LONG"
    if ha_close_below_alma and rsi_below_sma:
        return "SHORT"
    return None


def entry_prices(last_row: pd.Series, direction: str) -> tuple:
    """Entry 1 = avg(HA open, HA close); Entry 2 = HA close. Same for long & short."""
    entry1 = (last_row["ha_open"] + last_row["ha_close"]) / 2.0
    entry2 = last_row["ha_close"]
    return entry1, entry2


def select_margin_fraction(signal: str, close: float, trend_sma: float,
                            aligned_fraction: float, counter_fraction: float) -> tuple:
    """
    Sizes each entry based on whether this trade agrees with the broader trend, per a
    longer-period SMA on real close: LONG is "aligned" when close > trend_sma (price
    sitting above the longer-term average), SHORT is "aligned" when close < trend_sma.
    Trading WITH that regime gets the full (aligned) fraction; trading AGAINST it gets
    the smaller (counter-trend) fraction.

    Returns (fraction, is_aligned). is_aligned is None when trend_sma isn't available yet
    (insufficient warmup) - in that case alignment is genuinely unknown, so default to
    the SMALLER (counter-trend) fraction rather than the full one. Defaulting to full
    size on a data gap would be an optimistic assumption dressed up as a neutral one;
    sizing down under real uncertainty is the conservative, correct default.
    """
    if pd.isna(trend_sma):
        return counter_fraction, None
    is_aligned = (close > trend_sma) if signal == "LONG" else (close < trend_sma)
    return (aligned_fraction if is_aligned else counter_fraction), is_aligned


def tp_multiple_for_level(level: int, custom_levels: list, step: float) -> float:
    """
    ATR multiple for TP level n. The first len(custom_levels) levels use those exact
    values (which don't have to be evenly spaced); every level after that continues
    from the LAST custom value, adding `step` ATR per further level.
    Current default: custom_levels=[0.5], step=0.5 ->
      level 1 = 0.5, level 2 = 1.0, level 3 = 1.5, level 4 = 2.0, level 5 = 2.5, ...
    (custom_levels can hold multiple non-uniform starting values too, e.g. [0.75, 1.5, 2.5],
    with the step continuing uniformly after whichever values are listed.)
    """
    n_custom = len(custom_levels)
    if level <= n_custom:
        return custom_levels[level - 1]
    return custom_levels[-1] + step * (level - n_custom)


def tp_ladder_price(entry: float, atr: float, direction: str, level: int,
                     custom_levels: list, step: float = 0.5) -> float:
    """TP level price = entry +/- tp_multiple_for_level(level) x ATR, from the ORIGINAL
    fixed entry price (never a moving reference)."""
    multiple = tp_multiple_for_level(level, custom_levels, step)
    return entry + multiple * atr if direction == "LONG" else entry - multiple * atr


def sl_price_for_tp_level(entry: float, atr: float, direction: str, tp_level: int,
                           custom_levels: list, step: float = 0.5,
                           sl_multiple: float = 1.0, sl_trail_gap: float = 1.0) -> float:
    """
    tp_level = number of TP levels already hit (0 = none yet -> original stop).
    tp_level=0 -> entry -/+ (sl_multiple x ATR)     - the initial stop
    tp_level=1 -> entry                              - breakeven (special case: the general
                  trailing-gap formula would put TP1's own SL BELOW entry if TP1 sits
                  closer than sl_trail_gap, which would defeat the point of a "lock in
                  profit" step, so the first level always jumps straight to breakeven)
    tp_level>=2 -> (that level's own TP price) -/+ (sl_trail_gap x ATR)
                   - a CONSTANT ATR distance kept behind whichever TP just hit, not a
                   jump to some previous level's raw price. This is what keeps the
                   trailing stop from tightening down to less than sl_trail_gap even
                   once the ladder's own step size becomes smaller than that gap.
    """
    if tp_level == 0:
        return entry - sl_multiple * atr if direction == "LONG" else entry + sl_multiple * atr
    if tp_level == 1:
        return entry
    just_hit_price = tp_ladder_price(entry, atr, direction, tp_level, custom_levels, step)
    return (just_hit_price - sl_trail_gap * atr if direction == "LONG"
            else just_hit_price + sl_trail_gap * atr)


def next_tp_price_and_qty(entry: float, atr: float, direction: str,
                           tp_level: int, total_qty: float, min_qty,
                           custom_levels: list, step: float = 0.5,
                           close_fraction: float = 0.30,
                           min_notional=None) -> tuple:
    """
    Price of the next pending TP level, and how much it should close (close_fraction of
    whatever remains - e.g. 0.40 closes 40% each time). If that fraction (or what's left
    after taking it) would fall below the exchange's minimum tradable size - in EITHER
    base-asset quantity (LOT_SIZE) or order value (MIN_NOTIONAL, price x qty) - close the
    ENTIRE remaining position at this level instead of splitting into an un-tradeable size.
    Checking both matters once this isn't always BTC: a low-unit-price asset can clear
    LOT_SIZE easily while still failing MIN_NOTIONAL, and vice versa.
    """
    next_level = tp_level + 1
    price = tp_ladder_price(entry, atr, direction, next_level, custom_levels, step)
    close_qty = total_qty * close_fraction
    remainder = total_qty - close_qty
    from decimal import Decimal as _D

    fails_lot_size = _D(str(close_qty)) < min_qty or _D(str(remainder)) < min_qty
    fails_notional = False
    if min_notional and min_notional > 0:
        close_notional = _D(str(close_qty)) * _D(str(price))
        remainder_notional = _D(str(remainder)) * _D(str(price))
        fails_notional = close_notional < min_notional or remainder_notional < min_notional

    if fails_lot_size or fails_notional:
        qty = total_qty
    else:
        qty = close_qty
    return price, qty


# --------------------------------------------------------------------------
# BOT
# --------------------------------------------------------------------------

class TradingBot:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.log = setup_logger(cfg)
        self.ex = ExchangeGateway(cfg, self.log)
        self.notify = TelegramNotifier(cfg, self.log)
        self.state = BotState.load(cfg.state_file)

    def save_state(self):
        self.state.save(self.cfg.state_file)

    # ---------------------------------------------------------------
    def reconcile_on_startup(self):
        """
        Runs ONCE before the main loop starts. Compares saved state against the ACTUAL
        exchange state (live position + ALL open orders for the symbol, not just the
        order IDs bot_state.json happens to remember) and rebuilds internal state around
        that ground truth.

        This closes the specific, real gap where a crash between opening a position and
        placing its protective orders would otherwise cause the bot to blindly re-place a
        SECOND, duplicate set of SL/TP on restart - or where a trade that fully closed
        while the bot was down would leave it stuck thinking a trade is still active.
        """
        self.log.info("Running startup reconciliation against Binance...")
        try:
            pos_amt = self.ex.get_position_amt()
            open_orders = self.ex.get_open_orders()
            own_orders = [o for o in open_orders
                          if str(o.get("clientOrderId", "")).startswith(CLIENT_ORDER_ID_PREFIX)]
            foreign_orders = [o for o in open_orders if o not in own_orders]
            own_order_ids = {o["orderId"] for o in own_orders}
        except Exception as e:
            self.log.error(f"Startup reconciliation could not reach Binance: {e}. "
                            f"Proceeding with saved state as-is; will keep retrying via normal ticks.")
            self.notify.send(f"⚠️ Startup reconciliation failed to reach Binance: {e}\n"
                              f"Proceeding cautiously with saved state - watch closely.")
            return

        if foreign_orders:
            self.log.warning(f"Reconciliation: found {len(foreign_orders)} order(s) on "
                              f"{self.cfg.symbol} that this bot did NOT place (no matching "
                              f"clientOrderId prefix) - leaving them completely untouched. "
                              f"This bot assumes exclusive control of this symbol; if you're "
                              f"placing orders manually on it too, that assumption breaks.")
            self.notify.send(f"⚠️ Found {len(foreign_orders)} order(s) on {self.cfg.symbol} "
                              f"this bot didn't place - left untouched, but this bot expects "
                              f"exclusive control of the symbol it trades.")

        if abs(pos_amt) < QTY_EPSILON:
            if self.state.status == "ENTRIES_PLACED" and (
                self.state.entry1_order_id in own_order_ids
                or self.state.entry2_order_id in own_order_ids
            ):
                self.log.info("Reconciliation: pending entry order(s) from before restart "
                               "are still live - resuming normal wait for fill.")
                self.notify.send(f"🔄 Bot resumed - {self.state.direction} entries from before "
                                  f"restart are still pending on {self.cfg.symbol}.")
                return

            # Flat, and either nothing was pending or what was pending is gone now.
            if own_order_ids:
                self.log.warning(f"Reconciliation: found {len(own_order_ids)} of the bot's OWN "
                                  f"stray open order(s) with no position behind them - cancelling.")
                for oid in own_order_ids:
                    self.ex.cancel_order(oid)
            if self.state.status != "IDLE":
                self.log.info(f"Reconciliation: the {self.state.direction} trade on {self.cfg.symbol} "
                               f"resolved while the bot was down (reached TP level {self.state.tp_level}). "
                               f"Resetting to IDLE.")
                self.notify.send(f"🔄 Bot resumed - the {self.state.direction} trade on "
                                  f"{self.cfg.symbol} closed while the bot was down "
                                  f"(reached TP level {self.state.tp_level}). Back to IDLE.")
            else:
                self.log.info("Reconciliation: flat, matches saved state. Nothing to do.")
            self.state.reset()
            self.save_state()
            return

        # A real position exists on the exchange right now - rebuild around it.
        # Wrapped defensively: this runs once, OUTSIDE the main loop's try/except, so a
        # failure here (e.g. a transient network blip mid-reconciliation) must never be
        # allowed to crash the whole process on startup. If something does go wrong, log
        # and notify, then fall through to the normal loop - _monitor_position's own
        # checks will pick up and self-heal on the very next tick regardless.
        try:
            actual_direction = "LONG" if pos_amt > 0 else "SHORT"
            entry_price = self.ex.get_position_entry_price()

            self.log.warning(f"Reconciliation: found an OPEN {actual_direction} position on "
                              f"{self.cfg.symbol} (qty {abs(pos_amt):.6f}, entry {entry_price:.2f}). "
                              f"Clearing this bot's own existing orders and placing fresh protective orders.")
            for oid in own_order_ids:
                self.ex.cancel_order(oid)

            state_matches = (self.state.direction == actual_direction and self.state.atr_at_signal is not None)
            if state_matches:
                self.log.info(f"Saved direction/ATR match the live position - keeping "
                               f"tp_level={self.state.tp_level} (ladder progress preserved).")
            else:
                self.log.warning("Saved state didn't match the live position (or was missing/corrupted) "
                                  "- resetting ladder progress to level 0. The ORIGINAL frozen ATR from "
                                  "signal time can't be recovered once state is lost, so recomputing a "
                                  "fresh ATR from current market data as the best available approximation.")
                try:
                    df = self.ex.get_closed_klines()
                    df_ind = build_indicator_frame(
                        df, alma_window=self.cfg.alma_window, rsi_period=self.cfg.rsi_period,
                        rsi_sma_period=self.cfg.rsi_sma_period, atr_period=self.cfg.atr_period,
                        adx_period=self.cfg.adx_period, trend_sma_period=self.cfg.trend_sma_period,
                    )
                    fresh_atr = float(df_ind.iloc[-1]["atr"])
                except Exception as e:
                    fresh_atr = entry_price * 0.02
                    self.log.error(f"Could not recompute a fresh ATR ({e}); using a conservative "
                                    f"fallback of 2% of entry price ({fresh_atr:.2f}) instead.")
                self.state.direction = actual_direction
                self.state.atr_at_signal = fresh_atr
                self.state.tp_level = 0

            self.state.status = "IN_POSITION"
            self.state.entry1_order_id = None
            self.state.entry2_order_id = None
            self.state.sl_order_id = None
            self.state.tp_order_id = None

            self._place_or_update_protective_orders(entry_price, pos_amt)
            self.save_state()
            self.notify.send(f"🔄 Bot resumed - found an open {actual_direction} position on "
                              f"{self.cfg.symbol} (qty {abs(pos_amt):.6f}). Fresh protective orders placed. "
                              f"Ladder level: {self.state.tp_level}"
                              + (" (preserved)" if state_matches else " (reset - saved state was out of sync)"))
        except Exception as e:
            self.log.exception(f"Startup reconciliation hit an unexpected error while rebuilding "
                                f"around an open position: {e}. NOT crashing - proceeding into the "
                                f"normal loop, which will retry/self-heal on the next tick.")
            self.notify.send(f"⚠️ Startup reconciliation hit an error on {self.cfg.symbol}: {e}\n"
                              f"The bot did NOT crash and will keep retrying via normal ticks - "
                              f"watch closely until this resolves.")

    # ---------------------------------------------------------------
    def run_forever(self):
        self.ex.sync_clock()
        try:
            self.ex.setup_symbol()
        except Exception as e:
            # Unlike reconciliation, a setup_symbol() failure (e.g. hedge mode detected)
            # is intentionally allowed to stop the bot - trading with a broken position
            # model would be worse than not trading at all. But make sure the user
            # actually finds out why, via Telegram, before the process dies - a bare
            # stderr traceback is easy to miss if this is running headless/remote.
            self.log.exception(f"Startup setup failed - the bot will NOT start trading: {e}")
            self.notify.send(f"🛑 Bot could NOT start on {self.cfg.symbol}: {e}\n"
                              f"This needs to be fixed before the bot can safely trade.")
            raise
        self.log.info(f"Bot started. State on load: {self.state}")
        try:
            self.reconcile_on_startup()
        except Exception as e:
            # Belt-and-suspenders: reconcile_on_startup() has its own internal error
            # handling, but this outer guard ensures that ABSOLUTELY NOTHING that could
            # go wrong during one-time startup reconciliation is ever allowed to crash
            # the process before the main loop (with its own per-tick recovery) even
            # starts. Worse case here is starting with an unreconciled state, which the
            # normal tick loop's own self-healing checks will correct on the next cycle.
            self.log.exception(f"Startup reconciliation failed unexpectedly and was caught "
                                f"at the outermost level: {e}. Proceeding into the main loop anyway.")
            self.notify.send(f"⚠️ Startup reconciliation failed unexpectedly on {self.cfg.symbol}: "
                              f"{e}\nBot did NOT crash and is proceeding into normal operation.")
        self.notify.send(f"🤖 Bot started on {self.cfg.symbol} ({self.cfg.interval}). "
                          f"State after reconciliation: {self.state.status}"
                          + (f", {self.state.direction} trade in progress" if self.state.direction else "."))
        while True:
            try:
                self.tick()
            except Exception as e:
                self.log.exception(f"Unhandled error in tick(): {e}")
                self.notify.send(f"⚠️ Bot error on {self.cfg.symbol}: {e}\nBot will keep retrying.")
            time.sleep(self.cfg.poll_seconds)

    # ---------------------------------------------------------------
    def tick(self):
        # Pick up any dashboard config edits. symbol/interval only apply while IDLE -
        # never repoint a live trade's market/timeframe out from under itself.
        self.cfg.reload_editable(allow_symbol_interval_change=(self.state.status == "IDLE"))

        df = self.ex.get_closed_klines()
        if len(df) < max(self.cfg.alma_window, self.cfg.rsi_period + self.cfg.rsi_sma_period,
                          self.cfg.atr_period, self.cfg.adx_period, self.cfg.trend_sma_period) + 5:
            self.log.info("Not enough candle history yet, waiting...")
            self._write_live_status()
            return
        df_ind = build_indicator_frame(
            df, alma_window=self.cfg.alma_window, rsi_period=self.cfg.rsi_period,
            rsi_sma_period=self.cfg.rsi_sma_period, atr_period=self.cfg.atr_period,
            adx_period=self.cfg.adx_period, trend_sma_period=self.cfg.trend_sma_period,
        )
        last_row = df_ind.iloc[-1]
        last_candle_time = int(df["open_time"].iloc[-1])

        if self.state.status in ("ENTRIES_PLACED", "IN_POSITION"):
            self._check_opposite_signal(df_ind)

        if self.state.status == "IDLE":
            self._check_for_new_signal(df_ind, last_row, last_candle_time)
        elif self.state.status == "ENTRIES_PLACED":
            self._monitor_entries(last_row)
        elif self.state.status == "IN_POSITION":
            self._monitor_position()

        self._write_live_status(last_row)

    # ---------------------------------------------------------------
    def _write_live_status(self, last_row=None):
        """Snapshot everything the dashboard needs into a small JSON file. Best-effort -
        a failure here must never take down the trading loop itself."""
        try:
            try:
                mark_price = self.ex.get_current_price()
            except Exception:
                mark_price = None
            try:
                balance = self.ex.get_available_balance()
            except Exception:
                balance = None

            pos_amt = 0.0
            entry_price = 0.0
            unrealized_pnl = None
            if self.state.status != "IDLE":
                pos_amt = self.ex.get_position_amt()
                if pos_amt:
                    entry_price = self.ex.get_position_entry_price()
                    if mark_price:
                        unrealized_pnl = (mark_price - entry_price) * pos_amt

            current_adx = None
            if last_row is not None and "adx" in last_row and pd.notna(last_row["adx"]):
                current_adx = float(last_row["adx"])

            snapshot = {
                "timestamp": time.time(),
                "symbol": self.cfg.symbol,
                "interval": self.cfg.interval,
                "leverage": self.cfg.leverage,
                "bot_status": self.state.status,
                "direction": self.state.direction,
                "tp_level": self.state.tp_level,
                "position_amt": pos_amt,
                "entry_price": entry_price,
                "mark_price": mark_price,
                "unrealized_pnl": unrealized_pnl,
                "available_balance": balance,
                "atr_at_signal": self.state.atr_at_signal,
                "current_adx": current_adx,
                "adx_filter_enabled": self.cfg.adx_filter_enabled,
                "adx_threshold": self.cfg.adx_threshold,
                "sl_order_id": self.state.sl_order_id,
                "tp_order_id": self.state.tp_order_id,
                "sl_price": None, "sl_qty": None,
                "tp_price": None, "tp_qty": None,
            }
            for label, oid in (("sl", self.state.sl_order_id), ("tp", self.state.tp_order_id)):
                if oid:
                    o = self.ex.get_order_status(oid)
                    if o:
                        price = o.get("stopPrice") if float(o.get("stopPrice", 0) or 0) else o.get("price")
                        snapshot[f"{label}_price"] = float(price) if price else None
                        snapshot[f"{label}_qty"] = float(o.get("origQty", 0))

            atomic_write_json(self.cfg.live_status_file, snapshot)
        except Exception as e:
            self.log.warning(f"Could not write live status snapshot: {e}")


    # ---------------------------------------------------------------
    def _check_opposite_signal(self, df_ind):
        """
        Never hold through a trend reversal. If a fresh candle closes against the
        current trade's direction before SL/TP fired naturally, flip immediately:
        market-close the whole position, cancel every order tied to this trade, and
        reset to IDLE. `tick()` then falls through to `_check_for_new_signal` in this
        SAME cycle, so the new opposite trade opens right away rather than waiting
        for another candle.
        """
        signal = compute_signal(df_ind)
        if signal is None or signal == self.state.direction:
            return

        pos_amt = self.ex.get_position_amt()
        old_direction = self.state.direction
        if abs(pos_amt) >= QTY_EPSILON:
            self.log.info(f"Opposite signal ({signal}) seen while in a {self.state.direction} "
                           f"trade. Flipping: market-closing entire position (qty {abs(pos_amt):.6f}).")
            self.notify.send(f"🔄 Trend reversal detected on {self.cfg.symbol}\n"
                              f"Closing {old_direction} position (qty {abs(pos_amt):.6f}), "
                              f"then opening {signal}.")
            close_side = SIDE_SELL if self.state.direction == "LONG" else SIDE_BUY
            try:
                confirmed_flat = self._market_close_and_confirm(close_side, abs(pos_amt))
            except Exception as e:
                self.log.error(f"Market-close on trend flip failed, will retry next cycle: {e}")
                self.notify.send(f"⚠️ Market-close failed during trend flip on {self.cfg.symbol}: {e}\n"
                                  f"Will retry next cycle.")
                return
            if not confirmed_flat:
                self.log.warning("Market-close sent but position not confirmed flat yet - "
                                  "will re-check and retry next cycle before opening the new trade.")
                return  # don't reset state yet; try again next tick

        self._cancel_all_remaining_orders()
        self.state.reset()
        self.save_state()
        self.log.info(f"Flip complete - flat and reset. Now clear to open the new {signal} trade.")

    def _market_close_and_confirm(self, close_side: str, qty: float,
                                   max_wait_seconds: float = 10.0, poll_interval: float = 0.5) -> bool:
        """Send the market close, then poll position size until it reads flat (or time out)."""
        self.ex.place_market_close(close_side, qty)
        waited = 0.0
        while waited < max_wait_seconds:
            if abs(self.ex.get_position_amt()) < QTY_EPSILON:
                return True
            time.sleep(poll_interval)
            waited += poll_interval
        return abs(self.ex.get_position_amt()) < QTY_EPSILON

    # ---------------------------------------------------------------
    def _check_for_new_signal(self, df_ind, last_row, last_candle_time):
        if self.state.signal_candle_time == last_candle_time:
            return  # already acted on this candle

        signal = compute_signal(df_ind)
        if signal is None:
            return

        # Optional trend-strength gate (off by default - your judgment is the default
        # authority). If enabled, a signal that isn't backed by real conviction just
        # means staying flat and re-checking on the next candle - not a rejection, a wait.
        if self.cfg.adx_filter_enabled:
            adx_val = float(last_row["adx"])
            if pd.isna(adx_val) or adx_val < self.cfg.adx_threshold:
                self.log.info(f"{signal} signal seen on candle {last_candle_time} but ADX="
                               f"{adx_val:.1f} is below your threshold ({self.cfg.adx_threshold}). "
                               f"Staying flat - will re-check next candle close.")
                self.notify.send(f"⏸ {signal} signal on {self.cfg.symbol} skipped\n"
                                  f"ADX {adx_val:.1f} below threshold {self.cfg.adx_threshold} - "
                                  f"staying flat, watching for real conviction.")
                self.state.signal_candle_time = last_candle_time  # don't re-log every poll this candle
                self.save_state()
                return

        self.log.info(f"New {signal} signal on candle {last_candle_time}")

        # Re-apply leverage/margin type to the EXCHANGE right before opening a new trade.
        # This is the only place a dashboard leverage change actually reaches Binance -
        # without this, the bot's own sizing math would use the new leverage number while
        # Binance kept applying whatever leverage was set at startup, silently mismatching
        # intended vs actual exposure. Safe to call here since we're flat (IDLE) at this point.
        try:
            self.ex.setup_symbol()
        except Exception as e:
            self.log.error(f"Could not apply current leverage/margin settings before "
                            f"opening trade, skipping this signal: {e}")
            return

        e1, e2 = entry_prices(last_row, signal)
        atr_val = float(last_row["atr"])

        # Defense in depth: never let a degenerate/NaN/non-positive value reach a
        # division or an actual order price, regardless of what upstream checks
        # "should" have already caught. Cheap to check, and the failure mode of
        # skipping one signal is vastly preferable to placing a nonsensical order.
        if not (atr_val > 0) or pd.isna(atr_val):
            self.log.error(f"ATR is invalid ({atr_val}) - skipping this signal rather "
                            f"than risk a degenerate SL/TP.")
            return
        if not (e1 > 0) or not (e2 > 0) or pd.isna(e1) or pd.isna(e2):
            self.log.error(f"Entry price is invalid (e1={e1}, e2={e2}) - skipping this signal.")
            return

        balance = self.ex.get_available_balance()
        margin_fraction, is_aligned = select_margin_fraction(
            signal, float(last_row["close"]), last_row["trend_sma"],
            self.cfg.margin_fraction_per_entry, self.cfg.margin_fraction_counter_trend
        )
        if is_aligned is None:
            self.log.info(f"Trend SMA({self.cfg.trend_sma_period}) not available yet (warmup) - "
                           f"alignment unknown, defaulting to the conservative/counter-trend "
                           f"margin fraction ({margin_fraction:.2%}) rather than assuming full size.")
        else:
            self.log.info(f"{signal} is {'ALIGNED with' if is_aligned else 'AGAINST'} the "
                           f"SMA({self.cfg.trend_sma_period}) trend - using "
                           f"{margin_fraction:.2%} margin per entry.")
        margin_per_entry = balance * margin_fraction
        notional_per_entry = margin_per_entry * self.cfg.leverage

        qty1 = notional_per_entry / e1
        qty2 = notional_per_entry / e2

        min_qty = self.ex.min_qty()
        min_notional = self.ex.min_notional()
        if Decimal(str(qty1)) < min_qty or Decimal(str(qty2)) < min_qty:
            self.log.warning("Computed order quantity below exchange minimum (LOT_SIZE), "
                              "skipping this signal.")
            return
        if min_notional > 0 and Decimal(str(notional_per_entry)) < min_notional:
            self.log.warning(f"Computed order value ({notional_per_entry:.2f}) is below "
                              f"the exchange's minimum notional ({min_notional}) for "
                              f"{self.cfg.symbol} - skipping this signal. Increase leverage, "
                              f"margin fraction, or account balance to clear this floor.")
            return

        side = SIDE_BUY if signal == "LONG" else SIDE_SELL
        order1_id = None
        try:
            order1_id = self.ex.place_entry_limit(side, e1, qty1)
        except Exception as e:
            self.log.error(f"Failed to place entry 1: {e}")
            return

        try:
            order2_id = self.ex.place_entry_limit(side, e2, qty2)
        except Exception as e:
            # CRITICAL: entry1 is already live on the exchange at this point. If we just
            # log and return here without tracking it, it becomes an orphaned order the
            # bot has zero knowledge of - untracked, unprotected if it fills, invisible
            # until the next restart's reconciliation. Roll it back instead: cancel the
            # order we just placed rather than abandon it silently.
            self.log.error(f"Failed to place entry 2 after entry 1 succeeded (id {order1_id}): "
                            f"{e}. Rolling back by cancelling entry 1 rather than leaving it "
                            f"live and untracked.")
            try:
                self.ex.cancel_order(order1_id)
                self.notify.send(f"⚠️ Entry 2 placement failed on {self.cfg.symbol} after entry 1 "
                                  f"succeeded - rolled back by cancelling entry 1. Will retry on "
                                  f"the next signal.")
            except Exception as cancel_err:
                self.log.error(f"Rollback cancel of entry 1 (id {order1_id}) ALSO failed: "
                                f"{cancel_err}. This order may still be live on Binance - "
                                f"check manually. Startup reconciliation will catch this on "
                                f"the next restart regardless.")
                self.notify.send(f"🛑 Entry 2 failed AND rollback cancel of entry 1 also failed "
                                  f"on {self.cfg.symbol} (order id {order1_id}). Please check "
                                  f"Binance manually - this order may still be live.")
            return

        self.state.status = "ENTRIES_PLACED"
        self.state.direction = signal
        self.state.entry1_order_id = order1_id
        self.state.entry2_order_id = order2_id
        self.state.atr_at_signal = atr_val
        self.state.signal_candle_time = last_candle_time
        self.state.tp_level = 0
        self.save_state()
        self.log.info(f"Placed entries: e1={e1:.2f} qty={qty1:.6f} (id {order1_id}), "
                       f"e2={e2:.2f} qty={qty2:.6f} (id {order2_id}), ATR={atr_val:.2f}")
        arrow = "🟢📈" if signal == "LONG" else "🔴📉"
        alignment_note = (f"vs SMA trend: unknown (warmup)" if is_aligned is None
                           else f"vs SMA trend: {'ALIGNED' if is_aligned else 'COUNTER'}")
        self.notify.send(f"{arrow} New {signal} signal on {self.cfg.symbol}\n"
                          f"Entry 1: {e1:.2f}\nEntry 2: {e2:.2f}\nATR: {atr_val:.2f}\n"
                          f"Margin: {margin_fraction:.0%} each ({alignment_note})")

    # ---------------------------------------------------------------
    def _monitor_entries(self, last_row):
        """Waiting for either/both entry limit orders to fill."""
        pos_amt = self.ex.get_position_amt()

        if abs(pos_amt) < QTY_EPSILON:
            # Nothing filled yet. Check whether you manually cancelled both entry
            # orders on Binance directly - if so, release this trade slot back to IDLE
            # instead of waiting forever for orders that no longer exist.
            statuses = []
            for oid in (self.state.entry1_order_id, self.state.entry2_order_id):
                s = self.ex.get_order_status(oid) if oid else None
                statuses.append(s["status"] if s else "UNKNOWN")
            still_live = any(s in ("NEW", "PARTIALLY_FILLED") for s in statuses)
            if not still_live:
                self.log.info(f"Both entry orders no longer live (statuses={statuses}) "
                               f"and no position opened - assuming manual cancel. Resetting to IDLE.")
                self.state.reset()
                self.save_state()
            return  # neither has filled yet, keep waiting

        # At least one entry has filled -> (re)build SL/TP off Binance's own merged entryPrice
        entry_price = self.ex.get_position_entry_price()
        self._place_or_update_protective_orders(entry_price, pos_amt)
        self.state.status = "IN_POSITION"
        self.save_state()
        self.log.info(f"Position opened. amt={pos_amt}, merged entryPrice={entry_price}")
        self.notify.send(f"✅ Position opened on {self.cfg.symbol}\n"
                          f"Direction: {self.state.direction}\n"
                          f"Entry price: {entry_price:.2f}\nQty: {abs(pos_amt):.6f}")

    # ---------------------------------------------------------------
    def _monitor_position(self):
        pos_amt = self.ex.get_position_amt()

        if abs(pos_amt) < QTY_EPSILON:
            # Position fully closed (SL hit, or manually closed) -> clean up and reset
            self.log.info("Position closed. Cleaning up remaining orders and resetting state.")
            self.notify.send(f"⏹ Position closed on {self.cfg.symbol} "
                              f"({self.state.direction}, reached TP level {self.state.tp_level}). "
                              f"Bot back to IDLE, watching for the next signal.")
            self._cancel_all_remaining_orders()
            self.state.reset()
            self.save_state()
            return

        # If position size changed (second entry filled after the first, or TP partial fill),
        # refresh protective orders to match the new size / merged entry price.
        entry_price = self.ex.get_position_entry_price()

        tp_status = self.ex.get_order_status(self.state.tp_order_id) if self.state.tp_order_id else None
        tp_filled = tp_status is not None and tp_status.get("status") == "FILLED"

        if tp_filled:
            self.state.tp_level += 1
            self.log.info(f"TP level {self.state.tp_level} hit — ratcheting SL and advancing "
                           f"to the next ladder level.")
            self._cancel_stale_entry_orders()
            self._place_or_update_protective_orders(entry_price, pos_amt)
            self.save_state()
            self.notify.send(f"🎯 TP level {self.state.tp_level} hit on {self.cfg.symbol}\n"
                              f"SL ratcheted up. Remaining qty: {abs(pos_amt):.6f}")
            return

        # Otherwise just make sure SL/TP sizes still match current position size
        # (2nd entry filled late, or you manually closed part of it by hand on Binance).
        self._reconcile_protective_orders(entry_price, pos_amt)

    # ---------------------------------------------------------------
    def _place_or_update_protective_orders(self, entry_price: float, pos_amt: float):
        """
        Fully derived from self.state.tp_level, so this same function handles the very
        first SL/TP placement AND every ratchet step of the ladder. With the CURRENT
        defaults (tp_custom_levels="0.5", tp_step_atr=0.5, sl_trail_gap_atr=0.5,
        sl_atr_multiple=1.0, tp_close_fraction=0.30) - verified against the live
        Config class, not hardcoded here as a separate claim:
          tp_level=0 -> SL = entry -/+ 1.0x ATR (original stop),  TP1 pending at 0.5x ATR
          tp_level=1 -> SL = entry (breakeven),                    TP2 pending at 1.0x ATR
          tp_level=2 -> SL = TP2's price - 0.5x ATR,               TP3 pending at 1.5x ATR
          tp_level=3 -> SL = TP3's price - 0.5x ATR,               TP4 pending at 2.0x ATR
          ...continuing +0.5x ATR per level, unbounded, each level closing 30% of
          whatever remains, until a trend-reversal flip closes everything.

        These are all dashboard-configurable - if you've changed them, this docstring's
        specific numbers no longer apply, but the MECHANISM they describe still does.
        """
        direction = self.state.direction
        atr_val = self.state.atr_at_signal
        close_side = SIDE_SELL if direction == "LONG" else SIDE_BUY
        total_qty = abs(pos_amt)
        min_qty = self.ex.min_qty()
        min_notional = self.ex.min_notional()
        try:
            custom_levels = parse_tp_custom_levels(self.cfg.tp_custom_levels)
        except ValueError as e:
            self.log.error(f"Invalid tp_custom_levels ('{self.cfg.tp_custom_levels}'): {e}. "
                            f"Falling back to the current default (0.5) for this cycle.")
            custom_levels = [0.5]

        sl_price = sl_price_for_tp_level(entry_price, atr_val, direction, self.state.tp_level,
                                          custom_levels, self.cfg.tp_step_atr,
                                          self.cfg.sl_atr_multiple, self.cfg.sl_trail_gap_atr)
        tp_price, tp_qty = next_tp_price_and_qty(
            entry_price, atr_val, direction, self.state.tp_level, total_qty, min_qty,
            custom_levels, self.cfg.tp_step_atr, self.cfg.tp_close_fraction, min_notional
        )

        old_sl_id = self.state.sl_order_id
        old_tp_id = self.state.tp_order_id

        # CRITICAL ORDERING: place the NEW protective orders FIRST, and only cancel the
        # OLD ones once the new ones are confirmed live. Doing it the other way around
        # (cancel-then-place) leaves a real window - however brief - where the position
        # has NO stop-loss at all on the exchange, and if the new placement then fails
        # for any reason (rate limit, transient API error, margin/rounding issue), that
        # window has no fallback. Having both an old and a new SL briefly overlap is
        # harmless (Binance's reduce-only semantics cap fills at the actual position
        # size, so there's no double-close risk) - having NEITHER is not.
        try:
            new_sl_id = self.ex.place_stop_market(close_side, sl_price, total_qty)
        except Exception as e:
            self.log.error(f"Failed to place new SL - leaving the OLD SL in place untouched: {e}")
            self.notify.send(f"⚠️ Could not update SL on {self.cfg.symbol} - your PREVIOUS "
                              f"SL is still active and protecting the position: {e}")
            return  # do NOT touch old_sl_id/old_tp_id; retry again next cycle

        new_tp_id = None
        try:
            new_tp_id = self.ex.place_tp_limit(close_side, tp_price, tp_qty)
        except Exception as e:
            self.log.error(f"New SL placed OK, but failed to place new TP - "
                            f"keeping the OLD TP in place as a fallback: {e}")
            self.notify.send(f"⚠️ SL updated on {self.cfg.symbol}, but the next TP level "
                              f"failed to place - will retry next cycle: {e}")

        # Only now, with the new SL confirmed live (and new TP too, if it succeeded),
        # cancel the old orders.
        if old_sl_id:
            self.ex.cancel_order(old_sl_id)
        if old_tp_id and new_tp_id is not None:
            self.ex.cancel_order(old_tp_id)
        # else: TP placement failed above - deliberately leave old_tp_id alive as a
        # fallback and keep state.tp_order_id pointing at it; the next tick will retry.

        self.state.sl_order_id = new_sl_id
        if new_tp_id is not None:
            self.state.tp_order_id = new_tp_id
            self.log.info(f"Protective orders set: SL={sl_price:.2f} (qty {total_qty:.6f}), "
                           f"next TP (level {self.state.tp_level + 1})={tp_price:.2f} (qty {tp_qty:.6f})")
        else:
            self.log.warning(f"SL updated to {sl_price:.2f} (qty {total_qty:.6f}), but TP placement "
                              f"failed - old TP order {old_tp_id} remains active as fallback.")

    def _reconcile_protective_orders(self, entry_price: float, pos_amt: float):
        """If position size changed without a TP fill causing it (2nd entry filled late,
        or a manual partial close on Binance), resize SL/TP to match - same price logic,
        just recomputed against the current actual quantity."""
        total_qty = abs(pos_amt)

        # Tolerance here must be based on the symbol's actual LOT_SIZE step, not a tiny
        # fixed epsilon: origQty on the exchange is always quantized to that step, while
        # total_qty (from live position data) is not, so some difference up to about one
        # step is completely normal and must NOT trigger an unnecessary refresh - only a
        # difference bigger than that means the position size actually changed.
        try:
            qty_tolerance = float(self.ex.qty_step()) * 1.5
        except Exception:
            qty_tolerance = 1e-6  # conservative fallback if the filter lookup itself fails

        sl_status = self.ex.get_order_status(self.state.sl_order_id) if self.state.sl_order_id else None
        needs_refresh = (
            sl_status is None
            or sl_status.get("status") not in ("NEW", "PARTIALLY_FILLED")
            or abs(float(sl_status.get("origQty", 0)) - total_qty) > qty_tolerance
        )
        if needs_refresh:
            self.log.info("Position size changed without a TP fill (late 2nd entry fill, or "
                           "a manual partial close) - resizing protective orders.")
            self._place_or_update_protective_orders(entry_price, pos_amt)

    def _cancel_stale_entry_orders(self):
        for oid in (self.state.entry1_order_id, self.state.entry2_order_id):
            if oid:
                status = self.ex.get_order_status(oid)
                if status and status.get("status") == "NEW":
                    self.ex.cancel_order(oid)

    def _cancel_all_remaining_orders(self):
        for oid in (self.state.entry1_order_id, self.state.entry2_order_id,
                    self.state.sl_order_id, self.state.tp_order_id):
            if oid:
                self.ex.cancel_order(oid)


# --------------------------------------------------------------------------
if __name__ == "__main__":
    cfg = Config.load()  # reads config.json (created with defaults on first run)
    if not cfg.api_key or not cfg.api_secret:
        raise SystemExit(
            "Set BINANCE_API_KEY and BINANCE_API_SECRET environment variables before running.\n"
            "cfg.testnet is currently set to True — confirm this in config.json before going live."
        )
    bot = TradingBot(cfg)
    bot.run_forever()
