"""
============================================================
TREE DATA v3.0.0 — "Sang Hakim" Master Decision Engine
Client: Kembang Ayu Andini
============================================================
engine/sang_hakim.py: Core voting aggregation matrix and
operational arbiter. Computes D_final = Σ W_i,regime × V_i
and dispatches orders to appropriate execution horizons.
"""

from __future__ import annotations

import time
import math
import logging
import asyncio
from decimal import Decimal, ROUND_HALF_EVEN
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Literal, Callable, Any

from config import (
    ALPHA_CONFIDENCE_THRESHOLD, ALPHA_INTRADAY_THRESHOLD, ALPHA_LONGTERM_THRESHOLD,
    SCALPING_RISK_DEFAULT, INTRADAY_RISK_DEFAULT, LONGTERM_RISK_DEFAULT,
    SCALP_SL_POINTS, SCALP_TP_RATIO, INTRADAY_SL_POINTS, INTRADAY_TP_RATIO,
    LONGTERM_SL_POINTS, LONGTERM_TP_RATIO, MIN_LOT_SIZE, MAX_LOT_SIZE,
    MarketRegime, SYMBOL, DECIMAL_3,
)
from engine.data_learning_engine import MWUMLearningEngine

logger = logging.getLogger("SANG_HAKIM")

OrderHorizon = Literal["SCALPING_SNIPER", "INTRADAY", "LONG_TERM"]
OrderSide = Literal["BUY", "SELL", "FLAT"]


# ── Decision Models ────────────────────────────────────────────────────────────

@dataclass
class VerdictContext:
    """Complete context snapshot for a Sang Hakim decision."""
    d_final: float
    regime: MarketRegime
    side: OrderSide
    confidence: float
    triggered: bool
    alpha_threshold: float
    horizon: Optional[OrderHorizon]
    voting_breakdown: List[Dict[str, float]]
    model_votes: Dict[int, float]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "d_final": self.d_final,
            "regime": self.regime.name,
            "side": self.side,
            "confidence": self.confidence,
            "triggered": self.triggered,
            "horizon": self.horizon,
            "timestamp": self.timestamp,
        }


@dataclass
class OrderSpecification:
    """Fully specified order ready for gateway submission."""
    symbol: str
    side: OrderSide
    horizon: OrderHorizon
    lot_size: Decimal
    entry_price: Decimal
    take_profit: Decimal
    stop_loss: Decimal
    risk_pct: float
    risk_amount: Decimal
    d_final: float
    regime: MarketRegime
    verdict: VerdictContext


# ── Position Sizing ────────────────────────────────────────────────────────────

def compute_position_size(
    horizon: OrderHorizon,
    equity: Decimal,
    d_final: float,
    pip_value: Decimal = Decimal("10.0"),
) -> Tuple[Decimal, float, Decimal]:
    """
    Risk-adjusted position sizing using Kelly-like scaling.

    Formula:
        risk_pct = base_pct × |D_final|
        risk_amount = equity × risk_pct
        lot_size = risk_amount / (sl_points × pip_value_per_lot)

    Args:
        horizon: Trading time horizon
        equity: Current account equity
        d_final: Sang Hakim directional signal strength
        pip_value: USD value per pip per lot (default $10)

    Returns:
        (lot_size, risk_pct, risk_amount)
    """
    base_risk_map: Dict[str, float] = {
        "SCALPING_SNIPER": SCALPING_RISK_DEFAULT,
        "INTRADAY": INTRADAY_RISK_DEFAULT,
        "LONG_TERM": LONGTERM_RISK_DEFAULT,
    }
    sl_points_map: Dict[str, Decimal] = {
        "SCALPING_SNIPER": SCALP_SL_POINTS,
        "INTRADAY": INTRADAY_SL_POINTS,
        "LONG_TERM": LONGTERM_SL_POINTS,
    }

    try:
        base_pct = base_risk_map.get(horizon, SCALPING_RISK_DEFAULT)
        confidence_scale = min(1.0, abs(d_final))
        risk_pct = base_pct * confidence_scale

        equity_dec = Decimal(str(equity))
        risk_amount = (equity_dec * Decimal(str(risk_pct))).quantize(Decimal("0.01"))

        sl_pts = sl_points_map.get(horizon, SCALP_SL_POINTS)
        sl_pips = sl_pts * Decimal("100")  # Convert to pips for XAU
        denominator = sl_pips * pip_value

        if denominator <= 0:
            raise ValueError(f"Invalid denominator for lot sizing: {denominator}")

        raw_lot = risk_amount / denominator
        lot_size = max(MIN_LOT_SIZE, min(MAX_LOT_SIZE, raw_lot.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_EVEN
        )))

        return lot_size, risk_pct, risk_amount

    except Exception as e:
        logger.error(f"[SANG_HAKIM] Position sizing error: {e}")
        return MIN_LOT_SIZE, 0.01, Decimal("50.00")


