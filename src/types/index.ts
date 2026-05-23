// ============================================================
// TREE DATA v3.0.0 — Type Definitions
// Client: Kembang Ayu Andini
// ============================================================

export type MarketRegime = 'REGIME_TRENDING' | 'REGIME_RANGING' | 'REGIME_VOLATILE';
export type SystemState = 'idle' | 'processing' | 'executing' | 'profit' | 'loss' | 'warning' | 'fatal';
export type OrderHorizon = 'SCALPING_SNIPER' | 'INTRADAY' | 'LONG_TERM';
export type OrderSide = 'BUY' | 'SELL' | 'FLAT';
export type BrokerError = 10004 | 10014 | 10006 | 10016;

export interface ModelVote {
  id: number;
  name: string;
  shortName: string;
  vote: number;           // V_i ∈ [-1.0, 1.0]
  weight_trending: number; // W_i,TRENDING
  weight_ranging: number;  // W_i,RANGING
  confidence: number;
  active: boolean;
  category: 'STATISTICAL' | 'ML' | 'QUANT' | 'MARKET_MICROSTRUCTURE';
  color: string;
  lastUpdated: number;
}

export interface MarketTick {
  timestamp: number;
  bid: number;
  ask: number;
  spread: number;
  volume: number;
  mid: number;
}

export interface ATRData {
  period: number;
  value: number;
  mean: number;
  gamma: number;
}

export interface CMEData {
  openInterest: number;
  volume: number;
  callPutRatio: number;
  impliedVolatility: number;
  gamma: number;
  delta: number;
  gex: number;
  lastFetch: number;
  status: 'fresh' | 'cached' | 'stale' | 'fallback';
}

export interface RiskState {
  accountEquity: number;
  dailyDrawdown: number;
  dailyDrawdownPct: number;
  maxDailyDrawdown: number;
  spreadMean: number;
  spreadSigma: number;
  currentSpread: number;
  spreadZScore: number;
  circuitBreakerActive: boolean;
  fatalCutoffActive: boolean;
  scalpingRiskPct: number;
  intradayRiskPct: number;
  longtermRiskPct: number;
  totalAllocatedPct: number;
}

export interface TradeRecord {
  id: string;
  timestamp: number;
  side: OrderSide;
  horizon: OrderHorizon;
  entryPrice: number;
  exitPrice: number | null;
  lotSize: number;
  tp: number;
  sl: number;
  pnl: number | null;
  status: 'OPEN' | 'TP_HIT' | 'SL_HIT' | 'MANUAL_CLOSE' | 'FATAL_CLOSE';
  dFinal: number;
  regime: MarketRegime;
  modelSnapshot: ModelVote[];
}

export interface SystemLog {
  id: string;
  timestamp: number;
  level: 'INFO' | 'WARN' | 'ERROR' | 'FATAL' | 'SUCCESS' | 'DEBUG';
  module: string;
  message: string;
  data?: Record<string, unknown>;
}

export interface SangHakimDecision {
  dFinal: number;
  regime: MarketRegime;
  side: OrderSide;
  confidence: number;
  triggered: boolean;
  alphaThreshold: number;
  horizon: OrderHorizon | null;
  votingBreakdown: { modelId: number; contribution: number }[];
}

export interface WebhookPayload {
  symbol: string;
  action: 'BUY' | 'SELL' | 'CLOSE';
  price: number;
  strategy: string;
  timestamp: number;
  hmacSignature: string;
}

export interface ConstellationNode {
  id: number;
  x: number;
  y: number;
  model: ModelVote;
  pulse: number;
  connections: number[];
}

export interface PerformanceMetric {
  timestamp: number;
  equity: number;
  dFinal: number;
  regime: MarketRegime;
  winRate: number;
  sharpeRatio: number;
  maxDrawdown: number;
  totalTrades: number;
  profitFactor: number;
}
