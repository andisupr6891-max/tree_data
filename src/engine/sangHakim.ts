// ============================================================
// TREE DATA v3.0.0 — "Sang Hakim" Master Decision Engine
// Implements: D_final = Σ W_i,regime × V_i
// Regime-partitioned voting aggregation + MWUM self-learning
// ============================================================

import type {
  ModelVote,
  MarketRegime,
  SangHakimDecision,
  OrderSide,
  OrderHorizon,
  CMEData,
  MarketTick,
} from '../types';

const ALPHA_THRESHOLD = 0.80; // Confidence threshold for execution trigger
const LEARNING_RATE_ETA = 0.12; // η for MWUM exponential penalty

// ─── Voting Signal Generators ────────────────────────────────────────────────

function computeBlackScholesVote(tick: MarketTick, cme: CMEData): number {
  // Simplified BS delta-neutral directional bias
  const iv = cme.impliedVolatility;
  const spotVsStrike = tick.mid > 3300 ? 1.0 : -1.0;
  return Math.tanh(spotVsStrike * (0.5 + iv * 3));
}

function computeIVSurfaceVote(cme: CMEData): number {
  // IV skew: high IV → volatility expansion → directional bias by CPR
  const ivsSkew = cme.callPutRatio - 1.0;
  return Math.tanh(ivsSkew * 2.5);
}

function computeGARCHVote(ticks: MarketTick[], regime: MarketRegime): number {
  if (ticks.length < 5) return 0;
  const returns = ticks.slice(-20).map((t, i, arr) =>
    i === 0 ? 0 : (t.mid - arr[i - 1].mid) / arr[i - 1].mid
  ).slice(1);
  const meanReturn = returns.reduce((a, b) => a + b, 0) / returns.length;
  const variance = returns.reduce((s, r) => s + Math.pow(r - meanReturn, 2), 0) / returns.length;
  // GARCH signal: high variance in trending → continuation; in ranging → mean reversion
  const signal = regime === 'REGIME_TRENDING'
    ? Math.tanh(meanReturn / (Math.sqrt(variance) + 1e-8) * 10)
    : -Math.tanh(meanReturn / (Math.sqrt(variance) + 1e-8) * 8);
  return signal;
}

function computeHMMVote(ticks: MarketTick[]): number {
  // HMM state approximation via 3-state Viterbi proxy
  if (ticks.length < 15) return 0;
  const prices = ticks.slice(-15).map((t) => t.mid);
  const diff = prices[prices.length - 1] - prices[0];
  const momentum = diff / prices[0];
  const stateProb = Math.tanh(momentum * 2000);
  return stateProb;
}

function computeKalmanVote(ticks: MarketTick[]): number {
  // Kalman Filter: estimate true price vs observed, detect divergence
  if (ticks.length < 10) return 0;
  const prices = ticks.slice(-20).map((t) => t.mid);
  // Simple 1D Kalman
  let x = prices[0];
  let p = 1.0;
  const q = 0.001; // Process noise
  const r = 0.1;   // Measurement noise
  for (const z of prices.slice(1)) {
    p = p + q;
    const k = p / (p + r);
    x = x + k * (z - x);
    p = (1 - k) * p;
  }
  const current = prices[prices.length - 1];
  return Math.tanh((current - x) * 5);
}

function computeMonteCarloVote(tick: MarketTick, regime: MarketRegime): number {
  // Monte Carlo path probability: bullish paths vs bearish paths
  const simCount = 50;
  const sigma = regime === 'REGIME_TRENDING' ? 0.002 : 0.001;
  const mu = 0.00001;
  const horizon = 10;
  let bullishPaths = 0;
  for (let i = 0; i < simCount; i++) {
    let price = tick.mid;
    for (let j = 0; j < horizon; j++) {
      const rand = (Math.random() - 0.5) * 2;
      price *= Math.exp(mu - 0.5 * sigma * sigma + sigma * rand);
    }
    if (price > tick.mid) bullishPaths++;
  }
  return Math.tanh((bullishPaths / simCount - 0.5) * 4);
}

