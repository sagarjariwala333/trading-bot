# Order Management Layer: Bug Analysis & Fixes

## Overview
The bot has 4 critical order management issues that create a cascade of failures. These are not strategy bugs but rather order placement/tracking bugs.

---

## Issue 1: ERROR -2021 "Order would immediately trigger"

### Root Cause

**Location:** `_place_or_update_protective_orders()` → `sl_price_for_tp_level()`

The bot calculates SL prices mathematically but **does not validate** that the calculated price is on the correct side of the market before sending it to Binance.

### Why Binance Returns -2021

For a STOP_MARKET order to be valid:
- **LONG position** with SELL side stop: `stopPrice` must be BELOW current mark price
  - If `stopPrice >= markPrice`, the stop would trigger immediately → -2021 error
- **SHORT position** with BUY side stop: `stopPrice` must be ABOVE current mark price
  - If `stopPrice <= markPrice`, the stop would trigger immediately → -2021 error

### When This Happens

From the logs, this occurs after TP levels hit:

```
22:23:46 | TP level 1 hit
22:23:47 | futures_create_order failed: APIError(code=-2021): Order would immediately trigger.
```

**Scenario:**
1. Bot opens LONG at 64182.30
2. TP1 at 64188.65 hits (price moved UP)
3. Bot calculates: SL = TP1_price - 0.5*ATR = 64188.65 - 6.35 = 64182.30
4. But current mark_price = 64194 (price continued rising)
5. Bot tries to place SELL STOP at 64182.30
6. Since 64182.30 < 64194 (mark price), the stop is below market → would immediately trigger
7. Binance rejects: -2021

### The Bug in Code

**Current code (WRONG):**
```python
def sl_price_for_tp_level(entry: float, atr: float, direction: str, tp_level: int, ...):
    if tp_level == 0:
        return entry - sl_multiple * atr if direction == "LONG" else entry + sl_multiple * atr
    if tp_level == 1:
        return entry
    just_hit_price = tp_ladder_price(...)
    return (just_hit_price - sl_trail_gap * atr if direction == "LONG"
            else just_hit_price + sl_trail_gap * atr)
```

This calculates a price but has **no check** that:
- For LONG/SELL: `return_price < current_mark_price`
- For SHORT/BUY: `return_price > current_mark_price`

### Why This Is Critical

1. **No protection window exists** - Once a TP fills, the price might have moved significantly
2. **Race condition** - The SL price is calculated at cycle start, but price moves before execution
3. **No fallback** - When the order fails, the old SL is still in place (good), but the bot retries every cycle forever

---

## Issue 2: ERROR -2013 "Order does not exist"

### Root Cause

**Location:** `_reconcile_protective_orders()` → `get_order_status()`

When the bot polls an order that no longer exists (filled, cancelled, expired), Binance returns -2013. The bot treats this as a query failure and **retries 3 times**, then **incorrectly interprets** it as "position must have changed."

### Why Binance Returns -2013

