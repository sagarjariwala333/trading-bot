"""
Backtest engine for the HA/ALMA/RSI/ATR trading bot.

IMPORTANT - READ BEFORE TRUSTING ANY NUMBER THIS PRODUCES:

1. This reuses the REAL decision functions from bot.py and indicators.py directly
   (compute_signal, entry_prices, tp_ladder_price, sl_price_for_tp_level,
   next_tp_price_and_qty, parse_tp_custom_levels) - not a separate reimplementation
   that could quietly drift from what the live bot actually does.

2. Fill simulation is an APPROXIMATION, not a perfect replay. Working from OHLC candles
   only (no tick-by-tick order book data), a limit order is treated as filled if the
   candle's [low, high] range touches the limit price, filling AT that exact price.
   This is the standard, widely-used backtesting convention, but it is optimistic in
   one specific way real trading isn't: it assumes your resting order gets priority
   and a full fill the instant price touches it, ignoring queue position and partial
   fills. Real results will differ from this, likely modestly worse due to that.

3. Fees are modeled using Binance's current published USDT-M futures schedule (maker
   0.02%, taker 0.05%, standard/non-VIP tier, no BNB discount assumed) - entries and
   TP fills as maker, SL and reversal market-closes as taker.

4. Funding payments (charged every 8 hours on perpetual futures) are NOT modeled.
   This is a real omission, not a rounding error - funding can meaningfully affect
   returns over a year, especially for a strategy holding positions across many
   funding intervals. Historical funding-rate data would be needed to model this
   properly; treat the numbers here as somewhat optimistic on that basis.

5. Slippage is not modeled. Entries/exits fill at the exact computed price.

USAGE:
    python backtest.py --data btcusdt_12h.csv --balance 10000

The CSV must have columns: open_time,open,high,low,close,close_time (same shape as
Binance's own kline format - see download_historical_data.py to fetch this for real).
"""

import argparse
import sys
from collections import defaultdict
from decimal import Decimal

import numpy as np
import pandas as pd

try:
    # Relative imports when loaded as part of the app.trading_engine package
    from .indicators import build_indicator_frame
    from .bot import (
        compute_signal, entry_prices, tp_ladder_price, sl_price_for_tp_level,
        next_tp_price_and_qty, parse_tp_custom_levels, Config,
    )
except ImportError:
    # Fallback: bare imports when backtest.py is executed directly from its directory
    from indicators import build_indicator_frame  # type: ignore
    from bot import (  # type: ignore
        compute_signal, entry_prices, tp_ladder_price, sl_price_for_tp_level,
        next_tp_price_and_qty, parse_tp_custom_levels, Config,
    )

MAKER_FEE = 0.0002   # 0.02%, standard Binance USDT-M futures maker rate
TAKER_FEE = 0.0005   # 0.05%, standard Binance USDT-M futures taker rate
ASSUMED_MIN_QTY = Decimal("0.001")  # BTCUSDT-typical; override per-symbol if needed


def touches(low, high, price):
    return low <= price <= high


class Trade:
    """One full trade lifecycle, from signal to final close, for reporting."""
    def __init__(self, direction, signal_time):
        self.direction = direction
        self.signal_time = signal_time
        self.entry_price = None
        self.qty = 0.0
        self.tp_level = 0
        self.realized_pnl = 0.0
        self.fees_paid = 0.0
        self.close_time = None
        self.close_reason = None  # "SL", "TP_FINAL", "REVERSAL"


