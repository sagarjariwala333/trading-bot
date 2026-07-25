# Root Cause Analysis: Incorrect SL Order ID Storage

## Executive Summary
**The bot is storing `algoId` instead of `orderId` for stop-loss orders.**

The stored value `1000000146021371` is an `algoId` (algorithmic order identifier), not an `orderId`. When the bot later tries to query or cancel this order using `futures_get_order()` or `futures_cancel_order()`, Binance rejects it with "Order does not exist" or "Unknown order sent" because these methods expect `orderId`, not `algoId`.

---

## Root Cause Location

**File:** `app/trading_engine/bot.py`  
**Function:** `place_stop_market()` (lines 753-762)  
**Problematic Code:**

```python
def place_stop_market(self, side: str, stop_price: float, qty: float) -> int:
    order = self._call(
        self.client.futures_create_order,
        symbol=self.cfg.symbol, side=side, type=ORDER_TYPE_STOP_MARKET,
        stopPrice=self.round_price(stop_price),
        quantity=self.round_qty(qty),
        reduceOnly=True,
        newClientOrderId=self._new_client_order_id(),
    )
    return order.get("orderId") or order.get("algoId")  # ❌ BUG: Fallback to algoId
```

**The problematic line 759:**
```python
return order.get("orderId") or order.get("algoId")
```

---

## Why This Is Wrong

1. **Priority Issue:** The code tries `orderId` first, but if it's `None`, `0`, or falsy, it falls back to `algoId`
2. **Wrong Identifier Type:**
   - `orderId` (e.g., `23985160346`) = Standard Binance order identifier used by `futures_get_order()` and `futures_cancel_order()`
   - `algoId` (e.g., `1000000146021371`) = Algorithmic order identifier used by `futures_get_algo_order()` and `futures_cancel_algo_order()`
3. **API Mismatch:** When `futures_get_order()` is called with an `algoId`, Binance rejects it because it expects an `orderId`

---

## Evidence of the Bug

### Comparison: emails/bot.py vs app/trading_engine/bot.py

**emails/bot.py (CORRECT) - Line 740:**
```python
def place_stop_market(self, side: str, stop_price: float, qty: float) -> int:
    order = self._call(
        self.client.futures_create_order,
        symbol=self.cfg.symbol, side=side, type=ORDER_TYPE_STOP_MARKET,
        stopPrice=self.round_price(stop_price),
        quantity=self.round_qty(qty),
        reduceOnly=True,
        newClientOrderId=self._new_client_order_id(),
    )
    return order["orderId"]  # ✅ CORRECT: Always returns orderId
```

**app/trading_engine/bot.py (WRONG) - Line 759:**
```python
def place_stop_market(self, side: str, stop_price: float, qty: float) -> int:
    order = self._call(
        self.client.futures_create_order,
        symbol=self.cfg.symbol, side=side, type=ORDER_TYPE_STOP_MARKET,
        stopPrice=self.round_price(stop_price),
        quantity=self.round_qty(qty),
        reduceOnly=True,
        newClientOrderId=self._new_client_order_id(),
    )
    return order.get("orderId") or order.get("algoId")  # ❌ BUG: Fallback is wrong
```

### Inconsistent Implementations

Compare with other order placement functions in `app/trading_engine/bot.py`:

- **place_entry_limit()** - Line 751: `return order.get("orderId") or order.get("algoId")` (WRONG)
- **place_tp_limit()** - Line 773: `return order["orderId"]` (CORRECT)
- **place_market_close()** - Line 781: `return order["orderId"]` (CORRECT)

Even within the same file, `place_tp_limit()` and `place_market_close()` correctly use `order["orderId"]`, while `place_stop_market()` and `place_entry_limit()` have the dangerous fallback.

---

## The Lifecycle of the Bug

### Step 1: Order Creation (app/trading_engine/bot.py, line 1510)
```python
new_sl_id = self.ex.place_stop_market(close_side, sl_price, total_qty)
```
The returned `new_sl_id` is actually an `algoId` (e.g., `1000000146021371`).

### Step 2: State Persistence (app/trading_engine/bot.py, line 1522)
```python
self.state.sl_order_id = new_sl_id
```
The `algoId` is saved to `self.state.sl_order_id`.

### Step 3: JSON Serialization (app/trading_engine/bot.py, line ~200)
```python
atomic_write_json(self.state_path, asdict(self.state))
```
The state is written to `bot_state.json`:
```json
{
  "sl_order_id": 1000000146021371,
  ...
}
```

### Step 4: Bot Restart / State Loading (app/services/bot_manager.py, line 162)
```python
sl_order_id=state_data.get("sl_order_id"),
```
The `algoId` is loaded back from JSON.

### Step 5: Failed Order Lookup (app/trading_engine/bot.py, line 1560)
```python
sl_status = self.ex.get_order_status(self.state.sl_order_id)
```

**Inside get_order_status() - Line 701:**
```python
return self._call(self.client.futures_get_order, symbol=self.cfg.symbol, orderId=order_id)
```

Binance rejects this because it expects an `orderId`, not an `algoId`:
```
APIError(code=-2013): Order does not exist.
```

### Step 6: Failed Order Cancellation (app/trading_engine/bot.py, line 1528)
```python
self.ex.cancel_order(old_sl_id)
```

