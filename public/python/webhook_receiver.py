"""
============================================================
TREE DATA v3.0.0 — FastAPI Secure Webhook Receiver
Client: Kembang Ayu Andini
============================================================
webhook_receiver.py: FastAPI server managing secure TradingView
payload parsing with HMAC-SHA256 validation, async rate limiting,
and token bucket implementation.
"""

from __future__ import annotations

import time
import hashlib
import hmac
import asyncio
import logging
import json
from collections import deque
from decimal import Decimal
from typing import Optional, Deque, Dict, Any, Literal
from dataclasses import dataclass

from fastapi import FastAPI, Request, HTTPException, Depends, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator

from config import INFRA_CONFIG, verify_hmac_signature, SYMBOL, LOGGER

logger = logging.getLogger("WEBHOOK")

# ── Pydantic Models ────────────────────────────────────────────────────────────

class TradingViewPayload(BaseModel):
    """Strict-typed TradingView webhook payload schema."""
    symbol: str = Field(..., min_length=3, max_length=20)
    action: Literal["BUY", "SELL", "CLOSE"]
    price: float = Field(..., gt=0, lt=10000)
    strategy: str = Field(..., min_length=1, max_length=100)
    timestamp: int = Field(..., gt=0)
    hmac_signature: Optional[str] = Field(None, description="HMAC-SHA256 hex signature")

    @validator("symbol")
    def validate_symbol(cls, v: str) -> str:
        v = v.upper().strip()
        allowed_symbols = {"XAUUSD", "GOLD", "XAU_USD"}
        if v not in allowed_symbols:
            raise ValueError(f"Symbol '{v}' not in allowed list: {allowed_symbols}")
        return v

    @validator("price")
    def validate_price(cls, v: float) -> float:
        if not (1000.0 <= v <= 5000.0):
            raise ValueError(f"XAU/USD price {v} out of valid range [1000, 5000]")
        return round(v, 3)  # Enforce 3-decimal precision

    @validator("timestamp")
    def validate_timestamp(cls, v: int) -> int:
        # Reject stale payloads older than 60 seconds
        now_ms = int(time.time() * 1000)
        age_sec = abs(now_ms - v) / 1000
        if age_sec > 60:
            raise ValueError(f"Payload timestamp too old: {age_sec:.1f}s (max 60s)")
        return v


class CMEUpdatePayload(BaseModel):
    """CME data update from N8N fallback pipeline."""
    open_interest: int = Field(..., gt=0)
    volume: int = Field(..., gt=0)
    call_put_ratio: float = Field(..., gt=0, lt=10)
    implied_volatility: float = Field(..., gt=0, lt=5)
    gex: int
    delta: float = Field(..., ge=-1, le=1)
    source: Literal["N8N_PLAYWRIGHT", "N8N_OCR", "DIRECT_API"] = "DIRECT_API"


class TelegramCommandPayload(BaseModel):
    """Telegram bot command payload."""
    command: str
    chat_id: str
    user_id: str
    timestamp: int


# ── Token Bucket Rate Limiter ──────────────────────────────────────────────────

class TokenBucketRateLimiter:
    """
    Async Token Bucket / Sliding Window rate limiter.
    Absorbs high-frequency signal bursts during news events.
    """

    def __init__(self, max_requests: int = 100, window_sec: float = 60.0) -> None:
        self.max_requests = max_requests
        self.window_sec = window_sec
        self._requests: Deque[float] = deque()
        self._lock = asyncio.Lock()

    async def check(self, client_id: str = "global") -> bool:
        """
        Check if request is within rate limit.

        Returns:
            True if allowed, False if rate limited.
        """
        async with self._lock:
            now = time.time()
            cutoff = now - self.window_sec

            # Sliding window: remove expired entries
            while self._requests and self._requests[0] < cutoff:
                self._requests.popleft()

            if len(self._requests) >= self.max_requests:
                logger.warning(
                    f"[RATE_LIMITER] Rate limit exceeded for {client_id}: "
                    f"{len(self._requests)}/{self.max_requests} in {self.window_sec}s window"
                )
                return False

            self._requests.append(now)
            return True

    @property
    def current_count(self) -> int:
        return len(self._requests)


# ── HMAC Verification Dependency ──────────────────────────────────────────────

