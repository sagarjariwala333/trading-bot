import os
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, Any, List
from app.services.market_data_service import MarketDataService
from app.trading_engine.backtest import run_backtest, Trade
from app.trading_engine.bot import Config
from app.schemas.backtest import (
    BacktestResponseSchema,
    BacktestTradeSchema,
    EquityPointSchema,
    BacktestRequestSchema,
)


class BacktestService:
    @classmethod
    def calculate_max_drawdown(cls, equity_curve: List[float]) -> float:
        if not equity_curve:
            return 0.0
        equity_series = np.array(equity_curve)
        cum_max = np.maximum.accumulate(equity_series)
        drawdowns = (cum_max - equity_series) / cum_max
        return float(np.max(drawdowns) * 100)

    @classmethod
    def run_strategy_backtest(
        cls,
        req: BacktestRequestSchema,
        global_config: Config
    ) -> BacktestResponseSchema:
        # Load dataset
        filepath = MarketDataService.get_dataset_path(req.dataset_name)
        df = MarketDataService.load_kline_dataframe(filepath)

        # Merge requested settings with base config defaults
        cfg = Config(
            api_key="backtest_dummy",
            api_secret="backtest_dummy",
        )
        
        # Overlay any fields explicitly passed in the request
        for field_name in req.model_fields_set:
            if field_name not in ("dataset_name", "starting_balance") and getattr(req, field_name) is not None:
                setattr(cfg, field_name, getattr(req, field_name))
        
        # Override remaining fields from global_config to match bot's current setup
        for attr in [
            "leverage", "margin_fraction_per_entry", "margin_fraction_counter_trend",
            "trend_sma_period", "alma_window", "rsi_period", "rsi_sma_period",
            "atr_period", "sl_atr_multiple", "tp_custom_levels", "tp_step_atr",
            "tp_close_fraction", "sl_trail_gap_atr"
        ]:
            if getattr(cfg, attr) is None or getattr(req, attr) is None:
                setattr(cfg, attr, getattr(global_config, attr))

        # Run backtest
        result = run_backtest(df, cfg, req.starting_balance)

        # Process results
        final_balance = result["final_balance"]
        total_return_pct = (final_balance / req.starting_balance - 1.0) * 100.0

        # Trades
        trades_out: List[BacktestTradeSchema] = []
        wins_count = 0
        losses_count = 0
        close_reasons = {"SL": 0, "TP_FINAL": 0, "REVERSAL": 0}

        for t in result["closed_trades"]:
            if t.realized_pnl > 0:
                wins_count += 1
            else:
                losses_count += 1
                
            reason = t.close_reason or "UNKNOWN"
            close_reasons[reason] = close_reasons.get(reason, 0) + 1

            trades_out.append(
                BacktestTradeSchema(
                    direction=t.direction,
                    signal_time=t.signal_time.isoformat(),
                    entry_price=t.entry_price,
                    qty=t.qty,
                    tp_level=t.tp_level,
                    realized_pnl=t.realized_pnl,
                    fees_paid=t.fees_paid,
                    close_time=t.close_time.isoformat() if t.close_time else None,
                    close_reason=t.close_reason,
                )
            )

        total_trades = len(result["closed_trades"])
        win_rate = (wins_count / total_trades * 100.0) if total_trades > 0 else 0.0

        # Equity Curve points
        equity_points: List[EquityPointSchema] = []
        equity_balances = []
        for ts, bal in result["equity_curve"]:
            equity_points.append(
                EquityPointSchema(timestamp=ts.isoformat(), balance=bal)
            )
            equity_balances.append(bal)

        # Monthly PnL formatted
        monthly_pnl_str = {str(k): float(v) for k, v in result["monthly_pnl"].items()}

        return BacktestResponseSchema(
            dataset_name=req.dataset_name,
            starting_balance=req.starting_balance,
            final_balance=final_balance,
            total_return_pct=total_return_pct,
            total_trades=total_trades,
            win_rate_pct=win_rate,
            wins_count=wins_count,
            losses_count=losses_count,
            monthly_pnl=monthly_pnl_str,
            close_reasons=close_reasons,
            equity_curve=equity_points,
            trades=trades_out,
        )
