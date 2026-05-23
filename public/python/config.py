"""
============================================================
TREE DATA v3.0.0 — Global Configuration & Constants
Client: Kembang Ayu Andini
============================================================
config.py: Global constants, risk rules, cryptographic
parameters, API keys, and model state trackers.
"""

from __future__ import annotations

import os
import hashlib
import hmac
import logging
from decimal import Decimal, ROUND_HALF_EVEN, getcontext
from dataclasses import dataclass, field
from typing import Final, Literal, Dict, List, Optional, Any
from enum import Enum, auto

# ── Decimal Precision Context ──────────────────────────────────────────────────
getcontext().prec = 10
getcontext().rounding = ROUND_HALF_EVEN
DECIMAL_3 = Decimal('0.001')       # 3-decimal place quantization
DECIMAL_5 = Decimal('0.00001')     # 5-decimal for weights
DECIMAL_8 = Decimal('0.00000001')  # 8-decimal for internal calcs

# ── Versioning ─────────────────────────────────────────────────────────────────
SYSTEM_NAME: Final[str] = "TREE DATA"
SYSTEM_VERSION: Final[str] = "3.0.0"
CLIENT_NAME: Final[str] = "Kembang Ayu Andini"
BUILD_DATE: Final[str] = "2025-01-01"

# ── Trading Parameters ─────────────────────────────────────────────────────────
SYMBOL: Final[str] = "XAUUSD"
MAGIC_NUMBER: Final[int] = 300_000
MAX_SLIPPAGE_POINTS: Final[int] = 3
PRICE_DECIMAL_PLACES: Final[int] = 3      # 3-digit decimal (Exness format)
VOLUME_DECIMAL_PLACES: Final[int] = 2
MAX_LOT_SIZE: Final[Decimal] = Decimal("10.00")
MIN_LOT_SIZE: Final[Decimal] = Decimal("0.01")
LOT_STEP: Final[Decimal] = Decimal("0.01")

# ── Market Regime Constants ────────────────────────────────────────────────────
class MarketRegime(Enum):
    REGIME_TRENDING = auto()
    REGIME_RANGING = auto()
    REGIME_VOLATILE = auto()

ATR_PERIOD: Final[int] = 14
REGIME_GAMMA_MULTIPLIER: Final[float] = 1.5   # γ threshold multiplier
ROLLING_TICK_WINDOW: Final[int] = 1000         # σ rolling window
VOLATILITY_SIGMA_THRESHOLD: Final[float] = 1.5

# ── Sang Hakim Decision Engine ─────────────────────────────────────────────────
ALPHA_CONFIDENCE_THRESHOLD: Final[float] = 0.80     # |D_final| ≥ α → trigger
ALPHA_INTRADAY_THRESHOLD: Final[float] = 0.88       # D_final ≥ α_intra
ALPHA_LONGTERM_THRESHOLD: Final[float] = 0.95       # D_final ≥ α_long
NUM_MODELS: Final[int] = 14

# ── MWUM Self-Learning ─────────────────────────────────────────────────────────
LEARNING_RATE_ETA: Final[float] = 0.12    # η exponential penalty factor
MWUM_SYNC_INTERVAL_SEC: Final[int] = 30  # RAM cache → Supabase sync interval

# ── Risk Management ────────────────────────────────────────────────────────────
MAX_DAILY_DRAWDOWN_PCT: Final[float] = 0.12       # 12% hard stop
MAX_TOTAL_EQUITY_RISK_PCT: Final[float] = 0.40    # 40% max simultaneous

SCALPING_RISK_PCT_MIN: Final[float] = 0.02        # 2%
SCALPING_RISK_PCT_MAX: Final[float] = 0.05        # 5%
INTRADAY_RISK_PCT_MIN: Final[float] = 0.10        # 10%
INTRADAY_RISK_PCT_MAX: Final[float] = 0.15        # 15%
LONGTERM_RISK_PCT_MIN: Final[float] = 0.20        # 20%
LONGTERM_RISK_PCT_MAX: Final[float] = 0.25        # 25%

SCALPING_RISK_DEFAULT: Final[float] = 0.03        # Default 3%
INTRADAY_RISK_DEFAULT: Final[float] = 0.12        # Default 12%
LONGTERM_RISK_DEFAULT: Final[float] = 0.22        # Default 22%