def compute_tp_sl(
    side: OrderSide,
    entry_price: Decimal,
    horizon: OrderHorizon,
) -> Tuple[Decimal, Decimal]:
    """
    Calculate Take Profit and Stop Loss with 3-decimal precision.

    Returns:
        (take_profit, stop_loss) as Decimal
    """
    sl_map: Dict[str, Decimal] = {
        "SCALPING_SNIPER": SCALP_SL_POINTS,
        "INTRADAY": INTRADAY_SL_POINTS,
        "LONG_TERM": LONGTERM_SL_POINTS,
    }
    tp_ratio_map: Dict[str, float] = {
        "SCALPING_SNIPER": SCALP_TP_RATIO,
        "INTRADAY": INTRADAY_TP_RATIO,
        "LONG_TERM": LONGTERM_TP_RATIO,
    }

    sl_dist = sl_map.get(horizon, SCALP_SL_POINTS)
    tp_ratio = Decimal(str(tp_ratio_map.get(horizon, 1.5)))
    tp_dist = (sl_dist * tp_ratio).quantize(DECIMAL_3)

    if side == "BUY":
        tp = (entry_price + tp_dist).quantize(DECIMAL_3)
        sl = (entry_price - sl_dist).quantize(DECIMAL_3)
    else:  # SELL
        tp = (entry_price - tp_dist).quantize(DECIMAL_3)
        sl = (entry_price + sl_dist).quantize(DECIMAL_3)

    return tp, sl


# ── Sang Hakim Engine ──────────────────────────────────────────────────────────

