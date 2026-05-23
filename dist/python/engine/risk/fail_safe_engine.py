"""
============================================================
TREE DATA v3.0.0 — Fail-Safe Risk Engine
Client: Kembang Ayu Andini
============================================================
engine/risk/fail_safe_engine.py: Low-latency independent
thread for equity drawdown monitoring, 3-sigma spread
anomaly detection, and circuit breaker isolation.
Completely independent of external APIs.
"""

from __future__ import annotations

import time
import math
import logging
import threading
import statistics
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Callable, Optional, List, Deque
from collections import deque

from config import (
    MAX_DAILY_DRAWDOWN_PCT, MAX_TOTAL_EQUITY_RISK_PCT,
    EQUITY_POLLING_INTERVAL_MS, SPREAD_ANOMALY_SIGMA,
    DRAWDOWN_WARNING_PCT, DECIMAL_3, LOGGER
)

logger = logging.getLogger("FAIL_SAFE")

# ── Risk State ─────────────────────────────────────────────────────────────────

@dataclass
class RiskSnapshot:
    """Immutable point-in-time risk state snapshot."""
    timestamp: float
    account_equity: Decimal
    daily_drawdown: Decimal
    daily_drawdown_pct: float
    max_daily_drawdown_pct: float
    spread_mean: float
    spread_sigma: float
    current_spread: float
    spread_z_score: float
    circuit_breaker_active: bool
    fatal_cutoff_active: bool
    total_allocated_pct: float


@dataclass
class SpreadStats:
    """Rolling spread statistics for 3-sigma anomaly detection."""
    history: Deque[float] = field(default_factory=lambda: deque(maxlen=500))
    mean: float = 0.20
    sigma: float = 0.05
    z_score: float = 0.0

    def update(self, spread: float) -> None:
        """Update rolling spread statistics with new observation."""
        try:
            spread = max(0.0, float(spread))
            self.history.append(spread)

            if len(self.history) >= 10:
                self.mean = statistics.mean(self.history)
                if len(self.history) >= 2:
                    self.sigma = statistics.stdev(self.history)
                else:
                    self.sigma = 0.001

                if self.sigma > 0:
                    self.z_score = (spread - self.mean) / self.sigma
                else:
                    self.z_score = 0.0
            else:
                self.z_score = 0.0

        except (statistics.StatisticsError, ZeroDivisionError, ValueError) as e:
            logger.warning(f"[SPREAD_STATS] Update error: {e}")

    @property
    def is_anomalous(self) -> bool:
        """True if current spread exceeds μ + 3σ threshold."""
        return abs(self.z_score) >= SPREAD_ANOMALY_SIGMA

    @property
    def three_sigma_band(self) -> float:
        """μ + 3σ upper band value."""
        return self.mean + SPREAD_ANOMALY_SIGMA * self.sigma


# ── Circuit State Machine ──────────────────────────────────────────────────────

class CircuitBreakerState:
    """Thread-safe circuit breaker state machine."""

    NOMINAL = "NOMINAL"
    WARNING = "WARNING"
    TRIPPED = "TRIPPED"
    FATAL = "FATAL"

    def __init__(self) -> None:
        self._state = self.NOMINAL
        self._lock = threading.RLock()
        self._trip_reason: Optional[str] = None
        self._trip_time: Optional[float] = None

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def is_execution_blocked(self) -> bool:
        with self._lock:
            return self._state in (self.TRIPPED, self.FATAL)

    def set_warning(self) -> None:
        with self._lock:
            if self._state == self.NOMINAL:
                self._state = self.WARNING

    def trip(self, reason: str) -> bool:
        """Atomically trip the circuit breaker. Returns True if newly tripped."""
        with self._lock:
            if self._state in (self.TRIPPED, self.FATAL):
                return False
            self._state = self.TRIPPED
            self._trip_reason = reason
            self._trip_time = time.time()
            logger.critical(f"[CIRCUIT_BREAKER] ⚡ TRIPPED: {reason}")
            return True

    def fatal(self, reason: str) -> None:
        """Permanently lock to FATAL state (no reset possible)."""
        with self._lock:
            self._state = self.FATAL
            self._trip_reason = reason
            self._trip_time = time.time()
            logger.critical(f"[CIRCUIT_BREAKER] 💀 FATAL: {reason}")

    def reset(self) -> bool:
        """Reset from TRIPPED to NOMINAL (not allowed from FATAL)."""
        with self._lock:
            if self._state == self.FATAL:
                logger.warning("[CIRCUIT_BREAKER] Cannot reset from FATAL state — manual intervention required")
                return False
            if self._state == self.TRIPPED:
                self._state = self.NOMINAL
                self._trip_reason = None
                logger.info("[CIRCUIT_BREAKER] ✅ Reset to NOMINAL")
                return True
            return True  # Already nominal

    @property
    def trip_reason(self) -> Optional[str]:
        with self._lock:
            return self._trip_reason


