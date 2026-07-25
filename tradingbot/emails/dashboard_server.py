"""
Local dashboard server for the HA/ALMA/RSI/ATR bot.

Run this ALONGSIDE bot.py (same instance directory):
    python dashboard_server.py
Then open http://localhost:8787 (or your configured DASHBOARD_PORT) in a browser.

Deliberately stdlib-only (no Flask) to avoid an extra dependency. It never talks to
Binance directly and never touches your API keys - it only reads/writes the plain files
the bot itself already reads and writes:
    config.json        <- editable settings (read + written by this server)
    live_status.json    <- read-only snapshot the bot writes every poll cycle
    bot_state.json      <- read-only trade state the bot writes every poll cycle
    bot.log             <- read-only, tailed for the log panel

This keeps Binance API access confined to a single process (bot.py), which is the
safer design: one thing holds your keys, one thing calls the exchange.

MULTI-INSTANCE: set BOT_INSTANCE_DIR (same as bot.py) and DASHBOARD_PORT to run a
separate dashboard per running bot instance, e.g.:
    BOT_INSTANCE_DIR=instances/btc  DASHBOARD_PORT=8787 python dashboard_server.py
    BOT_INSTANCE_DIR=instances/gold DASHBOARD_PORT=8788 python dashboard_server.py

SECURITY: this server has no authentication. It binds to 127.0.0.1 (localhost) ONLY
by default, and should stay that way. For remote access, do NOT expose this port
directly to the internet - use a VPN (Tailscale/WireGuard) or a reverse proxy that
handles real authentication and HTTPS (e.g. Caddy/nginx with HTTP Basic Auth + a
certificate). An optional shared-secret token (DASHBOARD_TOKEN env var) is available
below as a minimal extra layer if you place this behind a reverse proxy - it is NOT a
substitute for a real login system, password hashing, sessions, or rate limiting.
"""

import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bot import (Config, EDITABLE_FIELDS, EDITABLE_FIELD_LIMITS, parse_tp_custom_levels,
                  validate_config_field, BOT_INSTANCE_DIR)  # noqa: E402

HOST = os.environ.get("DASHBOARD_HOST", "127.0.0.1")
PORT = int(os.environ.get("DASHBOARD_PORT", "8787"))
DASHBOARD_TOKEN = os.environ.get("DASHBOARD_TOKEN", "")  # optional - see SECURITY note above
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BOT_INSTANCE_DIR, "config.json")
STATUS_PATH = os.path.join(BOT_INSTANCE_DIR, "live_status.json")
STATE_PATH = os.path.join(BOT_INSTANCE_DIR, "bot_state.json")
LOG_PATH = os.path.join(BOT_INSTANCE_DIR, "bot.log")
DASHBOARD_HTML_PATH = os.path.join(BASE_DIR, "dashboard.html")  # the UI itself is shared, not per-instance

if HOST not in ("127.0.0.1", "localhost", "::1"):
    auth_note = ("a shared-secret token gate is configured, but it is still not a "
                 "full authentication system (no hashing, sessions, rate limiting, or "
                 "audit log)" if DASHBOARD_TOKEN else
                 "this server has NO authentication at all")
    print(f"⚠️  WARNING: DASHBOARD_HOST is set to '{HOST}', not localhost, and {auth_note}. "
          f"Use a VPN or a properly authenticated reverse proxy instead of exposing this "
          f"directly - see the module docstring for details.", file=sys.stderr)