def run_backtest(df: pd.DataFrame, cfg: Config, starting_balance: float):
    df_ind = build_indicator_frame(
        df, alma_window=cfg.alma_window, rsi_period=cfg.rsi_period,
        rsi_sma_period=cfg.rsi_sma_period, atr_period=cfg.atr_period,
        adx_period=cfg.adx_period,
    )
    custom_levels = parse_tp_custom_levels(cfg.tp_custom_levels)

    balance = starting_balance
    equity_curve = []  # (timestamp, balance)
    closed_trades = []
    monthly_pnl = defaultdict(float)

    # State machine mirrors bot.py's TradingBot exactly, simplified for backtest fills.
    status = "IDLE"   # IDLE, ENTRIES_PLACED, IN_POSITION
    direction = None
    entry1_price = entry2_price = None
    entry1_filled = entry2_filled = False
    entry1_qty = entry2_qty = 0.0
    merged_entry_price = 0.0
    total_qty = 0.0
    tp_level = 0
    atr_at_signal = None
    sl_price = tp_price = tp_qty = None
    current_trade = None

    min_qty = ASSUMED_MIN_QTY

    for i in range(len(df_ind)):
        row = df_ind.iloc[i]
        ts = df_ind.index[i]
        month_key = ts.strftime("%Y-%m")
        o, h, l, c = row["open"], row["high"], row["low"], row["close"]

        # ---- reversal check (applies while ENTRIES_PLACED or IN_POSITION) ----
        if status in ("ENTRIES_PLACED", "IN_POSITION"):
            sig = compute_signal(df_ind.iloc[:i + 1])
            if sig is not None and sig != direction:
                if status == "IN_POSITION" and total_qty > 0:
                    # Market-close the whole thing at this candle's open (approximation
                    # for "closes promptly once the reversal candle confirms")
                    close_price = o
                    pnl = (close_price - merged_entry_price) * total_qty if direction == "LONG" \
                        else (merged_entry_price - close_price) * total_qty
                    fee = close_price * total_qty * TAKER_FEE
                    balance += pnl - fee
                    monthly_pnl[month_key] += pnl - fee
                    if current_trade:
                        current_trade.realized_pnl += pnl
                        current_trade.fees_paid += fee
                        current_trade.close_time = ts
                        current_trade.close_reason = "REVERSAL"
                        closed_trades.append(current_trade)
                # Reset to idle, will re-enter opposite below in the same bar's IDLE check
                status = "IDLE"
                direction = None
                entry1_filled = entry2_filled = False
                total_qty = 0.0
                tp_level = 0
                current_trade = None

        # ---- IDLE: look for a new signal ----
        if status == "IDLE":
            sig = compute_signal(df_ind.iloc[:i + 1])
            if sig is not None:
                atr_val = row["atr"]
                if pd.notna(atr_val) and atr_val > 0:
                    e1, e2 = entry_prices(row, sig)
                    if e1 > 0 and e2 > 0:
                        margin_each = balance * cfg.margin_fraction_per_entry
                        notional_each = margin_each * cfg.leverage
                        q1 = notional_each / e1
                        q2 = notional_each / e2
                        if Decimal(str(q1)) >= min_qty and Decimal(str(q2)) >= min_qty:
                            status = "ENTRIES_PLACED"
                            direction = sig
                            entry1_price, entry2_price = e1, e2
                            entry1_qty, entry2_qty = q1, q2
                            entry1_filled = entry2_filled = False
                            atr_at_signal = atr_val
                            tp_level = 0
                            current_trade = Trade(direction, ts)
                            continue  # entries can't fill on the same bar they're placed

        # ---- ENTRIES_PLACED: check for fills on this bar ----
        if status == "ENTRIES_PLACED":
            if not entry1_filled and touches(l, h, entry1_price):
                entry1_filled = True
            if not entry2_filled and touches(l, h, entry2_price):
                entry2_filled = True
            if entry1_filled or entry2_filled:
                notional = 0.0
                qty_sum = 0.0
                if entry1_filled:
                    notional += entry1_price * entry1_qty
                    qty_sum += entry1_qty
                    balance -= entry1_price * entry1_qty * MAKER_FEE
                if entry2_filled:
                    notional += entry2_price * entry2_qty
                    qty_sum += entry2_qty
                    balance -= entry2_price * entry2_qty * MAKER_FEE
                merged_entry_price = notional / qty_sum
                total_qty = qty_sum
                current_trade.entry_price = merged_entry_price
                current_trade.qty = total_qty
                status = "IN_POSITION"
                sl_price = sl_price_for_tp_level(merged_entry_price, atr_at_signal, direction,
                                                   tp_level, custom_levels, cfg.tp_step_atr,
                                                   cfg.sl_atr_multiple, cfg.sl_trail_gap_atr)
                tp_price, tp_qty = next_tp_price_and_qty(
                    merged_entry_price, atr_at_signal, direction, tp_level, total_qty,
                    min_qty, custom_levels, cfg.tp_step_atr, cfg.tp_close_fraction
                )

        # ---- IN_POSITION: check SL/TP on this bar ----
        elif status == "IN_POSITION":
            # Late second fill, if it happens after the first
            if direction and ((not entry1_filled) or (not entry2_filled)):
                if not entry1_filled and touches(l, h, entry1_price):
                    entry1_filled = True
                    balance -= entry1_price * entry1_qty * MAKER_FEE
                    new_notional = merged_entry_price * total_qty + entry1_price * entry1_qty
                    total_qty += entry1_qty
                    merged_entry_price = new_notional / total_qty
                if not entry2_filled and touches(l, h, entry2_price):
                    entry2_filled = True
                    balance -= entry2_price * entry2_qty * MAKER_FEE
                    new_notional = merged_entry_price * total_qty + entry2_price * entry2_qty
                    total_qty += entry2_qty
                    merged_entry_price = new_notional / total_qty

            sl_hit = touches(l, h, sl_price)
            tp_hit = touches(l, h, tp_price)

            # If both could trigger on the same bar, treat the worse-case (SL) as
            # happening first - conservative assumption given we can't know intrabar order.
            if sl_hit:
                pnl = (sl_price - merged_entry_price) * total_qty if direction == "LONG" \
                    else (merged_entry_price - sl_price) * total_qty
                fee = sl_price * total_qty * TAKER_FEE
                balance += pnl - fee
                monthly_pnl[month_key] += pnl - fee
                current_trade.realized_pnl += pnl
                current_trade.fees_paid += fee
                current_trade.close_time = ts
                current_trade.close_reason = "SL"
                closed_trades.append(current_trade)
                status = "IDLE"
                direction = None
                total_qty = 0.0
                current_trade = None
            elif tp_hit:
                pnl = (tp_price - merged_entry_price) * tp_qty if direction == "LONG" \
                    else (merged_entry_price - tp_price) * tp_qty
                fee = tp_price * tp_qty * MAKER_FEE
                balance += pnl - fee
                monthly_pnl[month_key] += pnl - fee
                current_trade.realized_pnl += pnl
                current_trade.fees_paid += fee
                total_qty -= tp_qty
                tp_level += 1
                if total_qty < float(min_qty):
                    current_trade.close_time = ts
                    current_trade.close_reason = "TP_FINAL"
                    closed_trades.append(current_trade)
                    status = "IDLE"
                    direction = None
                    total_qty = 0.0
                    current_trade = None
                else:
                    sl_price = sl_price_for_tp_level(merged_entry_price, atr_at_signal, direction,
                                                       tp_level, custom_levels, cfg.tp_step_atr,
                                                       cfg.sl_atr_multiple, cfg.sl_trail_gap_atr)
                    tp_price, tp_qty = next_tp_price_and_qty(
                        merged_entry_price, atr_at_signal, direction, tp_level, total_qty,
                        min_qty, custom_levels, cfg.tp_step_atr, cfg.tp_close_fraction
                    )

        equity_curve.append((ts, balance))

    return {
        "final_balance": balance,
        "equity_curve": equity_curve,
        "closed_trades": closed_trades,
        "monthly_pnl": dict(sorted(monthly_pnl.items())),
    }