# ── Fail-Safe Engine ───────────────────────────────────────────────────────────

class FailSafeEngine:
    """
    Low-latency independent equity monitor and risk controller.

    Runs in an isolated daemon thread (500ms polling) completely
    independent from external APIs, CME feeds, or decision engine.
    Implements:
    - Hard daily drawdown circuit breaker
    - 3-sigma spread anomaly detection and entry halt
    - Fatal cutoff via external trigger (/fatalcutoff Telegram command)
    - Thread-safe state access for order router
    """

    def __init__(
        self,
        initial_equity: Decimal,
        on_circuit_break: Callable[[str], None],
        on_fatal_cutoff: Callable[[], None],
        close_all_positions_fn: Callable[[], int],
    ) -> None:
        self._initial_equity = initial_equity
        self._start_equity = initial_equity
        self._daily_high_equity = initial_equity
        self._current_equity = initial_equity

        self._spread_stats = SpreadStats()
        self._circuit = CircuitBreakerState()

        self._on_circuit_break = on_circuit_break
        self._on_fatal_cutoff = on_fatal_cutoff
        self._close_all_positions = close_all_positions_fn

        self._poll_thread: Optional[threading.Thread] = None
        self._running = threading.Event()
        self._lock = threading.RLock()

        self._current_spread = 0.0
        self._total_allocated_pct = 0.0

        logger.info(
            f"[FAIL_SAFE] Engine initialized | "
            f"Initial equity: {initial_equity} | "
            f"Max DD: {MAX_DAILY_DRAWDOWN_PCT*100:.0f}% | "
            f"Spread threshold: {SPREAD_ANOMALY_SIGMA}σ | "
            f"Poll interval: {EQUITY_POLLING_INTERVAL_MS}ms"
        )

    def start(self) -> None:
        """Launch the independent equity polling daemon thread."""
        if self._poll_thread is not None and self._poll_thread.is_alive():
            logger.warning("[FAIL_SAFE] Already running")
            return

        self._running.set()
        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            name="FailSafe-Monitor",
            daemon=True,
        )
        self._poll_thread.start()
        logger.info(f"[FAIL_SAFE] ⚡ Independent polling thread started — {EQUITY_POLLING_INTERVAL_MS}ms interval")

    def stop(self) -> None:
        """Gracefully stop the polling thread."""
        self._running.clear()
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=2.0)
        logger.info("[FAIL_SAFE] Polling thread stopped")

    def update_equity(self, new_equity: Decimal) -> None:
        """Thread-safe equity update from order manager."""
        with self._lock:
            try:
                self._current_equity = Decimal(str(new_equity)).quantize(Decimal("0.01"))
                if self._current_equity > self._daily_high_equity:
                    self._daily_high_equity = self._current_equity
            except Exception as e:
                logger.error(f"[FAIL_SAFE] update_equity error: {e}")

    def update_spread(self, spread: float) -> None:
        """Feed current spread for rolling 3σ anomaly calculation."""
        with self._lock:
            try:
                self._current_spread = max(0.0, float(spread))
                self._spread_stats.update(self._current_spread)

                if self._spread_stats.is_anomalous:
                    logger.warning(
                        f"[SPREAD_DETECTOR] 🚨 3σ Anomaly | "
                        f"Spread: {self._current_spread:.4f} | "
                        f"μ+3σ: {self._spread_stats.three_sigma_band:.4f} | "
                        f"Z: {self._spread_stats.z_score:.2f} | "
                        f"ENTRY HALTED"
                    )
            except Exception as e:
                logger.error(f"[FAIL_SAFE] update_spread error: {e}")

    def update_allocated_risk(self, total_pct: float) -> None:
        """Update total allocated risk percentage."""
        with self._lock:
            self._total_allocated_pct = max(0.0, min(1.0, float(total_pct)))

    def _poll_loop(self) -> None:
        """
        Main equity monitoring loop — runs every 500ms.
        Completely isolated from all external network calls.
        """
        poll_interval_sec = EQUITY_POLLING_INTERVAL_MS / 1000.0

        while self._running.is_set():
            poll_start = time.perf_counter()

            try:
                self._check_daily_drawdown()
            except Exception as e:
                logger.error(f"[FAIL_SAFE] Poll loop exception: {e}", exc_info=True)

            finally:
                elapsed = time.perf_counter() - poll_start
                sleep_duration = max(0, poll_interval_sec - elapsed)
                time.sleep(sleep_duration)

    def _check_daily_drawdown(self) -> None:
        """Core drawdown check — called every 500ms from polling thread."""
        with self._lock:
            if self._circuit.is_execution_blocked:
                return  # Already tripped — nothing to do

            daily_drawdown = self._daily_high_equity - self._current_equity
            daily_dd_pct = float(daily_drawdown / self._start_equity)

            # Warning level: 80% of max threshold
            warning_level = MAX_DAILY_DRAWDOWN_PCT * DRAWDOWN_WARNING_PCT
            if daily_dd_pct >= warning_level:
                self._circuit.set_warning()
                logger.warning(
                    f"[FAIL_SAFE] ⚠️ DD WARNING | "
                    f"{daily_dd_pct*100:.2f}% / {MAX_DAILY_DRAWDOWN_PCT*100:.0f}% max"
                )

            # Hard limit: trigger circuit breaker
            if daily_dd_pct >= MAX_DAILY_DRAWDOWN_PCT:
                reason = (
                    f"Daily drawdown {daily_dd_pct*100:.2f}% exceeded "
                    f"hard limit {MAX_DAILY_DRAWDOWN_PCT*100:.0f}%"
                )
                newly_tripped = self._circuit.trip(reason)

                if newly_tripped:
                    logger.critical(
                        f"[CIRCUIT_BREAKER] 💥 HARD DAILY DRAWDOWN BREAKER TRIGGERED | "
                        f"DD: {daily_dd_pct*100:.2f}% | "
                        f"Equity: {self._current_equity} | "
                        f"Daily High: {self._daily_high_equity}"
                    )
                    try:
                        closed = self._close_all_positions()
                        logger.critical(f"[CIRCUIT_BREAKER] {closed} positions force-closed")
                        self._on_circuit_break(reason)
                    except Exception as e:
                        logger.critical(f"[CIRCUIT_BREAKER] Force-close error: {e}")

    def trigger_fatal_cutoff(self, source: str = "UNKNOWN") -> None:
        """
        Global force-kill mechanism: /fatalcutoff (Telegram or UI).
        Immediately liquidates all positions and permanently halts auto-entry.
        """
        try:
            logger.critical(f"[FATAL_CUTOFF] 🔴 TRIGGERED from source: {source}")
            self._circuit.fatal(f"Manual fatal cutoff from {source}")

            closed = self._close_all_positions()
            logger.critical(f"[FATAL_CUTOFF] {closed} positions liquidated")

            self._on_fatal_cutoff()
            logger.critical("[FATAL_CUTOFF] Auto-entry PERMANENTLY CEASED — system requires full restart")

        except Exception as e:
            logger.critical(f"[FATAL_CUTOFF] CRITICAL exception during cutoff: {e}", exc_info=True)

    def is_entry_allowed(self) -> bool:
        """
        Check all safety conditions before allowing order entry.
        Thread-safe — called by order router.

        Returns:
            True only if ALL conditions pass:
            - Circuit breaker not tripped
            - Spread not anomalous (< 3σ)
            - Total allocated risk < 40%
        """
        with self._lock:
            if self._circuit.is_execution_blocked:
                return False
            if self._spread_stats.is_anomalous:
                return False
            if self._total_allocated_pct >= MAX_TOTAL_EQUITY_RISK_PCT:
                return False
            return True

    def get_risk_snapshot(self) -> RiskSnapshot:
        """Thread-safe read of current risk state."""
        with self._lock:
            daily_dd = self._daily_high_equity - self._current_equity
            daily_dd_pct = float(daily_dd / self._start_equity) if self._start_equity > 0 else 0.0

            return RiskSnapshot(
                timestamp=time.time(),
                account_equity=self._current_equity,
                daily_drawdown=daily_dd,
                daily_drawdown_pct=daily_dd_pct,
                max_daily_drawdown_pct=MAX_DAILY_DRAWDOWN_PCT,
                spread_mean=self._spread_stats.mean,
                spread_sigma=self._spread_stats.sigma,
                current_spread=self._current_spread,
                spread_z_score=self._spread_stats.z_score,
                circuit_breaker_active=self._circuit.state in (
                    CircuitBreakerState.TRIPPED, CircuitBreakerState.FATAL
                ),
                fatal_cutoff_active=self._circuit.state == CircuitBreakerState.FATAL,
                total_allocated_pct=self._total_allocated_pct,
            )

    def reset_circuit_breaker(self) -> bool:
        """
        Attempt to reset circuit breaker (only from TRIPPED, not FATAL).

        Returns:
            True if successfully reset, False otherwise.
        """
        result = self._circuit.reset()
        if result:
            logger.info("[FAIL_SAFE] ✅ Circuit breaker manually reset by operator")
        return result

    def reset_daily_stats(self) -> None:
        """Reset daily equity tracking at start of new trading day."""
        with self._lock:
            self._start_equity = self._current_equity
            self._daily_high_equity = self._current_equity
            logger.info(f"[FAIL_SAFE] Daily stats reset | Start equity: {self._start_equity}")
