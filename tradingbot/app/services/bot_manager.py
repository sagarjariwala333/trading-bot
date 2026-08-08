import os
import sys
import subprocess
from typing import Dict, List, Any
from app.core.config import settings, PROJECT_ROOT
from app.trading_engine.bot import Config, validate_config_field
from app.schemas.bot import BotStateSchema, BotStatusResponseSchema
from app.core.db import (
    get_db_config, save_db_config, get_db_state, save_db_state,
    get_db_live_status, delete_db_live_status,
    set_bot_active_status, get_log_lines, clear_log_lines,
)


class BotManager:
    # Class-level dictionary to keep track of active subprocesses: {symbol: subprocess.Popen}
    _processes: Dict[str, subprocess.Popen] = {}

    @classmethod
    def is_running(cls, symbol: str) -> bool:
        symbol_clean = symbol.strip().upper()
        process = cls._processes.get(symbol_clean)
        if process is not None:
            if process.poll() is None:
                return True
            del cls._processes[symbol_clean]

        # Fallback check DB if in-memory dict lost reference due to uvicorn hot-reload
        try:
            from app.core.db import get_active_bots
            return symbol_clean in get_active_bots()
        except Exception:
            return False

    @classmethod
    def start_bot(cls, symbol: str) -> bool:
        symbol_clean = symbol.strip().upper()
        if cls.is_running(symbol_clean):
            return True

        # Ensure a config and an IDLE state exist in the DB so the subprocess has something to load.
        if not get_db_config(symbol_clean):
            cfg = Config(symbol=symbol_clean)
            cfg.save_editable()

        if not get_db_state(symbol_clean):
            default_state = {
                "status": "IDLE",
                "direction": None,
                "entry1_order_id": None,
                "entry2_order_id": None,
                "sl_order_id": None,
                "tp_order_id": None,
                "atr_at_signal": None,
                "signal_candle_time": None,
                "tp_level": 0,
                "last_resized_qty": None,
                "realized_pnl": 0.0,
            }
            save_db_state(symbol_clean, default_state)

        # Mark bot as active in DB
        set_bot_active_status(symbol_clean, True)

        # Build env variables
        env = os.environ.copy()
        env["BOT_SYMBOL"] = symbol_clean
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONPATH"] = os.path.abspath(PROJECT_ROOT)

        # Inject API keys from Settings if they are set
        if settings.BINANCE_API_KEY:
            env["BINANCE_API_KEY"] = settings.BINANCE_API_KEY
        if settings.BINANCE_API_SECRET:
            env["BINANCE_API_SECRET"] = settings.BINANCE_API_SECRET
        if settings.TELEGRAM_BOT_TOKEN:
            env["TELEGRAM_BOT_TOKEN"] = settings.TELEGRAM_BOT_TOKEN
        if settings.TELEGRAM_CHAT_ID:
            env["TELEGRAM_CHAT_ID"] = settings.TELEGRAM_CHAT_ID

        # Launch app/trading_engine/bot.py as a subprocess
        bot_script_path = os.path.join(PROJECT_ROOT, "app", "trading_engine", "bot.py")

        # Start process (cwd = project root so relative paths / imports resolve identically)
        process = subprocess.Popen(
            [sys.executable, bot_script_path],
            env=env,
            cwd=PROJECT_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=sys.stderr,
        )
        cls._processes[symbol_clean] = process
        return True

    @classmethod
    def stop_bot(cls, symbol: str) -> bool:
        symbol_clean = symbol.strip().upper()
        # Always set active status to False in DB first
        try:
            set_bot_active_status(symbol_clean, False)
        except Exception:
            pass

        process = cls._processes.get(symbol_clean)
        if process:
            try:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            except Exception:
                pass

        return True

    @classmethod
    def clear_instance(cls, symbol: str) -> bool:
        symbol_clean = symbol.strip().upper()
        # 1. Stop bot if running
        cls.stop_bot(symbol_clean)

        # 2. Reset state, live status, and logs in the database
        default_state = {
            "status": "IDLE",
            "direction": None,
            "entry1_order_id": None,
            "entry2_order_id": None,
            "sl_order_id": None,
            "tp_order_id": None,
            "atr_at_signal": None,
            "signal_candle_time": None,
            "tp_level": 0,
            "last_resized_qty": None,
            "realized_pnl": 0.0,
        }
        try:
            save_db_state(symbol_clean, default_state)
        except Exception:
            pass

        try:
            delete_db_live_status(symbol_clean)
        except Exception:
            pass

        try:
            clear_log_lines(symbol_clean)
        except Exception:
            pass

        return True

    @classmethod
    def get_bot_status(cls, symbol: str, log_lines: int = 50) -> BotStatusResponseSchema:
        symbol_clean = symbol.strip().upper()
        running = cls.is_running(symbol_clean)

        state_data = get_db_state(symbol_clean)
        status_data = get_db_live_status(symbol_clean)
        logs = get_log_lines(symbol_clean, n=log_lines)

        bot_state = None
        if state_data:
            bot_state = BotStateSchema(
                status=state_data.get("status", "IDLE"),
                direction=state_data.get("direction"),
                entry1_order_id=state_data.get("entry1_order_id"),
                entry2_order_id=state_data.get("entry2_order_id"),
                sl_order_id=state_data.get("sl_order_id"),
                tp_order_id=state_data.get("tp_order_id"),
                atr_at_signal=state_data.get("atr_at_signal"),
                signal_candle_time=state_data.get("signal_candle_time"),
                tp_level=state_data.get("tp_level", 0),
            )

        return BotStatusResponseSchema(
            is_running=running,
            bot_state=bot_state,
            live_status=status_data if status_data else None,
            logs=logs,
        )

    @classmethod
    def get_config(cls, symbol: str) -> Dict[str, Any]:
        symbol_clean = symbol.strip().upper()

        # Load from DB primarily
        db_cfg = get_db_config(symbol_clean)
        if db_cfg:
            return db_cfg

        # Create defaults if not exists
        cfg = Config(symbol=symbol_clean)
        cfg.save_editable()
        return cfg.to_editable_dict()

    @classmethod
    def update_config(cls, symbol: str, new_config: Dict[str, Any]) -> tuple:
        symbol_clean = symbol.strip().upper()
        existing = cls.get_config(symbol_clean)

        clean = {}
        errors = []
        for k, v in new_config.items():
            clean_value, error = validate_config_field(k, v)
            if error is not None:
                errors.append(error)
                continue
            clean[k] = clean_value

        existing.update(clean)

        try:
            save_db_config(symbol_clean, existing)
            return existing, errors
        except Exception as e:
            raise RuntimeError(f"Could not save config: {e}")

    @classmethod
    def reset_config(cls, symbol: str) -> Dict[str, Any]:
        symbol_clean = symbol.strip().upper()

        current = cls.get_config(symbol_clean)
        preserved_symbol = current.get("symbol") or symbol_clean
        preserved_interval = current.get("interval") or "12h"

        # Load default values
        defaults = Config(symbol=symbol_clean).to_editable_dict()
        defaults["symbol"] = preserved_symbol
        defaults["interval"] = preserved_interval

        try:
            save_db_config(symbol_clean, defaults)
            return defaults
        except Exception as e:
            raise RuntimeError(f"Could not reset config: {e}")
