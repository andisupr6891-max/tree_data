// ============================================================
// TREE DATA v3.0.0 — Market Liquidity MAP
// Minimizable institutional liquidity visualization
// ============================================================

import { useState } from 'react';
import type { CMEData, MarketTick } from '../types';

interface LiquidityWall {
  level: number;
  strength: number;
  type: 'SUPPORT' | 'RESISTANCE';
}

interface Props {
  cmeData: CMEData | null;
  currentTick: MarketTick | null;
  liquidityWalls: LiquidityWall[];
  stopHuntDetected: boolean;
}

export function LiquidityMap({ cmeData, currentTick, liquidityWalls, stopHuntDetected }: Props) {
  const [minimized, setMinimized] = useState(false);

  const currentPrice = currentTick?.mid ?? 3318.542;

  return (
    <div
      className="rounded-lg border transition-all duration-300"
      style={{ borderColor: '#FFD70033', background: '#0a0800' }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-3 py-2 cursor-pointer border-b"
        style={{ borderColor: '#FFD70022' }}
        onClick={() => setMinimized(!minimized)}
      >
        <div className="flex items-center gap-2">
          <span className="text-lg">🗺️</span>
          <span className="text-xs font-bold tracking-widest" style={{ color: '#FFD700', fontFamily: "'Orbitron', monospace" }}>
            LIQUIDITY MAP
          </span>
          {stopHuntDetected && (
            <span className="text-xs px-2 py-0.5 rounded animate-pulse" style={{ background: '#FF6B6B22', color: '#FF6B6B', border: '1px solid #FF6B6B66' }}>
              ⚠️ STOP HUNT
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs" style={{ color: '#FFD70088', fontFamily: "'Share Tech Mono', monospace" }}>
            {minimized ? '▼ EXPAND' : '▲ MINIMIZE'}
          </span>
        </div>
      </div>

      {!minimized && (
        <div className="p-3 space-y-3">
          {/* CME Options Data Grid */}
          {cmeData && (
            <div className="grid grid-cols-2 gap-2">
              {[
                { label: 'OPEN INTEREST', value: cmeData.openInterest.toLocaleString(), color: '#FFD700' },
                { label: 'TOTAL VOLUME', value: cmeData.volume.toLocaleString(), color: '#22D3EE' },
                { label: 'CALL/PUT RATIO', value: cmeData.callPutRatio.toFixed(3), color: cmeData.callPutRatio > 1 ? '#4ADE80' : '#FF6B6B' },
                { label: 'IMPLIED VOL', value: `${(cmeData.impliedVolatility * 100).toFixed(2)}%`, color: '#A855F7' },
                { label: 'GEX', value: cmeData.gex > 0 ? `+${cmeData.gex.toLocaleString()}` : cmeData.gex.toLocaleString(), color: cmeData.gex > 0 ? '#4ADE80' : '#FF6B6B' },
                { label: 'NET DELTA', value: cmeData.delta.toFixed(4), color: cmeData.delta > 0 ? '#4ADE80' : '#FF6B6B' },
              ].map(({ label, value, color }) => (
                <div
                  key={label}
                  className="px-2 py-1.5 rounded border"
                  style={{ borderColor: `${color}33`, background: `${color}08` }}
                >
                  <div className="text-xs" style={{ color: `${color}88`, fontFamily: "'Share Tech Mono', monospace" }}>{label}</div>
                  <div className="text-sm font-bold" style={{ color, fontFamily: "'Orbitron', monospace" }}>{value}</div>
                </div>
              ))}
            </div>
          )}

          {/* CME Data Status */}
          {cmeData && (
            <div className="flex items-center gap-2 text-xs" style={{ fontFamily: "'Share Tech Mono', monospace" }}>
              <div
                className="w-2 h-2 rounded-full"
                style={{ background: cmeData.status === 'fresh' ? '#4ADE80' : '#FFD700', boxShadow: `0 0 6px ${cmeData.status === 'fresh' ? '#4ADE80' : '#FFD700'}` }}
              />
              <span style={{ color: '#FFD70088' }}>
                CME {cmeData.status.toUpperCase()} | Last: {new Date(cmeData.lastFetch).toLocaleTimeString()} | HTTP/2+JA3
              </span>
            </div>
          )}

          {/* Liquidity Walls */}
          {liquidityWalls.length > 0 && (
            <div>
              <div className="text-xs mb-2 font-bold tracking-widest" style={{ color: '#FFD70088', fontFamily: "'Orbitron', monospace" }}>
                LIQUIDITY WALLS
              </div>
              <div className="space-y-1">
                {liquidityWalls.map((wall, i) => (
                  <div key={i} className="flex items-center justify-between px-2 py-1 rounded" style={{ background: wall.type === 'RESISTANCE' ? '#FF6B6B0a' : '#4ADE800a', border: `1px solid ${wall.type === 'RESISTANCE' ? '#FF6B6B33' : '#4ADE8033'}` }}>
                    <div className="flex items-center gap-2">
                      <span className="text-xs" style={{ color: wall.type === 'RESISTANCE' ? '#FF6B6B' : '#4ADE80' }}>
                        {wall.type === 'RESISTANCE' ? '▼ RES' : '▲ SUP'}
                      </span>
                      <span className="text-xs font-bold" style={{ color: '#fff', fontFamily: "'Share Tech Mono', monospace" }}>
                        {wall.level.toFixed(3)}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs" style={{ color: '#FFD70088', fontFamily: "'Share Tech Mono', monospace" }}>
                        {Math.abs(wall.level - currentPrice).toFixed(3)} away
                      </span>
                      {/* Strength bar */}
                      <div className="w-16 h-1.5 rounded-full overflow-hidden" style={{ background: '#ffffff11' }}>
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${wall.strength}%`,
                            background: wall.type === 'RESISTANCE' ? '#FF6B6B' : '#4ADE80',
                          }}
                        />
                      </div>
                      <span className="text-xs" style={{ color: '#FFD70088', fontFamily: "'Share Tech Mono', monospace" }}>
                        {wall.strength}%
      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {liquidityWalls.length === 0 && (
            <div className="text-xs text-center py-2" style={{ color: '#FFD70044', fontFamily: "'Share Tech Mono', monospace" }}>
              No significant liquidity walls detected near current price
            </div>
          )}

          {/* Stop Hunt Alert */}
          {stopHuntDetected && (
            <div className="px-3 py-2 rounded border animate-pulse" style={{ background: '#FF6B6B11', borderColor: '#FF6B6B66' }}>
              <div className="text-xs font-bold" style={{ color: '#FF6B6B', fontFamily: "'Orbitron', monospace" }}>
                ⚠️ STOP-HUNT ZONE DETECTED
              </div>
              <div className="text-xs mt-1" style={{ color: '#FF6B6B88', fontFamily: "'Share Tech Mono', monospace" }}>
                Price is near session extreme — institutional stop-loss hunting probability HIGH
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
