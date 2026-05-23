// ============================================================
// TREE DATA v3.0.0 — Fail-Safe Risk Engine
// Implements: Circuit Breaker, 3-σ Spread Detector, Fatal Cutoff
// Independent thread simulation via setInterval polling
// ============================================================

import type { RiskState, TradeRecord, SystemLog } from '../types';

const MAX_DAILY_DRAWDOWN_PCT = 0.12;  // 12% hard stop
const SPREAD_SIGMA_THRESHOLD = 3.0;   // 3-sigma anomaly
const MAX_TOTAL_RISK_PCT = 0.40;      // 40% max equity at risk
const EQUITY_CHECK_INTERVAL_MS = 500;

export class FailSafeEngine {
  private riskState: RiskState;
  private intervalId: ReturnType<typeof setInterval> | null = null;
  private onRiskUpdate: (state: RiskState) => void;
  private onLog: (log: Omit<SystemLog, 'id' | 'timestamp'>) => void;
  private onCircuitBreak: () => void;
  private startEquity: number;
  private dailyHighEquity: number;

  constructor(
    initialEquity: number,
    onRiskUpdate: (state: RiskState) => void,
    onLog: (log: Omit<SystemLog, 'id' | 'timestamp'>) => void,
    onCircuitBreak: () => void
  ) {
    this.startEquity = initialEquity;
    this.dailyHighEquity = initialEquity;
    this.onRiskUpdate = onRiskUpdate;
    this.onLog = onLog;
    this.onCircuitBreak = onCircuitBreak;

    this.riskState = {
      accountEquity: initialEquity,
      dailyDrawdown: 0,
      dailyDrawdownPct: 0,
      maxDailyDrawdown: MAX_DAILY_DRAWDOWN_PCT,
      spreadMean: 0.20,
      spreadSigma: 0.05,
      currentSpread: 0.20,
      spreadZScore: 0,
      circuitBreakerActive: false,
      fatalCutoffActive: false,
      scalpingRiskPct: 0.03,
      intradayRiskPct: 0.12,
      longtermRiskPct: 0.22,
      totalAllocatedPct: 0,
    };
  }

  public start(): void {
    if (this.intervalId !== null) return;
    this.intervalId = setInterval(() => {
      this.checkEquityThreshold();
    }, EQUITY_CHECK_INTERVAL_MS);
    this.onLog({ level: 'INFO', module: 'RISK_ENGINE', message: '⚡ Fail-Safe Engine activated — 500ms equity polling thread ONLINE' });
  }

  public stop(): void {
    if (this.intervalId !== null) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
    this.onLog({ level: 'WARN', module: 'RISK_ENGINE', message: '⛔ Fail-Safe Engine polling thread STOPPED' });
  }

  public updateEquity(newEquity: number, openTrades: TradeRecord[]): void {
    if (newEquity > this.dailyHighEquity) {
      this.dailyHighEquity = newEquity;
    }

    const dailyDrawdown = this.dailyHighEquity - newEquity;
    const dailyDrawdownPct = dailyDrawdown / this.startEquity;
    const totalRisk = openTrades.reduce((sum, t) => {
      if (t.status === 'OPEN') {
        const horizonRisk = t.horizon === 'SCALPING_SNIPER' ? 0.03
          : t.horizon === 'INTRADAY' ? 0.12 : 0.22;
        return sum + horizonRisk;
      }
      return sum;
    }, 0);

    this.riskState = {
      ...this.riskState,
      accountEquity: Math.round(newEquity * 100) / 100,
      dailyDrawdown: Math.round(dailyDrawdown * 100) / 100,
      dailyDrawdownPct: Math.round(dailyDrawdownPct * 100000) / 100000,
      totalAllocatedPct: Math.round(totalRisk * 1000) / 1000,
    };

    this.onRiskUpdate({ ...this.riskState });
  }

  public updateSpreadStats(spreadMean: number, spreadSigma: number, currentSpread: number): void {
    const zScore = spreadSigma > 0 ? (currentSpread - spreadMean) / spreadSigma : 0;
    const spreadAnomaly = Math.abs(zScore) >= SPREAD_SIGMA_THRESHOLD;

    const prevAnomaly = Math.abs(this.riskState.spreadZScore) >= SPREAD_SIGMA_THRESHOLD;

    this.riskState = {
      ...this.riskState,
      spreadMean: Math.round(spreadMean * 10000) / 10000,
      spreadSigma: Math.round(spreadSigma * 10000) / 10000,
      currentSpread: Math.round(currentSpread * 10000) / 10000,
      spreadZScore: Math.round(zScore * 1000) / 1000,
    };

    if (spreadAnomaly && !prevAnomaly) {
      this.onLog({
        level: 'WARN',
        module: 'SPREAD_DETECTOR',
        message: `🚨 3-Sigma Spread Anomaly! Spread: ${currentSpread.toFixed(3)} | Z-Score: ${zScore.toFixed(2)} | ENTRY LOGIC PAUSED`,
        data: { zScore, currentSpread, spreadMean, spreadSigma },
      });
    }

    this.onRiskUpdate({ ...this.riskState });
  }

