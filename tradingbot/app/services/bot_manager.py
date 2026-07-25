import os
import sys
import json
import signal
import subprocess
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from app.core.config import settings
from app.trading_engine.bot import Config, validate_config_field, atomic_write_json
from app.schemas.bot import BotStateSchema, LiveStatusSchema, BotStatusResponseSchema
from app.core.db import (
    get_db_config, save_db_config, get_db_state, save_db_state, set_bot_active_status
)


class BotManager:
    # Class-level dictionary to keep track of active subprocesses: {symbol: subprocess.Popen}
    _processes: Dict[str, subprocess.Popen] = {}

    @classmethod
    def get_instance_dir(cls, symbol: str) -> str:
        symbol_clean = symbol.strip().upper()
        dir_path = os.path.join(settings.DATA_DIR, "instances", symbol_clean)
        abs_path = os.path.abspath(dir_path)
        os.makedirs(abs_path, exist_ok=True)
        return abs_path

    @classmethod
    def get_paths(cls, symbol: str) -> Dict[str, str]:
        inst_dir = cls.get_instance_dir(symbol)
        return {
            "config": os.path.join(inst_dir, "config.json"),
            "status": os.path.join(inst_dir, "live_status.json"),
            "state": os.path.join(inst_dir, "bot_state.json"),
            "log": os.path.join(inst_dir, "bot.log"),
        }

    @classmethod
    def is_running(cls, symbol: str) -> bool:
        symbol_clean = symbol.strip().upper()
        process = cls._processes.get(symbol_clean)
        if process is None:
            return False
        # poll() returns None if process is still running
        if process.poll() is None:
            return True
        # Process has terminated, clean it up
        del cls._processes[symbol_clean]
        return False

    @classmethod
    def start_bot(cls, symbol: str) -> bool:
        symbol_clean = symbol.strip().upper()
        if cls.is_running(symbol_clean):
            return True

        paths = cls.get_paths(symbol_clean)
        
        # Restore config and state from DB to local disk if they exist
        db_cfg = get_db_config(symbol_clean)
        if db_cfg:
            atomic_write_json(paths["config"], db_cfg)
        else:
            cfg = Config(config_path=paths["config"])
            cfg.symbol = symbol_clean
            cfg.save_editable()
            save_db_config(symbol_clean, cfg.to_editable_dict())

        db_state = get_db_state(symbol_clean)
        if db_state:
            atomic_write_json(paths["state"], db_state)

        # Mark bot as active in DB
        set_bot_active_status(symbol_clean, True)

        # Build env variables
        env = os.environ.copy()
        env["BOT_INSTANCE_DIR"] = cls.get_instance_dir(symbol_clean)
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

        # Launch app/trading_engine/bot.py as a subprocess
        bot_script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "trading_engine", "bot.py"))
        
        # Start process
        process = subprocess.Popen(
            [sys.executable, bot_script_path],
            env=env,
            cwd=os.path.abspath(settings.DATA_DIR),
            stdout=subprocess.DEVNULL,
            stderr=sys.stderr,
        )
        cls._processes[symbol_clean] = process
        return True

    @classmethod
    def stop_bot(cls, symbol: str) -> bool:
        symbol_clean = symbol.strip().upper()
        if not cls.is_running(symbol_clean):
            return True
        
        process = cls._processes.get(symbol_clean)
        if process:
            try:
                # Send terminate signal, wait briefly, and kill if it hangs
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            except Exception:
                pass
            
            if symbol_clean in cls._processes:
                del cls._processes[symbol_clean]
            
            # Mark bot as inactive in DB
            set_bot_active_status(symbol_clean, False)
            return True
        return False

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
        paths = cls.get_paths(symbol_clean)
        running = cls.is_running(symbol_clean)
        
        # Fallback to local files if DB read returns nothing
        state_data = get_db_state(symbol_clean) or cls.read_json_safe(paths["state"], {})
        status_data = cls.read_json_safe(paths["status"], {})
        logs = cls.tail_log_lines(paths["log"], log_lines)

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
        paths = cls.get_paths(symbol_clean)
        
        # Load from DB primarily
        db_cfg = get_db_config(symbol_clean)
        if db_cfg:
            return db_cfg
            
        # Fallback/create defaults if not exists
        cfg = Config(config_path=paths["config"])
        cfg.symbol = symbol_clean
        cfg.save_editable()
        save_db_config(symbol_clean, cfg.to_editable_dict())
        return cfg.to_editable_dict()

    @classmethod
    def update_config(cls, symbol: str, new_config: Dict[str, Any]) -> tuple:
        symbol_clean = symbol.strip().upper()
        paths = cls.get_paths(symbol_clean)
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
            # Write to both database and local config cache
            save_db_config(symbol_clean, existing)
            atomic_write_json(paths["config"], existing)
            return existing, errors
        except Exception as e:
            raise RuntimeError(f"Could not save config: {e}")

    @classmethod
    def reset_config(cls, symbol: str) -> Dict[str, Any]:
        symbol_clean = symbol.strip().upper()
        paths = cls.get_paths(symbol_clean)
        
        current = cls.get_config(symbol_clean)
        preserved_symbol = current.get("symbol") or symbol_clean
        preserved_interval = current.get("interval") or "12h"
        
        # Load default values
        defaults = Config(config_path=paths["config"]).to_editable_dict()
        defaults["symbol"] = preserved_symbol
        defaults["interval"] = preserved_interval
        
        try:
            # Write to both database and local config cache
            save_db_config(symbol_clean, defaults)
            atomic_write_json(paths["config"], defaults)
            return defaults
        except Exception as e:
            raise RuntimeError(f"Could not reset config: {e}")
