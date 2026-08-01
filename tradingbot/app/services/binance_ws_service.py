import asyncio
import json
import websockets
from typing import AsyncGenerator

class BinanceWebSocketService:
    """Utility service to stream live kline (candlestick) data from Binance Futures.
    
    The service connects to Binance's public futures websocket endpoint and yields
    raw kline dictionaries as they arrive. Consumers (FastAPI websocket handlers)
    can iterate over the async generator to forward data to frontend clients.
    """

    BINANCE_WS_URL = "wss://fstream.binance.com/stream?streams={streams}"

    @staticmethod
    async def stream_klines(symbol: str, interval: str = "1m") -> AsyncGenerator[dict, None]:
        """Connect to Binance and continuously yield kline payloads.
        
        Args:
            symbol: Trading pair symbol, e.g. "BTCUSDT".
            interval: Candle interval accepted by Binance, e.g. "1m", "5m", "1h".
        
        Yields:
            dict: The ``k`` object from Binance's websocket message containing
                  open, high, low, close, timestamps, etc.
        """
        url = BinanceWebSocketService.BINANCE_WS_URL.format(
            streams=f"{symbol.lower()}@kline_{interval}"
        )
        async with websockets.connect(url) as ws:
            while True:
                msg = await ws.recv()
                data = json.loads(msg)
                if "data" in data and "k" in data["data"]:
                    yield data["data"]["k"]
                await asyncio.sleep(0)
