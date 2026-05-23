"""
============================================================
TREE DATA v3.0.0 — MWUM Data Learning Engine
Client: Kembang Ayu Andini
============================================================
engine/data_learning_engine.py: Closed-loop self-learning
implementing MWUM formulas, regime partitioning, weight
normalization, and local-first RAM/SQLite caching before
async Supabase sync.
"""

from __future__ import annotations

import json
import math
import time
import logging
import asyncio
import sqlite3
import threading
from decimal import Decimal, ROUND_HALF_EVEN
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Literal, Optional, Tuple, Any

from config import (
    LEARNING_RATE_ETA, NUM_MODELS, MWUM_SYNC_INTERVAL_SEC,
    NORMALIZED_MODEL_CONFIGS, MarketRegime, LOGGER
)

logger = logging.getLogger("MWUM_ENGINE")

# ── Weight State ───────────────────────────────────────────────────────────────

@dataclass
class ModelWeightState:
    """Per-model weight container — regime-partitioned."""
    model_id: int
    model_name: str
    weight_trending: float
    weight_ranging: float
    cumulative_loss_trending: float = 0.0
    cumulative_loss_ranging: float = 0.0
    update_count: int = 0
    last_vote: float = 0.0
    last_updated: float = field(default_factory=time.time)

    def apply_mwum_update(
        self,
        vote: float,
        outcome: Literal[1, -1],
        regime: MarketRegime,
        eta: float = LEARNING_RATE_ETA,
    ) -> None:
        """
        Apply MWUM exponential penalty update in-place.

        Formulas:
            L_i^(t) = (1 - V_i × O) / 2
            w_i,regime^(t+1) = w_i,regime^(t) × (1 - η)^L_i
        """
        try:
            # Clamp vote to [-1, 1]
            clamped_vote = max(-1.0, min(1.0, float(vote)))
            outcome_float = float(outcome)

            # Fractional loss L_i ∈ [0, 1]
            loss = (1.0 - clamped_vote * outcome_float) / 2.0
            loss = max(0.0, min(1.0, loss))

            # Penalty factor: (1 - η)^L_i
            penalty = math.pow(1.0 - eta, loss)

            if regime == MarketRegime.REGIME_TRENDING:
                self.weight_trending = max(1e-10, self.weight_trending * penalty)
                self.cumulative_loss_trending += loss
            else:
                self.weight_ranging = max(1e-10, self.weight_ranging * penalty)
                self.cumulative_loss_ranging += loss

            self.last_vote = clamped_vote
            self.update_count += 1
            self.last_updated = time.time()

            logger.debug(
                f"[MWUM] Model {self.model_id} ({self.model_name[:12]}) | "
                f"L={loss:.4f} | penalty={penalty:.6f} | "
                f"w_trend={self.weight_trending:.6f} | w_range={self.weight_ranging:.6f}"
            )

        except (TypeError, ValueError, OverflowError) as e:
            logger.error(f"[MWUM] Weight update failed for model {self.model_id}: {e}")