  private checkEquityThreshold(): void {
    const { dailyDrawdownPct, maxDailyDrawdown, circuitBreakerActive, fatalCutoffActive } = this.riskState;

    if (fatalCutoffActive) return;
    if (circuitBreakerActive) return;

    if (dailyDrawdownPct >= maxDailyDrawdown) {
      this.riskState = {
        ...this.riskState,
        circuitBreakerActive: true,
      };
      this.onLog({
        level: 'FATAL',
        module: 'CIRCUIT_BREAKER',
        message: `💥 HARD DAILY DRAWDOWN BREAKER TRIGGERED! DD: ${(dailyDrawdownPct * 100).toFixed(2)}% >= ${(maxDailyDrawdown * 100).toFixed(0)}% limit. ALL TRADES FORCE-CLOSED. EXECUTION LOCKED.`,
        data: { dailyDrawdownPct, maxDailyDrawdown },
      });
      this.onCircuitBreak();
      this.onRiskUpdate({ ...this.riskState });
    } else if (dailyDrawdownPct >= maxDailyDrawdown * 0.80) {
      this.onLog({
        level: 'WARN',
        module: 'CIRCUIT_BREAKER',
        message: `⚠️ Approaching daily drawdown limit: ${(dailyDrawdownPct * 100).toFixed(2)}% / ${(maxDailyDrawdown * 100).toFixed(0)}%`,
        data: { dailyDrawdownPct, maxDailyDrawdown },
      });
    }
  }

  public triggerFatalCutoff(): void {
    this.riskState = {
      ...this.riskState,
      fatalCutoffActive: true,
      circuitBreakerActive: true,
    };
    this.onLog({
      level: 'FATAL',
      module: 'FATAL_CUTOFF',
      message: '🔴 /fatalcutoff COMMAND RECEIVED — GLOBAL FORCE-KILL INITIATED. All positions liquidated. Auto-entry CEASED.',
    });
    this.onCircuitBreak();
    this.onRiskUpdate({ ...this.riskState });
  }

  public resetCircuitBreaker(): void {
    if (this.riskState.fatalCutoffActive) {
      this.onLog({ level: 'WARN', module: 'RISK_ENGINE', message: '⛔ Cannot reset: Fatal Cutoff is active. Manual override required.' });
      return;
    }
    this.riskState = {
      ...this.riskState,
      circuitBreakerActive: false,
    };
    this.onLog({ level: 'INFO', module: 'RISK_ENGINE', message: '✅ Circuit Breaker manually reset. Execution resumed.' });
    this.onRiskUpdate({ ...this.riskState });
  }

  public isEntryAllowed(): boolean {
    const { circuitBreakerActive, fatalCutoffActive, spreadZScore, totalAllocatedPct } = this.riskState;
    if (circuitBreakerActive || fatalCutoffActive) return false;
    if (Math.abs(spreadZScore) >= SPREAD_SIGMA_THRESHOLD) return false;
    if (totalAllocatedPct >= MAX_TOTAL_RISK_PCT) return false;
    return true;
  }

  public getRiskState(): RiskState { return { ...this.riskState }; }
}

// ─── Broker Error Handler ─────────────────────────────────────────────────────

export async function handleBrokerError(
  errorCode: number,
  retryFn: () => Promise<boolean>,
  maxRetries: number = 5
): Promise<boolean> {
  const retriableErrors = [10004, 10014]; // Requote, Invalid Volume
  if (!retriableErrors.includes(errorCode)) return false;

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    const backoffMs = Math.min(1000 * Math.pow(2, attempt - 1), 30000);
    await new Promise((resolve) => setTimeout(resolve, backoffMs));
    try {
      const success = await retryFn();
      if (success) return true;
    } catch {
      // Continue retry loop
    }
  }
  return false;
}

// ─── Precision Arithmetic ─────────────────────────────────────────────────────

export function toFixed3(value: number): number {
  // Deterministic 3-decimal fixed-point (Exness XAU/USD format)
  return Math.round(value * 1000) / 1000;
}

export function toFixed5(value: number): number {
  return Math.round(value * 100000) / 100000;
}

export function validateXAUUSDPrice(price: number): boolean {
  if (!isFinite(price) || isNaN(price)) return false;
  if (price < 1000 || price > 5000) return false;
  const decimalStr = price.toString();
  const decimalPart = decimalStr.includes('.') ? decimalStr.split('.')[1] : '';
  return decimalPart.length <= 3;
}
