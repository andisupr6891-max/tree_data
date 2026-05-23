// ============================================================
// TREE DATA v3.0.0 — XAU/USD Real-Time Price Chart
// Tetris-style retro visualization with regime coloring
// ============================================================

import { useEffect, useRef } from 'react';
import type { MarketTick, MarketRegime, TradeRecord } from '../types';

interface Props {
  ticks: MarketTick[];
  regime: MarketRegime;
  trades: TradeRecord[];
  spreadMean: number;
  spreadSigma: number;
}

const CHART_HEIGHT = 220;
const CANDLE_WIDTH = 8;
const CANDLE_GAP = 2;

export function PriceChart({ ticks, regime, trades, spreadMean, spreadSigma }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const W = canvas.offsetWidth;
    const H = CHART_HEIGHT;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    ctx.scale(dpr, dpr);

    if (ticks.length < 2) {
      ctx.fillStyle = '#050a06';
      ctx.fillRect(0, 0, W, H);
      return;
    }

    // Build OHLC candles from ticks (group by 5 ticks)
    const CANDLE_TICKS = 5;
    const candles: { open: number; high: number; low: number; close: number; volume: number }[] = [];
    for (let i = 0; i < ticks.length; i += CANDLE_TICKS) {
      const group = ticks.slice(i, i + CANDLE_TICKS);
      if (group.length === 0) continue;
      candles.push({
        open: group[0].mid,
        high: Math.max(...group.map((t) => t.ask)),
        low: Math.min(...group.map((t) => t.bid)),
        close: group[group.length - 1].mid,
        volume: group.reduce((s, t) => s + t.volume, 0),
      });
    }

    const maxCandles = Math.floor(W / (CANDLE_WIDTH + CANDLE_GAP));
    const visibleCandles = candles.slice(-maxCandles);

    const prices = visibleCandles.flatMap((c) => [c.high, c.low]);
    const minP = Math.min(...prices) - 0.5;
    const maxP = Math.max(...prices) + 0.5;
    const priceRange = maxP - minP || 1;

    const toY = (price: number) => H - ((price - minP) / priceRange) * H * 0.85 - H * 0.05;

    // Background
    ctx.fillStyle = '#050a06';
    ctx.fillRect(0, 0, W, H);

    // Grid lines
    const priceStep = priceRange / 5;
    for (let i = 0; i <= 5; i++) {
      const price = minP + priceStep * i;
      const y = toY(price);
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(W, y);
      ctx.strokeStyle = '#00FFD108';
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.fillStyle = '#00FFD144';
      ctx.font = "9px 'Share Tech Mono', monospace";
      ctx.textAlign = 'left';
      ctx.fillText(price.toFixed(3), 3, y - 2);
    }

    // Spread bands (μ ± 3σ)
    const spreadBandHigh = spreadMean + 3 * spreadSigma;
    if (visibleCandles.length > 0) {
      const lastClose = visibleCandles[visibleCandles.length - 1].close;
      const bandY = toY(lastClose + spreadBandHigh);
      ctx.beginPath();
      ctx.moveTo(0, bandY);
      ctx.lineTo(W, bandY);
      ctx.strokeStyle = '#FF6B6B33';
      ctx.lineWidth = 1;
      ctx.setLineDash([6, 4]);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Draw candles
    const regimeColor = regime === 'REGIME_TRENDING' ? '#FFD700'
      : regime === 'REGIME_VOLATILE' ? '#FF6B6B' : '#00FFD1';

    visibleCandles.forEach((candle, i) => {
      const x = i * (CANDLE_WIDTH + CANDLE_GAP) + CANDLE_GAP;
      const isBull = candle.close >= candle.open;
      const candleColor = isBull ? '#4ADE80' : '#FF6B6B';

      // Wick
      ctx.beginPath();
      ctx.moveTo(x + CANDLE_WIDTH / 2, toY(candle.high));
      ctx.lineTo(x + CANDLE_WIDTH / 2, toY(candle.low));
      ctx.strokeStyle = `${candleColor}88`;
      ctx.lineWidth = 1;
      ctx.stroke();

      // Body
      const bodyTop = toY(Math.max(candle.open, candle.close));
      const bodyBot = toY(Math.min(candle.open, candle.close));
      const bodyH = Math.max(1, bodyBot - bodyTop);
      ctx.fillStyle = isBull ? '#4ADE80cc' : '#FF6B6Bcc';
      ctx.fillRect(x, bodyTop, CANDLE_WIDTH, bodyH);
    });

    // Regime indicator line (EMA proxy)
    if (visibleCandles.length > 5) {
      const ema: number[] = [];
      let prevEma = visibleCandles[0].close;
      const k = 2 / (14 + 1);
      for (const c of visibleCandles) {
        prevEma = c.close * k + prevEma * (1 - k);
        ema.push(prevEma);
      }
      ctx.beginPath();
      ema.forEach((val, i) => {
        const x = i * (CANDLE_WIDTH + CANDLE_GAP) + CANDLE_GAP + CANDLE_WIDTH / 2;
        if (i === 0) ctx.moveTo(x, toY(val));
        else ctx.lineTo(x, toY(val));
      });
      ctx.strokeStyle = `${regimeColor}bb`;
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }

    // Open trade markers
    const openTrades = trades.filter((t) => t.status === 'OPEN');
    for (const trade of openTrades.slice(0, 3)) {
      const tpY = toY(trade.tp);
      const slY = toY(trade.sl);
      const entryY = toY(trade.entryPrice);
      // Entry line
      ctx.beginPath(); ctx.moveTo(W * 0.6, entryY); ctx.lineTo(W, entryY);
      ctx.strokeStyle = '#22D3EEcc'; ctx.lineWidth = 1; ctx.setLineDash([4, 4]); ctx.stroke();
      // TP line
      ctx.beginPath(); ctx.moveTo(W * 0.6, tpY); ctx.lineTo(W, tpY);
      ctx.strokeStyle = '#4ADE80cc'; ctx.lineWidth = 1; ctx.setLineDash([2, 6]); ctx.stroke();
      // SL line
      ctx.beginPath(); ctx.moveTo(W * 0.6, slY); ctx.lineTo(W, slY);
      ctx.strokeStyle = '#FF6B6Bcc'; ctx.lineWidth = 1; ctx.setLineDash([2, 6]); ctx.stroke();
      ctx.setLineDash([]);
    }

    // Current price marker
    if (visibleCandles.length > 0) {
      const lastPrice = visibleCandles[visibleCandles.length - 1].close;
      const y = toY(lastPrice);
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(W, y);
      ctx.strokeStyle = '#FFFFFFaa';
      ctx.lineWidth = 0.5;
      ctx.setLineDash([3, 5]);
      ctx.stroke();
      ctx.setLineDash([]);

      // Price label box
      ctx.fillStyle = '#FFD700';
      ctx.fillRect(W - 65, y - 9, 63, 18);
      ctx.fillStyle = '#000';
      ctx.font = "bold 10px 'Share Tech Mono', monospace";
      ctx.textAlign = 'center';
      ctx.fillText(lastPrice.toFixed(3), W - 33, y + 4);
    }

    // Regime badge
    ctx.fillStyle = `${regimeColor}33`;
    ctx.fillRect(W - 100, H - 22, 98, 20);
    ctx.strokeStyle = `${regimeColor}88`;
    ctx.strokeRect(W - 100, H - 22, 98, 20);
    ctx.fillStyle = regimeColor;
    ctx.font = "bold 9px 'Orbitron', monospace";
    ctx.textAlign = 'center';
    ctx.fillText(regime.replace('REGIME_', ''), W - 51, H - 9);

  }, [ticks, regime, trades, spreadMean, spreadSigma]);

  return (
    <div className="relative w-full rounded-lg overflow-hidden border" style={{ borderColor: '#00FFD122' }}>
      <canvas
        ref={canvasRef}
        style={{ width: '100%', height: `${CHART_HEIGHT}px`, display: 'block' }}
      />
    </div>
  );
}