@dataclass
class WeightMatrix:
    """Complete weight matrix for all 14 models, both regimes."""
    states: List[ModelWeightState]
    normalization_count: int = 0
    last_sync_time: float = field(default_factory=time.time)

    @classmethod
    def from_config(cls) -> "WeightMatrix":
        """Initialize from normalized config registry."""
        states = [
            ModelWeightState(
                model_id=cfg.id,
                model_name=cfg.name,
                weight_trending=cfg.weight_trending,
                weight_ranging=cfg.weight_ranging,
            )
            for cfg in NORMALIZED_MODEL_CONFIGS
        ]
        return cls(states=states)

    def normalize(self) -> None:
        """
        Softmax-rescaling normalization: Σ W_i,regime = 1.0
        Applied after every MWUM batch update.
        """
        try:
            sum_trending = sum(s.weight_trending for s in self.states)
            sum_ranging = sum(s.weight_ranging for s in self.states)

            if sum_trending < 1e-15 or sum_ranging < 1e-15:
                logger.critical("[MWUM] Weight sum near zero — resetting to uniform distribution")
                uniform = 1.0 / len(self.states)
                for s in self.states:
                    s.weight_trending = uniform
                    s.weight_ranging = uniform
                return

            for s in self.states:
                s.weight_trending = round(s.weight_trending / sum_trending, 8)
                s.weight_ranging = round(s.weight_ranging / sum_ranging, 8)

            self.normalization_count += 1

            # Verify normalization
            final_sum_t = sum(s.weight_trending for s in self.states)
            final_sum_r = sum(s.weight_ranging for s in self.states)
            assert abs(final_sum_t - 1.0) < 1e-6, f"Trending weights sum={final_sum_t}"
            assert abs(final_sum_r - 1.0) < 1e-6, f"Ranging weights sum={final_sum_r}"

        except AssertionError as e:
            logger.error(f"[MWUM] Normalization assertion failed: {e}")
        except Exception as e:
            logger.critical(f"[MWUM] Normalization critical error: {e}", exc_info=True)

    def get_weights_for_regime(self, regime: MarketRegime) -> Dict[int, float]:
        """Return weight dict {model_id: weight} for active regime."""
        return {
            s.model_id: (
                s.weight_trending if regime == MarketRegime.REGIME_TRENDING
                else s.weight_ranging
            )
            for s in self.states
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize weight matrix for caching/syncing."""
        return {
            "normalization_count": self.normalization_count,
            "last_sync_time": self.last_sync_time,
            "states": [asdict(s) for s in self.states],
        }


# ── Local SQLite Cache ─────────────────────────────────────────────────────────

class LocalWeightCache:
    """
    RAM/SQLite local-first cache for weight matrices.
    Ensures persistence during network outages.
    """

    def __init__(self, db_path: str = "tree_data_cache.db") -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        """Initialize SQLite schema."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS weight_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        regime TEXT NOT NULL,
                        model_id INTEGER NOT NULL,
                        weight_trending REAL NOT NULL,
                        weight_ranging REAL NOT NULL,
                        synced INTEGER DEFAULT 0
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS trade_outcomes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        trade_id TEXT NOT NULL,
                        outcome INTEGER NOT NULL,
                        regime TEXT NOT NULL,
                        d_final REAL NOT NULL,
                        synced INTEGER DEFAULT 0
                    )
                """)
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"[CACHE] SQLite schema init error: {e}")

    def save_weights(self, matrix: WeightMatrix, regime: MarketRegime) -> bool:
        """Persist weight snapshot to local SQLite."""
        with self._lock:
            try:
                ts = time.time()
                with sqlite3.connect(self.db_path) as conn:
                    conn.executemany(
                        "INSERT INTO weight_snapshots (timestamp, regime, model_id, weight_trending, weight_ranging) VALUES (?, ?, ?, ?, ?)",
                        [
                            (ts, regime.name, s.model_id, s.weight_trending, s.weight_ranging)
                            for s in matrix.states
                        ]
                    )
                    conn.commit()
                return True
            except sqlite3.Error as e:
                logger.error(f"[CACHE] Save weights error: {e}")
                return False

    def save_trade_outcome(self, trade_id: str, outcome: int, regime: MarketRegime, d_final: float) -> bool:
        """Log trade outcome for audit trail."""
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        "INSERT INTO trade_outcomes (timestamp, trade_id, outcome, regime, d_final) VALUES (?, ?, ?, ?, ?)",
                        (time.time(), trade_id, outcome, regime.name, d_final)
                    )
                    conn.commit()
                return True
            except sqlite3.Error as e:
                logger.error(f"[CACHE] Save outcome error: {e}")
                return False

    def get_unsynced_count(self) -> int:
        """Return count of records pending Supabase sync."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM weight_snapshots WHERE synced = 0"
                ).fetchone()[0]
                return count
        except sqlite3.Error as e:
            logger.error(f"[CACHE] Unsynced count error: {e}")
            return -1

    def mark_synced(self, table: str, max_id: int) -> None:
        """Mark records as synced after successful Supabase push."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(f"UPDATE {table} SET synced = 1 WHERE id <= ?", (max_id,))
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"[CACHE] Mark synced error: {e}")


# ── MWUM Learning Engine ───────────────────────────────────────────────────────

class MWUMLearningEngine:
    """
    Multiplicative Weights Update Method (MWUM) Engine.

    Manages:
    - Regime-partitioned weight matrix
    - Trade outcome evaluation
    - Local SQLite caching
    - Async Supabase sync
    """

    def __init__(self) -> None:
        self.weight_matrix = WeightMatrix.from_config()
        self.cache = LocalWeightCache()
        self._sync_task: Optional[asyncio.Task] = None
        self._is_running = False

        logger.info(
            f"[MWUM] Engine initialized | {NUM_MODELS} models | "
            f"η={LEARNING_RATE_ETA} | Sync interval={MWUM_SYNC_INTERVAL_SEC}s"
        )

    def process_trade_outcome(
        self,
        trade_id: str,
        votes: Dict[int, float],
        outcome: Literal[1, -1],
        regime: MarketRegime,
        d_final: float,
    ) -> None:
        """
        Full MWUM update cycle after trade resolution.

        Pipeline:
        1. Evaluate L_i for each model
        2. Apply exponential penalty update
        3. Softmax-rescale normalization
        4. Cache to local SQLite
        5. Queue async Supabase sync

        Args:
            trade_id: Unique trade identifier
            votes: {model_id: vote_value} snapshot at trade entry
            outcome: +1 (TP hit / profit) or -1 (SL hit / loss)
            regime: Active market regime at trade entry
            d_final: Sang Hakim D_final value at entry
        """
        try:
            logger.info(
                f"[MWUM] Processing outcome | Trade: {trade_id} | "
                f"Outcome: {'WIN' if outcome == 1 else 'LOSS'} | Regime: {regime.name}"
            )

            # Step 1 & 2: Apply MWUM updates
            for state in self.weight_matrix.states:
                vote = votes.get(state.model_id, 0.0)
                state.apply_mwum_update(vote, outcome, regime)

            # Step 3: Normalize weights
            self.weight_matrix.normalize()

            # Step 4: Cache locally
            self.cache.save_weights(self.weight_matrix, regime)
            self.cache.save_trade_outcome(trade_id, outcome, regime, d_final)

            # Step 5: Mark for async sync
            self.weight_matrix.last_sync_time = time.time()

            logger.info(
                f"[MWUM] ✅ Weight matrix updated | "
                f"Normalization #{self.weight_matrix.normalization_count} | "
                f"Pending sync: {self.cache.get_unsynced_count()} records"
            )

        except Exception as e:
            logger.critical(f"[MWUM] process_trade_outcome CRITICAL: {e}", exc_info=True)

    def get_current_weights(self, regime: MarketRegime) -> Dict[int, float]:
        """Thread-safe read of current weights for given regime."""
        try:
            return self.weight_matrix.get_weights_for_regime(regime)
        except Exception as e:
            logger.error(f"[MWUM] get_current_weights error: {e}")
            uniform = 1.0 / NUM_MODELS
            return {i: uniform for i in range(NUM_MODELS)}

    def compute_d_final(
        self,
        votes: Dict[int, float],
        regime: MarketRegime,
    ) -> Tuple[float, List[Dict[str, float]]]:
        """
        Compute D_final = Σ W_i,regime × V_i

        Returns:
            (d_final, breakdown) where breakdown is list of {model_id, weight, vote, contribution}
        """
        weights = self.get_current_weights(regime)
        d_final = 0.0
        breakdown = []

        for model_id, vote in votes.items():
            weight = weights.get(model_id, 1.0 / NUM_MODELS)
            contribution = weight * vote
            d_final += contribution
            breakdown.append({
                "model_id": model_id,
                "weight": round(weight, 8),
                "vote": round(vote, 6),
                "contribution": round(contribution, 8),
            })

        d_final = max(-1.0, min(1.0, d_final))
        return round(d_final, 8), breakdown

    async def async_supabase_sync(self, supabase_client: Any) -> None:
        """
        Async Supabase PostgreSQL sync for weight matrix and trade outcomes.
        Runs in background; failures do not block trading.
        """
        try:
            matrix_data = self.weight_matrix.to_dict()
            records = [
                {
                    "model_id": s["model_id"],
                    "model_name": s["model_name"],
                    "weight_trending": s["weight_trending"],
                    "weight_ranging": s["weight_ranging"],
                    "update_count": s["update_count"],
                    "timestamp": time.time(),
                }
                for s in matrix_data["states"]
            ]

            await supabase_client.table("model_weights").upsert(records).execute()
            logger.info(f"[MWUM] ✅ Supabase sync complete | {len(records)} model weights uploaded")

        except Exception as e:
            logger.warning(f"[MWUM] Supabase sync deferred (non-blocking): {e}")

    async def start_sync_loop(self, supabase_client: Any) -> None:
        """Background sync loop — runs every MWUM_SYNC_INTERVAL_SEC seconds."""
        self._is_running = True
        logger.info(f"[MWUM] Background sync loop started | interval={MWUM_SYNC_INTERVAL_SEC}s")
        while self._is_running:
            try:
                await asyncio.sleep(MWUM_SYNC_INTERVAL_SEC)
                await self.async_supabase_sync(supabase_client)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[MWUM] Sync loop iteration error: {e}")

    def stop(self) -> None:
        """Gracefully stop the sync loop."""
        self._is_running = False
        logger.info("[MWUM] Learning engine stopped")


# ── Singleton ──────────────────────────────────────────────────────────────────
MWUM_ENGINE = MWUMLearningEngine()
