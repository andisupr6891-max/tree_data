// ============================================================
// TREE DATA v3.0.0 — Trade Blotter & Performance Dashboard
// ============================================================

import type { TradeRecord, PerformanceMetric } from '../types';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';

interface Props {
  trades: TradeRecord[];
  performanceHistory: PerformanceMetric[];
  equity: number;
  totalPnL: number;
  winCount: number;
  lossCount: number;
  initialEquity: number;
}

const STATUS_COLOR: Record<TradeRecord['status'], string> = {
  OPEN: '#22D3EE',
  TP_HIT: '#4ADE80',
  SL_HIT: '#FF6B6B',
  MANUAL_CLOSE: '#FFD700',
  FATAL_CLOSE: '#FF0000',
};

const HORIZON_COLORS: Record<TradeRecord['horizon'], string> = {
  SCALPING_SNIPER: '#A855F7',
  INTRADAY: '#FFD700',
  LONG_TERM: '#22D3EE',
};

export function TradeBlotter({ trades, performanceHistory, equity, totalPnL, winCount, lossCount, initialEquity }: Props) {
  const totalTrades = winCount + lossCount;
  const winRate = totalTrades > 0 ? (winCount / totalTrades * 100) : 0;
  const equityPct = ((equity - initialEquity) / initialEquity * 100);
  const profitFactor = lossCount > 0 ? (winCount / lossCount) : winCount > 0 ? 99 : 0;

  const chartData = performanceHistory.slice(-60).map((p, i) => ({
    i,
    equity: p.equity,
    dFinal: p.dFinal * 100,
  }));

  return (
    <div className="space-y-3">
      {/* Performance KPIs */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {[
          { label: 'EQUITY', value: `$${equity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`, subvalue: `${equityPct >= 0 ? '+' : ''}${equityPct.toFixed(2)}%`, color: equityPct >= 0 ? '#4ADE80' : '#FF6B6B' },
          { label: 'TOTAL P&L', value: `${totalPnL >= 0 ? '+' : ''}$${Math.abs(totalPnL).toFixed(2)}`, subvalue: `${winCount}W / ${lossCount}L`, color: totalPnL >= 0 ? '#4ADE80' : '#FF6B6B' },
          { label: 'WIN RATE', value: `${winRate.toFixed(1)}%`, subvalue: `${totalTrades} trades`, color: winRate >= 55 ? '#4ADE80' : winRate >= 40 ? '#FFD700' : '#FF6B6B' },
          { label: 'PROFIT FACTOR', value: profitFactor >= 99 ? '∞' : profitFactor.toFixed(2), subvalue: 'W÷L ratio', color: profitFactor >= 1.5 ? '#4ADE80' : profitFactor >= 1 ? '#FFD700' : '#FF6B6B' },
        ].map(({ label, value, subvalue, color }) => (
          <div
            key={label}
            className="px-3 py-2 rounded-lg border text-center"
            style={{ borderColor: `${color}33`, background: `${color}08` }}
          >
            <div className="text-xs opacity-60 mb-1" style={{ color, fontFamily: "'Share Tech Mono', monospace" }}>{label}</div>
            <div className="text-base font-bold" style={{ color, fontFamily: "'Orbitron', monospace" }}>{value}</div>
            <div className="text-xs mt-0.5" style={{ color: `${color}88`, fontFamily: "'Share Tech Mono', monospace" }}>{subvalue}</div>
          </div>
        ))}
      </div>

      {/* Equity curve */}
      {chartData.length > 2 && (
        <div className="rounded-lg border p-3" style={{ borderColor: '#4ADE8022', background: '#020a04' }}>
          <div className="text-xs font-bold mb-2 tracking-widest" style={{ color: '#4ADE80', fontFamily: "'Orbitron', monospace" }}>
            EQUITY CURVE
          </div>
          <ResponsiveContainer width="100%" height={80}>
            <LineChart data={chartData}>
              <XAxis dataKey="i" hide />
              <YAxis domain={['auto', 'auto']} hide />
              <Tooltip
                contentStyle={{ background: '#050a06', border: '1px solid #4ADE8066', fontFamily: "'Share Tech Mono', monospace", fontSize: '11px' }}
                formatter={(val: unknown) => [`$${Number(val).toLocaleString('en-US', { minimumFractionDigits: 2 })}`, 'Equity']}
                labelFormatter={() => ''}
              />
              <ReferenceLine y={initialEquity} stroke="#FFD70044" strokeDasharray="4 4" />
              <Line type="monotone" dataKey="equity" stroke="#4ADE80" strokeWidth={1.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Trade list */}
      <div>
        <div className="text-xs font-bold mb-2 tracking-widest" style={{ color: '#22D3EE', fontFamily: "'Orbitron', monospace" }}>
          RECENT EXECUTIONS
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs" style={{ fontFamily: "'Share Tech Mono', monospace" }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #ffffff11' }}>
                {['TIME', 'SIDE', 'HORIZON', 'ENTRY', 'EXIT', 'LOT', 'P&L', 'STATUS'].map((h) => (
                  <th key={h} className="text-left px-2 py-1.5 font-bold" style={{ color: '#00FFD188' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {trades.slice(0, 10).map((trade) => {
                const pnlColor = trade.pnl === null ? '#22D3EE' : trade.pnl >= 0 ? '#4ADE80' : '#FF6B6B';
                return (
                  <tr key={trade.id} className="border-b" style={{ borderColor: '#ffffff08' }}>
                    <td className="px-2 py-1" style={{ color: '#aaa' }}>
                      {new Date(trade.timestamp).toLocaleTimeString()}
                    </td>
                    <td className="px-2 py-1">
                      <span
                        className="px-1.5 py-0.5 rounded text-xs font-bold"
                        style={{
                          background: trade.side === 'BUY' ? '#4ADE8022' : '#FF6B6B22',
                          color: trade.side === 'BUY' ? '#4ADE80' : '#FF6B6B',
                        }}
                      >
                        {trade.side}
                      </span>
                    </td>
                    <td className="px-2 py-1">
                      <span style={{ color: HORIZON_COLORS[trade.horizon] }}>
                        {trade.horizon === 'SCALPING_SNIPER' ? 'SCALP' : trade.horizon === 'INTRADAY' ? 'INTRA' : 'LONG'}
                      </span>
                    </td>
                    <td className="px-2 py-1" style={{ color: '#fff' }}>{trade.entryPrice.toFixed(3)}</td>
                    <td className="px-2 py-1" style={{ color: '#aaa' }}>{trade.exitPrice?.toFixed(3) ?? '—'}</td>
                    <td className="px-2 py-1" style={{ color: '#FFD700' }}>{trade.lotSize.toFixed(2)}</td>
                    <td className="px-2 py-1 font-bold" style={{ color: pnlColor }}>
                      {trade.pnl !== null ? `${trade.pnl >= 0 ? '+' : ''}$${trade.pnl.toFixed(2)}` : '—'}
                    </td>
                    <td className="px-2 py-1">
                      <span style={{ color: STATUS_COLOR[trade.status], fontWeight: 'bold' }}>
                        {trade.status.replace('_', ' ')}
                      </span>
                    </td>
                  </tr>
                );
              })}
              {trades.length === 0 && (
                <tr>
                  <td colSpan={8} className="text-center py-4" style={{ color: '#ffffff33' }}>
                    No trades executed yet — awaiting Sang Hakim signal
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