# Stop Loss / Take Profit (in price points, 3-decimal)
SCALP_SL_POINTS: Final[Decimal] = Decimal("0.300")
SCALP_TP_RATIO: Final[float] = 1.5   # TP = SL × ratio
INTRADAY_SL_POINTS: Final[Decimal] = Decimal("1.500")
INTRADAY_TP_RATIO: Final[float] = 2.0
LONGTERM_SL_POINTS: Final[Decimal] = Decimal("5.000")
LONGTERM_TP_RATIO: Final[float] = 2.5

# ── Circuit Breaker ────────────────────────────────────────────────────────────
EQUITY_POLLING_INTERVAL_MS: Final[int] = 500      # Independent thread
SPREAD_ANOMALY_SIGMA: Final[float] = 3.0          # 3σ spread halt
DRAWDOWN_WARNING_PCT: Final[float] = 0.80         # 80% of max → warn

# ── Broker Error Retry ─────────────────────────────────────────────────────────
RETRIABLE_BROKER_ERRORS: Final[List[int]] = [10004, 10014]  # Requote, Invalid Vol
MAX_RETRY_ATTEMPTS: Final[int] = 5
BASE_BACKOFF_MS: Final[int] = 1000
MAX_BACKOFF_MS: Final[int] = 30_000

# ── CME Data Fetch ─────────────────────────────────────────────────────────────
CME_REFRESH_INTERVAL_SEC: Final[int] = 300   # 5 minutes
CME_REQUEST_TIMEOUT_SEC: Final[float] = 15.0
CME_HTTP2_ENABLED: Final[bool] = True
CME_USER_AGENT_POOL: Final[List[str]] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]
CME_GOLD_OPTIONS_URL: Final[str] = "https://www.cmegroup.com/CmeWS/mvc/Quotes/Option/305/G/0/R"

# ── Infrastructure & API Keys (from environment) ───────────────────────────────
@dataclass(frozen=True)
class InfrastructureConfig:
    """All external service credentials — loaded from environment variables."""

    # Supabase
    supabase_url: str = field(default_factory=lambda: os.getenv("SUPABASE_URL", ""))
    supabase_anon_key: str = field(default_factory=lambda: os.getenv("SUPABASE_ANON_KEY", ""))
    supabase_service_key: str = field(default_factory=lambda: os.getenv("SUPABASE_SERVICE_KEY", ""))

    # Exness MT5
    mt5_login: int = field(default_factory=lambda: int(os.getenv("MT5_LOGIN", "0")))
    mt5_password: str = field(default_factory=lambda: os.getenv("MT5_PASSWORD", ""))
    mt5_server: str = field(default_factory=lambda: os.getenv("MT5_SERVER", "Exness-MT5Real8"))

    # Telegram Bot
    telegram_bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))

    # Webhook Security
    webhook_hmac_secret: bytes = field(
        default_factory=lambda: os.getenv("WEBHOOK_HMAC_SECRET", "tree-data-default-secret-key-256bit").encode("utf-8")
    )
    webhook_port: int = field(default_factory=lambda: int(os.getenv("WEBHOOK_PORT", "8000")))

    # Google Sheets
    google_sheets_id: str = field(default_factory=lambda: os.getenv("GOOGLE_SHEETS_ID", ""))
    google_service_account_json: str = field(
        default_factory=lambda: os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
    )

    def validate(self) -> None:
        """Validate all required credentials are present."""
        required_fields = [
            ("supabase_url", self.supabase_url),
            ("mt5_login", str(self.mt5_login)),
            ("mt5_password", self.mt5_password),
            ("telegram_bot_token", self.telegram_bot_token),
        ]
        missing = [name for name, val in required_fields if not val or val == "0"]
        if missing:
            raise EnvironmentError(
                f"[CONFIG] Missing required environment variables: {', '.join(missing)}. "
                f"Please configure your .env file."
            )


# Singleton config instance
INFRA_CONFIG = InfrastructureConfig()

# ── Model Registry Initial Weights ────────────────────────────────────────────
@dataclass
class ModelConfig:
    id: int
    name: str
    short_name: str
    category: Literal["STATISTICAL", "ML", "QUANT", "MARKET_MICROSTRUCTURE"]
    weight_trending: float
    weight_ranging: float
    active: bool = True

