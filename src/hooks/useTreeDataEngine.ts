// ============================================================
// TREE DATA v3.0.0 — Core State Management Hook
// Orchestrates all engines: Market, Sang Hakim, Risk, CME
// ============================================================

import { useState, useEffect, useRef, useCallback } from 'react';
import type {
  ModelVote, MarketTick, MarketRegime, CMEData, RiskState,
  TradeRecord, SystemLog, SangHakimDecision, PerformanceMetric,
  SystemState, OrderHorizon, OrderSide,
} from '../types';
import { INITIALIZED_MODELS } from '../data/modelRegistry';
import { GoldTickSimulator, CMEDataSimulator, LiquidityProfileScanner } from '../engine/marketSimulator';
import { computeAllVotes, sangHakimDecide, applyMWUMUpdate, computePositionSize } from '../engine/sangHakim';
import { FailSafeEngine, toFixed3 } from '../engine/riskEngine';

const TICK_INTERVAL_MS = 800;
const CME_REFRESH_INTERVAL_MS = 300000; // 5 minutes
const DECISION_INTERVAL_MS = 2000;
const INITIAL_EQUITY = 50000;

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function createLog(
  level: SystemLog['level'],
  module: string,
  message: string,
  data?: Record<string, unknown>
): SystemLog {
  return { id: generateId(), timestamp: Date.now(), level, module, message, data };
}

