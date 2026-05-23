// ============================================================
// TREE DATA v3.0.0 — Real-Time Market Data Simulator
// XAU/USD 3-decimal precision tick engine
// ============================================================

import type { MarketTick, ATRData, CMEData, MarketRegime } from '../types';

const BASE_GOLD_PRICE = 3318.542; // XAU/USD 3-decimal format

// Geometric Brownian Motion tick generator with regime-aware volatility
export class GoldTickSimulator {
  private currentMid: number;
  private trendBias: number;
  private tickHistory: MarketTick[];
  private atrHistory: number[];
  private spreadHistory: number[];
  private sessionPhase: 'ASIAN' | 'LONDON' | 'NY' | 'OVERLAP';

  constructor() {
    this.currentMid = BASE_GOLD_PRICE;
    this.trendBias = 0;
    this.tickHistory = [];
    this.atrHistory = [];
    this.spreadHistory = [];
    this.sessionPhase = this.detectSessionPhase();
  }

  private detectSessionPhase(): 'ASIAN' | 'LONDON' | 'NY' | 'OVERLAP' {
    const hour = new Date().getUTCHours();
    if (hour >= 0 && hour < 8) return 'ASIAN';
    if (hour >= 8 && hour < 12) return 'LONDON';
    if (hour >= 12 && hour < 17) return 'OVERLAP';
    return 'NY';
  }

  private getSessionVolatilityMultiplier(): number {
    switch (this.sessionPhase) {
      case 'ASIAN': return 0.6;
      case 'LONDON': return 1.2;
      case 'OVERLAP': return 1.8;
      case 'NY': return 1.4;
    }
  }

  private getBaseSpread(): number {
    // Exness XAU/USD typical spreads in 3-digit decimal
    switch (this.sessionPhase) {
      case 'ASIAN': return 0.35;
      case 'LONDON': return 0.18;
      case 'OVERLAP': return 0.12;
      case 'NY': return 0.20;
    }
  }

  private generateOUNoise(prevValue: number, mean: number, theta: number, sigma: number): number {
    // Ornstein-Uhlenbeck process for mean-reverting noise
    const dt = 1 / 1000;
    const drift = theta * (mean - prevValue) * dt;
    const diffusion = sigma * Math.sqrt(dt) * this.gaussianRandom();
    return prevValue + drift + diffusion;
  }

  private gaussianRandom(): number {
    // Box-Muller transform
    let u = 0, v = 0;
    while (u === 0) u = Math.random();
    while (v === 0) v = Math.random();
    return Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);
  }

  public generateTick(): MarketTick {
    this.sessionPhase = this.detectSessionPhase();
    const volMult = this.getSessionVolatilityMultiplier();
    
    // GBM parameters for XAU/USD
    const mu = 0.00002 + this.trendBias;
    const sigma = 0.00085 * volMult;

    // Price change via GBM
    const dt = 1 / 86400;
    const priceChange = this.currentMid * (mu * dt + sigma * Math.sqrt(dt) * this.gaussianRandom());
    
    // Apply occasional regime jumps (news/liquidity events)
    const jumpProbability = 0.005;
    const jumpMagnitude = Math.random() < jumpProbability
      ? (Math.random() - 0.5) * 2.5 * volMult
      : 0;

    this.currentMid = Math.max(
      BASE_GOLD_PRICE * 0.85,
      Math.min(BASE_GOLD_PRICE * 1.15, this.currentMid + priceChange + jumpMagnitude)
    );

    // 3-decimal precision rounding (Exness broker format)
    const mid = Math.round(this.currentMid * 1000) / 1000;
    
    // Spread calculation with OU noise
    const baseSpread = this.getBaseSpread();
    const prevSpread = this.spreadHistory.length > 0 
      ? this.spreadHistory[this.spreadHistory.length - 1] 
      : baseSpread;
    const spreadNoise = this.generateOUNoise(prevSpread, baseSpread, 0.5, 0.03);
    const spread = Math.max(0.08, Math.round(Math.abs(spreadNoise) * 1000) / 1000);
    
    const bid = Math.round((mid - spread / 2) * 1000) / 1000;
    const ask = Math.round((mid + spread / 2) * 1000) / 1000;
    
    // Volume simulation (tick volume proxy)
    const baseVolume = this.sessionPhase === 'OVERLAP' ? 850 : 
                       this.sessionPhase === 'NY' ? 650 : 300;
    const volume = Math.max(1, Math.round(baseVolume * (0.5 + Math.random())));

    const tick: MarketTick = {
      timestamp: Date.now(),
      bid,
      ask,
      spread: Math.round(spread * 1000) / 1000,
      volume,
      mid,
    };

    // Maintain rolling histories
    this.tickHistory = [...this.tickHistory.slice(-999), tick];
    this.spreadHistory = [...this.spreadHistory.slice(-999), spread];

    return tick;
  }

  public computeATR(period: number = 14): ATRData {
    if (this.tickHistory.length < 2) {
      return { period, value: 0.5, mean: 0.5, gamma: 1.5 };
    }

    const trueRanges: number[] = [];
    const ticks = this.tickHistory.slice(-Math.max(period * 3, 50));

    for (let i = 1; i < ticks.length; i++) {
      const high = ticks[i].ask;
      const low = ticks[i].bid;
      const prevClose = ticks[i - 1].mid;
      const tr = Math.max(
        high - low,
        Math.abs(high - prevClose),
        Math.abs(low - prevClose)
      );
      trueRanges.push(tr);
    }

    // Wilder's ATR smoothing
    let atr = trueRanges.slice(0, period).reduce((a, b) => a + b, 0) / period;
    for (let i = period; i < trueRanges.length; i++) {
      atr = (atr * (period - 1) + trueRanges[i]) / period;
    }

    const meanATR = trueRanges.reduce((a, b) => a + b, 0) / trueRanges.length;
    this.atrHistory = [...this.atrHistory.slice(-99), atr];

    return {
      period,
      value: Math.round(atr * 1000) / 1000,
      mean: Math.round(meanATR * 1000) / 1000,
      gamma: 1.5, // γ threshold multiplier
    };
  }

  public detectRegime(atr: ATRData): MarketRegime {
    // Primary regime detection: ATR vs γ × mean(ATR)
    if (atr.value > atr.gamma * atr.mean) {
      return 'REGIME_TRENDING';
    }
    // Secondary: Rolling σ of tick prices
    if (this.tickHistory.length >= 20) {
      const recentPrices = this.tickHistory.slice(-20).map((t) => t.mid);
      const meanPrice = recentPrices.reduce((a, b) => a + b, 0) / recentPrices.length;
      const variance = recentPrices.reduce((s, p) => s + Math.pow(p - meanPrice, 2), 0) / recentPrices.length;
      const rollingStdDev = Math.sqrt(variance);
      if (rollingStdDev > 1.5) return 'REGIME_VOLATILE';
    }
    return 'REGIME_RANGING';
  }

  public getSpreadStats(): { mean: number; sigma: number; zScore: number } {
    if (this.spreadHistory.length < 10) {
      return { mean: 0.20, sigma: 0.05, zScore: 0 };
    }
    const spreads = this.spreadHistory.slice(-200);
    const mean = spreads.reduce((a, b) => a + b, 0) / spreads.length;
    const variance = spreads.reduce((s, sp) => s + Math.pow(sp - mean, 2), 0) / spreads.length;
    const sigma = Math.sqrt(variance);
    const currentSpread = this.spreadHistory[this.spreadHistory.length - 1];
    const zScore = sigma > 0 ? (currentSpread - mean) / sigma : 0;
    return {
      mean: Math.round(mean * 10000) / 10000,
      sigma: Math.round(sigma * 10000) / 10000,
      zScore: Math.round(zScore * 100) / 100,
    };
  }

  public setTrendBias(bias: number): void {
    this.trendBias = Math.max(-0.001, Math.min(0.001, bias));
  }

  public getCurrentMid(): number { return this.currentMid; }
  public getTickHistory(): MarketTick[] { return [...this.tickHistory]; }
}