async def verify_tradingview_hmac(
    request: Request,
    x_signature: Optional[str] = Header(None, alias="X-Signature"),
) -> bytes:
    """
    FastAPI dependency: verify HMAC-SHA256 signature from TradingView.

    Raises:
        HTTPException 401: If signature is missing or invalid
        HTTPException 400: If request body cannot be read

    Returns:
        Raw request body bytes
    """
    try:
        body = await request.body()
        if not body:
            raise HTTPException(status_code=400, detail="Empty request body")

        # Check signature header
        if not x_signature:
            # Also check payload-embedded signature
            try:
                payload_dict = json.loads(body)
                x_signature = payload_dict.get("hmac_signature")
            except json.JSONDecodeError:
                pass

        if not x_signature:
            logger.warning("[WEBHOOK] HMAC signature missing from request")
            raise HTTPException(
                status_code=401,
                detail="X-Signature header required for HMAC verification",
            )

        is_valid = verify_hmac_signature(
            payload=body,
            signature=x_signature,
            secret=INFRA_CONFIG.webhook_hmac_secret,
        )

        if not is_valid:
            logger.error(
                f"[WEBHOOK] ❌ HMAC signature MISMATCH | "
                f"Received: {x_signature[:16]}... | IP spoofing attempt?"
            )
            raise HTTPException(
                status_code=401,
                detail="Invalid HMAC signature — payload rejected",
            )

        logger.info(f"[WEBHOOK] ✅ HMAC signature VERIFIED | Body size: {len(body)} bytes")
        return body

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[WEBHOOK] HMAC verification exception: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Signature verification error")


# ── FastAPI Application ────────────────────────────────────────────────────────

app = FastAPI(
    title="TREE DATA v3.0.0 Webhook Server",
    description="Secure TradingView + N8N + Telegram webhook endpoint with HMAC-SHA256",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://www.tradingview.com", "https://tradingview.com"],
    allow_methods=["POST"],
    allow_headers=["X-Signature", "Content-Type"],
)

# Global rate limiter instances
_tv_rate_limiter = TokenBucketRateLimiter(max_requests=60, window_sec=60.0)  # 60 req/min
_news_rate_limiter = TokenBucketRateLimiter(max_requests=500, window_sec=60.0)  # News burst

# Signal queue for async processing (non-blocking webhook responses)
_signal_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)

# External signal handler (injected by main.py)
_signal_handler: Optional[Any] = None

def set_signal_handler(handler: Any) -> None:
    """Inject the Sang Hakim signal handler from main trading loop."""
    global _signal_handler
    _signal_handler = handler
    logger.info("[WEBHOOK] Signal handler registered")


# ── Webhook Endpoints ──────────────────────────────────────────────────────────