def print_report(result, starting_balance):
    print(f"\n{'='*60}\nBACKTEST REPORT\n{'='*60}")
    print(f"Starting balance: {starting_balance:,.2f} USDT")
    print(f"Final balance:    {result['final_balance']:,.2f} USDT")
    total_return = (result['final_balance'] / starting_balance - 1) * 100
    print(f"Total return:     {total_return:+.2f}%")
    print(f"Total trades:     {len(result['closed_trades'])}")

    wins = [t for t in result["closed_trades"] if t.realized_pnl > 0]
    losses = [t for t in result["closed_trades"] if t.realized_pnl <= 0]
    if result["closed_trades"]:
        print(f"Win rate:         {len(wins)/len(result['closed_trades'])*100:.1f}% "
              f"({len(wins)} wins / {len(losses)} losses)")

    print(f"\n{'Month':<10}{'PnL (USDT)':>15}")
    print("-" * 25)
    running = starting_balance
    for month, pnl in result["monthly_pnl"].items():
        print(f"{month:<10}{pnl:>15,.2f}")

    print(f"\nClose reasons: ", end="")
    reasons = defaultdict(int)
    for t in result["closed_trades"]:
        reasons[t.close_reason] += 1
    print(dict(reasons))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="CSV with open_time,open,high,low,close,close_time")
    parser.add_argument("--balance", type=float, default=10000.0)
    args = parser.parse_args()

    raw = pd.read_csv(args.data)
    raw["open_time"] = pd.to_datetime(raw["open_time"], unit="ms" if raw["open_time"].iloc[0] > 1e12 else None)
    df = raw.set_index("open_time")

    cfg = Config(api_key="x", api_secret="y")  # values only, never connects to Binance
    result = run_backtest(df, cfg, args.balance)
    print_report(result, args.balance)