function computeOUVote(ticks: MarketTick[]): number {
  // Ornstein-Uhlenbeck: measures distance from long-run mean
  if (ticks.length < 30) return 0;
  const prices = ticks.slice(-100).map((t) => t.mid);
  const mean = prices.reduce((a, b) => a + b, 0) / prices.length;
  const current = prices[prices.length - 1];
  const deviation = (current - mean) / mean;
  // OU reverts to mean: negative deviation → long signal
  return Math.tanh(-deviation * 500);
}

function computeFourierVote(ticks: MarketTick[]): number {
  // FFT-based dominant cycle detection
  if (ticks.length < 32) return 0;
  const prices = ticks.slice(-32).map((t) => t.mid);
  const mean = prices.reduce((a, b) => a + b, 0) / prices.length;
  const centered = prices.map((p) => p - mean);
  // Approximate dominant frequency via DFT of first 8 components
  let maxAmplitude = 0;
  let dominantPhase = 0;
  for (let k = 1; k <= 8; k++) {
    let re = 0, im = 0;
    for (let n = 0; n < centered.length; n++) {
      re += centered[n] * Math.cos((2 * Math.PI * k * n) / centered.length);
      im -= centered[n] * Math.sin((2 * Math.PI * k * n) / centered.length);
    }
    const amplitude = Math.sqrt(re * re + im * im);
    if (amplitude > maxAmplitude) {
      maxAmplitude = amplitude;
      dominantPhase = Math.atan2(im, re);
    }
  }
  return Math.tanh(Math.sin(dominantPhase) * 1.5);
}

function computeDRLVote(ticks: MarketTick[], regime: MarketRegime): number {
  // Simulates DRL policy output (Q-value difference → action probability)
  if (ticks.length < 10) return 0;
  const recentTicks = ticks.slice(-10);
  const features = [
    (recentTicks[9].mid - recentTicks[0].mid) / recentTicks[0].mid * 1000,
    recentTicks[9].spread,
    recentTicks[9].volume / 500,
    regime === 'REGIME_TRENDING' ? 1 : 0,
  ];
  // Simulated neural network forward pass (2-layer)
  const w1 = [0.3, -0.2, 0.15, 0.4];
  const bias1 = 0.01;
  const hidden = Math.tanh(features.reduce((s, f, i) => s + f * w1[i], bias1));
  return Math.tanh(hidden * 1.8);
}

function computeSDEVote(ticks: MarketTick[]): number {
  // Stochastic Calculus: Itô's lemma volatility-adjusted drift
  if (ticks.length < 5) return 0;
  const prices = ticks.slice(-20).map((t) => t.mid);
  const logReturns = prices.slice(1).map((p, i) => Math.log(p / prices[i]));
  const mu = logReturns.reduce((a, b) => a + b, 0) / logReturns.length;
  const sigma2 = logReturns.reduce((s, r) => s + Math.pow(r - mu, 2), 0) / logReturns.length;
  // Itô drift: μ - σ²/2
  const itoDrift = mu - sigma2 / 2;
  return Math.tanh(itoDrift * 5000);
}

function computeOrderflowVote(ticks: MarketTick[]): number {
  // Order flow imbalance: buy vs sell pressure via bid-ask dynamics
  if (ticks.length < 5) return 0;
  const recentTicks = ticks.slice(-20);
  let buyPressure = 0;
  let sellPressure = 0;
  for (let i = 1; i < recentTicks.length; i++) {
    const priceMove = recentTicks[i].mid - recentTicks[i - 1].mid;
    const vol = recentTicks[i].volume;
    if (priceMove > 0) buyPressure += vol;
    else if (priceMove < 0) sellPressure += vol;
  }
  const total = buyPressure + sellPressure;
  if (total === 0) return 0;
  return Math.tanh((buyPressure - sellPressure) / total * 3);
}

