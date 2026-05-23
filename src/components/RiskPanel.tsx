// ============================================================
// TREE DATA v3.0.0 — Risk Control Panel
// Circuit breaker, spread detector, fatal cutoff controls
// ============================================================

import type { RiskState } from '../types';

interface Props {
  riskState: RiskState | null;
  onFatalCutoff: () => void;
  onResetCircuitBreaker: () => void;
  onSimulateWebhook: (action: 'BUY' | 'SELL' | 'CLOSE') => void;
  webhookStatus: 'IDLE' | 'ACTIVE' | 'VERIFIED' | 'REJECTED';
  telegramStatus: 'CONNECTED' | 'DISCONNECTED';
  supabaseStatus: 'SYNCED' | 'SYNCING' | 'OFFLINE';
}

function GaugeBar({ value, max, color, label, subLabel }: {
  value: number; max: number; color: string; label: string; subLabel?: string;
}) {
  const pct = Math.min(100, (value / max) * 100);
  const isWarning = pct >= 75;
  const isCritical = pct >= 90;
  const barColor = isCritical ? '#FF0000' : isWarning ? '#FF6B6B' : color;

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs" style={{ fontFamily: "'Share Tech Mono', monospace" }}>
        <span style={{ color: barColor }}>{label}</span>
        <span style={{ color: barColor, fontWeight: 'bold' }}>
          {(value * 100).toFixed(2)}% / {(max * 100).toFixed(0)}%
          {subLabel && <span className="ml-1 opacity-60">{subLabel}</span>}
        </span>
      </div>
      <div className="relative h-3 rounded-full overflow-hidden" style={{ background: '#ffffff11' }}>
        <div
          className="absolute top-0 left-0 h-full rounded-full transition-all duration-500"
          style={{
            width: `${pct}%`,
            background: `linear-gradient(90deg, ${barColor}88, ${barColor})`,
            boxShadow: isCritical ? `0 0 8px ${barColor}` : 'none',
          }}
        />
      </div>
    </div>
  );
}

