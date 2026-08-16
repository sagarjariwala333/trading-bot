import asyncio
import json
import logging
import threading
import time
from typing import Optional, Dict, Any, Union

import websockets

TESTNET_WS_BASE = "wss://stream.binancefuture.com"
MAINNET_WS_BASE = "wss://fstream.binance.com"


class BinanceFuturesWebSocketManager:
    """
    Manages background WebSocket streams (User Data Stream and Market Streams)
    for Binance Futures, maintaining an in-memory thread-safe state cache.
    """

    def __init__(self, client: Any, symbol: str, interval: str, testnet: bool = True, logger: Optional[logging.Logger] = None):
        self.client = client
        self.symbol = symbol.strip().upper()
        self.interval = interval.strip()
        self.testnet = testnet
        self.log = logger or logging.getLogger(__name__)

        self.ws_base = TESTNET_WS_BASE if testnet else MAINNET_WS_BASE

        # Thread-safe state cache
        self._lock = threading.Lock()
        self._position_amt: Optional[float] = None
        self._entry_price: Optional[float] = None
        self._available_balance: Optional[float] = None
        self._mark_price: Optional[float] = None
        self._order_statuses: Dict[Union[int, str], dict] = {}
        self._last_ws_update: float = 0.0
        self._is_connected: bool = False

        self._listen_key: Optional[str] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._is_connected

    # ---- Thread-safe state getters ------------------------------------
    def get_position_amt(self) -> Optional[float]:
        with self._lock:
            return self._position_amt

    def get_position_entry_price(self) -> Optional[float]:
        with self._lock:
            return self._entry_price

    def get_available_balance(self) -> Optional[float]:
        with self._lock:
            return self._available_balance

    def get_mark_price(self) -> Optional[float]:
        with self._lock:
            return self._mark_price

    def get_order_status(self, order_id: Union[int, str]) -> Optional[dict]:
        with self._lock:
            if order_id in self._order_statuses:
                return dict(self._order_statuses[order_id])
            str_id = str(order_id)
            if str_id in self._order_statuses:
                return dict(self._order_statuses[str_id])
            return None

    def update_snapshot(self, position_amt: Optional[float] = None, entry_price: Optional[float] = None,
                        available_balance: Optional[float] = None, mark_price: Optional[float] = None):
        """Update cache from REST sync when needed."""
        with self._lock:
            if position_amt is not None:
                self._position_amt = position_amt
            if entry_price is not None:
                self._entry_price = entry_price
            if available_balance is not None:
                self._available_balance = available_balance
            if mark_price is not None:
                self._mark_price = mark_price
            self._last_ws_update = time.time()

    # ---- Lifecycle ----------------------------------------------------
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name=f"WSManager-{self.symbol}")
        self._thread.start()
        self.log.info(f"WebSocketManager background thread started for {self.symbol}.")

    def stop(self):
        self._stop_event.set()
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self.log.info(f"WebSocketManager stopped for {self.symbol}.")

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main_task())
        except Exception as e:
            self.log.error(f"WebSocketManager loop terminated: {e}")
        finally:
            self._loop.close()

    async def _main_task(self):
        user_data_task = asyncio.create_task(self._user_data_stream_loop())
        market_data_task = asyncio.create_task(self._market_data_stream_loop())
        keepalive_task = asyncio.create_task(self._listen_key_keepalive_loop())

        done, pending = await asyncio.wait(
            [user_data_task, market_data_task, keepalive_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()

    # ---- ListenKey Keepalive ------------------------------------------
    async def _listen_key_keepalive_loop(self):
        while not self._stop_event.is_set():
            await asyncio.sleep(1200)  # Ping every 20 minutes (Binance expires in 60 mins)
            if self._listen_key and self.client:
                try:
                    self.log.info(f"[BINANCE REST REQ] -> futures_stream_keepalive(listenKey={self._listen_key})")
                    await asyncio.to_thread(self.client.futures_stream_keepalive, listenKey=self._listen_key)
                    self.log.debug("User Data Stream listenKey keepalive ping sent.")
                except Exception as e:
                    self.log.warning(f"ListenKey keepalive ping failed: {e}")

    # ---- User Data Stream ---------------------------------------------
    async def _get_listen_key(self) -> Optional[str]:
        try:
            self.log.info("[BINANCE REST REQ] -> futures_stream_get_listen_key()")
            res = await asyncio.to_thread(self.client.futures_stream_get_listen_key)
            if isinstance(res, dict) and "listenKey" in res:
                return res["listenKey"]
            elif isinstance(res, str):
                return res
        except Exception as e:
            self.log.error(f"Failed to obtain Binance Futures listenKey: {e}")
        return None

    async def _user_data_stream_loop(self):
        backoff = 2.0
        while not self._stop_event.is_set():
            self._listen_key = await self._get_listen_key()
            if not self._listen_key:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)
                continue

            ws_url = f"{self.ws_base}/ws/{self._listen_key}"
            try:
                self.log.info(f"Connecting to User Data Stream: {ws_url}")
                async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as ws:
                    with self._lock:
                        self._is_connected = True
                    backoff = 2.0
                    self.log.info("User Data Stream connected successfully.")
                    while not self._stop_event.is_set():
                        msg_raw = await ws.recv()
                        msg = json.loads(msg_raw)
                        self._handle_user_data_event(msg)
            except Exception as e:
                with self._lock:
                    self._is_connected = False
                self.log.warning(f"User Data Stream disconnected ({e}). Reconnecting in {backoff:.1f}s...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)

    def _handle_user_data_event(self, msg: dict):
        event_type = msg.get("e")
        if event_type == "ACCOUNT_UPDATE":
            acct_data = msg.get("a", {})
            positions = acct_data.get("P", [])
            balances = acct_data.get("B", [])

            with self._lock:
                for p in positions:
                    if p.get("s") == self.symbol:
                        self._position_amt = float(p.get("pa", 0.0))
                        self._entry_price = float(p.get("ep", 0.0))
                for b in balances:
                    if b.get("a") == "USDT":
                        self._available_balance = float(b.get("wb", b.get("cw", 0.0)))
                self._last_ws_update = time.time()
                self.log.debug(f"WS ACCOUNT_UPDATE -> pos_amt: {self._position_amt}, entry_price: {self._entry_price}")

        elif event_type == "ORDER_TRADE_UPDATE":
            o = msg.get("o", {})
            symbol = o.get("s")
            if symbol == self.symbol:
                order_id = o.get("i")
                client_id = o.get("c")
                status = o.get("X")
                price = float(o.get("p", 0.0))
                stop_price = float(o.get("sp", 0.0))
                avg_price = float(o.get("ap", 0.0))
                orig_qty = float(o.get("q", 0.0))
                executed_qty = float(o.get("z", 0.0))

                parsed_status = {
                    "symbol": symbol,
                    "orderId": order_id,
                    "clientOrderId": client_id,
                    "status": status,
                    "price": price,
                    "stopPrice": stop_price,
                    "avgPrice": avg_price,
                    "origQty": orig_qty,
                    "executedQty": executed_qty,
                    "type": o.get("o"),
                    "side": o.get("S"),
                }
                with self._lock:
                    if order_id:
                        self._order_statuses[order_id] = parsed_status
                        self._order_statuses[str(order_id)] = parsed_status
                    if client_id:
                        self._order_statuses[client_id] = parsed_status
                    self._last_ws_update = time.time()
                self.log.info(f"WS ORDER_TRADE_UPDATE -> orderId: {order_id}, status: {status}, execQty: {executed_qty}")

    # ---- Market Data Stream -------------------------------------------
    async def _market_data_stream_loop(self):
        sym_lower = self.symbol.lower()
        stream_name = f"{sym_lower}@markPrice@1s/{sym_lower}@kline_{self.interval}"
        ws_url = f"{self.ws_base}/stream?streams={stream_name}"

        backoff = 2.0
        while not self._stop_event.is_set():
            try:
                self.log.info(f"Connecting to Market Data Stream: {ws_url}")
                async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as ws:
                    backoff = 2.0
                    self.log.info("Market Data Stream connected successfully.")
                    while not self._stop_event.is_set():
                        msg_raw = await ws.recv()
                        msg = json.loads(msg_raw)
                        data = msg.get("data", msg)
                        self._handle_market_data_event(data)
            except Exception as e:
                self.log.warning(f"Market Data Stream disconnected ({e}). Reconnecting in {backoff:.1f}s...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)

    def _handle_market_data_event(self, data: dict):
        event_type = data.get("e")
        if event_type == "markPriceUpdate":
            price = float(data.get("p", 0.0))
            with self._lock:
                self._mark_price = price
                self._last_ws_update = time.time()

        elif event_type == "kline":
            k = data.get("k", {})
            close_price = float(k.get("c", 0.0))
            with self._lock:
                self._mark_price = close_price
                self._last_ws_update = time.time()
