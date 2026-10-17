# gcquant — engineering spec (contract between modules)

Personal computation & analysis engine for COMEX gold (GC, MGC, 1OZ futures; OG options)
and spot XAUUSD. Primary market data: Databento `GLBX.MDP3`. Python ≥ 3.10, numpy, pandas
(2.x and 3.x — pandas 3 defaults datetimes to µs: ALWAYS `.as_unit("ns")` before `.asi8`),
scipy. Optional: `databento`, `lightgbm`, `scikit-learn`. No numba.

User-facing text (docstrings, CLI help, errors, README) is **Bahasa Indonesia**; identifiers
are English. Keep code readable, typed, vectorised where it matters.

## 0. Non-negotiable rules

1. **Zero-cost by default.** No code path may download billable data unless the caller passed
   an explicit budget. Databento `metadata.get_cost` (free) runs before every
   `timeseries.get_range`/`batch.submit_job`; if `cost > max_cost_usd` raise
   `gcquant.core.BiayaDitolak` with the estimate in the message. Default `max_cost_usd = 0.0`.
   Live subscriptions require `allow_live=True`. Downloads are cached to disk; a cache hit
   never calls the API.
2. **No look-ahead.** Every feature at time t uses only records with `ts_recv <= t`.
   Bars are labelled by their OPEN time and become known at `open + bar_len`.
   Signals are applied strictly after the decision time (+ latency for event backtests).
   Rolling statistics use trailing windows only; any normalisation (z-score, scaler) is
   fit on training data only. Tests must include at least one "future-perturbation" test:
   altering data after t must not change outputs at t.
3. **Honest statistics.** Every reported strategy result carries trade count, net-of-cost
   PnL, t-stat (Newey-West where autocorrelated), and the number of configurations tried.
4. Imports between modules only through the public functions listed here.

## 1. Conventions (gcquant/core.py — already written, do not modify)

- Raw time: int64 ns since epoch UTC. DataFrames: `datetime64[ns, UTC]`.
- Analysis clock for market data = `ts_recv` (when the record was observable). `ts_event`
  (matching-engine time) is kept as a column.
- Prices: float USD/oz. Sizes: contracts. Aggressor side of trades: `'B'` buy (+1),
  `'A'` sell (−1), `'N'` unknown (0).
- `core.SPECS[root] -> ContractSpec(root, name, exchange, multiplier, tick_size,
  settlement, option_of, exercise, notes)`, `.tick_value`.
- `core.CostModel(commission_per_side, slippage_ticks, latency_ms, pay_spread)`,
  `.round_turn_usd(spec, spread_ticks)`. `core.DEFAULT_COSTS[root]`.
- Calendar: `cme_holidays(year)`, `is_business_day(d)`, `business_days_in_month(y, m)`,
  `add_business_days(d, n)`, `cme_trade_date(ts)` (session starts 17:00 Chicago).
- Symbols: `futures_symbol(root, year, month, digits=1)`, `parse_futures_symbol(sym, ref_year)`.
- Time: `to_ns(x)`, `ns_to_ts(ns)`, `ensure_utc_index(df)`; zones `UTC`, `NY`, `CHI`.
- Databento constants: `FIXED_PRICE_SCALE`, `UNDEF_PRICE`, `F_LAST`, `F_TOB`, `F_SNAPSHOT`,
  `F_MBP`, `F_BAD_TS_RECV`, `F_MAYBE_BAD_BOOK`, `DATASET_CME`.
- Errors: `GcquantError`, `BiayaDitolak`, `LookAheadError`.

## 2. Canonical frames

| Name | Columns (all frames have a RangeIndex unless stated) |
|---|---|
| **MBO** | `ts_recv:int64, ts_event:int64, instrument_id:int64, order_id:uint64, action:str1 (A C M R T F N), side:str1 (B A N), price:float (NaN if undefined), size:int64, flags:int64, sequence:int64, channel_id:int64, publisher_id:int64, symbol:str` |
| **TRADES** | `ts_recv, ts_event, instrument_id, price, size, side, sequence, symbol` |
| **BOOK** (from MBP-10 or MBO replay) | `ts_recv, ts_event, instrument_id, symbol, bid_px_00..bid_px_09, ask_px_00..ask_px_09, bid_sz_00..09, ask_sz_00..09, bid_ct_00..09, ask_ct_00..09` (Databento MBP-10 names; NaN price / 0 size for empty levels) |
| **BBO** (L1) | `ts_recv, ts_event, instrument_id, symbol, bid_px, ask_px, bid_sz, ask_sz` |
| **BARS** | index `ts` = bar OPEN time (UTC ns); `open, high, low, close, volume`; optional `spread` (USD), `symbol`, `instrument_id`. Known at `ts + bar_len`. |
| **DAILY** (per contract) | `trade_date:date, symbol, instrument_id, open, high, low, close, settle, volume, open_interest` |
| **DEFS** | `instrument_id, raw_symbol, instrument_class (F C P S), expiration (UTC ts), activation, min_price_increment, unit_of_measure_qty, strike_price, underlying, asset, ts_recv` |
| **STATS** | `ts_recv, ts_event, ts_ref, instrument_id, symbol, stat_type:int, price, quantity, update_action` |