export function RiskPanel({
  riskState, onFatalCutoff, onResetCircuitBreaker,
  onSimulateWebhook, webhookStatus, telegramStatus, supabaseStatus,
}: Props) {
  const webhookColors = {
    IDLE: '#aaa', ACTIVE: '#FFD700', VERIFIED: '#4ADE80', REJECTED: '#FF6B6B',
  };

  return (
    <div className="space-y-4">
      {/* Infrastructure Status */}
      <div>
        <div className="text-xs font-bold mb-2 tracking-widest" style={{ color: '#00FFD1', fontFamily: "'Orbitron', monospace" }}>
          INFRASTRUCTURE STATUS
        </div>
        <div className="grid grid-cols-2 gap-2">
          {[
            { label: '🗄️ Supabase PostgreSQL', status: supabaseStatus, color: supabaseStatus === 'SYNCED' ? '#4ADE80' : supabaseStatus === 'SYNCING' ? '#FFD700' : '#FF6B6B' },
            { label: '🤖 Telegram Bot API', status: telegramStatus, color: telegramStatus === 'CONNECTED' ? '#4ADE80' : '#FF6B6B' },
            { label: '📡 CME Async Worker', status: 'HTTP/2+JA3', color: '#22D3EE' },
            { label: '🔐 HMAC Webhook', status: webhookStatus, color: webhookColors[webhookStatus] },
            { label: '☁️ Vercel Deploy', status: 'LIVE', color: '#4ADE80' },
            { label: '📋 GitHub Actions', status: 'PASSING', color: '#4ADE80' },
          ].map(({ label, status, color }) => (
            <div
              key={label}
              className="flex items-center justify-between px-2 py-1.5 rounded border text-xs"
              style={{ borderColor: `${color}33`, background: `${color}08`, fontFamily: "'Share Tech Mono', monospace" }}
            >
              <span style={{ color: '#aaa' }}>{label}</span>
              <span className="font-bold" style={{ color }}>{status}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Risk Gauges */}
      {riskState && (
        <div>
          <div className="text-xs font-bold mb-2 tracking-widest" style={{ color: '#FF6B6B', fontFamily: "'Orbitron', monospace" }}>
            RISK MONITOR
          </div>
          <div className="space-y-3 p-3 rounded-lg border" style={{ borderColor: '#FF6B6B22', background: '#0a0202' }}>
            <GaugeBar
              value={riskState.dailyDrawdownPct}
              max={riskState.maxDailyDrawdown}
              color="#FF6B6B"
              label="DAILY DRAWDOWN"
            />
            <GaugeBar
              value={riskState.totalAllocatedPct}
              max={0.40}
              color="#FFD700"
              label="TOTAL RISK ALLOCATED"
              subLabel="/ 40% MAX"
            />

            {/* Spread Z-Score */}
            <div className="space-y-1">
              <div className="flex justify-between text-xs" style={{ fontFamily: "'Share Tech Mono', monospace" }}>
                <span style={{ color: Math.abs(riskState.spreadZScore) >= 3 ? '#FF6B6B' : '#FFD700' }}>
                  3σ SPREAD DETECTOR
                </span>
                <span style={{ color: Math.abs(riskState.spreadZScore) >= 3 ? '#FF6B6B' : '#4ADE80', fontWeight: 'bold' }}>
                  Z = {riskState.spreadZScore.toFixed(2)} | {riskState.currentSpread.toFixed(4)} pts
                </span>
              </div>
              <div className="flex gap-2 text-xs" style={{ color: '#aaa', fontFamily: "'Share Tech Mono', monospace" }}>
                <span>μ={riskState.spreadMean.toFixed(4)}</span>
                <span>σ={riskState.spreadSigma.toFixed(4)}</span>
                <span>μ+3σ={Math.round((riskState.spreadMean + 3 * riskState.spreadSigma) * 10000) / 10000}</span>
              </div>
            </div>

            {/* Equity */}
            <div className="flex justify-between text-xs" style={{ fontFamily: "'Share Tech Mono', monospace" }}>
              <span style={{ color: '#22D3EE' }}>ACCOUNT EQUITY</span>
              <span className="font-bold" style={{ color: '#22D3EE' }}>
                ${riskState.accountEquity.toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </span>
            </div>

            {/* Risk breakdown */}
            <div className="grid grid-cols-3 gap-1 text-xs" style={{ fontFamily: "'Share Tech Mono', monospace" }}>
              {[
                { label: 'SCALP', value: riskState.scalpingRiskPct, max: 0.05, color: '#A855F7' },
                { label: 'INTRA', value: riskState.intradayRiskPct, max: 0.15, color: '#FFD700' },
                { label: 'LONG', value: riskState.longtermRiskPct, max: 0.25, color: '#22D3EE' },
              ].map(({ label, value, max, color }) => (
                <div key={label} className="text-center px-2 py-1 rounded" style={{ background: `${color}11`, border: `1px solid ${color}33` }}>
                  <div style={{ color: `${color}88` }}>{label}</div>
                  <div className="font-bold" style={{ color }}>{(value * 100).toFixed(0)}%</div>
                  <div style={{ color: `${color}55` }}>/{(max * 100).toFixed(0)}%</div>
                </div>
              ))}
            </div>

            {/* Status indicators */}
            <div className="flex gap-2">
              {riskState.circuitBreakerActive && (
                <div className="flex-1 text-center py-1.5 rounded border animate-pulse text-xs font-bold" style={{ borderColor: '#FF6B6B', background: '#FF6B6B22', color: '#FF6B6B', fontFamily: "'Orbitron', monospace" }}>
                  ⚡ CIRCUIT BREAKER ACTIVE
                </div>
              )}
              {riskState.fatalCutoffActive && (
                <div className="flex-1 text-center py-1.5 rounded border animate-pulse text-xs font-bold" style={{ borderColor: '#FF0000', background: '#FF000022', color: '#FF0000', fontFamily: "'Orbitron', monospace" }}>
                  💀 FATAL CUTOFF
                </div>
              )}
              {!riskState.circuitBreakerActive && !riskState.fatalCutoffActive && (
                <div className="flex-1 text-center py-1.5 rounded border text-xs font-bold" style={{ borderColor: '#4ADE8044', background: '#4ADE8011', color: '#4ADE80', fontFamily: "'Share Tech Mono', monospace" }}>
                  ✅ ALL SYSTEMS NOMINAL
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Control Buttons */}
      <div>
        <div className="text-xs font-bold mb-2 tracking-widest" style={{ color: '#A855F7', fontFamily: "'Orbitron', monospace" }}>
          OVERRIDE CONTROLS
        </div>
        <div className="space-y-2">
          {/* Webhook simulation */}
          <div className="flex gap-2">
            {(['BUY', 'SELL', 'CLOSE'] as const).map((action) => (
              <button
                key={action}
                onClick={() => onSimulateWebhook(action)}
                className="flex-1 py-1.5 rounded border text-xs font-bold transition-all duration-200 hover:opacity-80 active:scale-95"
                style={{
                  borderColor: action === 'BUY' ? '#4ADE8066' : action === 'SELL' ? '#FF6B6B66' : '#FFD70066',
                  background: action === 'BUY' ? '#4ADE8011' : action === 'SELL' ? '#FF6B6B11' : '#FFD70011',
                  color: action === 'BUY' ? '#4ADE80' : action === 'SELL' ? '#FF6B6B' : '#FFD700',
                  fontFamily: "'Orbitron', monospace",
                }}
              >
                TV {action}
              </button>
            ))}
          </div>

          {/* Circuit breaker reset */}
          <button
            onClick={onResetCircuitBreaker}
            className="w-full py-2 rounded border text-xs font-bold transition-all duration-200 hover:opacity-80 active:scale-95"
            style={{
              borderColor: '#FFD70066',
              background: '#FFD70011',
              color: '#FFD700',
              fontFamily: "'Orbitron', monospace",
            }}
          >
            ⚡ RESET CIRCUIT BREAKER
          </button>

          {/* Fatal Cutoff */}
          <button
            onClick={() => {
              if (window.confirm('⚠️ CONFIRM FATAL CUTOFF — This will liquidate ALL positions and HALT execution permanently until manual reset.')) {
                onFatalCutoff();
              }
            }}
            className="w-full py-2 rounded border text-xs font-bold transition-all duration-200 hover:opacity-80 active:scale-95"
            style={{
              borderColor: '#FF000099',
              background: '#FF000022',
              color: '#FF6B6B',
              fontFamily: "'Orbitron', monospace",
              letterSpacing: '0.1em',
            }}
          >
            🔴 /fatalcutoff — EMERGENCY HALT
          </button>

          {/* Telegram command hint */}
          <div className="text-xs text-center py-1" style={{ fontFamily: "'Share Tech Mono', monospace", color: '#ffffff33' }}>
            or send /fatalcutoff via Telegram Bot
          </div>
        </div>
      </div>
    </div>
  );
}