function computeGEXVote(cme: CMEData): number {
  // Gamma Exposure: positive GEX → pin, negative GEX → amplification
  const gexNormalized = cme.gex / 5000000;
  // Negative GEX → trend continuation signal
  return Math.tanh(-gexNormalized * 0.8);
}

function computeRegimeDetectionVote(regime: MarketRegime, ticks: MarketTick[]): number {
  // Regime Detection: outputs directional bias based on regime state
  if (ticks.length < 10) return 0;
  const prices = ticks.slice(-20).map((t) => t.mid);
  const momentum = (prices[prices.length - 1] - prices[0]) / prices[0];
  if (regime === 'REGIME_TRENDING') {
    return Math.tanh(momentum * 3000);
  } else if (regime === 'REGIME_VOLATILE') {
    return Math.tanh(-momentum * 1500); // Contrarian in volatile
  }
  return Math.tanh(-momentum * 2000); // Mean-reversion in ranging
}

function computeLiquidityProfileVote(ticks: MarketTick[], cme: CMEData): number {
  // Liquidity Profile: OI gradient + volume acceleration
  if (ticks.length < 10) return 0;
  const recent = ticks.slice(-10);
  const volumeAccel = recent[recent.length - 1].volume - recent[0].volume;
  const oiSignal = (cme.openInterest > 570000) ? 0.3 : -0.2;
  const deltaSignal = cme.delta * 0.5;
  return Math.tanh(volumeAccel / 500 + oiSignal + deltaSignal);
}

// ─── Vote Aggregation ─────────────────────────────────────────────────────────

export function computeAllVotes(
  models: ModelVote[],
  ticks: MarketTick[],
  cme: CMEData,
  regime: MarketRegime
): ModelVote[] {
  const tick = ticks.length > 0 ? ticks[ticks.length - 1] : {
    timestamp: Date.now(), bid: 3318.0, ask: 3318.2, spread: 0.2, volume: 400, mid: 3318.1
  };

  const voteComputers: ((m: ModelVote) => number)[] = [
    () => computeBlackScholesVote(tick, cme),
    () => computeIVSurfaceVote(cme),
    () => computeGARCHVote(ticks, regime),
    () => computeHMMVote(ticks),
    () => computeKalmanVote(ticks),
    () => computeMonteCarloVote(tick, regime),
    () => computeOUVote(ticks),
    () => computeFourierVote(ticks),
    () => computeDRLVote(ticks, regime),
    () => computeSDEVote(ticks),
    () => computeOrderflowVote(ticks),
    () => computeGEXVote(cme),
    () => computeRegimeDetectionVote(regime, ticks),
    () => computeLiquidityProfileVote(ticks, cme),
  ];

  return models.map((model, i) => {
    try {
      const rawVote = voteComputers[i] ? voteComputers[i](model) : 0;
      const clampedVote = Math.max(-1.0, Math.min(1.0, rawVote));
      const noise = (Math.random() - 0.5) * 0.04; // micro-noise for realism
      const finalVote = Math.max(-1.0, Math.min(1.0, clampedVote + noise));
      return {
        ...model,
        vote: Math.round(finalVote * 10000) / 10000,
        confidence: Math.round(Math.abs(finalVote) * 10000) / 10000,
        lastUpdated: Date.now(),
      };
    } catch {
      return { ...model, vote: 0, confidence: 0, lastUpdated: Date.now() };
    }
  });
}

// ─── Sang Hakim Decision Engine ───────────────────────────────────────────────