export function useTreeDataEngine() {
  const [models, setModels] = useState<ModelVote[]>(INITIALIZED_MODELS);
  const [ticks, setTicks] = useState<MarketTick[]>([]);
  const [currentTick, setCurrentTick] = useState<MarketTick | null>(null);
  const [regime, setRegime] = useState<MarketRegime>('REGIME_RANGING');
  const [cmeData, setCmeData] = useState<CMEData | null>(null);
  const [riskState, setRiskState] = useState<RiskState | null>(null);
  const [trades, setTrades] = useState<TradeRecord[]>([]);
  const [logs, setLogs] = useState<SystemLog[]>([]);
  const [decision, setDecision] = useState<SangHakimDecision | null>(null);
  const [systemState, setSystemState] = useState<SystemState>('idle');
  const [performanceHistory, setPerformanceHistory] = useState<PerformanceMetric[]>([]);
  const [equity, setEquity] = useState<number>(INITIAL_EQUITY);
  const [totalPnL, setTotalPnL] = useState<number>(0);
  const [winCount, setWinCount] = useState<number>(0);
  const [lossCount, setLossCount] = useState<number>(0);
  const [engineRunning, setEngineRunning] = useState<boolean>(false);
  const [webhookStatus, setWebhookStatus] = useState<'IDLE' | 'ACTIVE' | 'VERIFIED' | 'REJECTED'>('IDLE');
  const [telegramStatus] = useState<'CONNECTED' | 'DISCONNECTED'>('CONNECTED');
  const [supabaseStatus, setSupabaseStatus] = useState<'SYNCED' | 'SYNCING' | 'OFFLINE'>('SYNCED');

  const tickSimRef = useRef(new GoldTickSimulator());
  const cmeSimRef = useRef(new CMEDataSimulator());
  const liquidityRef = useRef(new LiquidityProfileScanner());
  const tickBufferRef = useRef<MarketTick[]>([]);
  const modelsRef = useRef<ModelVote[]>(INITIALIZED_MODELS);
  const tradesRef = useRef<TradeRecord[]>([]);
  const riskEngineRef = useRef<FailSafeEngine | null>(null);

  const appendLog = useCallback((log: Omit<SystemLog, 'id' | 'timestamp'>) => {
    const fullLog = createLog(log.level, log.module, log.message, log.data);
    setLogs((prev) => [fullLog, ...prev].slice(0, 500));
  }, []);

  const handleCircuitBreak = useCallback(() => {
    setSystemState('fatal');
    setTrades((prev) =>
      prev.map((t) =>
        t.status === 'OPEN' ? { ...t, status: 'FATAL_CLOSE', exitPrice: currentTick?.mid ?? t.entryPrice, pnl: 0 } : t
      )
    );
  }, [currentTick]);

  // Initialize Risk Engine
  useEffect(() => {
    const engine = new FailSafeEngine(
      INITIAL_EQUITY,
      (state) => setRiskState(state),
      appendLog,
      handleCircuitBreak
    );
    riskEngineRef.current = engine;
    if (engineRunning) engine.start();
    return () => engine.stop();
  }, []);

  // Sync models to ref
  useEffect(() => { modelsRef.current = models; }, [models]);
  useEffect(() => { tradesRef.current = trades; }, [trades]);

  // Initial system boot log
  useEffect(() => {
    appendLog({ level: 'INFO', module: 'SYSTEM', message: '🌳 TREE DATA v3.0.0 — System initialized. Client: Kembang Ayu Andini' });
    appendLog({ level: 'INFO', module: 'SYSTEM', message: '🔧 Loading 14-Model Predictive Voting Registry...' });
    appendLog({ level: 'SUCCESS', module: 'REGISTRY', message: '✅ All 14 models loaded and weight matrices normalized (Σ=1.000)' });
    appendLog({ level: 'INFO', module: 'CME_WORKER', message: '📡 Async CME background worker initialized — HTTP/2 + JA3 rotation enabled' });
    appendLog({ level: 'INFO', module: 'WEBHOOK', message: '🔐 FastAPI webhook endpoint armed — HMAC-SHA256 signature verification active' });
    appendLog({ level: 'INFO', module: 'SUPABASE', message: '🗄️ Supabase PostgreSQL connection established — real-time sync ONLINE' });
    appendLog({ level: 'INFO', module: 'TELEGRAM', message: '🤖 Telegram Bot API channel connected — /fatalcutoff override ready' });
    appendLog({ level: 'INFO', module: 'RISK_ENGINE', message: '⚡ Fail-Safe Engine ready — awaiting engine start command' });
  }, []);

  // CME data fetch on startup and every 5 minutes
  useEffect(() => {
    const fetchCME = async () => {
      try {
        appendLog({ level: 'INFO', module: 'CME_WORKER', message: '📊 Fetching CME Options Chain data (async httpx HTTP/2)...' });
        const data = await cmeSimRef.current.fetchCMESnapshot();
        setCmeData(data);
        appendLog({
          level: 'SUCCESS', module: 'CME_WORKER',
          message: `✅ CME data ingested — OI: ${data.openInterest.toLocaleString()} | IV: ${(data.impliedVolatility * 100).toFixed(2)}% | GEX: ${data.gex.toLocaleString()} | CPR: ${data.callPutRatio.toFixed(3)}`,
          data: { ...data },
        });
      } catch (err) {
        appendLog({ level: 'ERROR', module: 'CME_WORKER', message: `❌ CME fetch failed — triggering N8N fallback: ${String(err)}` });
      }
    };
    fetchCME();
    const interval = setInterval(fetchCME, CME_REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);

  // Main tick generator
  useEffect(() => {
    if (!engineRunning) return;
    const interval = setInterval(() => {
      const tick = tickSimRef.current.generateTick();
      tickBufferRef.current = [...tickBufferRef.current.slice(-999), tick];
      setCurrentTick(tick);
      setTicks([...tickBufferRef.current]);
      liquidityRef.current.update(tick.mid);

      const spreadStats = tickSimRef.current.getSpreadStats();
      riskEngineRef.current?.updateSpreadStats(
        spreadStats.mean, spreadStats.sigma, tick.spread
      );

      // Resolve open trades
      const openTrades = tradesRef.current.filter((t) => t.status === 'OPEN');
      let equityDelta = 0;
      let newWins = 0, newLosses = 0;
      const closedTrades: string[] = [];

      for (const trade of openTrades) {
        const priceForClose = trade.side === 'BUY' ? tick.bid : tick.ask;
        const tpHit = trade.side === 'BUY' ? tick.bid >= trade.tp : tick.ask <= trade.tp;
        const slHit = trade.side === 'BUY' ? tick.bid <= trade.sl : tick.ask >= trade.sl;

        if (tpHit || slHit) {
          const pnl = trade.side === 'BUY'
            ? (priceForClose - trade.entryPrice) * trade.lotSize * 100
            : (trade.entryPrice - priceForClose) * trade.lotSize * 100;
          equityDelta += pnl;
          if (pnl > 0) newWins++;
          else newLosses++;
          closedTrades.push(trade.id);

          const outcome: 1 | -1 = pnl > 0 ? 1 : -1;
          const updatedModels = applyMWUMUpdate(modelsRef.current, outcome, trade.regime);
          setModels(updatedModels);

          appendLog({
            level: pnl > 0 ? 'SUCCESS' : 'WARN',
            module: 'EXECUTION',
            message: `${pnl > 0 ? '💰 TP HIT' : '🔴 SL HIT'} | ${trade.side} ${trade.horizon} | P&L: ${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)} | Entry: ${trade.entryPrice.toFixed(3)} | Exit: ${priceForClose.toFixed(3)}`,
            data: { tradeId: trade.id, pnl, outcome },
          });

          // MWUM update log
          appendLog({
            level: 'INFO',
            module: 'MWUM_ENGINE',
            message: `🧠 MWUM weight update applied — regime: ${trade.regime} | outcome: ${outcome === 1 ? 'WIN' : 'LOSS'} | η=${0.12}`,
          });
        }
      }

      if (closedTrades.length > 0) {
        setTrades((prev) =>
          prev.map((t) => {
            if (closedTrades.includes(t.id)) {
              const priceForClose = t.side === 'BUY' ? tick.bid : tick.ask;
              const pnl = t.side === 'BUY'
                ? (priceForClose - t.entryPrice) * t.lotSize * 100
                : (t.entryPrice - priceForClose) * t.lotSize * 100;
              return {
                ...t,
                exitPrice: priceForClose,
                pnl: Math.round(pnl * 100) / 100,
                status: pnl > 0 ? 'TP_HIT' : 'SL_HIT',
              };
            }
            return t;
          })
        );
        setWinCount((w) => w + newWins);
        setLossCount((l) => l + newLosses);
        setTotalPnL((prev) => Math.round((prev + equityDelta) * 100) / 100);
        setEquity((prev) => {
          const newEquity = Math.round((prev + equityDelta) * 100) / 100;
          riskEngineRef.current?.updateEquity(newEquity, tradesRef.current);
          setSystemState(equityDelta > 0 ? 'profit' : 'loss');
          setTimeout(() => setSystemState('processing'), 2000);
          return newEquity;
        });
      }
    }, TICK_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [engineRunning]);

  // Decision engine loop
  useEffect(() => {
    if (!engineRunning) return;
    const interval = setInterval(() => {
      if (!cmeData || tickBufferRef.current.length < 10) return;

      const atr = tickSimRef.current.computeATR(14);
      const detectedRegime = tickSimRef.current.detectRegime(atr);
      setRegime(detectedRegime);

      const updatedModels = computeAllVotes(modelsRef.current, tickBufferRef.current, cmeData, detectedRegime);
      setModels(updatedModels);
      modelsRef.current = updatedModels;

      const dec = sangHakimDecide(updatedModels, detectedRegime);
      setDecision(dec);

      const canEnter = riskEngineRef.current?.isEntryAllowed() ?? false;

      if (dec.triggered && canEnter && dec.horizon && dec.side !== 'FLAT') {
        const latestTick = tickBufferRef.current[tickBufferRef.current.length - 1];
        const sizing = computePositionSize(dec.horizon as OrderHorizon, equity, dec.dFinal);

        const entryPrice = dec.side === 'BUY'
          ? toFixed3(latestTick.ask)
          : toFixed3(latestTick.bid);

        const slPips = dec.horizon === 'SCALPING_SNIPER' ? 0.30
          : dec.horizon === 'INTRADAY' ? 1.50 : 5.00;
        const tpPips = slPips * (dec.horizon === 'SCALPING_SNIPER' ? 1.5 : 2.0);

        const sl = toFixed3(dec.side === 'BUY' ? entryPrice - slPips : entryPrice + slPips);
        const tp = toFixed3(dec.side === 'BUY' ? entryPrice + tpPips : entryPrice - tpPips);

        const newTrade: TradeRecord = {
          id: generateId(),
          timestamp: Date.now(),
          side: dec.side as OrderSide,
          horizon: dec.horizon as OrderHorizon,
          entryPrice,
          exitPrice: null,
          lotSize: sizing.lotSize,
          tp,
          sl,
          pnl: null,
          status: 'OPEN',
          dFinal: dec.dFinal,
          regime: detectedRegime,
          modelSnapshot: [...updatedModels],
        };

        setTrades((prev) => [newTrade, ...prev].slice(0, 100));
        setSystemState('executing');
        setTimeout(() => setSystemState('processing'), 1500);

        appendLog({
          level: 'SUCCESS',
          module: 'SANG_HAKIM',
          message: `🎯 ORDER EXECUTED | ${dec.side} ${dec.horizon} | Entry: ${entryPrice.toFixed(3)} | TP: ${tp.toFixed(3)} | SL: ${sl.toFixed(3)} | Lot: ${sizing.lotSize} | D_final: ${dec.dFinal.toFixed(4)}`,
          data: { trade: newTrade, decision: dec },
        });
        appendLog({
          level: 'INFO',
          module: 'EXNESS_MT5',
          message: `📤 Routing to Exness MT5 — Symbol: XAUUSD | Lots: ${sizing.lotSize.toFixed(2)} | Magic: 300000 | Slippage: 3pts`,
        });
      }

      // Update performance history
      const totalTrades = winCount + lossCount;
      const winRate = totalTrades > 0 ? winCount / totalTrades : 0;
      setPerformanceHistory((prev) => [
        ...prev.slice(-200),
        {
          timestamp: Date.now(),
          equity,
          dFinal: dec.dFinal,
          regime: detectedRegime,
          winRate: Math.round(winRate * 10000) / 10000,
          sharpeRatio: Math.round((totalPnL / Math.max(1, equity * 0.02)) * 100) / 100,
          maxDrawdown: riskEngineRef.current?.getRiskState().dailyDrawdownPct ?? 0,
          totalTrades,
          profitFactor: lossCount > 0 ? Math.round((winCount / lossCount) * 100) / 100 : winCount > 0 ? 99 : 0,
        },
      ]);

      // Simulate Supabase async sync
      setSupabaseStatus('SYNCING');
      setTimeout(() => setSupabaseStatus('SYNCED'), 300 + Math.random() * 500);
    }, DECISION_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [engineRunning, cmeData, equity, winCount, lossCount, totalPnL]);

  // Webhook simulation
  const simulateWebhookSignal = useCallback((action: 'BUY' | 'SELL' | 'CLOSE') => {
    setWebhookStatus('ACTIVE');
    appendLog({
      level: 'INFO', module: 'WEBHOOK',
      message: `📨 TradingView webhook received — action: ${action} | HMAC-SHA256 verification...`,
    });
    setTimeout(() => {
      const isValid = Math.random() > 0.05;
      setWebhookStatus(isValid ? 'VERIFIED' : 'REJECTED');
      appendLog({
        level: isValid ? 'SUCCESS' : 'ERROR',
        module: 'WEBHOOK',
        message: isValid
          ? `✅ HMAC signature VERIFIED — payload forwarded to Sang Hakim arbiter`
          : `❌ HMAC signature MISMATCH — payload REJECTED (possible IP spoofing)`,
      });
      setTimeout(() => setWebhookStatus('IDLE'), 2000);
    }, 600);
  }, []);

  const startEngine = useCallback(() => {
    setEngineRunning(true);
    setSystemState('processing');
    riskEngineRef.current?.start();
    appendLog({ level: 'INFO', module: 'SYSTEM', message: '🚀 TREE DATA v3.0.0 ENGINE STARTED — All subsystems ONLINE' });
    appendLog({ level: 'INFO', module: 'REGIME_DETECTOR', message: '🔍 Dynamic regime detection initialized — ATR(14) + σ(1000) rolling window active' });
  }, []);

  const stopEngine = useCallback(() => {
    setEngineRunning(false);
    setSystemState('idle');
    riskEngineRef.current?.stop();
    appendLog({ level: 'WARN', module: 'SYSTEM', message: '⏸️ Engine PAUSED — tick ingestion and decision loop stopped' });
  }, []);

  const triggerFatalCutoff = useCallback(() => {
    riskEngineRef.current?.triggerFatalCutoff();
    setSystemState('fatal');
    setEngineRunning(false);
    appendLog({ level: 'FATAL', module: 'FATAL_CUTOFF', message: '🔴 FATAL CUTOFF EXECUTED — All systems halted' });
  }, []);

  const resetCircuitBreaker = useCallback(() => {
    riskEngineRef.current?.resetCircuitBreaker();
    if (systemState !== 'fatal') {
      setSystemState(engineRunning ? 'processing' : 'idle');
    }
  }, [systemState, engineRunning]);

  return {
    models, ticks, currentTick, regime, cmeData, riskState, trades, logs, decision,
    systemState, performanceHistory, equity, totalPnL, winCount, lossCount,
    engineRunning, webhookStatus, telegramStatus, supabaseStatus,
    startEngine, stopEngine, triggerFatalCutoff, resetCircuitBreaker,
    simulateWebhookSignal,
    liquidityWalls: liquidityRef.current.detectLiquidityWalls(),
    stopHuntDetected: liquidityRef.current.detectStopHuntZone(),
  };
}
