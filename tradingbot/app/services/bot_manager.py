import os
import sys
import subprocess
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from binance.client import Client
from app.core.config import settings
from app.services.database_service import db_service
from app.schemas.bot import BotStateSchema, LiveStatusSchema, BotStatusResponseSchema


class BotManager:
    """Bot management using database-only storage (no file dependencies)."""
    
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
        
        # Fallback check database
        try:
            return symbol_clean in db_service.get_active_bots()
        except Exception:
            return False

    @classmethod
    def start_bot(cls, symbol: str) -> bool:
        symbol_clean = symbol.strip().upper()
        if cls.is_running(symbol_clean):
            return True

        # Ensure bot configuration exists in database
        config = db_service.get_bot_config(symbol_clean)
        if not config:
            # Create default config if none exists
            db_service.save_bot_config(symbol_clean, db_service._get_default_config(symbol_clean))
        
        # Ensure bot state exists in database
        state = db_service.get_bot_state(symbol_clean)
        if not state:
            # Create default state if none exists
            db_service.save_bot_state(symbol_clean, db_service._get_default_state())

        # Mark bot as active in database
        db_service.set_bot_active(symbol_clean, True)

        # Build env variables
        env = os.environ.copy()
        env["BOT_SYMBOL"] = symbol_clean  # Pass symbol via environment
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONPATH"] = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        
        # Inject API keys from Settings if they are set
        if settings.BINANCE_API_KEY:
            env["BINANCE_API_KEY"] = settings.BINANCE_API_KEY
        if settings.BINANCE_API_SECRET:
            env["BINANCE_API_SECRET"] = settings.BINANCE_API_SECRET
        if settings.TELEGRAM_BOT_TOKEN:
            env["TELEGRAM_BOT_TOKEN"] = settings.TELEGRAM_BOT_TOKEN
        if settings.TELEGRAM_CHAT_ID:
            env["TELEGRAM_CHAT_ID"] = settings.TELEGRAM_CHAT_ID
        if settings.DATABASE_URL:
            env["DATABASE_URL"] = settings.DATABASE_URL

        # Launch app/trading_engine/bot.py as a subprocess
        bot_script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "trading_engine", "bot.py"))
        
        # Start process
        process = subprocess.Popen(
            [sys.executable, bot_script_path],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=sys.stderr,
        )
        cls._processes[symbol_clean] = process
        return True

    @classmethod
    def stop_bot(cls, symbol: str) -> bool:
        symbol_clean = symbol.strip().upper()
        # Set active status to False in database
        try:
            db_service.set_bot_active(symbol_clean, False)
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
        
        # 2. Reset state in database
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
            "realized_pnl": 0.0
        }
        
        try:
            db_service.save_bot_state(symbol_clean, default_state)
            db_service.log_event("INFO", f"Bot instance {symbol_clean} cleared and reset", symbol_clean)
        except Exception as e:
            db_service.log_event("ERROR", f"Failed to clear bot instance {symbol_clean}: {e}", symbol_clean)

        return True

    @classmethod
    def _close_binance_positions(cls, symbol_clean: str):
        config = db_service.get_bot_config(symbol_clean) or {}
        testnet = config.get("testnet", True)
        
        api_key = settings.BINANCE_API_KEY
        api_secret = settings.BINANCE_API_SECRET
        if not api_key or not api_secret:
            raise ValueError("BINANCE_API_KEY or BINANCE_API_SECRET is missing from settings.")
            
        client = Client(api_key, api_secret, testnet=testnet)
        
        # Cancel all open orders
        client.futures_cancel_all_open_orders(symbol=symbol_clean)
        
        # Close open positions
        positions = client.futures_position_information(symbol=symbol_clean)
        for pos in positions:
            pos_amt = float(pos["positionAmt"])
            if pos_amt != 0:
                side = 'BUY' if pos_amt < 0 else 'SELL'
                qty = abs(pos_amt)
                client.futures_create_order(
                    symbol=symbol_clean,
                    side=side,
                    type='MARKET',
                    quantity=qty
                )

    @classmethod
    def close_trade(cls, symbol: str) -> bool:
        symbol_clean = symbol.strip().upper()
        was_running = cls.is_running(symbol_clean)
        
        if was_running:
            cls.stop_bot(symbol_clean)

        try:
            cls._close_binance_positions(symbol_clean)
        except Exception as e:
            db_service.log_event("ERROR", f"Failed to close trade on Binance for {symbol_clean}: {e}", symbol_clean)
            raise RuntimeError(f"Failed to close trade on Binance: {e}")

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
            "realized_pnl": 0.0
        }
        
        db_service.save_bot_state(symbol_clean, default_state)
        db_service.log_event("INFO", f"Trade closed and state reset for {symbol_clean}", symbol_clean)
        
        if was_running:
            cls.start_bot(symbol_clean)
            
        return True

    @classmethod
    def reset_bot(cls, symbol: str) -> bool:
        symbol_clean = symbol.strip().upper()
        cls.stop_bot(symbol_clean)

        try:
            cls._close_binance_positions(symbol_clean)
        except Exception as e:
            db_service.log_event("ERROR", f"Failed to close trade during reset for {symbol_clean}: {e}", symbol_clean)
            raise RuntimeError(f"Failed to close trade on Binance during reset: {e}")

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
            "realized_pnl": 0.0
        }
        
        db_service.save_bot_state(symbol_clean, default_state)
        cls.reset_config(symbol_clean)
        
        db_service.log_event("INFO", f"Bot {symbol_clean} has been completely reset", symbol_clean)
        return True

    @classmethod
    def read_json_safe(cls, path: str, default: Any) -> Any:
        if not os.path.exists(path):
            return default
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return default

    @classmethod
    def tail_log_lines(cls, path: str, n: int = 50) -> List[str]:
        if not os.path.exists(path):
            return []
        try:
            with open(path, "rb") as f:
                f.seek(0, os.SEEK_END)
                remaining = f.tell()
                data = b""
                newline_count = 0
                chunk_size = 4096
                while remaining > 0 and newline_count <= n:
                    read_size = min(chunk_size, remaining)
                    remaining -= read_size
                    f.seek(remaining)
                    data = f.read(read_size) + data
                    newline_count = data.count(b"\n")
                text = data.decode("utf-8", errors="replace")
                return text.splitlines()[-n:]
        except OSError:
            return []

    @classmethod
    def get_bot_status(cls, symbol: str, log_lines: int = 50) -> BotStatusResponseSchema:
        symbol_clean = symbol.strip().upper()
        running = cls.is_running(symbol_clean)
        
        # Get state from database
        state_data = db_service.get_bot_state(symbol_clean)
        
        # Get recent logs from database
        logs = []
        try:
            log_entries = db_service.get_recent_logs(symbol_clean, limit=log_lines)
            logs = [f"{entry['timestamp']} [{entry['level']}] {entry['message']}" 
                   for entry in log_entries]
        except Exception:
            logs = ["Database logging not available"]

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

        # Get performance data as live status
        try:
            performance = db_service.get_performance_summary(symbol_clean, days=1)
            live_status = performance if performance else {}
        except Exception:
            live_status = {}

        return BotStatusResponseSchema(
            is_running=running,
            bot_state=bot_state,
            live_status=live_status,
            logs=logs,
        )

    @classmethod
    def get_config(cls, symbol: str) -> Dict[str, Any]:
        symbol_clean = symbol.strip().upper()
        return db_service.get_bot_config(symbol_clean)

    @classmethod
    def update_config(cls, symbol: str, new_config: Dict[str, Any]) -> tuple:
        symbol_clean = symbol.strip().upper()
        
        # Get existing config
        existing = cls.get_config(symbol_clean)
        
        # Validate new config fields
        clean = {}
        errors = []
        
        # Import validation function
        try:
            from app.trading_engine.bot import validate_config_field
            
            for k, v in new_config.items():
                clean_value, error = validate_config_field(k, v)
                if error is not None:
                    errors.append(error)
                    continue
                clean[k] = clean_value
        except ImportError:
            # If validation not available, use values as-is
            clean = new_config
            
        # Update existing config
        existing.update(clean)
        
        try:
            # Save to database
            db_service.save_bot_config(symbol_clean, existing)
            db_service.log_event("INFO", f"Config updated for {symbol_clean}", symbol_clean)
            return existing, errors
        except Exception as e:
            raise RuntimeError(f"Could not save config: {e}")

    @classmethod
    def reset_config(cls, symbol: str) -> Dict[str, Any]:
        symbol_clean = symbol.strip().upper()
        
        # Get current config to preserve symbol and interval
        current = cls.get_config(symbol_clean)
        preserved_symbol = current.get("symbol") or symbol_clean
        preserved_interval = current.get("interval") or "12h"
        
        # Get default config
        defaults = db_service._get_default_config(symbol_clean)
        defaults["symbol"] = preserved_symbol
        defaults["interval"] = preserved_interval
        
        try:
            # Save to database
            db_service.save_bot_config(symbol_clean, defaults)
            db_service.log_event("INFO", f"Config reset to defaults for {symbol_clean}", symbol_clean)
            return defaults
        except Exception as e:
            raise RuntimeError(f"Could not reset config: {e}")
