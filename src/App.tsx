// ============================================================
// TREE DATA v3.0.0 — Main Dashboard Application
// Client: Kembang Ayu Andini
// Retro Tetris Interface | XAU/USD Ultra-Quant System
// ============================================================

import { useState } from 'react';
import { useTreeDataEngine } from './hooks/useTreeDataEngine';
import { EmotionalRobot } from './components/EmotionalRobot';
import { ConstellationMap } from './components/ConstellationMap';
import { SystemLogBox } from './components/SystemLog';
import { PriceChart } from './components/PriceChart';
import { LiquidityMap } from './components/LiquidityMap';
import { ModelVotingPanel } from './components/ModelVotingPanel';
import { TradeBlotter } from './components/TradeBlotter';
import { RiskPanel } from './components/RiskPanel';
import { TetrisBackground } from './components/TetrisBlocks';

type TabKey = 'dashboard' | 'models' | 'trades' | 'risk' | 'system';

const TABS: { key: TabKey; label: string; icon: string }[] = [
  { key: 'dashboard', label: 'DASHBOARD', icon: '🌳' },
  { key: 'models', label: '14 MODELS', icon: '⚛️' },
  { key: 'trades', label: 'EXECUTION', icon: '🎯' },
  { key: 'risk', label: 'RISK OPS', icon: '⚡' },
  { key: 'system', label: 'SYS LOG', icon: '📋' },
];