def read_json_safe(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def tail_lines(path: str, n: int = 50, chunk_size: int = 8192):
    """
    Returns the last `n` lines of a (potentially very large) log file WITHOUT reading
    the whole file into memory. Seeks backward from the end in chunks, accumulating
    bytes until enough newlines have been found (or the start of the file is reached).
    """
    if not os.path.exists(path):
        return []
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            remaining = f.tell()
            data = b""
            newline_count = 0
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


def json_safe_limits() -> dict:
    return {k: [lo, hi, typ.__name__] for k, (lo, hi, typ) in EDITABLE_FIELD_LIMITS.items()}


def validate_and_coerce(payload: dict) -> tuple:
    """
    Returns (clean_dict, errors_list). Delegates every field to
    bot.validate_config_field() - the SAME validator the bot itself uses when
    re-reading config.json on its own - so there is exactly one definition of "is this
    a legitimate value for this field" shared by both the write-path (here) and the
    read-path (Config.reload_editable), rather than two implementations that could
    quietly drift apart over time.
    """
    clean = {}
    errors = []
    for k, v in payload.items():
        if k not in EDITABLE_FIELDS:
            errors.append(f"Unknown field ignored: {k}")
            continue
        clean_value, error = validate_config_field(k, v)
        if error is not None:
            errors.append(error)
            continue
        clean[k] = clean_value
    return clean, errors


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # keep console quiet; the dashboard has its own log panel

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _token_ok(self) -> bool:
        """
        If DASHBOARD_TOKEN is unset (the default), no gate - preserves the original
        localhost-only, zero-friction behavior. If set, every request (page load and
        API calls alike) must present it via ?token=... or an X-Dashboard-Token header.
        This is a minimal shared-secret check, NOT a real authentication system - no
        hashing, no sessions, no rate limiting, no audit log. See module docstring.
        """
        if not DASHBOARD_TOKEN:
            return True
        parsed = urlparse(self.path)
        query_token = parse_qs(parsed.query).get("token", [None])[0]
        header_token = self.headers.get("X-Dashboard-Token")
        return query_token == DASHBOARD_TOKEN or header_token == DASHBOARD_TOKEN

    def do_GET(self):
        if not self._token_ok():
            self._send_json({"error": "unauthorized - missing or incorrect token"}, 401)
            return
        path = urlparse(self.path).path

        if path == "/" or path == "/index.html":
            if os.path.exists(DASHBOARD_HTML_PATH):
                with open(DASHBOARD_HTML_PATH, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self._send_json({"error": "dashboard.html not found next to dashboard_server.py"}, 500)
            return

        if path == "/api/status":
            status = read_json_safe(STATUS_PATH, {})
            state = read_json_safe(STATE_PATH, {})
            logs = tail_lines(LOG_PATH, 60)
            self._send_json({"live_status": status, "bot_state": state, "logs": logs})
            return

        if path == "/api/config":
            cfg_data = read_json_safe(CONFIG_PATH, Config(config_path=CONFIG_PATH).to_editable_dict())
            self._send_json({"config": cfg_data, "limits": json_safe_limits()})
            return

        self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        if not self._token_ok():
            self._send_json({"error": "unauthorized - missing or incorrect token"}, 401)
            return
        path = urlparse(self.path).path

        if path == "/api/reset-defaults":
            self._handle_reset_defaults()
            return

        if path != "/api/config":
            self._send_json({"error": "not found"}, 404)
            return

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            self._send_json({"error": "invalid JSON body"}, 400)
            return

        clean, errors = validate_and_coerce(payload)

        existing = read_json_safe(CONFIG_PATH, Config(config_path=CONFIG_PATH).to_editable_dict())
        existing.update(clean)

        try:
            from bot import atomic_write_json
            atomic_write_json(CONFIG_PATH, existing)
        except OSError as e:
            self._send_json({"error": f"could not write config.json: {e}"}, 500)
            return

        self._send_json({"config": existing, "warnings": errors, "saved": True})

    def _handle_reset_defaults(self):
        """
        Resets every editable field to the code's built-in defaults, EXCEPT symbol and
        interval - those are instance-specific (this dashboard might be managing the
        Gold instance, not BTC), and a "reset to defaults" button silently flipping a
        running Gold instance's symbol back to BTCUSDT would be a genuinely dangerous
        surprise, not a helpful reset. Everything else (leverage, margin fractions,
        indicator periods, TP ladder, SL settings, ADX, poll interval, Telegram toggle)
        resets to the values shipped in the code.
        """
        current = read_json_safe(CONFIG_PATH, {})
        preserved_symbol = current.get("symbol")
        preserved_interval = current.get("interval")

        defaults = Config(config_path=CONFIG_PATH).to_editable_dict()
        if preserved_symbol is not None:
            defaults["symbol"] = preserved_symbol
        if preserved_interval is not None:
            defaults["interval"] = preserved_interval

        try:
            from bot import atomic_write_json
            atomic_write_json(CONFIG_PATH, defaults)
        except OSError as e:
            self._send_json({"error": f"could not write config.json: {e}"}, 500)
            return

        self._send_json({"config": defaults, "reset": True})


def main():
    if not os.path.exists(CONFIG_PATH):
        Config(config_path=CONFIG_PATH).save_editable()  # seed config.json with defaults

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Dashboard running at http://{HOST}:{PORT}  (Ctrl+C to stop)")
    print(f"Reading/writing: {CONFIG_PATH}")
    print(f"Reading:         {STATUS_PATH}, {STATE_PATH}, {LOG_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down dashboard.")
        server.shutdown()


if __name__ == "__main__":
    main()