## 3. Modules and public API

### 3.1 `gcquant/data/` — sources (agent DATA)
- `databento_source.py`
  - `class DatabentoSource(key=None, cache_dir="~/.gcquant/cache", max_cost_usd=0.0, client=None)`
    (`client` lets tests inject a fake Historical; key from arg or `DATABENTO_API_KEY`).
  - `.estimate(dataset, schema, symbols, start, end, stype_in="raw_symbol") -> dict(cost_usd, size_bytes, records)` — free metadata calls only.
  - `.get(dataset, schema, symbols, start, end, stype_in="raw_symbol", max_cost_usd=None) -> databento.DBNStore`
    — cache key = sha256 of request; cost guard; writes `<cache>/<key>.dbn.zst` + JSON sidecar.
  - `.free_metadata()` → datasets/schemas/dataset_range for GLBX.MDP3 (all free).
  - `class LiveFeed(key=None, allow_live=False)` thin wrapper around `databento.Live`
    (subscribe dataset/schema/symbols/stype_in/start/snapshot; callback → canonical row dict).
    Raises `BiayaDitolak` unless `allow_live=True`.
- `dbn_io.py`
  - `load_dbn(path_or_store, schema=None) -> pd.DataFrame` canonical frame for schema
    (mbo, mbp-1/tbbo→BBO+trade cols, mbp-10→BOOK, trades→TRADES, ohlcv-*→BARS,
    definition→DEFS, statistics→STATS, status→raw). Handles undefined prices → NaN,
    UNDEF quantities → NaN, symbol mapping.
  - `write_synthetic_mbo_dbn(path, frame)` optional (databento_dbn encoders) for e2e tests.
- `synthetic.py`
  - `synthetic_mbo(n_events=20000, seed=0, root="GC", tick=0.10, start="2026-01-05T14:30Z", instrument_id=1, symbol="GCG6") -> MBO frame`
    — internally consistent book: starts with `R` clear + snapshot adds (F_SNAPSHOT), then
    adds/cancels/modifies/trades with fills that reduce resting orders via subsequent
    C/M records exactly like Databento CME MBO. Latent mid follows a random walk with a
    planted weak OFI→future-return effect (so features have something to find).
  - `synthetic_bars(n, freq="1min", seed=0, start=..., price0=2000.0, vol=..., drift=0.0) -> BARS`.
  - `synthetic_daily_curve(start, end, seed=0) -> DAILY` multi-contract GC curve with OI roll pattern.
- `free_sources.py`
  - `load_m1_csv(path, tz="UTC") -> BARS` for the existing Dukascopy-derived files
    `XAUUSD_M1_YYYY.csv` (columns: time, open, high, low, close, volume, spread_points; spread in
    points of 0.01) — read header to detect; `spread` column in USD.
  - `load_daily_csv(path, date_col=None, price_col=None) -> pd.DataFrame` generic.
  - `resample_bars(bars, rule) -> BARS` (open-time labelled, left-closed, no partial future bar).

### 3.2 `gcquant/book/` + `gcquant/features/micro.py` — order book & microstructure (agent BOOK)
- `book/mbo_book.py`
  - `class OrderBook` per instrument: `apply(rec)` with Databento semantics:
    T/F/N no change; R clear; A add; C reduce size by rec.size (remove at 0);
    M modify — unknown order → treat as add; price change or size increase → loses queue
    priority (moves to back); size decrease keeps priority. Side mismatch → raise.
    `.bbo() -> (bid_px, bid_sz, ask_px, ask_sz)`, `.levels(side, n) -> list[(px, sz, ct)]`,
    `.queue_ahead(order_id) -> int` (size ahead at same price), `.depth(side, n)`.
  - `class Market` dict of books keyed by instrument_id (and publisher), `apply(rec)`.
  - `replay_mbo(mbo_frame, n_levels=10, emit="last") -> BOOK frame` emitting a snapshot only
    when `flags & F_LAST` (consistent book); `emit="tob_change"` emits only when L1 changes.
    Records flagged `F_MAYBE_BAD_BOOK` mark the instrument stale until next `R` + snapshot.
  - Must reproduce Databento MBP-10 from MBO on synthetic data; must parse the fixture.