**Inside cancel_order() - Line 723:**
```python
self._call(self.client.futures_cancel_order, symbol=self.cfg.symbol, orderId=order_id)
```

Binance rejects this:
```
APIError(code=-2011): Unknown order sent.
```

---

## When Does Binance Return an algoId Instead of orderId?

Based on the code structure and the fallback logic, here are the scenarios:

1. **Some Edge Case in the Binance API:** Perhaps under certain conditions (network latency, partial response, etc.), `futures_create_order` might return a response where `orderId` is missing or `None`, and the fallback code was added as a "defensive" measure.

2. **Python-binance Library Version Difference:** Different versions of the `python-binance` package might parse the response differently.

3. **Misunderstanding of Binance API:** Whoever added the `or order.get("algoId")` fallback may have confused the two identifiers and thought this was a safe fallback.

**Most Likely:** The code is **defensively trying to handle a case that shouldn't happen**, and in doing so, it's creating a worse bug by silently using the wrong identifier.

---

## The Fix

### Option 1: Match emails/bot.py (Recommended)
Remove the fallback entirely and always use `orderId`:

```python
def place_stop_market(self, side: str, stop_price: float, qty: float) -> int:
    order = self._call(
        self.client.futures_create_order,
        symbol=self.cfg.symbol, side=side, type=ORDER_TYPE_STOP_MARKET,
        stopPrice=self.round_price(stop_price),
        quantity=self.round_qty(qty),
        reduceOnly=True,
        newClientOrderId=self._new_client_order_id(),
    )
    return order["orderId"]  # ✅ Direct access, fails loudly if missing
```

### Option 2: Defensive with Logging
If you want to keep defensive code, log it clearly:

```python
def place_stop_market(self, side: str, stop_price: float, qty: float) -> int:
    order = self._call(
        self.client.futures_create_order,
        symbol=self.cfg.symbol, side=side, type=ORDER_TYPE_STOP_MARKET,
        stopPrice=self.round_price(stop_price),
        quantity=self.round_qty(qty),
        reduceOnly=True,
        newClientOrderId=self._new_client_order_id(),
    )
    
    # Debug logging
    self.log.info("Raw SL response: %s", order)
    
    order_id = order.get("orderId")
    if not order_id:
        self.log.error(
            "CRITICAL: Binance STOP_MARKET response missing orderId! "
            "Full response: %s. Falling back to algoId=%s (THIS IS WRONG and will fail later)",
            order, order.get("algoId")
        )
        order_id = order.get("algoId")
    
    self.log.info("Saving SL orderId=%s clientOrderId=%s", order_id, order.get("clientOrderId"))
    return order_id
```

**Option 1 is recommended** because:
- It matches the `emails/bot.py` implementation
- It fails fast/loudly if Binance ever returns an unexpected response
- It doesn't silently accept wrong identifiers

---

## Also Check: place_entry_limit()

The same fallback bug exists in `place_entry_limit()` at line 751:

```python
def place_entry_limit(self, side: str, price: float, qty: float) -> int:
    order = self._call(...)
    return order.get("orderId") or order.get("algoId")  # ❌ Same bug
```

While this bug hasn't manifested yet (entry orders are working in your logs), it should be fixed for consistency and to prevent future issues.

---

## Files to Fix

1. **app/trading_engine/bot.py** - Lines 751 and 759
   - `place_entry_limit()` - Line 751
   - `place_stop_market()` - Line 759

2. **(Optional) emails/bot.py** - Check lines 729 and 740
   - These appear to be correct in emails/bot.py but should be verified

---

## Verification Steps

After applying the fix:

1. **Clear the state files:**
   ```bash
   rm data/instances/BTCUSDT/bot_state.json
   rm data/instances/BTCUSDT/live_status.json
   ```

2. **Add debug logging to place_stop_market():**
   ```python
   self.log.info("Raw SL response: %s", order)
   self.log.info("Saving SL orderId=%s", order.get("orderId"))
   ```

3. **Create a new SL order** and verify:
   - The log shows the correct `orderId` (not a 16-digit `algoId`)
   - The bot can successfully query/cancel the order
   - bot_state.json stores the correct `orderId`

4. **Test order status checks:**
   ```python
   sl_status = self.ex.get_order_status(self.state.sl_order_id)
   # Should NOT raise "Order does not exist"
   ```

---

## Summary Table

| Aspect | Current (Wrong) | Should Be |
|--------|-----------------|-----------|
| **place_stop_market() return** | `order.get("orderId") or order.get("algoId")` | `order["orderId"]` |
| **Stored in sl_order_id** | `1000000146021371` (algoId) | `23985160346` (orderId) |
| **futures_get_order() result** | ❌ -2013: Order does not exist | ✅ Valid order status |
| **futures_cancel_order() result** | ❌ -2011: Unknown order sent | ✅ Order cancelled successfully |

---

## Root Cause: Why This Happened

Someone (likely trying to be defensive) added a fallback to `algoId` in `app/trading_engine/bot.py` without realizing that:

1. `algoId` and `orderId` are **different identifier types** for **different API endpoints**
2. Using `algoId` in `futures_get_order()` will always fail
3. The `emails/bot.py` version (which is correct) never needed this fallback

This is a classic example of **defensive coding gone wrong**: the fallback silently accepts an identifier that should never be used, creating a subtle, hard-to-debug bug that only manifests when you try to interact with the order.