class SangHakimEngine:
    """
    "Sang Hakim" — The Judge: Master Decision Arbiter.

    Aggregates 14 model votes using regime-partitioned weight matrices
    and determines whether to trigger execution across three time horizons.

    Architecture:
        ModelVotes → WeightMatrix[regime] → D_final → Threshold → Order
    """

    def __init__(self, mwum_engine: MWUMLearningEngine) -> None:
        self.mwum = mwum_engine
        self._decision_history: List[VerdictContext] = []
        self._execution_callbacks: List[Callable[[OrderSpecification], None]] = []

        logger.info(
            f"[SANG_HAKIM] Engine initialized | "
            f"α={ALPHA_CONFIDENCE_THRESHOLD} | "
            f"α_intra={ALPHA_INTRADAY_THRESHOLD} | "
            f"α_long={ALPHA_LONGTERM_THRESHOLD}"
        )

    def register_execution_callback(self, cb: Callable[[OrderSpecification], None]) -> None:
        """Register callback for when a qualified signal is generated."""
        self._execution_callbacks.append(cb)

    def adjudicate(
        self,
        model_votes: Dict[int, float],
        regime: MarketRegime,
        current_bid: Decimal,
        current_ask: Decimal,
        account_equity: Decimal,
        entry_allowed: bool,
    ) -> VerdictContext:
        """
        Execute the full Sang Hakim adjudication cycle.

        Steps:
        1. Compute D_final = Σ W_i,regime × V_i
        2. Evaluate |D_final| against α threshold
        3. Determine execution horizon
        4. Build OrderSpecification if triggered
        5. Dispatch to registered execution callbacks

        Args:
            model_votes: {model_id: vote_value} from all 14 models
            regime: Current market regime (TRENDING/RANGING/VOLATILE)
            current_bid: Live bid price (3-decimal)
            current_ask: Live ask price (3-decimal)
            account_equity: Current account equity
            entry_allowed: Risk engine clearance flag

        Returns:
            VerdictContext with full decision context
        """
        try:
            # Step 1: Aggregate D_final
            d_final, breakdown = self.mwum.compute_d_final(model_votes, regime)
            abs_d = abs(d_final)

            # Step 2: Threshold evaluation
            triggered = abs_d >= ALPHA_CONFIDENCE_THRESHOLD and entry_allowed
            side: OrderSide = "BUY" if d_final > 0.01 else "SELL" if d_final < -0.01 else "FLAT"

            if side == "FLAT":
                triggered = False

            # Step 3: Horizon determination
            horizon: Optional[OrderHorizon] = None
            if triggered:
                if abs_d >= ALPHA_LONGTERM_THRESHOLD:
                    horizon = "LONG_TERM"
                elif abs_d >= ALPHA_INTRADAY_THRESHOLD:
                    horizon = "INTRADAY"
                else:
                    horizon = "SCALPING_SNIPER"

            verdict = VerdictContext(
                d_final=d_final,
                regime=regime,
                side=side,
                confidence=abs_d,
                triggered=triggered,
                alpha_threshold=ALPHA_CONFIDENCE_THRESHOLD,
                horizon=horizon,
                voting_breakdown=breakdown,
                model_votes=dict(model_votes),
            )

            self._decision_history = self._decision_history[-999:] + [verdict]

            logger.info(
                f"[SANG_HAKIM] Verdict | D_final={d_final:+.5f} | "
                f"Regime={regime.name} | Side={side} | "
                f"Triggered={triggered} | Horizon={horizon}"
            )

            # Step 4 & 5: Build and dispatch order if triggered
            if triggered and horizon is not None:
                entry_price = current_ask if side == "BUY" else current_bid
                tp, sl = compute_tp_sl(side, entry_price, horizon)
                lot_size, risk_pct, risk_amount = compute_position_size(
                    horizon, account_equity, d_final
                )

                order_spec = OrderSpecification(
                    symbol=SYMBOL,
                    side=side,
                    horizon=horizon,
                    lot_size=lot_size,
                    entry_price=entry_price,
                    take_profit=tp,
                    stop_loss=sl,
                    risk_pct=risk_pct,
                    risk_amount=risk_amount,
                    d_final=d_final,
                    regime=regime,
                    verdict=verdict,
                )

                logger.info(
                    f"[SANG_HAKIM] 🎯 ORDER SPECIFICATION | "
                    f"{side} {lot_size} {SYMBOL} @ {entry_price} | "
                    f"TP={tp} | SL={sl} | Risk={risk_pct*100:.1f}% (${risk_amount})"
                )

                for callback in self._execution_callbacks:
                    try:
                        callback(order_spec)
                    except Exception as cb_err:
                        logger.error(f"[SANG_HAKIM] Callback error: {cb_err}")

            return verdict

        except Exception as e:
            logger.critical(f"[SANG_HAKIM] Adjudication critical error: {e}", exc_info=True)
            return VerdictContext(
                d_final=0.0,
                regime=regime,
                side="FLAT",
                confidence=0.0,
                triggered=False,
                alpha_threshold=ALPHA_CONFIDENCE_THRESHOLD,
                horizon=None,
                voting_breakdown=[],
                model_votes={},
            )

    def get_regime_weight_summary(self, regime: MarketRegime) -> str:
        """Human-readable weight summary for logging/dashboard."""
        weights = self.mwum.get_current_weights(regime)
        lines = [f"[SANG_HAKIM] Weight Summary [{regime.name}]:"]
        for model_id, weight in sorted(weights.items()):
            lines.append(f"  Model {model_id:2d}: {weight:.6f} ({weight*100:.2f}%)")
        return "\n".join(lines)

    @property
    def decision_history(self) -> List[VerdictContext]:
        return list(self._decision_history)

    @property
    def last_verdict(self) -> Optional[VerdictContext]:
        return self._decision_history[-1] if self._decision_history else None