export function sangHakimDecide(
  models: ModelVote[],
  regime: MarketRegime
): SangHakimDecision {
  // D_final = Σ W_i,regime × V_i
  let dFinal = 0;
  const votingBreakdown: { modelId: number; contribution: number }[] = [];

  for (const model of models) {
    const weight = regime === 'REGIME_TRENDING'
      ? model.weight_trending
      : model.weight_ranging;
    const contribution = weight * model.vote;
    dFinal += contribution;
    votingBreakdown.push({
      modelId: model.id,
      contribution: Math.round(contribution * 100000) / 100000,
    });
  }

  dFinal = Math.max(-1.0, Math.min(1.0, dFinal));
  const absDFinal = Math.abs(dFinal);
  const triggered = absDFinal >= ALPHA_THRESHOLD;
  const side: OrderSide = dFinal > 0.01 ? 'BUY' : dFinal < -0.01 ? 'SELL' : 'FLAT';

  // Horizon selection based on D_final magnitude
  let horizon: OrderHorizon | null = null;
  if (triggered) {
    if (absDFinal >= 0.95) horizon = 'LONG_TERM';
    else if (absDFinal >= 0.88) horizon = 'INTRADAY';
    else horizon = 'SCALPING_SNIPER';
  }

  return {
    dFinal: Math.round(dFinal * 100000) / 100000,
    regime,
    side,
    confidence: Math.round(absDFinal * 100000) / 100000,
    triggered,
    alphaThreshold: ALPHA_THRESHOLD,
    horizon,
    votingBreakdown,
  };
}

// ─── MWUM Self-Learning Weight Update ─────────────────────────────────────────

export function applyMWUMUpdate(
  models: ModelVote[],
  outcome: 1 | -1,
  regime: MarketRegime
): ModelVote[] {
  // L_i = (1 - V_i × O) / 2
  // w_i^(t+1) = w_i^(t) × (1-η)^L_i
  const updated = models.map((model) => {
    const loss = (1 - model.vote * outcome) / 2;
    const penalty = Math.pow(1 - LEARNING_RATE_ETA, loss);
    return {
      ...model,
      weight_trending: regime === 'REGIME_TRENDING'
        ? model.weight_trending * penalty
        : model.weight_trending,
      weight_ranging: regime !== 'REGIME_TRENDING'
        ? model.weight_ranging * penalty
        : model.weight_ranging,
    };
  });

  // Softmax-rescaling normalization: Σ W_i,regime = 1.0
  const sumTrending = updated.reduce((s, m) => s + m.weight_trending, 0);
  const sumRanging = updated.reduce((s, m) => s + m.weight_ranging, 0);

  return updated.map((m) => ({
    ...m,
    weight_trending: Math.round((m.weight_trending / sumTrending) * 1000000) / 1000000,
    weight_ranging: Math.round((m.weight_ranging / sumRanging) * 1000000) / 1000000,
  }));
}

// ─── Risk-Adjusted Position Sizing ────────────────────────────────────────────

export function computePositionSize(
  horizon: OrderHorizon,
  equity: number,
  dFinal: number
): { lotSize: number; riskPct: number; riskAmount: number } {
  const riskMap: Record<OrderHorizon, number> = {
    SCALPING_SNIPER: 0.03,  // 3% of equity
    INTRADAY: 0.12,          // 12% of equity
    LONG_TERM: 0.22,         // 22% of equity
  };

  const basePct = riskMap[horizon];
  const confidenceScale = Math.abs(dFinal) / 1.0;
  const riskPct = basePct * confidenceScale;
  const riskAmount = equity * riskPct;

  // XAU/USD lot sizing: 1 lot = 100 oz, approximate pip value
  const pipValue = 10; // USD per pip per 0.01 lot
  const stopLossPips = horizon === 'SCALPING_SNIPER' ? 30 : horizon === 'INTRADAY' ? 150 : 500;
  const lotSize = Math.max(0.01, Math.round((riskAmount / (stopLossPips * pipValue)) * 100) / 100);

  return {
    lotSize: Math.min(lotSize, 10.0), // Max 10 lots
    riskPct: Math.round(riskPct * 10000) / 10000,
    riskAmount: Math.round(riskAmount * 100) / 100,
  };
}