- `book/l1.py`: `bbo_from_book(BOOK) -> BBO`, `mid`, `spread`, `weighted_mid`.
- `features/micro.py` (all inputs canonical frames, outputs aligned to input rows or a grid):
  - `ofi_l1(bbo) -> pd.Series` per-event OFI e_n (Cont, Kukanov, Stoikov 2014).
  - `mlofi(book, levels=5) -> pd.DataFrame` multi-level OFI (Xu, Gould, Howison 2018).
  - `queue_imbalance(bbo) -> Series` (Qb−Qa)/(Qb+Qa); `depth_imbalance(book, levels)`.
  - `microprice_weighted(bbo)`; `class StoikovMicroprice(n_imb=10, n_spread=2)` with
    `.fit(bbo_train, horizon_events)` and `.predict(bbo)` (Stoikov 2018 estimator; fit on
    training data only).
  - `trade_flow(trades, window)` signed volume, trade-sign autocorrelation, aggressor ratio.
  - `vpin(trades, bucket_volume, n_buckets=50, method="aggressor"|"bvc")` (Easley, López de
    Prado, O'Hara 2012), indexed by bucket completion time.
  - `kyle_lambda(bbo, trades, window)` rolling OLS of Δmid on signed volume.
  - `realized_measures(bars_or_mid, rule="5min", window=...)` RV, bipower variation, jump
    component, realised semivariances; `roll_spread`, `amihud`.
  - `on_grid(frame_or_series, grid_ns, how="last")` — causal as-of alignment
    (value at grid t = last row with ts_recv <= t).
  - `feature_matrix(bbo, book, trades, grid="1s") -> pd.DataFrame` standard bundle.

### 3.3 `gcquant/contracts/` — listing, roll, continuous, carry, basis (agent CURVE)
- `calendar.py`: `last_trade_date(root, year, month)` (GC/MGC: 3rd-last business day of
  contract month), `first_notice_date(root, year, month)` (last business day of prior month),
  `og_expiry(year, month)` (4th-last business day of month prior to contract month; if Friday
  or day before a holiday → prior business day), `listed_contracts(root, asof) -> list[(sym, y, m)]`,
  `active_months(root)` (GC: G J M Q V Z).
- `roll.py`: `roll_schedule(root, start, end, rule="fnd-2"|"volume"|"oi", daily=None) ->
  DataFrame(trade_date, front_symbol, next_symbol)`; rule `fnd-k` rolls k business days
  before FND; `volume`/`oi` roll when the next contract's volume/OI exceeds front's (decided
  on day d using data of day d, applied from d+1).
  `continuous(daily, schedule, adjust="none"|"difference"|"ratio") -> DataFrame` with
  `close, settle, ret` (returns computed within the same contract, never across a roll gap),
  `contract`.
- `carry.py`: `implied_financing(F, S, tau_years)`, `implied_lease(F, S, r, tau)`,
  `calendar_spread_rate(F1, F2, tau1, tau2)`, `term_structure(daily_on_date, spot=None, r=None)`.
- `basis.py`: `basis(gc_bbo_or_bars, xau_bars, tolerance="1s")` causal as-of join → GC−XAU,
  `fair_basis(S, r, lease, tau)`, `gc_to_xau(gc_price, tau, r_minus_lease)` mapping for MT5,
  `basis_zscore(basis, window)` trailing.

### 3.4 `gcquant/options/` — OG options (agent OPTIONS)
- `black76.py`: `price(F, K, T, r, sigma, cp)`, `greeks(...) -> dict(delta, gamma, vega,
  theta, rho, vanna, volga)`, vectorised; `cp` = 1 call / −1 put.
- `american.py`: Barone-Adesi–Whaley for options on futures (b = 0): `baw_price(F,K,T,r,sigma,cp)`.
- `iv.py`: `implied_vol(price, F, K, T, r, cp, model="black76"|"baw")` robust Brent with
  bounds and intrinsic checks → NaN when no solution.
- `surface.py`: `fit_svi(k, w)` raw-SVI per expiry (bounded least squares, no butterfly
  violation check optional), `atm_vol`, `delta_strike(…, delta=0.25)`, `rr_bf(smile, F, T, r)`
  → 25Δ risk reversal & butterfly; `skew_slope`.
- `chain.py`: `build_chain(defs, bbo, stats, asof_ns, underlying_px)` → per option row
  (symbol, expiry, strike, cp, bid, ask, mid, iv, delta, gamma, oi). OG strike/expiry from
  DEFS (`strike_price`, `expiration`, `instrument_class` C/P, `underlying`).
  `gamma_exposure(chain, F, contract_mult=100, dealer_sign="short_calls_long_puts")` with
  the assumption documented; `max_pain(chain)`; `put_call_ratios(chain)`.

### 3.5 `gcquant/research/` — validation & stats (agent VALID)
- `validation.py`: `PurgedKFold(n_splits, embargo_pct)` with `.split(t0, t1)` (label start/end
  times; purge overlap; embargo), `walk_forward(index, train, test, step, expanding)`,
  `cpcv_paths` (combinatorial purged CV).
- `stats.py`: `sharpe(r, periods)`, `psr(sr, n, skew, kurt, sr_star=0)` (kurt = non-excess),
  `dsr(sr, n, skew, kurt, sr_trials_var, n_trials)` (Bailey & López de Prado 2014),
  `min_trl`, `newey_west_t(x, lags=None)`, `stationary_bootstrap(x, stat, n_boot, mean_block)`,
  `pbo_cscv(perf_matrix, n_blocks=16)` (Bailey et al. 2017) → dict(pbo, logits),
  `spa_test(loss_diffs_matrix, n_boot)` (Hansen 2005), `holm`, `benjamini_hochberg`.
- `labels.py`: `forward_return(px, horizon)`, `triple_barrier(px, events, pt, sl, max_hold,
  vol)` → (t1, ret, label), `meta_labels(primary_side, tb)`.
- `protocol.py`: `ResearchLog` that counts every configuration tried and writes JSON;
  `discovery_holdout_split(index, discovery_end, holdout_start)`; a `verdict()` helper
  applying pre-declared thresholds (discovery t ≥ 3; holdout net > 0 and t ≥ 2; DSR > 0.95).

### 3.6 `gcquant/backtest/`, `gcquant/strategies/`, `gcquant/decision/` (agent STRAT)
- `backtest/bars.py`: `backtest_bars(bars, target, spec, cost, spread_col="spread",
  exec="next_open") -> BacktestResult` — target index = decision time (bar close time);
  executed at the next bar's open after the decision, paying half-spread (+slippage) and
  commission per contract changed; PnL in USD = Δprice × multiplier × contracts.
  `BacktestResult(equity, pnl, positions, trades, stats)`; stats include n_trades, net,
  gross, cost, sharpe (daily), t_nw, max_dd, hit_rate, turnover.
- `backtest/events.py`: latency-aware event backtester on BOOK/BBO + TRADES:
  decision at ts → order reaches exchange at ts+latency; market orders walk the book state
  valid at arrival time; limit (maker) orders get queue position = displayed size at that
  price at arrival, filled only after that much volume trades at the price (conservative);
  cancels also delayed. Returns fills & PnL.
- `strategies/` each a class with `name`, `params`, `signal(data: dict) -> pd.Series` of
  target position in [−1, 1] indexed by decision time; nothing may use data after the index:
  `tsmom.py` (multi-lookback trend, vol-targeted), `event_drift.py` (scheduled-release
  follow/fade from CSV events), `basis_mr.py` (GC−XAU basis z-score reversion),
  `micro_ofi.py` (OFI/microprice short-horizon with cost threshold),
  `session.py` (time-of-day / overnight-vs-day), `meta.py` (meta-labelling ensemble with
  purged CV, LightGBM optional → fallback logistic).
- `decision/engine.py`: `combine(signals: dict[str, Series], weights) -> Series`,
  `vol_target(signal, returns, target_ann_vol)`, `kelly_cap`, `no_trade_band(target, band)`,
  `RiskLimits(max_contracts, daily_loss_usd, max_dd_usd)` applied causally,
  `Decision(ts, target_contracts, confidence, reasons)`.

### 3.7 `gcquant/bridge/`, `gcquant/cli.py`, `mql5/`, docs (agent BRIDGE)
- `bridge/mt5.py`: `write_signal(path, Decision, gc_px, xau_equiv, basis, valid_secs,
  model_id)` atomic write (tmp + rename) of a one-line CSV `GCQuant_signal.csv` in MT5
  `Common\Files`; `read_signal(path)`.
- `mql5/GCQuantBridge.mqh` (read & validate signal: staleness, model id, NaNs) and
  `mql5/GCQuant_Executor.mq5` (maps target → XAUUSD lots with hard risk caps; defaults to
  monitor-only).
- `cli.py` (`python -m gcquant …`, Indonesian help): `biaya`, `unduh`, `buku`, `fitur`,
  `kurva`, `opsi`, `riset`, `sinyal`, `demo` (runs end-to-end on synthetic data offline).
- `README.md` (Indonesian): install, zero-cost workflow, Databento usage, module map.

## 4. Tests
`tests/test_<module>.py`, pytest, offline, < 60 s total per module. Databento fixtures in
`tests/data/databento/` (ESH1 from Databento's Apache-2.0 test suite; 1–4 rows per schema).
Required: hand-computed expected values for formulas; MBO→book equals MBP-10 on synthetic
data; future-perturbation (no look-ahead) tests; cost-guard tests with a fake client
(no network).