// CME Data Simulator (mimics async background fetch)
export class CMEDataSimulator {
  private lastData: CMEData | null = null;
  private fetchCounter: number = 0;

  public async fetchCMESnapshot(): Promise<CMEData> {
    // Simulates async httpx HTTP/2 fetch with JA3 rotation
    await new Promise((resolve) => setTimeout(resolve, 50 + Math.random() * 200));
    this.fetchCounter++;

    const baseIV = 0.14 + Math.random() * 0.06;
    const callVolume = Math.round(45000 + Math.random() * 20000);
    const putVolume = Math.round(38000 + Math.random() * 18000);
    const openInterest = Math.round(550000 + Math.random() * 50000);
    const callPutRatio = callVolume / putVolume;
    const gex = (callPutRatio - 1.0) * 2500000 * (Math.random() > 0.5 ? 1 : -1);
    const delta = (callVolume - putVolume) / (callVolume + putVolume);

    const data: CMEData = {
      openInterest,
      volume: callVolume + putVolume,
      callPutRatio: Math.round(callPutRatio * 1000) / 1000,
      impliedVolatility: Math.round(baseIV * 10000) / 10000,
      gamma: Math.round((baseIV * 0.85) * 10000) / 10000,
      delta: Math.round(delta * 10000) / 10000,
      gex: Math.round(gex),
      lastFetch: Date.now(),
      status: this.fetchCounter > 1 ? 'fresh' : 'cached',
    };

    this.lastData = data;
    return data;
  }

  public getCachedData(): CMEData | null { return this.lastData; }
}

// Liquidity Wall & Stop-Hunt Detector
export class LiquidityProfileScanner {
  private priceHistory: number[] = [];

  public update(price: number): void {
    this.priceHistory = [...this.priceHistory.slice(-999), price];
  }

  public detectLiquidityWalls(): { level: number; strength: number; type: 'SUPPORT' | 'RESISTANCE' }[] {
    if (this.priceHistory.length < 50) return [];
    const walls: { level: number; strength: number; type: 'SUPPORT' | 'RESISTANCE' }[] = [];
    const current = this.priceHistory[this.priceHistory.length - 1];
    const roundLevels = [
      Math.round(current / 5) * 5,
      Math.round(current / 5) * 5 + 5,
      Math.round(current / 5) * 5 - 5,
      Math.round(current / 10) * 10,
      Math.round(current / 10) * 10 + 10,
    ];
    for (const level of roundLevels) {
      const proximity = Math.abs(current - level);
      if (proximity < 3.0) {
        walls.push({
          level: Math.round(level * 1000) / 1000,
          strength: Math.round((1 - proximity / 3.0) * 100),
          type: level > current ? 'RESISTANCE' : 'SUPPORT',
        });
      }
    }
    return walls;
  }

  public detectStopHuntZone(): boolean {
    if (this.priceHistory.length < 30) return false;
    const recent = this.priceHistory.slice(-30);
    const high = Math.max(...recent);
    const low = Math.min(...recent);
    const range = high - low;
    const current = recent[recent.length - 1];
    const nearHigh = Math.abs(current - high) < range * 0.05;
    const nearLow = Math.abs(current - low) < range * 0.05;
    return nearHigh || nearLow;
  }
}
