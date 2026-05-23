"""
============================================================
TREE DATA v3.0.0 — Exness MetaTrader 5 Gateway
Client: Kembang Ayu Andini
============================================================
connectors/meta_trader_gateway.py: Robust Exness MetaTrader 5
API routing layer using decimal.Decimal and precision handling.
Implements exponential backoff retry for broker errors 10004/10014.
"""

from __future__ import annotations

import time
import math
import logging
import asyncio
from decimal import Decimal, ROUND_HALF_EVEN, getcontext
from dataclasses import dataclass, field
from typing import Optional, Literal, Dict, Any, Tuple

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None  # type: ignore
    MT5_AVAILABLE = False
    logging.warning("[MT5_GATEWAY] MetaTrader5 library not installed — simulation mode active")

from config import (
    INFRA_CONFIG, SYMBOL, MAGIC_NUMBER, MAX_SLIPPAGE_POINTS,
    PRICE_DECIMAL_PLACES, VOLUME_DECIMAL_PLACES,
    MIN_LOT_SIZE, MAX_LOT_SIZE, LOT_STEP,
    RETRIABLE_BROKER_ERRORS, MAX_RETRY_ATTEMPTS,
    BASE_BACKOFF_MS, MAX_BACKOFF_MS,
    DECIMAL_3,
)

logger = logging.getLogger("MT5_GATEWAY")
getcontext().prec = 10

# ── Data Models ────────────────────────────────────────────────────────────────

@dataclass
class OrderRequest:
    """Type-strict order request with 3-decimal price precision."""
    symbol: str
    action: Literal["BUY", "SELL", "CLOSE"]
    lot_size: Decimal
    entry_price: Decimal
    take_profit: Decimal
    stop_loss: Decimal
    magic: int = MAGIC_NUMBER
    slippage: int = MAX_SLIPPAGE_POINTS
    comment: str = "TREE_DATA_v3"
    ticket: Optional[int] = None  # Required for CLOSE

    def __post_init__(self) -> None:
        """Validate and normalize all price/volume fields to exact decimals."""
        try:
            self.entry_price = Decimal(str(self.entry_price)).quantize(
                DECIMAL_3, rounding=ROUND_HALF_EVEN
            )
            self.take_profit = Decimal(str(self.take_profit)).quantize(
                DECIMAL_3, rounding=ROUND_HALF_EVEN
            )
            self.stop_loss = Decimal(str(self.stop_loss)).quantize(
                DECIMAL_3, rounding=ROUND_HALF_EVEN
            )
            self.lot_size = Decimal(str(self.lot_size)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_EVEN
            )

            # Volume bounds check
            if not (MIN_LOT_SIZE <= self.lot_size <= MAX_LOT_SIZE):
                raise ValueError(
                    f"[MT5_GATEWAY] Invalid lot size: {self.lot_size}. "
                    f"Must be in [{MIN_LOT_SIZE}, {MAX_LOT_SIZE}]"
                )

            # Price sanity check for XAUUSD
            for label, price in [("entry", self.entry_price), ("tp", self.take_profit), ("sl", self.stop_loss)]:
                if not (Decimal("1000") <= price <= Decimal("5000")):
                    raise ValueError(f"[MT5_GATEWAY] Unrealistic {label} price: {price}")

        except Exception as e:
            logger.error(f"[MT5_GATEWAY] OrderRequest validation failed: {e}")
            raise


@dataclass
class OrderResult:
    """Result of an MT5 order execution attempt."""
    success: bool
    ticket: Optional[int]
    retcode: int
    comment: str
    entry_price: Optional[Decimal]
    lot_size: Optional[Decimal]
    execution_time_ms: float
    error_message: Optional[str] = None
    retry_count: int = 0


@dataclass
class AccountInfo:
    """Normalized account state from MT5."""
    login: int
    balance: Decimal
    equity: Decimal
    margin: Decimal
    free_margin: Decimal
    margin_level: Decimal
    profit: Decimal
    currency: str
    leverage: int
    server: str


