// ============================================================
// TREE DATA v3.0.0 — Emotional Robot Pixel Icon
// States: idle, processing, executing, profit, loss, warning, fatal
// ============================================================

import { useEffect, useState } from 'react';
import type { SystemState } from '../types';

interface Props {
  state: SystemState;
  dFinal: number;
}

const ROBOT_CONFIGS: Record<SystemState, {
  eyes: string; mouth: string; color: string; bgColor: string; label: string; blink: boolean; shake: boolean;
}> = {
  idle: {
    eyes: '◉ ◉', mouth: '─', color: '#00FFD1', bgColor: '#001a12',
    label: 'STANDBY', blink: true, shake: false,
  },
  processing: {
    eyes: '◈ ◈', mouth: '⌒', color: '#FFD700', bgColor: '#1a1400',
    label: 'PROCESSING', blink: false, shake: false,
  },
  executing: {
    eyes: '★ ★', mouth: '◡', color: '#22D3EE', bgColor: '#001a1f',
    label: 'EXECUTING', blink: false, shake: false,
  },
  profit: {
    eyes: '▲ ▲', mouth: '◠', color: '#4ADE80', bgColor: '#001a08',
    label: 'PROFIT!', blink: false, shake: false,
  },
  loss: {
    eyes: '▼ ▼', mouth: '⌢', color: '#FF6B6B', bgColor: '#1a0000',
    label: 'LOSS', blink: false, shake: true,
  },
  warning: {
    eyes: '! !', mouth: '─', color: '#FB923C', bgColor: '#1a0c00',
    label: 'WARNING', blink: true, shake: false,
  },
  fatal: {
    eyes: '✕ ✕', mouth: '⌢', color: '#FF0000', bgColor: '#1a0000',
    label: '!! FATAL !!', blink: true, shake: true,
  },
};

export function EmotionalRobot({ state, dFinal }: Props) {
  const [blinked, setBlinked] = useState(false);
  const [frame, setFrame] = useState(0);
  const config = ROBOT_CONFIGS[state];

  useEffect(() => {
    if (!config.blink) { setBlinked(false); return; }
    const t = setInterval(() => setBlinked((b) => !b), 600);
    return () => clearInterval(t);
  }, [config.blink]);

  useEffect(() => {
    const t = setInterval(() => setFrame((f) => (f + 1) % 8), 150);
    return () => clearInterval(t);
  }, []);

  const antennaY = Math.sin(frame * Math.PI / 4) * 2;
  const barCount = 8;
  const signalBars = Array.from({ length: barCount }, (_, i) => {
    const height = ((i + 1) / barCount) * 100;
    const active = Math.abs(dFinal) * barCount > i;
    return { height, active };
  });

  return (
    <div className="flex flex-col items-center gap-3">
      {/* Robot container */}
      <div
        className="relative select-none"
        style={{ fontFamily: "'VT323', monospace" }}
      >
        {/* Scan line overlay */}
        <div className="absolute inset-0 pointer-events-none z-10 overflow-hidden rounded-lg">
          <div
            className="absolute w-full h-0.5 opacity-20"
            style={{
              background: config.color,
              top: `${(frame / 8) * 100}%`,
              transition: 'top 0.1s linear',
            }}
          />
        </div>

        <div
          className="relative p-4 rounded-lg border-2 transition-all duration-300"
          style={{
            background: config.bgColor,
            borderColor: config.color,
            boxShadow: `0 0 20px ${config.color}44, inset 0 0 20px ${config.color}11`,
            transform: config.shake ? `translateX(${Math.sin(frame * 2) * 3}px)` : 'none',
          }}
        >
          {/* Head */}
          <div className="flex flex-col items-center gap-1" style={{ color: config.color }}>
            {/* Antenna */}
            <div className="flex flex-col items-center" style={{ transform: `translateY(${antennaY}px)` }}>
              <div className="w-1.5 h-1.5 rounded-full" style={{ background: config.color, boxShadow: `0 0 6px ${config.color}` }} />
              <div className="w-px h-4" style={{ background: config.color }} />
            </div>

            {/* Head box */}
            <div
              className="px-6 py-3 rounded border text-center"
              style={{ borderColor: `${config.color}66`, background: `${config.bgColor}cc` }}
            >
              {/* Eyes */}
              <div className="text-2xl tracking-widest mb-1" style={{ letterSpacing: '0.3em' }}>
                {blinked ? '─ ─' : config.eyes}
              </div>
              {/* Nose */}
              <div className="text-xs opacity-60">·</div>
              {/* Mouth */}
              <div className="text-xl mt-1" style={{ letterSpacing: '0.2em' }}>
                {config.mouth}
              </div>
            </div>

            {/* Neck */}
            <div className="flex gap-1">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="w-2 h-2" style={{ background: `${config.color}88` }} />
              ))}
            </div>

            {/* Body */}
            <div
              className="px-5 py-3 rounded border"
              style={{ borderColor: `${config.color}66`, minWidth: '120px' }}
            >
              {/* Signal bars (D_final indicator) */}
              <div className="flex items-end justify-center gap-0.5 h-8 mb-2">
                {signalBars.map((bar, i) => (
                  <div
                    key={i}
                    className="w-2 rounded-sm transition-all duration-200"
                    style={{
                      height: `${bar.height}%`,
                      background: bar.active
                        ? dFinal >= 0 ? '#4ADE80' : '#FF6B6B'
                        : `${config.color}22`,
                      boxShadow: bar.active ? `0 0 4px ${dFinal >= 0 ? '#4ADE80' : '#FF6B6B'}` : 'none',
                    }}
                  />
                ))}
              </div>
              {/* Chest display */}
              <div className="text-center text-xs opacity-80 font-mono">
                D={dFinal >= 0 ? '+' : ''}{dFinal.toFixed(3)}
              </div>
            </div>

            {/* Arms */}
            <div className="flex justify-between w-full px-1 -mt-8">
              <div className="w-3 h-8 rounded" style={{ background: `${config.color}44`, border: `1px solid ${config.color}66`, transform: state === 'executing' ? 'rotate(-20deg)' : 'none', transition: 'transform 0.3s' }} />
              <div className="w-3 h-8 rounded" style={{ background: `${config.color}44`, border: `1px solid ${config.color}66`, transform: state === 'executing' ? 'rotate(20deg)' : 'none', transition: 'transform 0.3s' }} />
            </div>

            {/* Legs */}
            <div className="flex gap-3 mt-1">
              <div className="w-3 h-5 rounded-b" style={{ background: `${config.color}44`, border: `1px solid ${config.color}66` }} />
              <div className="w-3 h-5 rounded-b" style={{ background: `${config.color}44`, border: `1px solid ${config.color}66` }} />
            </div>
          </div>
        </div>
      </div>

      {/* State label */}
      <div
        className="text-sm font-bold tracking-widest px-4 py-1 rounded border animate-pulse"
        style={{
          color: config.color,
          borderColor: config.color,
          fontFamily: "'Orbitron', monospace",
          boxShadow: `0 0 10px ${config.color}44`,
          background: `${config.color}11`,
        }}
      >
        {config.label}
      </div>
    </div>
  );
}
