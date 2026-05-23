// ============================================================
// TREE DATA v3.0.0 — Constellation Map: 14 Model Nodes
// Circular cluster with pulsing votes and dynamic connections
// ============================================================

import { useEffect, useRef, useState } from 'react';
import type { ModelVote, MarketRegime } from '../types';

interface Props {
  models: ModelVote[];
  regime: MarketRegime;
  dFinal: number;
}

interface NodePosition {
  x: number;
  y: number;
  model: ModelVote;
}

const CANVAS_SIZE = 460;
const CENTER = CANVAS_SIZE / 2;
const ORBIT_RADIUS = 170;
const NODE_RADIUS = 22;

export function ConstellationMap({ models, regime, dFinal }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animFrameRef = useRef<number>(0);
  const [hoveredNode, setHoveredNode] = useState<number | null>(null);
  const [pulsePhase, setPulsePhase] = useState(0);

  // Compute node positions in circular layout
  const getNodePositions = (): NodePosition[] => {
    return models.map((model, i) => {
      const angle = (2 * Math.PI * i) / models.length - Math.PI / 2;
      return {
        x: CENTER + ORBIT_RADIUS * Math.cos(angle),
        y: CENTER + ORBIT_RADIUS * Math.sin(angle),
        model,
      };
    });
  };

  useEffect(() => {
    let phase = 0;
    const animate = () => {
      phase += 0.04;
      setPulsePhase(phase);
      animFrameRef.current = requestAnimationFrame(animate);
    };
    animFrameRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animFrameRef.current);
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = CANVAS_SIZE * dpr;
    canvas.height = CANVAS_SIZE * dpr;
    ctx.scale(dpr, dpr);

    // Clear
    ctx.clearRect(0, 0, CANVAS_SIZE, CANVAS_SIZE);

    const nodes = getNodePositions();
    const regimeColor = regime === 'REGIME_TRENDING' ? '#FFD700'
      : regime === 'REGIME_VOLATILE' ? '#FF6B6B' : '#00FFD1';

    // ── Background grid ──────────────────────────────────────
    ctx.strokeStyle = '#00FFD108';
    ctx.lineWidth = 0.5;
    for (let i = 0; i < CANVAS_SIZE; i += 30) {
      ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i, CANVAS_SIZE); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(0, i); ctx.lineTo(CANVAS_SIZE, i); ctx.stroke();
    }

    // ── Orbit ring ────────────────────────────────────────────
    ctx.beginPath();
    ctx.arc(CENTER, CENTER, ORBIT_RADIUS, 0, 2 * Math.PI);
    ctx.strokeStyle = `${regimeColor}22`;
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 8]);
    ctx.stroke();
    ctx.setLineDash([]);

    // ── Connections (high-vote agreement) ─────────────────────
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const mi = nodes[i].model;
        const mj = nodes[j].model;
        const agreement = mi.vote * mj.vote;
        if (agreement > 0.2) {
          const alpha = Math.min(0.6, agreement * 0.8);
          const lineColor = agreement > 0 ? '#4ADE80' : '#FF6B6B';
          ctx.beginPath();
          ctx.moveTo(nodes[i].x, nodes[i].y);
          ctx.lineTo(nodes[j].x, nodes[j].y);
          ctx.strokeStyle = `${lineColor}${Math.floor(alpha * 255).toString(16).padStart(2, '0')}`;
          ctx.lineWidth = agreement > 0.5 ? 1.5 : 0.8;
          ctx.stroke();
        }
      }
    }

    // ── Center hub ───────────────────────────────────────────
    const hubPulse = 1 + 0.15 * Math.sin(pulsePhase);
    const hubRadius = 28 * hubPulse;
    const dGrad = ctx.createRadialGradient(CENTER, CENTER, 0, CENTER, CENTER, hubRadius);
    const hubColor = dFinal >= 0.8 ? '#4ADE80' : dFinal <= -0.8 ? '#FF6B6B' : regimeColor;
    dGrad.addColorStop(0, `${hubColor}cc`);
    dGrad.addColorStop(0.5, `${hubColor}55`);
    dGrad.addColorStop(1, `${hubColor}00`);
    ctx.beginPath();
    ctx.arc(CENTER, CENTER, hubRadius, 0, 2 * Math.PI);
    ctx.fillStyle = dGrad;
    ctx.fill();

    // Center text
    ctx.fillStyle = hubColor;
    ctx.font = "bold 11px 'Orbitron', monospace";
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('HAKIM', CENTER, CENTER - 8);
    ctx.font = "bold 13px 'Share Tech Mono', monospace";
    ctx.fillText((dFinal >= 0 ? '+' : '') + dFinal.toFixed(3), CENTER, CENTER + 8);

    // ── Connection spokes from center ─────────────────────────
    for (const node of nodes) {
      const voteAbs = Math.abs(node.model.vote);
      if (voteAbs < 0.1) continue;
      const alpha = voteAbs * 0.4;
      const spokeColor = node.model.vote >= 0 ? '#4ADE80' : '#FF6B6B';
      ctx.beginPath();
      ctx.moveTo(CENTER, CENTER);
      ctx.lineTo(node.x, node.y);
      ctx.strokeStyle = `${spokeColor}${Math.floor(alpha * 255).toString(16).padStart(2, '0')}`;
      ctx.lineWidth = 0.5;
      ctx.stroke();
    }

    // ── Model nodes ──────────────────────────────────────────
    for (const node of nodes) {
      const { x, y, model } = node;
      const isHovered = hoveredNode === model.id;
      const voteAbs = Math.abs(model.vote);
      const pulseAmplitude = 0.12 + voteAbs * 0.08;
      const pulse = 1 + pulseAmplitude * Math.sin(pulsePhase + model.id * 0.5);
      const r = (isHovered ? NODE_RADIUS * 1.3 : NODE_RADIUS) * pulse;

      // Glow
      const glow = ctx.createRadialGradient(x, y, 0, x, y, r * 1.8);
      glow.addColorStop(0, `${model.color}66`);
      glow.addColorStop(1, `${model.color}00`);
      ctx.beginPath();
      ctx.arc(x, y, r * 1.8, 0, 2 * Math.PI);
      ctx.fillStyle = glow;
      ctx.fill();

      // Node background
      ctx.beginPath();
      ctx.arc(x, y, r, 0, 2 * Math.PI);
      ctx.fillStyle = `#0a0a0a`;
      ctx.fill();

      // Vote arc indicator
      const startAngle = -Math.PI / 2;
      const endAngle = startAngle + (2 * Math.PI * Math.abs(model.vote));
      ctx.beginPath();
      ctx.arc(x, y, r, startAngle, endAngle);
      ctx.strokeStyle = model.vote >= 0 ? '#4ADE80' : '#FF6B6B';
      ctx.lineWidth = 3;
      ctx.stroke();

      // Node border
      ctx.beginPath();
      ctx.arc(x, y, r, 0, 2 * Math.PI);
      ctx.strokeStyle = model.color;
      ctx.lineWidth = isHovered ? 2.5 : 1.5;
      ctx.stroke();

      // Label
      ctx.fillStyle = model.color;
      ctx.font = `bold ${isHovered ? 10 : 9}px 'Share Tech Mono', monospace`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(model.shortName, x, y - 3);
      ctx.font = `8px 'Share Tech Mono', monospace`;
      ctx.fillStyle = model.vote >= 0 ? '#4ADE80' : '#FF6B6B';
      ctx.fillText((model.vote >= 0 ? '+' : '') + model.vote.toFixed(2), x, y + 7);
    }

    // ── Regime label ──────────────────────────────────────────
    ctx.fillStyle = regimeColor;
    ctx.font = "bold 10px 'Orbitron', monospace";
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(regime.replace('REGIME_', ''), CENTER, 8);

  }, [models, regime, dFinal, pulsePhase, hoveredNode]);

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const scaleX = CANVAS_SIZE / rect.width;
    const scaleY = CANVAS_SIZE / rect.height;
    const mx = (e.clientX - rect.left) * scaleX;
    const my = (e.clientY - rect.top) * scaleY;
    const nodes = getNodePositions();
    const hit = nodes.find(({ x, y }) => Math.sqrt((mx - x) ** 2 + (my - y) ** 2) < NODE_RADIUS * 1.4);
    setHoveredNode(hit ? hit.model.id : null);
  };

  const hoveredModel = hoveredNode !== null ? models.find((m) => m.id === hoveredNode) : null;

  return (
    <div className="relative flex flex-col items-center">
      <canvas
        ref={canvasRef}
        width={CANVAS_SIZE}
        height={CANVAS_SIZE}
        style={{ width: '100%', maxWidth: `${CANVAS_SIZE}px`, cursor: 'crosshair' }}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHoveredNode(null)}
      />
      {hoveredModel && (
        <div
          className="absolute top-2 right-2 text-xs p-2 rounded border z-20"
          style={{
            background: '#0a0f0a',
            borderColor: hoveredModel.color,
            color: hoveredModel.color,
            fontFamily: "'Share Tech Mono', monospace",
            boxShadow: `0 0 10px ${hoveredModel.color}44`,
            minWidth: '180px',
          }}
        >
          <div className="font-bold mb-1">{hoveredModel.name}</div>
          <div>Vote: {hoveredModel.vote >= 0 ? '+' : ''}{hoveredModel.vote.toFixed(4)}</div>
          <div>Confidence: {(hoveredModel.confidence * 100).toFixed(1)}%</div>
          <div>W(Trend): {(hoveredModel.weight_trending * 100).toFixed(2)}%</div>
          <div>W(Range): {(hoveredModel.weight_ranging * 100).toFixed(2)}%</div>
          <div>Category: {hoveredModel.category}</div>
        </div>
      )}
    </div>
  );
}