@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint for Vercel/monitoring."""
    return {
        "status": "operational",
        "service": "TREE DATA v3.0.0 Webhook",
        "timestamp": time.time(),
        "rate_limiter": {
            "tradingview": f"{_tv_rate_limiter.current_count}/60 per min",
            "news": f"{_news_rate_limiter.current_count}/500 per min",
        },
        "signal_queue_size": _signal_queue.qsize(),
    }


@app.post("/webhook/tradingview")
async def receive_tradingview_signal(
    request: Request,
    background_tasks: BackgroundTasks,
    body: bytes = Depends(verify_tradingview_hmac),
) -> JSONResponse:
    """
    Primary TradingView webhook endpoint.

    Security:
    - HMAC-SHA256 signature verification (via dependency)
    - Token bucket rate limiting (60 req/min)
    - Payload timestamp validation (max 60s stale)
    - Symbol allowlist check

    Flow:
    1. Verify HMAC → 2. Parse payload → 3. Validate → 4. Queue signal
    """
    try:
        # Rate limit check
        client_ip = request.client.host if request.client else "unknown"
        if not await _tv_rate_limiter.check(client_ip):
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded — reduce signal frequency",
            )

        # Parse and validate payload
        try:
            payload_dict = json.loads(body)
            payload = TradingViewPayload(**payload_dict)
        except json.JSONDecodeError as e:
            logger.error(f"[WEBHOOK] JSON parse error: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")
        except Exception as e:
            logger.error(f"[WEBHOOK] Payload validation error: {e}")
            raise HTTPException(status_code=422, detail=f"Validation error: {e}")

        logger.info(
            f"[WEBHOOK] ✅ TV Signal received | "
            f"Action: {payload.action} | Symbol: {payload.symbol} | "
            f"Price: {payload.price:.3f} | Strategy: {payload.strategy}"
        )

        # Queue for async processing (non-blocking response)
        signal_event = {
            "source": "TRADINGVIEW",
            "action": payload.action,
            "symbol": payload.symbol,
            "price": payload.price,
            "strategy": payload.strategy,
            "received_at": time.time(),
        }

        try:
            _signal_queue.put_nowait(signal_event)
        except asyncio.QueueFull:
            logger.warning("[WEBHOOK] Signal queue full — dropping event")
            raise HTTPException(status_code=503, detail="Signal queue full — retry later")

        if _signal_handler:
            background_tasks.add_task(_signal_handler.process_webhook_signal, signal_event)

        return JSONResponse(
            status_code=200,
            content={
                "status": "accepted",
                "message": f"Signal {payload.action} @ {payload.price:.3f} queued for Sang Hakim",
                "queue_size": _signal_queue.qsize(),
                "timestamp": time.time(),
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.critical(f"[WEBHOOK] Unhandled exception: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/webhook/cme-update")
async def receive_cme_update(payload: CMEUpdatePayload) -> JSONResponse:
    """
    N8N fallback CME data update endpoint.
    Triggered by Playwright Stealth + Tesseract OCR when spot price hits targets.
    No HMAC required (internal N8N network only).
    """
    try:
        logger.info(
            f"[WEBHOOK] N8N CME Update | Source: {payload.source} | "
            f"OI: {payload.open_interest:,} | CPR: {payload.call_put_ratio:.3f} | "
            f"IV: {payload.implied_volatility*100:.2f}%"
        )

        # Update global CME cache (injected by main.py)
        if _signal_handler and hasattr(_signal_handler, "update_cme_data"):
            await _signal_handler.update_cme_data(payload.dict())

        return JSONResponse(status_code=200, content={"status": "cme_updated", "source": payload.source})

    except Exception as e:
        logger.error(f"[WEBHOOK] CME update error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhook/telegram")
async def receive_telegram_command(
    payload: TelegramCommandPayload,
    request: Request,
) -> JSONResponse:
    """
    Telegram bot command webhook for remote override execution.
    Handles: /fatalcutoff, /pause, /resume, /status
    """
    try:
        command = payload.command.lower().strip()
        allowed_commands = {"/fatalcutoff", "/pause", "/resume", "/status", "/reset"}

        if command not in allowed_commands:
            return JSONResponse(status_code=400, content={"error": f"Unknown command: {command}"})

        logger.info(f"[TELEGRAM] Command received: {command} from user {payload.user_id}")

        response_msg = ""
        if command == "/fatalcutoff":
            if _signal_handler and hasattr(_signal_handler, "trigger_fatal_cutoff"):
                _signal_handler.trigger_fatal_cutoff(source="TELEGRAM")
            response_msg = "🔴 FATAL CUTOFF EXECUTED — All positions liquidated"

        elif command == "/status":
            if _signal_handler and hasattr(_signal_handler, "get_status"):
                status = _signal_handler.get_status()
                response_msg = json.dumps(status, indent=2)
            else:
                response_msg = "Status unavailable"

        elif command == "/pause":
            if _signal_handler:
                _signal_handler.pause_engine()
            response_msg = "⏸️ Engine paused"

        elif command == "/resume":
            if _signal_handler:
                _signal_handler.resume_engine()
            response_msg = "▶️ Engine resumed"

        elif command == "/reset":
            if _signal_handler and hasattr(_signal_handler, "reset_circuit_breaker"):
                _signal_handler.reset_circuit_breaker()
            response_msg = "⚡ Circuit breaker reset"

        return JSONResponse(
            status_code=200,
            content={"status": "command_executed", "command": command, "response": response_msg}
        )

    except Exception as e:
        logger.error(f"[TELEGRAM] Command processing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ── Signal Consumer ────────────────────────────────────────────────────────────

async def consume_signal_queue() -> None:
    """Background coroutine consuming queued signals."""
    logger.info("[WEBHOOK] Signal consumer started")
    while True:
        try:
            signal = await asyncio.wait_for(_signal_queue.get(), timeout=1.0)
            logger.debug(f"[WEBHOOK] Signal consumed: {signal}")
            _signal_queue.task_done()
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            logger.error(f"[WEBHOOK] Consumer error: {e}")


@app.on_event("startup")
async def startup_event() -> None:
    """Start background signal consumer on server startup."""
    asyncio.create_task(consume_signal_queue())
    logger.info("[WEBHOOK] FastAPI server started — HMAC-SHA256 verification ACTIVE")
    logger.info(f"[WEBHOOK] Rate limits: TV={60}/min | News={500}/min")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=INFRA_CONFIG.webhook_port,
        log_level="info",
        access_log=True,
    )