1. The order was already filled (partial or full) → removed from open orders
2. The order was manually cancelled on Binance
3. The order expired (GTC orders don't expire, but FOK/IOC would)
4. The order ID is simply wrong (which we fixed in the orderId/algoId bug)

### When This Happens

From logs:

```
22:23:30 | WARNING | futures_get_order failed (attempt 1/3): APIError(code=-2013): Order does not exist.
22:23:32 | WARNING | futures_get_order failed (attempt 3/3): APIError(code=-2013): Order does not exist.
22:23:34 | INFO | Could not fetch order 1000000146025604: APIError(code=-2013): Order does not exist.
22:23:34 | INFO | Position size changed without a TP fill - resizing protective orders.
```

The flow:
1. Bot calls `get_order_status(sl_order_id)`
2. Binance says -2013 "Order does not exist"
3. `_call()` retries 3 times
4. After 3 retries, `get_order_status()` returns None
5. `_reconcile_protective_orders()` sees `sl_status is None` and assumes position size changed
6. It calls `_place_or_update_protective_orders()` again

### The Bug in Code

**Current code (WRONG):**
```python
def get_order_status(self, order_id: int) -> Optional[dict]:
    try:
        return self._call(self.client.futures_get_order, symbol=self.cfg.symbol, orderId=order_id)
    except Exception as e:
        self.log.warning(f"Could not fetch order {order_id}: {e}")
        return None  # ← Returns None for ANY error, including -2013

def _reconcile_protective_orders(self, entry_price: float, pos_amt: float):
    sl_status = self.ex.get_order_status(self.state.sl_order_id) if self.state.sl_order_id else None
    needs_refresh = (
        sl_status is None  # ← Treats ALL query failures as "position changed"
        or sl_status.get("status") not in ("NEW", "PARTIALLY_FILLED")
        or ...
    )
```

The problem: **Can't distinguish between:**
- "Query failed (network issue)" → Retry later
- "Order doesn't exist (already filled/gone)" → Don't try to query again
- "Position size changed" → Need to resize

All three cases return `None`, so the bot can't handle them differently.

---

## Issue 3: ERROR -2011 "Unknown order sent"

### Root Cause

**Location:** `cancel_order()`

When the bot tries to cancel an order that no longer exists, Binance returns -2011. The current code retries this 3 times (via `_call()`), then tries to cancel an "algo order" with the same ID, which also fails.

### Why Binance Returns -2011

- The order was already filled (no longer exists to cancel)
- The order was already cancelled
- The order ID is invalid

### When This Happens

From logs:

```
22:20:06 | futures_cancel_order failed (attempt 1/3): APIError(code=-2011): Unknown order sent.
22:20:08 | futures_cancel_order failed (attempt 2/3): APIError(code=-2011): Unknown order sent.
22:20:11 | futures_cancel_order failed (attempt 3/3): APIError(code=-2011): Unknown order sent.
22:20:13 | futures_cancel_algo_order failed (attempt 1/3): APIError(code=-2011): Unknown order sent.
```

### The Bug in Code

**Current code (WRONG):**
```python
def cancel_order(self, order_id: int):
    if not order_id:
        return
    try:
        self._call(self.client.futures_cancel_order, ...)  # ← Retries 3 times on any error
    except Exception:
        try:
            if hasattr(self.client, "futures_cancel_algo_order"):
                self._call(self.client.futures_cancel_algo_order, ...)  # ← Also retries 3 times
        except Exception as e:
            self.log.info(f"Cancel order {order_id} skipped/failed (likely already gone): {e}")
```

Problems:
1. -2011 is **not retryable** - if the order doesn't exist, it won't magically reappear
2. Trying "algo order" cancel for a regular stop market order is incorrect
3. 6 total API calls (3 retries × 2 attempts) for a single cancel operation

---

## Issue 4: Repeated Position Resize Loop

### Root Cause

**Location:** `_reconcile_protective_orders()` + `get_order_status()` interaction

The bot enters a loop where:
1. It tries to get SL order status
2. The order status query fails (maybe -2013, maybe network)
3. Bot thinks position changed
4. Bot tries to place new SL
5. New SL placement fails (maybe -2021 because price moved)
6. Old SL is retained but marked as possibly stale
7. Loop repeats every 15 seconds

### The Cascade

From logs (all the repeated messages at 15-second intervals):

```
22:23:24 | futures_get_order failed: -2013
22:23:30 | futures_get_order failed: -2013
22:23:34 | INFO | Position size changed - resizing protective orders
22:23:38 | futures_create_order failed: -2021
22:23:47 | TP level 1 hit — ratcheting SL
22:23:50 | futures_create_order failed: -2021
```

### The Bug in Code

**Current code (WRONG):**
```python
def _monitor_position(self):
    pos_amt = self.ex.get_position_amt()
    ...
    tp_status = self.ex.get_order_status(self.state.tp_order_id) if self.state.tp_order_id else None
    
    # This doesn't cache the checked position size, so every query failure 
    # triggers a resize attempt
    self._reconcile_protective_orders(entry_price, pos_amt)

def _reconcile_protective_orders(self, entry_price: float, pos_amt: float):
    # No memory of last successful query
    sl_status = self.ex.get_order_status(self.state.sl_order_id)
    
    needs_refresh = (
        sl_status is None  # ← Query failure treated as "position changed"
        or ...
    )
    if needs_refresh:
        self._place_or_update_protective_orders(...)  # ← Retry placement
```

The bot has **no memory** of:
- When it last successfully placed an SL
- What position size that SL was for
- Whether a query failure was temporary or permanent

---

## Issue 5: General Problems

### Duplicate Orders
- When SL placement fails with -2021, the bot keeps the old SL
- But if the old SL also can't be queried, the bot tries to place a NEW one on the next cycle
- This could create duplicate protective orders if the first placement actually succeeded but the bot didn't see the response

### Stale Order IDs
- If `get_order_status()` fails due to network issue, the bot doesn't know if:
  - The order is still pending (don't touch)
  - The order is already filled (need to update TP level)
  - The order never existed (data corruption)

### Order Lifecycle Gaps
- Entry orders: If entry fills and bot crashes before TP/SL are placed, the position has no protection
- TP orders: If TP fills but bot crashes before cancelling the old SL, next restart might have stale SL ID
- SL orders: If SL fills due to stop loss, bot might not detect it if the -2013 error is treated as network failure

---

## Fixes Summary

### Fix 1: Validate SL Prices Before Placement

**Change:** Add `validate_sl_price()` function that checks:
- For LONG/SELL stop: `sl_price < current_mark_price`
- For SHORT/BUY stop: `sl_price > current_mark_price`

**Why Safe:**
- Only adds validation, doesn't change calculations
- Prevents invalid orders from being sent
- If validation fails, keeps old SL in place and logs warning

### Fix 2: Distinguish Between Query Failures

**Change:** Make `get_order_status()` raise specific exceptions for -2013 vs -2011 vs network errors

**Why Safe:**
- `_reconcile_protective_orders()` only resizes if it gets actual order data
- Network failures are retried, permanent failures (filled/cancelled) are handled gracefully
- Prevents infinite resize loops

### Fix 3: Treat -2011 as Success

**Change:** In `cancel_order()`, catch -2011 specifically and log as "already gone" without retry

**Why Safe:**
- Reduces API calls (6 down to 1 for already-gone orders)
- Prevents wasted retries on non-retriable error codes
- Still falls back to "algo order" cancel if we need to (though we shouldn't need to)

### Fix 4: Cache Position Size After Successful Resize

**Change:** Store `last_resized_qty` in `BotState` after successful `_place_or_update_protective_orders()`

**Why Safe:**
- Only resize if actual position size differs from cached size
- Prevents repeated resize on query failures
- Backwards compatible (will be set on first resize)

### Fix 5: Add Comprehensive Error Handling

**Changes:**
- Log every order operation with before/after IDs
- Detect filled orders from error context
- Handle -2021 with warning, keep old order
- Handle -2013 with smart retry logic
- Handle -2011 as success with log message

---

## Implementation Strategy

1. Add helper functions for validation and error classification
2. Enhance `get_order_status()` to return detailed error info
3. Update `cancel_order()` to handle -2011 specifically
4. Add SL price validation before placement
5. Update `_reconcile_protective_orders()` to use cached position size
6. Add comprehensive logging for debugging

**Testing:**
- All changes are additive (validation only, no logic changes)
- All changes preserve existing order protection (old SL kept if new one fails)
- All changes reduce API calls (fewer retries on non-retriable errors)