MODEL_REGISTRY_CONFIG: Final[List[ModelConfig]] = [
    ModelConfig(0,  "Black-Scholes Pricing Engine",    "BS",    "QUANT",                  0.0714, 0.0600),
    ModelConfig(1,  "Implied Volatility Surface",       "IV",    "QUANT",                  0.0650, 0.0800),
    ModelConfig(2,  "GARCH(1,1) Volatility Forecast",  "GARCH", "STATISTICAL",            0.0720, 0.0900),
    ModelConfig(3,  "Hidden Markov Model",              "HMM",   "ML",                     0.0800, 0.0750),
    ModelConfig(4,  "Kalman Filter State Estimator",    "KF",    "STATISTICAL",            0.0680, 0.0820),
    ModelConfig(5,  "Monte Carlo Simulation",           "MC",    "STATISTICAL",            0.0600, 0.0550),
    ModelConfig(6,  "Ornstein-Uhlenbeck Process",       "OU",    "QUANT",                  0.0550, 0.0900),
    ModelConfig(7,  "Fourier Spectral Analysis",        "FFT",   "STATISTICAL",            0.0620, 0.0700),
    ModelConfig(8,  "Deep Reinforcement Learning",      "DRL",   "ML",                     0.0900, 0.0800),
    ModelConfig(9,  "Stochastic Calculus (Itô)",        "SDE",   "QUANT",                  0.0700, 0.0600),
    ModelConfig(10, "Orderflow Imbalance Analysis",     "OFA",   "MARKET_MICROSTRUCTURE",  0.0850, 0.0650),
    ModelConfig(11, "Gamma Exposure (GEX) Model",       "GEX",   "MARKET_MICROSTRUCTURE",  0.0750, 0.0700),
    ModelConfig(12, "Regime Detection Engine",          "RDE",   "ML",                     0.0800, 0.0880),
    ModelConfig(13, "Liquidity Profile Scanner",        "LPS",   "MARKET_MICROSTRUCTURE",  0.0866, 0.0850),
]


def normalize_model_weights(models: List[ModelConfig]) -> List[ModelConfig]:
    """Ensure Σ W_i,regime = 1.0 via proportional normalization."""
    sum_trending = sum(m.weight_trending for m in models)
    sum_ranging = sum(m.weight_ranging for m in models)

    try:
        assert abs(sum_trending) > 1e-10, "Sum of trending weights is zero"
        assert abs(sum_ranging) > 1e-10, "Sum of ranging weights is zero"
    except AssertionError as e:
        logging.critical(f"[CONFIG] Weight normalization failed: {e}")
        raise

    normalized = []
    for m in models:
        normalized.append(ModelConfig(
            id=m.id,
            name=m.name,
            short_name=m.short_name,
            category=m.category,
            weight_trending=round(m.weight_trending / sum_trending, 8),
            weight_ranging=round(m.weight_ranging / sum_ranging, 8),
            active=m.active,
        ))
    return normalized


NORMALIZED_MODEL_CONFIGS = normalize_model_weights(MODEL_REGISTRY_CONFIG)

# ── Security: HMAC-SHA256 ──────────────────────────────────────────────────────
def verify_hmac_signature(payload: bytes, signature: str, secret: bytes) -> bool:
    """
    Cryptographically verify TradingView webhook HMAC-SHA256 signature.
    Prevents IP spoofing and payload injection.

    Args:
        payload: Raw request body bytes
        signature: X-Signature header value (hex digest)
        secret: Pre-shared secret key bytes

    Returns:
        True if signature is valid, False otherwise
    """
    try:
        expected = hmac.new(secret, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature.lower().strip())
    except (TypeError, ValueError) as e:
        logging.error(f"[SECURITY] HMAC verification error: {e}")
        return False


# ── Logging Setup ──────────────────────────────────────────────────────────────
def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure structured logging for all TREE DATA modules."""
    log_format = (
        "[%(asctime)s] [%(levelname)-7s] [%(name)-20s] %(message)s"
    )
    logging.basicConfig(
        level=level,
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S.%f"[:-3],
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("tree_data.log", encoding="utf-8"),
        ]
    )
    logger = logging.getLogger("TREE_DATA")
    logger.info(f"{'='*60}")
    logger.info(f"  {SYSTEM_NAME} v{SYSTEM_VERSION} — Initialized")
    logger.info(f"  Client: {CLIENT_NAME}")
    logger.info(f"{'='*60}")
    return logger


LOGGER = setup_logging()
