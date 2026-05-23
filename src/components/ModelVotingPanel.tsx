// ============================================================
// TREE DATA v3.0.0 — 14-Model Voting Panel
// Weight matrix display with regime-partitioned visualization
// ============================================================

import type { ModelVote, MarketRegime, SangHakimDecision } from '../types';

interface Props {
  models: ModelVote[];
  regime: MarketRegime;
  decision: SangHakimDecision | null;
}

const CATEGORY_ICONS: Record<ModelVote['category'], string> = {
  STATISTICAL: '📊',
  ML: '🧠',
  QUANT: '⚛️',
  MARKET_MICROSTRUCTURE: '🔬',
};

export function ModelVotingPanel({ models, regime, decision }: Props) {
  const regimeWeight = (m: ModelVote) =>
    regime === 'REGIME_TRENDING' ? m.weight_trending : m.weight_ranging;

  const sorted = [...models].sort((a, b) => Math.abs(b.vote) - Math.abs(a.vote));

  return (
    <div className="space-y-2">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="text-xs font-bold tracking-widest" style={{ color: '#00FFD1', fontFamily: "'Orbitron', monospace" }}>
          14-MODEL VOTING MATRIX
        </div>
        <div
          className="text-xs px-2 py-0.5 rounded border"
          style={{
            color: regime === 'REGIME_TRENDING' ? '#FFD700' : '#00FFD1',
            borderColor: regime === 'REGIME_TRENDING' ? '#FFD70066' : '#00FFD166',
            fontFamily: "'Share Tech Mono', monospace",
          }}
        >
          {regime.replace('REGIME_', '')} WEIGHTS ACTIVE
        </div>
      </div>

      {/* Model rows */}
      <div className="space-y-1 max-h-96 overflow-y-auto pr-1">
        {sorted.map((model) => {
          const weight = regimeWeight(model);
          const contribution = weight * model.vote;
          const isPositive = model.vote >= 0;
          const isStrong = Math.abs(model.vote) >= 0.6;

          return (
            <div
              key={model.id}
              className="relative flex items-center gap-2 px-2 py-1.5 rounded border transition-all duration-300"
              style={{
                borderColor: isStrong ? `${model.color}55` : `${model.color}22`,
                background: `${model.color}05`,
              }}
            >
              {/* Vote bar background */}
              <div
                className="absolute inset-y-0 left-0 rounded transition-all duration-500"
                style={{
                  width: `${Math.abs(model.vote) * 50}%`,
                  marginLeft: model.vote < 0 ? 0 : '50%',
                  background: isPositive ? '#4ADE8011' : '#FF6B6B11',
                  transform: model.vote < 0 ? 'translateX(0)' : 'none',
                }}
              />

              {/* Category icon */}
              <span className="text-xs flex-shrink-0" title={model.category}>
                {CATEGORY_ICONS[model.category]}
              </span>

              {/* Model name */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1">
                  <span
                    className="text-xs font-bold truncate"
                    style={{ color: model.color, fontFamily: "'Share Tech Mono', monospace" }}
                  >
                    {model.shortName}
                  </span>
                  <span className="text-xs opacity-60 truncate hidden sm:block" style={{ color: '#aaa', fontFamily: "'Share Tech Mono', monospace" }}>
                    {model.name.replace(model.shortName, '').trim().slice(0, 20)}
                  </span>
                </div>
              </div>

              {/* Weight */}
              <div className="text-xs flex-shrink-0 w-10 text-right" style={{ color: '#FFD70088', fontFamily: "'Share Tech Mono', monospace" }}>
                {(weight * 100).toFixed(1)}%
              </div>

              {/* Vote bar */}
              <div className="flex items-center gap-1 flex-shrink-0 w-24">
                {/* Negative side */}
                <div className="w-10 h-3 rounded-sm overflow-hidden flex justify-end" style={{ background: '#FF6B6B11' }}>
                  {model.vote < 0 && (
                    <div
                      className="h-full rounded-sm"
                      style={{
                        width: `${Math.abs(model.vote) * 100}%`,
                        background: '#FF6B6B',
                        boxShadow: '0 0 4px #FF6B6B',
                      }}
                    />
                  )}
                </div>
                {/* Vote number */}
                <span
                  className="text-xs w-12 text-center font-bold"
                  style={{
                    color: isPositive ? '#4ADE80' : '#FF6B6B',
                    fontFamily: "'Share Tech Mono', monospace",
                  }}
                >
                  {model.vote >= 0 ? '+' : ''}{model.vote.toFixed(3)}
                </span>
                {/* Positive side */}
                <div className="w-10 h-3 rounded-sm overflow-hidden" style={{ background: '#4ADE8011' }}>
                  {model.vote >= 0 && (
                    <div
                      className="h-full rounded-sm"
                      style={{
                        width: `${model.vote * 100}%`,
                        background: '#4ADE80',
                        boxShadow: '0 0 4px #4ADE80',
                      }}
                    />
                  )}
                </div>
              </div>

              {/* Contribution */}
              <div
                className="text-xs flex-shrink-0 w-14 text-right font-bold"
                style={{
                  color: contribution >= 0 ? '#4ADE80' : '#FF6B6B',
                  fontFamily: "'Share Tech Mono', monospace",
                }}
              >
                {contribution >= 0 ? '+' : ''}{contribution.toFixed(4)}
              </div>
            </div>
          );
        })}
      </div>

      {/* D_final summary */}
      {decision && (
        <div
          className="mt-3 px-3 py-2 rounded border"
          style={{
            borderColor: Math.abs(decision.dFinal) >= decision.alphaThreshold ? '#4ADE8066' : '#00FFD133',
            background: '#00FFD108',
          }}
        >
          <div className="flex items-center justify-between">
            <div className="text-xs font-bold" style={{ color: '#00FFD1', fontFamily: "'Orbitron', monospace" }}>
              SANG HAKIM VERDICT
            </div>
            <div
              className="text-xs px-2 py-0.5 rounded font-bold"
              style={{
                background: decision.triggered ? (decision.side === 'BUY' ? '#4ADE8022' : '#FF6B6B22') : '#FFD70022',
                color: decision.triggered ? (decision.side === 'BUY' ? '#4ADE80' : '#FF6B6B') : '#FFD700',
                fontFamily: "'Orbitron', monospace",
              }}
            >
              {decision.triggered ? `${decision.side} ${decision.horizon?.replace('_', ' ')}` : 'BELOW α THRESHOLD'}
            </div>
          </div>
          <div className="flex items-center gap-4 mt-2">
            <div className="flex-1">
              <div className="text-xs mb-1" style={{ color: '#00FFD188', fontFamily: "'Share Tech Mono', monospace" }}>
                D_final | α = {decision.alphaThreshold}
              </div>
              <div className="relative h-4 rounded-full overflow-hidden" style={{ background: '#ffffff11' }}>
                <div
                  className="absolute top-0 bottom-0 transition-all duration-500 rounded-full"
                  style={{
                    width: `${Math.abs(decision.dFinal) * 100}%`,
                    left: decision.dFinal >= 0 ? '50%' : `${50 - Math.abs(decision.dFinal) * 50}%`,
                    background: decision.dFinal >= 0 ? 'linear-gradient(90deg, #22D3EE, #4ADE80)' : 'linear-gradient(90deg, #FF6B6B, #FF0000)',
                  }}
                />
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="text-xs font-bold" style={{ color: '#fff', fontFamily: "'Orbitron', monospace" }}>
                    {decision.dFinal >= 0 ? '+' : ''}{decision.dFinal.toFixed(4)}
                  </span>
                </div>
              </div>
            </div>
            <div
              className="text-2xl font-black"
              style={{
                color: decision.dFinal >= 0.05 ? '#4ADE80' : decision.dFinal <= -0.05 ? '#FF6B6B' : '#FFD700',
                fontFamily: "'Orbitron', monospace",
                textShadow: `0 0 20px ${decision.dFinal >= 0.05 ? '#4ADE80' : decision.dFinal <= -0.05 ? '#FF6B6B' : '#FFD700'}`,
              }}
            >
              {decision.side}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