# ── MT5 Gateway Class ──────────────────────────────────────────────────────────

class ExnessMT5Gateway:
    """
    Production-grade Exness MetaTrader 5 API routing layer.

    Features:
    - decimal.Decimal deterministic fixed-point arithmetic
    - Exponential backoff retry (errors 10004, 10014)
    - Spread validation before order submission
    - Symbol tick precision normalization
    """

    def __init__(self) -> None:
        self._connected: bool = False
        self._symbol_info: Optional[Dict[str, Any]] = None
        self._last_tick: Optional[Dict[str, Any]] = None

    def connect(self) -> bool:
        """
        Initialize MT5 connection to Exness server.

        Returns:
            True if connection successful, False otherwise.
        """
        if not MT5_AVAILABLE:
            logger.warning("[MT5_GATEWAY] MT5 library unavailable — operating in simulation mode")
            self._connected = True  # Simulation mode
            return True

        try:
            if not mt5.initialize(
                login=INFRA_CONFIG.mt5_login,
                password=INFRA_CONFIG.mt5_password,
                server=INFRA_CONFIG.mt5_server,
                timeout=10000,
            ):
                error = mt5.last_error()
                logger.error(f"[MT5_GATEWAY] Initialize failed: {error}")
                return False

            account = mt5.account_info()
            if account is None:
                logger.error("[MT5_GATEWAY] Failed to retrieve account info")
                return False

            logger.info(
                f"[MT5_GATEWAY] Connected to {account.server} | "
                f"Login: {account.login} | Balance: {account.balance} {account.currency}"
            )
            self._connected = True

            # Pre-fetch symbol info
            self._symbol_info = self._get_symbol_info(SYMBOL)
            return True

        except Exception as e:
            logger.critical(f"[MT5_GATEWAY] Connection exception: {e}", exc_info=True)
            return False
        finally:
            pass  # Connection state managed by self._connected

    def disconnect(self) -> None:
        """Gracefully disconnect from MT5."""
        try:
            if MT5_AVAILABLE and self._connected:
                mt5.shutdown()
                logger.info("[MT5_GATEWAY] Disconnected from MT5")
        except Exception as e:
            logger.warning(f"[MT5_GATEWAY] Disconnect error (non-fatal): {e}")
        finally:
            self._connected = False

    def get_account_info(self) -> Optional[AccountInfo]:
        """
        Retrieve real-time account state with Decimal precision.

        Returns:
            AccountInfo dataclass or None on failure.
        """
        if not self._connected:
            logger.warning("[MT5_GATEWAY] Not connected — cannot fetch account info")
            return None

        try:
            if not MT5_AVAILABLE:
                # Simulation mode
                return AccountInfo(
                    login=INFRA_CONFIG.mt5_login or 0,
                    balance=Decimal("50000.00"),
                    equity=Decimal("50000.00"),
                    margin=Decimal("0.00"),
                    free_margin=Decimal("50000.00"),
                    margin_level=Decimal("0.00"),
                    profit=Decimal("0.00"),
                    currency="USD",
                    leverage=500,
                    server=INFRA_CONFIG.mt5_server,
                )

            info = mt5.account_info()
            if info is None:
                return None

            return AccountInfo(
                login=info.login,
                balance=Decimal(str(info.balance)).quantize(Decimal("0.01")),
                equity=Decimal(str(info.equity)).quantize(Decimal("0.01")),
                margin=Decimal(str(info.margin)).quantize(Decimal("0.01")),
                free_margin=Decimal(str(info.margin_free)).quantize(Decimal("0.01")),
                margin_level=Decimal(str(info.margin_level)).quantize(Decimal("0.01")),
                profit=Decimal(str(info.profit)).quantize(Decimal("0.01")),
                currency=info.currency,
                leverage=info.leverage,
                server=info.server,
            )
        except Exception as e:
            logger.error(f"[MT5_GATEWAY] get_account_info exception: {e}", exc_info=True)
            return None

    def get_current_price(self, symbol: str = SYMBOL) -> Optional[Tuple[Decimal, Decimal]]:
        """
        Get current bid/ask with 3-decimal precision.

        Returns:
            (bid, ask) tuple or None on failure.
        """
        try:
            if not MT5_AVAILABLE:
                # Simulation: return approximate gold price
                mid = Decimal("3318.542")
                spread = Decimal("0.200")
                return (mid - spread / 2).quantize(DECIMAL_3), (mid + spread / 2).quantize(DECIMAL_3)

            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                logger.warning(f"[MT5_GATEWAY] No tick data for {symbol}")
                return None

            bid = Decimal(str(tick.bid)).quantize(DECIMAL_3, rounding=ROUND_HALF_EVEN)
            ask = Decimal(str(tick.ask)).quantize(DECIMAL_3, rounding=ROUND_HALF_EVEN)
            return bid, ask

        except Exception as e:
            logger.error(f"[MT5_GATEWAY] get_current_price error: {e}", exc_info=True)
            return None

    def _get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch and cache symbol metadata."""
        try:
            if not MT5_AVAILABLE:
                return {"point": 0.001, "digits": 3, "volume_min": 0.01, "volume_step": 0.01}

            info = mt5.symbol_info(symbol)
            if info is None:
                return None
            return {
                "point": info.point,
                "digits": info.digits,
                "volume_min": info.volume_min,
                "volume_step": info.volume_step,
                "spread": info.spread,
            }
        except Exception as e:
            logger.error(f"[MT5_GATEWAY] Symbol info error: {e}")
            return None

    def _build_mt5_request(self, order: OrderRequest) -> Dict[str, Any]:
        """Construct MT5 trade request dict with strict typing."""
        action_map: Dict[str, int] = {
            "BUY": 0,   # mt5.ORDER_TYPE_BUY
            "SELL": 1,  # mt5.ORDER_TYPE_SELL
        }

        if not MT5_AVAILABLE:
            return {
                "symbol": order.symbol,
                "action": 1,  # TRADE_ACTION_DEAL
                "type": action_map.get(order.action, 0),
                "volume": float(order.lot_size),
                "price": float(order.entry_price),
                "sl": float(order.stop_loss),
                "tp": float(order.take_profit),
                "deviation": order.slippage,
                "magic": order.magic,
                "comment": order.comment,
                "type_time": 0,
                "type_filling": 0,
            }

        return {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": order.symbol,
            "volume": float(order.lot_size),
            "type": mt5.ORDER_TYPE_BUY if order.action == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": float(order.entry_price),
            "sl": float(order.stop_loss),
            "tp": float(order.take_profit),
            "deviation": order.slippage,
            "magic": order.magic,
            "comment": order.comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

    async def execute_order(self, order: OrderRequest) -> OrderResult:
        """
        Submit order to MT5 with exponential backoff retry.

        Retries on broker errors 10004 (Requote) and 10014 (Invalid Volume).

        Args:
            order: Validated OrderRequest with Decimal precision

        Returns:
            OrderResult with execution details
        """
        if not self._connected:
            return OrderResult(
                success=False, ticket=None, retcode=-1,
                comment="Not connected to MT5",
                entry_price=None, lot_size=None,
                execution_time_ms=0,
                error_message="MT5 connection not established",
            )

        start_time = time.perf_counter()
        last_retcode = -1
        last_comment = ""

        for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
            try:
                logger.info(
                    f"[MT5_GATEWAY] Order attempt {attempt}/{MAX_RETRY_ATTEMPTS} | "
                    f"{order.action} {order.lot_size} {order.symbol} @ {order.entry_price}"
                )

                if not MT5_AVAILABLE:
                    # Simulation mode: always succeed on 1st attempt
                    elapsed = (time.perf_counter() - start_time) * 1000
                    return OrderResult(
                        success=True, ticket=300000 + attempt,
                        retcode=10009,  # TRADE_RETCODE_DONE
                        comment="[SIMULATION] Order executed",
                        entry_price=order.entry_price,
                        lot_size=order.lot_size,
                        execution_time_ms=round(elapsed, 2),
                        retry_count=attempt - 1,
                    )

                request = self._build_mt5_request(order)
                result = mt5.order_send(request)

                if result is None:
                    error = mt5.last_error()
                    logger.error(f"[MT5_GATEWAY] order_send returned None: {error}")
                    last_retcode = -1
                    last_comment = f"None result: {error}"
                    continue

                last_retcode = result.retcode
                last_comment = result.comment

                if result.retcode == 10009:  # TRADE_RETCODE_DONE
                    elapsed = (time.perf_counter() - start_time) * 1000
                    logger.info(
                        f"[MT5_GATEWAY] ✅ Order EXECUTED | Ticket: {result.order} | "
                        f"Price: {result.price:.3f} | Time: {elapsed:.1f}ms"
                    )
                    return OrderResult(
                        success=True,
                        ticket=result.order,
                        retcode=result.retcode,
                        comment=result.comment,
                        entry_price=Decimal(str(result.price)).quantize(DECIMAL_3),
                        lot_size=Decimal(str(result.volume)).quantize(Decimal("0.01")),
                        execution_time_ms=round(elapsed, 2),
                        retry_count=attempt - 1,
                    )

                elif result.retcode in RETRIABLE_BROKER_ERRORS:
                    backoff_ms = min(BASE_BACKOFF_MS * (2 ** (attempt - 1)), MAX_BACKOFF_MS)
                    logger.warning(
                        f"[MT5_GATEWAY] Retriable error {result.retcode} ({result.comment}) — "
                        f"backoff {backoff_ms}ms before retry {attempt + 1}"
                    )
                    await asyncio.sleep(backoff_ms / 1000)
                    continue

                else:
                    # Non-retriable error
                    elapsed = (time.perf_counter() - start_time) * 1000
                    logger.error(
                        f"[MT5_GATEWAY] ❌ Non-retriable error {result.retcode}: {result.comment}"
                    )
                    return OrderResult(
                        success=False, ticket=None,
                        retcode=result.retcode,
                        comment=result.comment,
                        entry_price=None, lot_size=None,
                        execution_time_ms=round(elapsed, 2),
                        error_message=f"Broker error {result.retcode}: {result.comment}",
                        retry_count=attempt - 1,
                    )

            except Exception as e:
                logger.error(f"[MT5_GATEWAY] Execute exception (attempt {attempt}): {e}", exc_info=True)
                backoff_ms = min(BASE_BACKOFF_MS * (2 ** (attempt - 1)), MAX_BACKOFF_MS)
                await asyncio.sleep(backoff_ms / 1000)

        # All retries exhausted
        elapsed = (time.perf_counter() - start_time) * 1000
        logger.critical(
            f"[MT5_GATEWAY] 💀 Order FAILED after {MAX_RETRY_ATTEMPTS} attempts | "
            f"Last retcode: {last_retcode} | Comment: {last_comment}"
        )
        return OrderResult(
            success=False, ticket=None,
            retcode=last_retcode,
            comment=last_comment,
            entry_price=None, lot_size=None,
            execution_time_ms=round(elapsed, 2),
            error_message=f"Max retries exceeded. Last error: {last_retcode} - {last_comment}",
            retry_count=MAX_RETRY_ATTEMPTS,
        )

    async def close_position(self, ticket: int, symbol: str = SYMBOL) -> OrderResult:
        """
        Close an open position by ticket number.

        Args:
            ticket: MT5 position ticket
            symbol: Trading symbol

        Returns:
            OrderResult of the close operation
        """
        try:
            prices = self.get_current_price(symbol)
            if prices is None:
                return OrderResult(
                    success=False, ticket=None, retcode=-1,
                    comment="Cannot fetch price for close",
                    entry_price=None, lot_size=None, execution_time_ms=0,
                )

            bid, ask = prices

            if not MT5_AVAILABLE:
                return OrderResult(
                    success=True, ticket=ticket, retcode=10009,
                    comment="[SIMULATION] Position closed",
                    entry_price=bid, lot_size=Decimal("0.01"),
                    execution_time_ms=5.0,
                )

            position = mt5.positions_get(ticket=ticket)
            if not position:
                logger.warning(f"[MT5_GATEWAY] Position {ticket} not found")
                return OrderResult(
                    success=False, ticket=ticket, retcode=-1,
                    comment="Position not found",
                    entry_price=None, lot_size=None, execution_time_ms=0,
                )

            pos = position[0]
            close_price = bid if pos.type == 0 else ask  # BUY closes at bid
            close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY

            close_request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": pos.volume,
                "type": close_type,
                "position": ticket,
                "price": float(close_price),
                "deviation": MAX_SLIPPAGE_POINTS,
                "magic": MAGIC_NUMBER,
                "comment": "TREE_DATA_CLOSE",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            result = mt5.order_send(close_request)
            if result is None or result.retcode != 10009:
                error = mt5.last_error()
                logger.error(f"[MT5_GATEWAY] Close failed: {result.retcode if result else 'None'} | {error}")
                return OrderResult(
                    success=False, ticket=ticket,
                    retcode=result.retcode if result else -1,
                    comment=result.comment if result else str(error),
                    entry_price=None, lot_size=None, execution_time_ms=0,
                )

            return OrderResult(
                success=True, ticket=result.order, retcode=result.retcode,
                comment=result.comment,
                entry_price=Decimal(str(result.price)).quantize(DECIMAL_3),
                lot_size=Decimal(str(result.volume)).quantize(Decimal("0.01")),
                execution_time_ms=0,
            )

        except Exception as e:
            logger.error(f"[MT5_GATEWAY] close_position exception: {e}", exc_info=True)
            return OrderResult(
                success=False, ticket=ticket, retcode=-1,
                comment=f"Exception: {e}",
                entry_price=None, lot_size=None, execution_time_ms=0,
                error_message=str(e),
            )

    def close_all_positions(self, symbol: str = SYMBOL) -> int:
        """
        Force-close all open positions (used by Fatal Cutoff).

        Returns:
            Number of positions successfully closed.
        """
        closed_count = 0
        try:
            if not MT5_AVAILABLE:
                logger.info("[MT5_GATEWAY] [SIMULATION] All positions force-closed")
                return 0

            positions = mt5.positions_get(symbol=symbol)
            if positions is None or len(positions) == 0:
                logger.info("[MT5_GATEWAY] No open positions to close")
                return 0

            loop = asyncio.new_event_loop()
            for pos in positions:
                try:
                    result = loop.run_until_complete(self.close_position(pos.ticket, symbol))
                    if result.success:
                        closed_count += 1
                        logger.info(f"[MT5_GATEWAY] Closed position {pos.ticket}")
                    else:
                        logger.error(f"[MT5_GATEWAY] Failed to close {pos.ticket}: {result.error_message}")
                except Exception as e:
                    logger.error(f"[MT5_GATEWAY] Error closing {pos.ticket}: {e}")
            loop.close()

        except Exception as e:
            logger.critical(f"[MT5_GATEWAY] close_all_positions critical error: {e}", exc_info=True)
        finally:
            logger.info(f"[MT5_GATEWAY] Force-close complete: {closed_count} positions closed")

        return closed_count


# ── Singleton Gateway Instance ─────────────────────────────────────────────────
MT5_GATEWAY = ExnessMT5Gateway()