export default function App() {
  const {
    models, ticks, currentTick, regime, cmeData, riskState, trades, logs,
    decision, systemState, performanceHistory, equity, totalPnL,
    winCount, lossCount, engineRunning, webhookStatus, telegramStatus,
    supabaseStatus, startEngine, stopEngine, triggerFatalCutoff,
    resetCircuitBreaker, simulateWebhookSignal, liquidityWalls, stopHuntDetected,
  } = useTreeDataEngine();

  const [activeTab, setActiveTab] = useState<TabKey>('dashboard');

  const dFinal = decision?.dFinal ?? 0;
  const spreadStats = riskState
    ? { mean: riskState.spreadMean, sigma: riskState.spreadSigma }
    : { mean: 0.2, sigma: 0.05 };

  const regimeColor = regime === 'REGIME_TRENDING' ? '#FFD700'
    : regime === 'REGIME_VOLATILE' ? '#FF6B6B' : '#00FFD1';

  const totalTrades = winCount + lossCount;
  const winRate = totalTrades > 0 ? (winCount / totalTrades * 100) : 0;

  return (
    <div
      className="min-h-screen w-full overflow-x-hidden"
      style={{
        background: '#020804',
        color: '#e0e0e0',
        fontFamily: "'Share Tech Mono', monospace",
      }}
    >
      {/* Tetris falling blocks background */}
      <TetrisBackground />

      {/* CRT scan line overlay */}
      <div
        className="fixed inset-0 pointer-events-none z-50 opacity-10"
        style={{
          background: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,255,209,0.05) 2px, rgba(0,255,209,0.05) 4px)',
        }}
      />

      {/* ── Header ────────────────────────────────────── */}
      <header
        className="sticky top-0 z-40 border-b px-4 py-2"
        style={{
          background: '#020804ee',
          borderColor: '#00FFD122',
          backdropFilter: 'blur(8px)',
        }}
      >
        <div className="max-w-screen-2xl mx-auto flex items-center justify-between gap-2 flex-wrap">
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div
              className="text-2xl font-black tracking-widest"
              style={{
                color: '#00FFD1',
                fontFamily: "'Orbitron', monospace",
                textShadow: '0 0 20px #00FFD155',
              }}
            >
              🌳 TREE DATA
            </div>
            <div style={{ borderLeft: '1px solid #00FFD133', paddingLeft: '12px' }}>
              <div className="text-xs font-bold" style={{ color: '#FFD700', fontFamily: "'Orbitron', monospace" }}>
                v3.0.0 ULTIMATE
              </div>
              <div className="text-xs opacity-60">XAU/USD | Kembang Ayu Andini</div>
            </div>
          </div>

          {/* Price ticker */}
          <div className="flex items-center gap-4">
            {currentTick && (
              <div className="flex items-center gap-3 px-3 py-1.5 rounded border" style={{ borderColor: '#00FFD133', background: '#00FFD108' }}>
                <div>
                  <div className="text-xs" style={{ color: '#00FFD188' }}>XAU/USD BID</div>
                  <div className="text-lg font-bold" style={{ color: '#FFD700', fontFamily: "'Orbitron', monospace" }}>
                    {currentTick.bid.toFixed(3)}
                  </div>
                </div>
                <div className="text-xs opacity-50">|</div>
                <div>
                  <div className="text-xs" style={{ color: '#00FFD188' }}>ASK</div>
                  <div className="text-base font-bold" style={{ color: '#FF6B6B' }}>
                    {currentTick.ask.toFixed(3)}
                  </div>
                </div>
                <div>
                  <div className="text-xs" style={{ color: '#00FFD188' }}>SPREAD</div>
                  <div className="text-sm font-bold" style={{ color: '#A855F7' }}>
                    {currentTick.spread.toFixed(3)}
                  </div>
                </div>
              </div>
            )}

            {/* Regime badge */}
            <div
              className="px-2 py-1 rounded text-xs font-bold"
              style={{
                color: regimeColor,
                border: `1px solid ${regimeColor}55`,
                background: `${regimeColor}11`,
                fontFamily: "'Orbitron', monospace",
              }}
            >
              {regime.replace('REGIME_', '')}
            </div>

            {/* Engine controls */}
            <div className="flex gap-2">
              <button
                onClick={engineRunning ? stopEngine : startEngine}
                className="px-3 py-1.5 rounded text-xs font-bold transition-all duration-200 hover:opacity-80 active:scale-95"
                style={{
                  background: engineRunning ? '#FF6B6B22' : '#4ADE8022',
                  border: `1px solid ${engineRunning ? '#FF6B6B66' : '#4ADE8066'}`,
                  color: engineRunning ? '#FF6B6B' : '#4ADE80',
                  fontFamily: "'Orbitron', monospace",
                }}
              >
                {engineRunning ? '⏸ STOP' : '▶ START'}
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* ── Navigation Tabs ────────────────────────────── */}
      <nav
        className="border-b px-4"
        style={{ borderColor: '#00FFD111', background: '#020804' }}
      >
        <div className="max-w-screen-2xl mx-auto flex gap-0">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className="px-4 py-2.5 text-xs font-bold tracking-widest transition-all duration-200 border-b-2"
              style={{
                color: activeTab === tab.key ? '#00FFD1' : '#ffffff44',
                borderColor: activeTab === tab.key ? '#00FFD1' : 'transparent',
                background: activeTab === tab.key ? '#00FFD108' : 'transparent',
                fontFamily: "'Orbitron', monospace",
              }}
            >
              <span className="mr-1.5">{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </div>
      </nav>

      {/* ── Status Bar ────────────────────────────────── */}
      <div
        className="px-4 py-1.5 border-b flex items-center gap-4 overflow-x-auto"
        style={{ borderColor: '#00FFD108', background: '#010602' }}
      >
        <div className="max-w-screen-2xl mx-auto flex items-center gap-4 w-full flex-wrap">
          {[
            { label: 'EQUITY', value: `$${equity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`, color: '#22D3EE' },
            { label: 'P&L', value: `${totalPnL >= 0 ? '+' : ''}$${Math.abs(totalPnL).toFixed(2)}`, color: totalPnL >= 0 ? '#4ADE80' : '#FF6B6B' },
            { label: 'WIN RATE', value: `${winRate.toFixed(1)}%`, color: winRate >= 50 ? '#4ADE80' : '#FFD700' },
            { label: 'TRADES', value: totalTrades.toString(), color: '#FFD700' },
            { label: 'D_FINAL', value: `${dFinal >= 0 ? '+' : ''}${dFinal.toFixed(4)}`, color: Math.abs(dFinal) >= 0.8 ? '#4ADE80' : '#00FFD1' },
            { label: 'WEBHOOK', value: webhookStatus, color: webhookStatus === 'VERIFIED' ? '#4ADE80' : webhookStatus === 'REJECTED' ? '#FF6B6B' : '#FFD700' },
            { label: 'SUPABASE', value: supabaseStatus, color: supabaseStatus === 'SYNCED' ? '#4ADE80' : '#FFD700' },
            { label: 'TELEGRAM', value: telegramStatus, color: telegramStatus === 'CONNECTED' ? '#4ADE80' : '#FF6B6B' },
          ].map(({ label, value, color }) => (
            <div key={label} className="flex items-center gap-1.5 flex-shrink-0 text-xs" style={{ fontFamily: "'Share Tech Mono', monospace" }}>
              <span style={{ color: '#ffffff33' }}>{label}:</span>
              <span className="font-bold" style={{ color }}>{value}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Main Content ───────────────────────────────── */}
      <main className="max-w-screen-2xl mx-auto px-4 py-4">

        {/* ═══════════════ DASHBOARD TAB ═══════════════ */}
        {activeTab === 'dashboard' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Left column: Robot + Decision */}
            <div className="space-y-4">
              {/* Emotional Robot */}
              <div
                className="p-4 rounded-lg border"
                style={{ borderColor: '#00FFD122', background: '#030d05' }}
              >
                <div className="text-xs font-bold mb-3 tracking-widest text-center" style={{ color: '#00FFD1', fontFamily: "'Orbitron', monospace" }}>
                  SYSTEM STATE MONITOR
                </div>
                <EmotionalRobot state={systemState} dFinal={dFinal} />
              </div>

              {/* Sang Hakim Quick Decision */}
              {decision && (
                <div
                  className="p-4 rounded-lg border"
                  style={{
                    borderColor: decision.triggered ? '#4ADE8066' : '#00FFD122',
                    background: '#030d05',
                  }}
                >
                  <div className="text-xs font-bold mb-3 tracking-widest" style={{ color: '#00FFD1', fontFamily: "'Orbitron', monospace" }}>
                    SANG HAKIM ARBITER
                  </div>
                  <div className="space-y-2 text-xs" style={{ fontFamily: "'Share Tech Mono', monospace" }}>
                    <div className="flex justify-between">
                      <span style={{ color: '#aaa' }}>D_FINAL</span>
                      <span className="font-bold text-base" style={{
                        color: decision.dFinal >= 0.05 ? '#4ADE80' : decision.dFinal <= -0.05 ? '#FF6B6B' : '#FFD700',
                        fontFamily: "'Orbitron', monospace",
                      }}>
                        {decision.dFinal >= 0 ? '+' : ''}{decision.dFinal.toFixed(4)}
                      </span>
                    </div>
                    {/* D_final bar */}
                    <div className="relative h-5 rounded overflow-hidden" style={{ background: '#ffffff11' }}>
                      <div
                        className="absolute top-0 h-full rounded transition-all duration-500"
                        style={{
                          width: `${Math.abs(decision.dFinal) * 50}%`,
                          left: decision.dFinal >= 0 ? '50%' : `${50 - Math.abs(decision.dFinal) * 50}%`,
                          background: decision.dFinal >= 0
                            ? 'linear-gradient(90deg, #22D3EE, #4ADE80)'
                            : 'linear-gradient(90deg, #FF6B6B, #FF0000)',
                        }}
                      />
                      {/* Alpha threshold markers */}
                      <div className="absolute top-0 bottom-0 w-px" style={{ left: `${50 + 80 * 50 / 100}%`, background: '#FFD70088' }} />
                      <div className="absolute top-0 bottom-0 w-px" style={{ left: `${50 - 80 * 50 / 100}%`, background: '#FFD70088' }} />
                      <div className="absolute inset-0 flex items-center justify-center text-xs font-bold" style={{ color: '#fff', fontFamily: "'Orbitron', monospace" }}>
                        α=0.80
                      </div>
                    </div>
                    <div className="flex justify-between">
                      <span style={{ color: '#aaa' }}>SIGNAL</span>
                      <span className="font-bold" style={{
                        color: decision.side === 'BUY' ? '#4ADE80' : decision.side === 'SELL' ? '#FF6B6B' : '#FFD700',
                        fontFamily: "'Orbitron', monospace",
                      }}>
                        {decision.side}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span style={{ color: '#aaa' }}>HORIZON</span>
                      <span style={{ color: '#22D3EE' }}>{decision.horizon?.replace('_', ' ') ?? 'WAITING'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span style={{ color: '#aaa' }}>TRIGGERED</span>
                      <span style={{ color: decision.triggered ? '#4ADE80' : '#FF6B6B' }}>
                        {decision.triggered ? '✅ YES' : '⏳ NO'}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span style={{ color: '#aaa' }}>REGIME</span>
                      <span style={{ color: regimeColor }}>{regime.replace('REGIME_', '')}</span>
                    </div>
                  </div>
                </div>
              )}

              {/* Quick stats */}
              <div className="grid grid-cols-2 gap-2">
                {[
                  { label: 'OPEN TRADES', value: trades.filter(t => t.status === 'OPEN').length.toString(), color: '#22D3EE' },
                  { label: 'DRAWDOWN', value: riskState ? `${(riskState.dailyDrawdownPct * 100).toFixed(2)}%` : '0.00%', color: (riskState?.dailyDrawdownPct ?? 0) > 0.08 ? '#FF6B6B' : '#4ADE80' },
                ].map(({ label, value, color }) => (
                  <div key={label} className="px-3 py-2 rounded border text-center" style={{ borderColor: `${color}33`, background: `${color}08` }}>
                    <div className="text-xs mb-1" style={{ color: `${color}88`, fontFamily: "'Share Tech Mono', monospace" }}>{label}</div>
                    <div className="text-xl font-bold" style={{ color, fontFamily: "'Orbitron', monospace" }}>{value}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Center column: Price chart + Constellation */}
            <div className="space-y-4">
              {/* Price chart */}
              <div
                className="p-3 rounded-lg border"
                style={{ borderColor: '#00FFD122', background: '#030d05' }}
              >
                <div className="text-xs font-bold mb-2 tracking-widest" style={{ color: '#00FFD1', fontFamily: "'Orbitron', monospace" }}>
                  XAU/USD LIVE CHART — 3-DECIMAL PRECISION
                </div>
                <PriceChart
                  ticks={ticks}
                  regime={regime}
                  trades={trades}
                  spreadMean={spreadStats.mean}
                  spreadSigma={spreadStats.sigma}
                />
                {currentTick && (
                  <div className="flex gap-4 mt-2 text-xs" style={{ color: '#ffffff55', fontFamily: "'Share Tech Mono', monospace" }}>
                    <span>BID: {currentTick.bid.toFixed(3)}</span>
                    <span>ASK: {currentTick.ask.toFixed(3)}</span>
                    <span>SPREAD: {currentTick.spread.toFixed(3)}</span>
                    <span>VOL: {currentTick.volume}</span>
                  </div>
                )}
              </div>

              {/* Constellation Map */}
              <div
                className="p-3 rounded-lg border"
                style={{ borderColor: '#00FFD122', background: '#030d05' }}
              >
                <div className="text-xs font-bold mb-1 tracking-widest" style={{ color: '#00FFD1', fontFamily: "'Orbitron', monospace" }}>
                  CONSTELLATION MAP — 14-MODEL CLUSTER
                </div>
                <ConstellationMap models={models} regime={regime} dFinal={dFinal} />
              </div>
            </div>

            {/* Right column: Liquidity + System Log */}
            <div className="space-y-4">
              <LiquidityMap
                cmeData={cmeData}
                currentTick={currentTick}
                liquidityWalls={liquidityWalls}
                stopHuntDetected={stopHuntDetected}
              />

              <div
                className="p-3 rounded-lg border"
                style={{ borderColor: '#00FFD122', background: '#030d05' }}
              >
                <SystemLogBox logs={logs} maxVisible={100} />
              </div>

              {/* Risk summary */}
              {riskState && (
                <div className="p-3 rounded-lg border space-y-2" style={{ borderColor: '#FF6B6B22', background: '#0a0202' }}>
                  <div className="text-xs font-bold tracking-widest" style={{ color: '#FF6B6B', fontFamily: "'Orbitron', monospace" }}>
                    RISK STATUS
                  </div>
                  <div className="relative h-2 rounded-full overflow-hidden" style={{ background: '#ffffff11' }}>
                    <div
                      className="absolute top-0 left-0 h-full rounded-full transition-all duration-500"
                      style={{
                        width: `${Math.min(100, (riskState.dailyDrawdownPct / riskState.maxDailyDrawdown) * 100)}%`,
                        background: riskState.dailyDrawdownPct > riskState.maxDailyDrawdown * 0.8 ? '#FF0000' : '#FF6B6B',
                      }}
                    />
                  </div>
                  <div className="flex justify-between text-xs" style={{ fontFamily: "'Share Tech Mono', monospace", color: '#aaa' }}>
                    <span>Daily DD: {(riskState.dailyDrawdownPct * 100).toFixed(2)}%</span>
                    <span>Max: {(riskState.maxDailyDrawdown * 100).toFixed(0)}%</span>
                  </div>
                  {riskState.circuitBreakerActive && (
                    <div className="text-xs text-center py-1 font-bold animate-pulse" style={{ color: '#FF0000', fontFamily: "'Orbitron', monospace" }}>
                      ⚡ CIRCUIT BREAKER ACTIVE
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ═══════════════ MODELS TAB ═══════════════ */}
        {activeTab === 'models' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div
              className="p-4 rounded-lg border"
              style={{ borderColor: '#00FFD122', background: '#030d05' }}
            >
              <ModelVotingPanel models={models} regime={regime} decision={decision} />
            </div>
            <div
              className="p-4 rounded-lg border"
              style={{ borderColor: '#00FFD122', background: '#030d05' }}
            >
              <div className="text-xs font-bold mb-3 tracking-widest" style={{ color: '#00FFD1', fontFamily: "'Orbitron', monospace" }}>
                CONSTELLATION MAP
              </div>
              <ConstellationMap models={models} regime={regime} dFinal={dFinal} />

              {/* Weight matrix breakdown */}
              <div className="mt-4 space-y-2">
                <div className="text-xs font-bold tracking-widest" style={{ color: '#A855F7', fontFamily: "'Orbitron', monospace" }}>
                  MWUM WEIGHT EVOLUTION
                </div>
                <div className="text-xs" style={{ color: '#aaa', fontFamily: "'Share Tech Mono', monospace" }}>
                  <div>η (learning rate): <span style={{ color: '#FFD700' }}>0.12</span></div>
                  <div>Normalization: <span style={{ color: '#4ADE80' }}>Σ W_i = 1.000 ✓</span></div>
                  <div>Active regime: <span style={{ color: regimeColor }}>{regime}</span></div>
                  <div>Regime γ multiplier: <span style={{ color: '#22D3EE' }}>1.5 × mean(ATR)</span></div>
                </div>
                <div className="grid grid-cols-2 gap-2 mt-3">
                  {(['STATISTICAL', 'ML', 'QUANT', 'MARKET_MICROSTRUCTURE'] as const).map((cat) => {
                    const catModels = models.filter(m => m.category === cat);
                    const avgVote = catModels.reduce((s, m) => s + m.vote, 0) / catModels.length;
                    const icons = { STATISTICAL: '📊', ML: '🧠', QUANT: '⚛️', MARKET_MICROSTRUCTURE: '🔬' };
                    return (
                      <div key={cat} className="px-2 py-1.5 rounded border text-xs" style={{ borderColor: '#00FFD122', background: '#020a04' }}>
                        <div className="flex justify-between mb-1">
                          <span style={{ color: '#00FFD188' }}>{icons[cat]} {cat.replace('_', ' ')}</span>
                          <span style={{ color: avgVote >= 0 ? '#4ADE80' : '#FF6B6B', fontWeight: 'bold' }}>
                            {avgVote >= 0 ? '+' : ''}{avgVote.toFixed(3)}
                          </span>
                        </div>
                        <div style={{ color: '#aaa', fontFamily: "'Share Tech Mono', monospace" }}>
                          {catModels.length} models
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ═══════════════ TRADES TAB ═══════════════ */}
        {activeTab === 'trades' && (
          <div
            className="p-4 rounded-lg border"
            style={{ borderColor: '#4ADE8022', background: '#030d05' }}
          >
            <TradeBlotter
              trades={trades}
              performanceHistory={performanceHistory}
              equity={equity}
              totalPnL={totalPnL}
              winCount={winCount}
              lossCount={lossCount}
              initialEquity={50000}
            />
          </div>
        )}

        {/* ═══════════════ RISK TAB ═══════════════ */}
        {activeTab === 'risk' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div
              className="p-4 rounded-lg border"
              style={{ borderColor: '#FF6B6B22', background: '#030d05' }}
            >
              <RiskPanel
                riskState={riskState}
                onFatalCutoff={triggerFatalCutoff}
                onResetCircuitBreaker={resetCircuitBreaker}
                onSimulateWebhook={simulateWebhookSignal}
                webhookStatus={webhookStatus}
                telegramStatus={telegramStatus}
                supabaseStatus={supabaseStatus}
              />
            </div>
            <div className="space-y-4">
              <div
                className="p-4 rounded-lg border"
                style={{ borderColor: '#FFD70022', background: '#030d05' }}
              >
                <LiquidityMap
                  cmeData={cmeData}
                  currentTick={currentTick}
                  liquidityWalls={liquidityWalls}
                  stopHuntDetected={stopHuntDetected}
                />
              </div>
              {/* Horizon risk breakdown */}
              <div className="p-4 rounded-lg border" style={{ borderColor: '#A855F722', background: '#030d05' }}>
                <div className="text-xs font-bold mb-3 tracking-widest" style={{ color: '#A855F7', fontFamily: "'Orbitron', monospace" }}>
                  RISK BUDGET ALLOCATION
                </div>
                <div className="space-y-3">
                  {[
                    { horizon: 'SCALPING SNIPER', min: '2%', max: '5%', default: '3%', color: '#A855F7', slPts: '0.300', tpR: '1.5×' },
                    { horizon: 'INTRADAY', min: '10%', max: '15%', default: '12%', color: '#FFD700', slPts: '1.500', tpR: '2.0×' },
                    { horizon: 'LONG TERM', min: '20%', max: '25%', default: '22%', color: '#22D3EE', slPts: '5.000', tpR: '2.5×' },
                  ].map(({ horizon, min, max, default: def, color, slPts, tpR }) => (
                    <div key={horizon} className="px-3 py-2 rounded border" style={{ borderColor: `${color}33`, background: `${color}08` }}>
                      <div className="flex justify-between items-center mb-1">
                        <span className="text-xs font-bold" style={{ color, fontFamily: "'Orbitron', monospace" }}>{horizon}</span>
                        <span className="text-xs" style={{ color: `${color}88` }}>{min} – {max} equity</span>
                      </div>
                      <div className="grid grid-cols-3 gap-1 text-xs" style={{ color: '#aaa', fontFamily: "'Share Tech Mono', monospace" }}>
                        <span>Default: <span style={{ color }}>{def}</span></span>
                        <span>SL: <span style={{ color }}>±{slPts}</span></span>
                        <span>TP: <span style={{ color }}>{tpR} SL</span></span>
                      </div>
                    </div>
                  ))}
                  <div className="text-xs text-center py-1 rounded border" style={{ borderColor: '#ffffff22', color: '#ffffff55', fontFamily: "'Share Tech Mono', monospace" }}>
                    Total Cap: 40% equity | Circuit Breaker: 12% daily DD
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ═══════════════ SYSTEM LOG TAB ═══════════════ */}
        {activeTab === 'system' && (
          <div className="space-y-4">
            {/* Module status grid */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
              {[
                { module: 'TICK ENGINE', status: engineRunning ? 'ONLINE' : 'OFFLINE', color: engineRunning ? '#4ADE80' : '#FF6B6B', desc: '800ms interval' },
                { module: 'CME WORKER', status: cmeData ? 'ACTIVE' : 'PENDING', color: cmeData ? '#4ADE80' : '#FFD700', desc: 'HTTP/2+JA3' },
                { module: 'SANG HAKIM', status: decision ? 'RUNNING' : 'IDLE', color: decision ? '#22D3EE' : '#aaa', desc: '2s decision loop' },
                { module: 'MWUM ENGINE', status: 'READY', color: '#A855F7', desc: 'η=0.12' },
                { module: 'FAIL_SAFE', status: riskState?.circuitBreakerActive ? 'TRIPPED' : 'NOMINAL', color: riskState?.circuitBreakerActive ? '#FF0000' : '#4ADE80', desc: '500ms poll' },
                { module: 'WEBHOOK', status: webhookStatus, color: webhookStatus === 'VERIFIED' ? '#4ADE80' : '#FFD700', desc: 'HMAC-SHA256' },
              ].map(({ module, status, color, desc }) => (
                <div key={module} className="px-3 py-2 rounded border text-center" style={{ borderColor: `${color}33`, background: `${color}08` }}>
                  <div className="w-2 h-2 rounded-full mx-auto mb-1" style={{ background: color, boxShadow: `0 0 6px ${color}` }} />
                  <div className="text-xs font-bold" style={{ color, fontFamily: "'Orbitron', monospace", fontSize: '9px' }}>{module}</div>
                  <div className="text-xs font-bold mt-0.5" style={{ color }}>{status}</div>
                  <div className="text-xs mt-0.5" style={{ color: '#ffffff33', fontFamily: "'Share Tech Mono', monospace", fontSize: '9px' }}>{desc}</div>
                </div>
              ))}
            </div>

            {/* Full log box */}
            <div
              className="p-3 rounded-lg border"
              style={{ borderColor: '#00FFD122', background: '#030d05' }}
            >
              <SystemLogBox logs={logs} maxVisible={500} />
            </div>

            {/* Python module reference */}
            <div className="p-4 rounded-lg border" style={{ borderColor: '#A855F722', background: '#030d05' }}>
              <div className="text-xs font-bold mb-3 tracking-widest" style={{ color: '#A855F7', fontFamily: "'Orbitron', monospace" }}>
                PYTHON BACKEND MODULES
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs" style={{ fontFamily: "'Share Tech Mono', monospace" }}>
                {[
                  { file: 'config.py', desc: 'Global constants, risk rules, cryptographic parameters', color: '#00FFD1' },
                  { file: 'connectors/meta_trader_gateway.py', desc: 'Exness MT5 decimal.Decimal routing layer', color: '#FFD700' },
                  { file: 'engine/data_learning_engine.py', desc: 'MWUM self-learning, regime partitioning, SQLite cache', color: '#4ADE80' },
                  { file: 'engine/risk/fail_safe_engine.py', desc: 'Circuit breaker, 3σ spread detector, 500ms thread', color: '#FF6B6B' },
                  { file: 'engine/sang_hakim.py', desc: 'Sang Hakim voting aggregation + order specification', color: '#22D3EE' },
                  { file: 'webhook_receiver.py', desc: 'FastAPI HMAC webhook + Token Bucket rate limiter', color: '#A855F7' },
                ].map(({ file, desc, color }) => (
                  <div key={file} className="px-3 py-2 rounded border" style={{ borderColor: `${color}22`, background: `${color}05` }}>
                    <div className="font-bold mb-0.5" style={{ color }}>{file}</div>
                    <div style={{ color: '#ffffff66' }}>{desc}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

      </main>

      {/* ── Footer ────────────────────────────────────── */}
      <footer
        className="mt-8 px-4 py-3 border-t text-center text-xs"
        style={{ borderColor: '#00FFD111', color: '#ffffff22', fontFamily: "'Share Tech Mono', monospace" }}
      >
        TREE DATA v3.0.0 ULTIMATE EDITION | XAU/USD Ultra-Quant System | Client: Kembang Ayu Andini |
        14-Model Predictive Voting | Sang Hakim Arbiter | MWUM Self-Learning | Exness MT5 | CME Group
      </footer>
    </div>
  );
}
