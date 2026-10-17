"""Simulator order braket (entry + stop + target) berbasis R-multiple pada bar bid + spread.

Dibuat untuk menguji strategi payoff asimetris (mis. risk:reward 1:3) secara jujur:

- Sinyal dihitung pada bar yang SUDAH TUTUP (indeks ``i_signal``); entry paling cepat di open
  bar berikutnya. Tidak ada informasi bar ke-``i_signal + 1`` yang dipakai untuk memutuskan.
- Harga data = bid. Ask = bid + spread bar itu. Long masuk di ask, keluar di bid;
  short masuk di bid, keluar di ask.
- R (unit risiko) = jarak harga acuan entry ke stop pada skala keluar (long: bid saat masuk,
  short: ask saat masuk), TANPA spread. Biaya spread/komisi karenanya terlihat sebagai pengurang hasil dalam R:
  stop kena = sedikit lebih buruk dari −1R; target kena = sedikit kurang dari +kR.
- Bila stop dan target tersentuh di bar yang sama, dianggap STOP lebih dulu (konservatif).
- Gap melewati stop diisi di harga open (slippage nyata), bukan di harga stop.
- Pindah ke impas / trailing hanya berlaku mulai bar SETELAH syaratnya tercapai.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class Bracket:
    i_signal: int                 # indeks bar sinyal (sudah tutup)
    direction: int                # +1 long, −1 short
    stop: float                   # level stop: long dibandingkan dgn bid, short dgn ask
    r_target: float | None = 3.0  # target = acuan ± r_target × R (None = tanpa target)
    target: float | None = None   # target harga absolut (mengalahkan r_target bila diisi)
    max_bars: int = 240           # batas lama posisi (bar)
    entry_limit: float | None = None   # None = order pasar di open bar berikutnya
    limit_bars: int = 0           # masa berlaku order limit (bar setelah sinyal)
    be_at_r: float | None = None  # geser stop ke impas setelah untung ≥ x R
    trail_start_r: float | None = None  # mulai trailing setelah untung ≥ x R
    trail_r: float = 1.0          # jarak trailing dalam R dari harga terbaik
    exit_at_ns: int | None = None # tutup paksa pada bar pertama dengan waktu ≥ ini
    tag: str = ""
    meta: dict = field(default_factory=dict)


@dataclass
class Bars:
    """Bar bid + spread dalam array numpy (lebih cepat daripada DataFrame per trade)."""
    t: np.ndarray       # int64 ns, waktu open bar
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    sp: np.ndarray      # spread USD per bar
    extra_cost: float = 0.0   # biaya tambahan per sisi (komisi/slippage) dalam USD/oz

    @classmethod
    def from_frame(cls, df: pd.DataFrame, spread_col: str = "spread", extra_cost: float = 0.0,
                   zero_spread: bool = False) -> "Bars":
        idx = pd.DatetimeIndex(df.index)
        sp = np.zeros(len(df)) if zero_spread or spread_col not in df else df[spread_col].to_numpy(float)
        return cls(idx.as_unit("ns").asi8, df["open"].to_numpy(float), df["high"].to_numpy(float),
                   df["low"].to_numpy(float), df["close"].to_numpy(float), sp,
                   0.0 if zero_spread else extra_cost)

    def __len__(self):
        return len(self.o)


def _simulate_one(b: Bars, x: Bracket):
    """Simulasi satu braket. Skala harga: long dinilai di bid, short di ask.

    ``ref`` = harga entry pada skala keluar (long: bid saat masuk; short: ask saat masuk),
    sehingga R = |ref − stop| bebas spread dan biaya muncul simetris untuk long & short:
    kalah = −(R + spread + biaya), menang = kR − spread − biaya.
    """
    n = len(b)
    d = x.direction
    i0 = x.i_signal + 1
    if i0 >= n:
        return None
    ec = b.extra_cost
    if x.entry_limit is None:
        ie = i0
        raw = b.o[ie] + b.sp[ie] if d > 0 else b.o[ie]
    else:
        lp = x.entry_limit
        ie = None
        for j in range(i0, min(n, i0 + max(1, x.limit_bars))):
            if d > 0:
                if b.l[j] + b.sp[j] <= lp:
                    ie, raw = j, min(lp, b.o[j] + b.sp[j])
                    break
            elif b.h[j] >= lp:
                ie, raw = j, max(lp, b.o[j])
                break
        if ie is None:
            return None
    ref = raw - d * b.sp[ie]
    fill = raw + d * ec
    risk = d * (ref - x.stop)
    if not np.isfinite(risk) or risk <= 0:
        return None
    if x.target is not None:
        target = x.target
    elif x.r_target is not None:
        target = ref + d * x.r_target * risk
    else:
        target = None
    stop = x.stop
    last = min(n - 1, ie + x.max_bars)
    best = ref
    be_armed = trail_armed = False
    outcome, exit_px, ix = None, None, last
    mfe = mae = 0.0
    t_limit = ie + x.max_bars
    for j in range(ie, last + 1):
        first = j == ie
        if not first and ((x.exit_at_ns is not None and b.t[j] >= x.exit_at_ns) or j == t_limit):
            outcome = "sesi" if (x.exit_at_ns is not None and b.t[j] >= x.exit_at_ns) else "waktu"
            ix = j
            exit_px = b.o[j] - ec if d > 0 else b.o[j] + b.sp[j] + ec
            break
        sh = 0.0 if d > 0 else b.sp[j]          # geser ke skala ask untuk short
        op, hi, lo = b.o[j] + sh, b.h[j] + sh, b.l[j] + sh
        if d > 0:
            hit_stop, hit_tgt = lo <= stop, target is not None and hi >= target
            gap_stop = (not first) and op <= stop
            gap_tgt = (not first) and target is not None and op >= target
        else:
            hit_stop, hit_tgt = hi >= stop, target is not None and lo <= target
            gap_stop = (not first) and op >= stop
            gap_tgt = (not first) and target is not None and op <= target
        if gap_tgt:
            exit_px, outcome, ix = op, "target", j
        elif hit_stop:
            exit_px = op if gap_stop else stop
            outcome = "trail" if trail_armed else ("impas" if be_armed else "stop")
            ix = j
        elif hit_tgt:
            exit_px, outcome, ix = target, "target", j
        if outcome is not None:
            exit_px = exit_px - ec if d > 0 else exit_px + ec
            break
        fav, adv = (hi, lo) if d > 0 else (lo, hi)
        mfe = max(mfe, d * (fav - ref) / risk)
        mae = min(mae, d * (adv - ref) / risk)
        best = max(best, fav) if d > 0 else min(best, fav)
        # pembaruan stop hanya berlaku untuk bar BERIKUTNYA
        gain_r = d * (best - ref) / risk
        if x.be_at_r is not None and gain_r >= x.be_at_r and not be_armed:
            be_armed = True
            stop = max(stop, ref) if d > 0 else min(stop, ref)
        if x.trail_start_r is not None and gain_r >= x.trail_start_r:
            trail_armed = True
            cand = best - d * x.trail_r * risk
            stop = max(stop, cand) if d > 0 else min(stop, cand)
    if exit_px is None:          # data habis sebelum stop/target/batas waktu: tutup di close terakhir
        ix = last
        outcome = "data_habis"
        exit_px = b.c[ix] - ec if d > 0 else b.c[ix] + b.sp[ix] + ec
    pnl = d * (exit_px - fill)
    return dict(i_signal=x.i_signal, i_entry=ie, i_exit=ix, t_entry=b.t[ie], t_exit=b.t[ix],
                dir=d, ref=ref, fill=fill, stop0=x.stop, target=target, exit=exit_px,
                risk=risk, pnl=pnl, r=pnl / risk, outcome=outcome, mfe_r=mfe, mae_r=mae,
                bars=ix - ie, tag=x.tag, **x.meta)


def simulate(bars: Bars, brackets: list[Bracket], no_overlap: bool = True) -> pd.DataFrame:
    """Jalankan daftar braket. ``no_overlap`` = hanya satu posisi pada satu waktu (per daftar)."""
    rows = []
    busy_until = -1
    for x in sorted(brackets, key=lambda z: z.i_signal):
        if no_overlap and x.i_signal + 1 <= busy_until:
            continue
        r = _simulate_one(bars, x)
        if r is None:
            continue
        rows.append(r)
        busy_until = r["i_exit"]
    df = pd.DataFrame(rows)
    if len(df):
        df["t_entry"] = pd.to_datetime(df["t_entry"], unit="ns", utc=True)
        df["t_exit"] = pd.to_datetime(df["t_exit"], unit="ns", utc=True)
    return df


def summarize(trades: pd.DataFrame, gross: pd.DataFrame | None = None) -> dict:
    """Ringkasan dalam R: n, menang%, rata-rata R, t, profit factor, rugi beruntun, per tahun."""
    if trades is None or len(trades) == 0:
        return dict(n=0)
    r = trades["r"].to_numpy(float)
    n = len(r)
    m = r.mean()
    s = r.std(ddof=1) if n > 1 else 0.0
    t = m / s * np.sqrt(n) if s > 0 else 0.0
    wins, losses = r[r > 0].sum(), -r[r < 0].sum()
    pf = wins / losses if losses > 0 else np.inf
    streak = cur = 0
    for v in r:
        cur = cur + 1 if v <= 0 else 0
        streak = max(streak, cur)
    eq = np.cumsum(r)
    dd = float((np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:] - eq).max())
    yrs = trades.groupby(trades["t_entry"].dt.year)["r"].sum()
    out = dict(n=n, win_pct=round(100 * (r > 0).mean(), 1), avg_r=round(m, 4), med_r=round(float(np.median(r)), 3),
               t=round(t, 2), pf=round(float(pf), 3), total_r=round(float(r.sum()), 2),
               max_dd_r=round(dd, 2), max_loss_streak=int(streak),
               avg_risk_usd=round(float(trades["risk"].mean()), 3),
               outcomes={k: int(v) for k, v in trades["outcome"].value_counts().items()},
               per_year_r={int(k): round(float(v), 2) for k, v in yrs.items()},
               pos_years=int((yrs > 0).sum()), years=int(len(yrs)))
    if gross is not None and len(gross):
        g = gross["r"].to_numpy(float)
        gs = g.std(ddof=1) if len(g) > 1 else 0.0
        out["gross_avg_r"] = round(float(g.mean()), 4)
        out["gross_t"] = round(float(g.mean() / gs * np.sqrt(len(g))) if gs > 0 else 0.0, 2)
        out["cost_r"] = round(float(g.mean() - m), 4)
    return out


def breakeven_winrate(k: float, cost_r: float = 0.0) -> float:
    """Win rate impas untuk payoff 1:k bila biaya bolak-balik = cost_r (dalam R).

    Menang: k − c, kalah: −(1 + c) → p(k − c) = (1 − p)(1 + c) → p = (1 + c)/(1 + k).
    """
    return (1.0 + cost_r) / (1.0 + k)
