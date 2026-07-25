"""
Core indicator calculations for the HA + ALMA + RSI/SMA + ATR strategy.
Pure pandas/numpy - no exchange dependency, so this can be unit tested standalone.
"""
import numpy as np
import pandas as pd


def heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    """
    df must have columns: open, high, low, close (regular candles).
    Returns a new dataframe with ha_open, ha_high, ha_low, ha_close.
    """
    ha = pd.DataFrame(index=df.index)
    ha_close = (df["open"] + df["high"] + df["low"] + df["close"]) / 4.0

    ha_open = np.empty(len(df))
    ha_open[0] = (df["open"].iloc[0] + df["close"].iloc[0]) / 2.0
    for i in range(1, len(df)):
        ha_open[i] = (ha_open[i - 1] + ha_close.iloc[i - 1]) / 2.0

    ha["ha_open"] = ha_open
    ha["ha_close"] = ha_close
    ha["ha_high"] = pd.concat([df["high"], ha["ha_open"], ha["ha_close"]], axis=1).max(axis=1)
    ha["ha_low"] = pd.concat([df["low"], ha["ha_open"], ha["ha_close"]], axis=1).min(axis=1)
    return ha


def alma(series: pd.Series, window: int = 9, offset: float = 0.85, sigma: float = 6.0) -> pd.Series:
    """
    Arnaud Legoux Moving Average - "standard setting 9" = window 9, offset 0.85, sigma 6
    (these are the universally used TradingView defaults for ALMA(9)).
    """
    m = offset * (window - 1)
    s = window / sigma
    weights = np.array([np.exp(-((i - m) ** 2) / (2 * s * s)) for i in range(window)])
    weights /= weights.sum()

    result = series.rolling(window).apply(
        lambda x: np.dot(x, weights), raw=True
    )
    return result


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi_val = 100 - (100 / (1 + rs))
    rsi_val = rsi_val.where(avg_loss != 0, 100)
    rsi_val = rsi_val.where(~((avg_loss == 0) & (avg_gain == 0)), 50)
    return rsi_val


def sma(series: pd.Series, period: int = 7) -> pd.Series:
    return series.rolling(period).mean()


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Wilder's ATR, computed on the REAL (non-Heikin-Ashi) candles.
    HA ranges are synthetic/smoothed and understate true volatility, so SL/TP
    distance is calculated from the actual market range, not the HA range.
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)

    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Wilder's ADX - direction-agnostic trend STRENGTH (0-100). Doesn't say which way the
    trend is going, only how much real directional conviction is behind it. Computed on
    REAL candles (not Heikin Ashi), same reasoning as ATR - HA smooths away exactly the
    information ADX needs to measure.
    Rough convention: <20 choppy/no real trend, 20-25 developing, >25 confirmed trend,
    >40 strong trend. Used as an optional entry filter, not a directional signal.
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    prev_high = high.shift(1)
    prev_low = low.shift(1)

    up_move = high - prev_high
    down_move = prev_low - low

    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)

    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    atr_ = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    plus_dm_smooth = plus_dm.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    minus_dm_smooth = minus_dm.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    plus_di = 100 * (plus_dm_smooth / atr_)
    minus_di = 100 * (minus_dm_smooth / atr_)

    di_sum = (plus_di + minus_di).replace(0, np.nan)  # avoid div-by-zero on dead-flat data
    dx = 100 * (plus_di - minus_di).abs() / di_sum
    dx = dx.fillna(0.0)

    adx_val = dx.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    return adx_val


def build_indicator_frame(df: pd.DataFrame,
                           alma_window: int = 9,
                           rsi_period: int = 14,
                           rsi_sma_period: int = 7,
                           atr_period: int = 14,
                           adx_period: int = 14,
                           trend_sma_period: int = 50) -> pd.DataFrame:
    """
    df: raw OHLCV with columns open, high, low, close (indexed by candle close time).
    Returns df with all indicator columns needed to generate signals.
    """
    out = df.copy()
    ha = heikin_ashi(df)
    out = pd.concat([out, ha], axis=1)

    out["alma"] = alma(out["ha_close"], window=alma_window)
    out["rsi"] = rsi(out["close"], period=rsi_period)          # RSI on real close (standard practice)
    out["rsi_sma"] = sma(out["rsi"], period=rsi_sma_period)
    out["atr"] = atr(out, period=atr_period)
    out["adx"] = adx(out, period=adx_period)                   # optional entry-strength filter
    out["trend_sma"] = sma(out["close"], period=trend_sma_period)  # real close, for trend-regime sizing

    return out
