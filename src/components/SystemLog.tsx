// ============================================================
// TREE DATA v3.0.0 — Real-Time System Log Scrollbox
// Chronological terminal output with color-coded levels
// ============================================================

import { useEffect, useRef } from 'react';
import type { SystemLog } from '../types';

interface Props {
  logs: SystemLog[];
  maxVisible?: number;
}

const LEVEL_CONFIG = {
  INFO: { color: '#00FFD1', prefix: '[INFO ]', bg: '' },
  WARN: { color: '#FFD700', prefix: '[WARN ]', bg: '' },
  ERROR: { color: '#FF6B6B', prefix: '[ERROR]', bg: '' },
  FATAL: { color: '#FF0000', prefix: '[FATAL]', bg: '#1a000022' },
  SUCCESS: { color: '#4ADE80', prefix: '[SUCC ]', bg: '' },
  DEBUG: { color: '#A855F7', prefix: '[DEBUG]', bg: '' },
};

function formatTimestamp(ts: number): string {
  const d = new Date(ts);
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}.${d.getMilliseconds().toString().padStart(3, '0')}`;
}

export function SystemLogBox({ logs, maxVisible = 200 }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const isAtBottom = useRef(true);

  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    isAtBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 30;
  };

  useEffect(() => {
    if (isAtBottom.current && scrollRef.current) {
      scrollRef.current.scrollTop = 0; // newest at top
    }
  }, [logs]);

  const visible = logs.slice(0, maxVisible);

  return (
    <div
      className="relative rounded-lg border overflow-hidden"
      style={{
        background: '#050a06',
        borderColor: '#00FFD133',
        boxShadow: 'inset 0 0 20px #00FFD108',
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-3 py-2 border-b"
        style={{ borderColor: '#00FFD122', background: '#020a04' }}
      >
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
          <span className="text-xs font-bold tracking-widest" style={{ color: '#00FFD1', fontFamily: "'Orbitron', monospace" }}>
            SYSTEM LOG — LIVE FEED
          </span>
        </div>
        <div className="flex items-center gap-3 text-xs" style={{ color: '#00FFD188', fontFamily: "'Share Tech Mono', monospace" }}>
          <span>{logs.length} events</span>
          <span>|</span>
          <span>SUPABASE SYNC ✓</span>
        </div>
      </div>

      {/* Log entries */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="overflow-y-auto"
        style={{ height: '280px', fontFamily: "'Share Tech Mono', monospace" }}
      >
        {visible.map((log) => {
          const cfg = LEVEL_CONFIG[log.level];
          return (
            <div
              key={log.id}
              className="flex gap-2 px-3 py-0.5 text-xs border-b transition-all duration-200"
              style={{
                borderColor: '#00FFD108',
                background: cfg.bg || 'transparent',
                animation: 'fadeIn 0.3s ease',
              }}
            >
              <span style={{ color: '#00FFD144', minWidth: '90px', flexShrink: 0 }}>
                {formatTimestamp(log.timestamp)}
              </span>
              <span style={{ color: cfg.color, minWidth: '64px', flexShrink: 0, fontWeight: 'bold' }}>
                {cfg.prefix}
              </span>
              <span style={{ color: '#22D3EE88', minWidth: '80px', flexShrink: 0 }}>
                [{log.module.padEnd(12)}]
              </span>
              <span style={{ color: cfg.color === '#FF0000' ? '#FF6B6B' : '#e0e0e0' }}>
                {log.message}
              </span>
            </div>
          );
        })}

        {visible.length === 0 && (
          <div className="flex items-center justify-center h-full text-xs" style={{ color: '#00FFD144' }}>
            Awaiting system events...
          </div>
        )}
      </div>

      {/* Scan line effect */}
      <div className="absolute inset-0 pointer-events-none"
        style={{ background: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,255,209,0.015) 2px, rgba(0,255,209,0.015) 4px)' }}
      />
    </div>
  );
}
