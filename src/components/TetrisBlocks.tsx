// ============================================================
// TREE DATA v3.0.0 — Decorative Tetris Block Background
// Animated falling tetrominos for retro aesthetic
// ============================================================

import { useEffect, useRef } from 'react';

interface TetrisBlock {
  x: number;
  y: number;
  shape: number[][];
  color: string;
  speed: number;
  rotation: number;
}

const TETROMINOS = [
  [[1,1,1,1]],                          // I
  [[1,1],[1,1]],                        // O
  [[0,1,0],[1,1,1]],                    // T
  [[1,0],[1,0],[1,1]],                  // L
  [[0,1],[0,1],[1,1]],                  // J
  [[0,1,1],[1,1,0]],                    // S
  [[1,1,0],[0,1,1]],                    // Z
];

const COLORS = ['#00FFD122', '#FFD70022', '#4ADE8022', '#FF6B6B22', '#A855F722', '#22D3EE22', '#FB923C22'];

export function TetrisBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const blocksRef = useRef<TetrisBlock[]>([]);
  const animRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const W = window.innerWidth;
    const H = window.innerHeight;
    canvas.width = W;
    canvas.height = H;

    const CELL = 24;

    // Initialize blocks
    blocksRef.current = Array.from({ length: 15 }, (_) => ({
      x: Math.random() * W,
      y: -100 - Math.random() * H,
      shape: TETROMINOS[Math.floor(Math.random() * TETROMINOS.length)],
      color: COLORS[Math.floor(Math.random() * COLORS.length)],
      speed: 0.3 + Math.random() * 0.5,
      rotation: Math.floor(Math.random() * 4),
    }));

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    function drawBlock(block: TetrisBlock) {
      if (!ctx) return;
      ctx.fillStyle = block.color;
      ctx.strokeStyle = block.color.replace('22', '44');
      ctx.lineWidth = 1;

      for (let r = 0; r < block.shape.length; r++) {
        for (let c = 0; c < block.shape[r].length; c++) {
          if (block.shape[r][c]) {
            ctx.fillRect(
              block.x + c * CELL, block.y + r * CELL,
              CELL - 1, CELL - 1
            );
            ctx.strokeRect(
              block.x + c * CELL, block.y + r * CELL,
              CELL - 1, CELL - 1
            );
          }
        }
      }
    }

    function animate() {
      if (!ctx || !canvas) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      for (const block of blocksRef.current) {
        block.y += block.speed;
        if (block.y > canvas.height + 200) {
          block.y = -150;
          block.x = Math.random() * canvas.width;
          block.shape = TETROMINOS[Math.floor(Math.random() * TETROMINOS.length)];
          block.color = COLORS[Math.floor(Math.random() * COLORS.length)];
          block.speed = 0.3 + Math.random() * 0.5;
        }
        drawBlock(block);
      }

      animRef.current = requestAnimationFrame(animate);
    }

    animate();

    const handleResize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    window.addEventListener('resize', handleResize);

    return () => {
      cancelAnimationFrame(animRef.current);
      window.removeEventListener('resize', handleResize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 w-full h-full pointer-events-none z-0 opacity-40"
    />
  );
}
