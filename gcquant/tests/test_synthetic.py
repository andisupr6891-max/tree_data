"""Uji generator data sintetis (gcquant.data.synthetic) — luring, deterministik."""
from __future__ import annotations

import datetime as dt
import math
import time

import numpy as np
import pandas as pd
import pytest

from gcquant import core
from gcquant.data import (
    MBO_COLUMNS, gc_first_notice_date, gc_last_trade_date, synthetic_bars,
    synthetic_daily_curve, synthetic_mbo, synthetic_mbo_with_truth,
)


# ---------------------------------------------------------------------------
# Replay buku referensi INDEPENDEN (tidak memakai kode generator)
# ---------------------------------------------------------------------------

class RefBook:
    """Buku order per-order dengan semantik Databento: A tambah, C kurangi (hapus di 0),
    M ubah (harga berubah / ukuran naik → ke belakang antrean; ukuran turun → prioritas tetap),
    R kosongkan, T/F/N tidak mengubah buku."""

    def __init__(self):
        self.orders: dict[int, list] = {}            # oid -> [side, px, size]
        self.queues: dict[tuple[str, float], list[int]] = {}

    def _q(self, side, px):
        return self.queues.setdefault((side, px), [])

    def _remove(self, oid):
        side, px, _ = self.orders[oid]
        q = self.queues[(side, px)]
        q.remove(oid)
        if not q:
            del self.queues[(side, px)]

    def clear(self):
        self.orders.clear()
        self.queues.clear()

    def add(self, oid, side, px, sz):
        assert oid not in self.orders, f"A untuk order yang sudah ada {oid}"
        assert sz > 0
        self.orders[oid] = [side, px, sz]
        self._q(side, px).append(oid)

    def cancel(self, oid, side, px, sz):
        o = self.orders[oid]
        assert o[0] == side and o[1] == px, "C dengan sisi/harga tidak cocok"
        assert 0 < sz <= o[2]
        o[2] -= sz
        if o[2] == 0:
            self._remove(oid)
            del self.orders[oid]

    def modify(self, oid, side, px, sz):
        assert oid in self.orders, "M untuk order tak dikenal"
        o = self.orders[oid]
        assert o[0] == side, "M dengan sisi berbeda"
        assert sz > 0
        if px != o[1] or sz > o[2]:
            self._remove(oid)
            o[1], o[2] = px, sz
            self._q(side, px).append(oid)
        else:
            o[2] = sz

    def levels(self, side):
        pxs = sorted({px for (s, px) in self.queues if s == side}, reverse=(side == "B"))
        return pxs

    def bbo(self):
        bl, al = self.levels("B"), self.levels("A")
        bb, ba = bl[0], al[0]
        bsz = sum(self.orders[o][2] for o in self.queues[("B", bb)])
        asz = sum(self.orders[o][2] for o in self.queues[("A", ba)])
        return bb, ba, bsz, asz, len(self.queues[("B", bb)]), len(self.queues[("A", ba)])


def group_bounds(flags: np.ndarray) -> list[tuple[int, int]]:
    ends = np.flatnonzero(flags & core.F_LAST)
    starts = np.concatenate([[0], ends[:-1] + 1])
    return list(zip(starts.tolist(), ends.tolist()))


def replay_and_check(mbo: pd.DataFrame, truth: pd.DataFrame | None = None) -> list[tuple]:
    """Replay penuh + pemeriksaan semantik trade CME. Kembalikan BBO per kelompok event."""
    act = mbo["action"].to_numpy()
    side = mbo["side"].to_numpy()
    px = mbo["price"].to_numpy()
    sz = mbo["size"].to_numpy()
    oid = mbo["order_id"].to_numpy().astype(np.int64)
    flags = mbo["flags"].to_numpy()
    book = RefBook()
    out = []
    for gi, (s, e) in enumerate(group_bounds(flags)):
        pending: dict[int, int] = {}          # oid -> kuantitas terisi (menunggu C/M)
        i = s
        while i <= e:
            a = act[i]
            if a == "R":
                book.clear()
            elif a == "A":
                book.add(oid[i], side[i], px[i], sz[i])
            elif a == "T":
                assert side[i] in ("A", "B")
                rest = "A" if side[i] == "B" else "B"
                # Level terbaik lawan yang masih punya sisa (setelah pengisian sebelumnya di grup).
                lv = [p for p in book.levels(rest)
                      if sum(book.orders[o][2] - pending.get(o, 0)
                             for o in book.queues[(rest, p)]) > 0]
                assert px[i] == lv[0], "harga T bukan harga terbaik lawan"
                if rest == "A":
                    assert px[i] > book.levels("B")[0]
                q = [o for o in book.queues[(rest, px[i])]
                     if book.orders[o][2] - pending.get(o, 0) > 0]
                j, total, fills = i + 1, 0, []
                while j <= e and act[j] == "F":
                    assert side[j] == rest, "F harus di sisi resting"
                    assert px[j] == px[i]
                    fills.append((oid[j], sz[j]))
                    total += sz[j]
                    j += 1
                assert total == sz[i] and len(fills) >= 1, "jumlah F ≠ ukuran T"
                # FIFO: order terisi = prefiks antrean; semua kecuali terakhir terisi penuh.
                assert [f[0] for f in fills] == q[:len(fills)], "pengisian melanggar FIFO"
                for k, (o, f) in enumerate(fills):
                    remaining = book.orders[o][2] - pending.get(o, 0)
                    assert 0 < f <= remaining
                    if k < len(fills) - 1:
                        assert f == remaining
                    pending[o] = pending.get(o, 0) + f
                i = j
                continue
            elif a == "F":
                raise AssertionError("F tanpa T sebelumnya")
            elif a == "C":
                if oid[i] in pending:
                    f = pending.pop(oid[i])
                    assert book.orders[oid[i]][2] == f == sz[i], "C setelah fill harus menghabiskan order"
                book.cancel(oid[i], side[i], px[i], sz[i])
            elif a == "M":
                if oid[i] in pending:
                    f = pending.pop(oid[i])
                    o = book.orders[oid[i]]
                    assert o[1] == px[i] and sz[i] == o[2] - f, "M setelah fill harus sisa ukuran"
                book.modify(oid[i], side[i], px[i], sz[i])
            else:
                raise AssertionError(f"aksi tak dikenal {a}")
            i += 1
        assert not pending, "ada fill tanpa pembaruan buku C/M"
        bb, ba, bsz, asz, bct, act_ = book.bbo()
        assert bb < ba, f"buku menyilang pada kelompok {gi}"
        out.append((bb, ba, bsz, asz, bct, act_))
        if truth is not None:
            t = truth.iloc[gi]
            assert (bb, ba, bsz, asz, bct, act_) == (t.bid_px, t.ask_px, t.bid_sz, t.ask_sz,
                                                     t.bid_ct, t.ask_ct)
            assert t.last_row == e
    return out


def cont_ofi(bp, ap, bs, as_):
    """OFI per event Cont-Kukanov-Stoikov (2014)."""
    bp, ap, bs, as_ = map(np.asarray, (bp, ap, bs, as_))
    e = np.zeros(len(bp))
    e[1:] = ((bp[1:] >= bp[:-1]) * bs[1:] - (bp[1:] <= bp[:-1]) * bs[:-1]
             - (ap[1:] <= ap[:-1]) * as_[1:] + (ap[1:] >= ap[:-1]) * as_[:-1])
    return e


# ---------------------------------------------------------------------------
# MBO
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def mbo_truth():
    return synthetic_mbo_with_truth(20000, seed=0)


def test_mbo_schema_and_dtypes(mbo_truth):
    mbo, _ = mbo_truth
    assert list(mbo.columns) == MBO_COLUMNS
    assert isinstance(mbo.index, pd.RangeIndex)
    for c in ("ts_recv", "ts_event", "instrument_id", "size", "flags", "sequence", "channel_id",
              "publisher_id"):
        assert mbo[c].dtype == np.int64, c
    assert mbo["order_id"].dtype == np.uint64
    assert mbo["price"].dtype == np.float64
    assert set(mbo["action"].unique()) <= set("ACMRTFN")
    assert set(mbo["side"].unique()) <= set("BAN")
    assert (mbo["symbol"] == "GCG6").all() and (mbo["instrument_id"] == 1).all()
    # Harga = kelipatan tick 0,10 persis seperti hasil fixed-point Databento (px_fixed / 1e9).
    p = mbo["price"].dropna().to_numpy()
    fixed = np.rint(p * 1e9).astype(np.int64)
    assert np.all(fixed % 100_000_000 == 0)
    assert np.array_equal(fixed / 1e9, p)


def test_mbo_fast_and_deterministic():
    t = time.perf_counter()
    a = synthetic_mbo(20000, seed=7)
    assert time.perf_counter() - t < 2.0
    b = synthetic_mbo(20000, seed=7)
    pd.testing.assert_frame_equal(a, b)
    c = synthetic_mbo(20000, seed=8)
    assert not a["price"].equals(c["price"])


def test_mbo_snapshot_structure(mbo_truth):
    mbo, _ = mbo_truth
    fl = mbo["flags"].to_numpy()
    assert mbo.loc[0, "action"] == "R" and mbo.loc[0, "side"] == "N"
    assert np.isnan(mbo.loc[0, "price"]) and mbo.loc[0, "size"] == 0
    snap_end = int(np.flatnonzero(fl & core.F_LAST)[0])
    snap = mbo.iloc[: snap_end + 1]
    assert ((snap["flags"] & core.F_SNAPSHOT) != 0).all()
    assert (snap["action"].iloc[1:] == "A").all()
    assert (snap["flags"].iloc[:-1] & core.F_LAST == 0).all()
    assert snap["flags"].iloc[-1] == core.F_SNAPSHOT | core.F_LAST
    assert (mbo["flags"].iloc[snap_end + 1:] & core.F_SNAPSHOT == 0).all()
    assert set(snap["side"].iloc[1:]) == {"A", "B"}


def test_mbo_event_groups_and_clock(mbo_truth):
    mbo, truth = mbo_truth
    fl = mbo["flags"].to_numpy()
    bounds = group_bounds(fl)
    assert len(bounds) == 20000 + 1                       # snapshot + n_events kelompok
    assert bounds[-1][1] == len(mbo) - 1                  # rekaman terakhir ber-F_LAST
    tr, te, sq = (mbo[c].to_numpy() for c in ("ts_recv", "ts_event", "sequence"))
    for s, e in bounds:
        assert (tr[s:e + 1] == tr[s]).all() and (te[s:e + 1] == te[s]).all()
        assert (sq[s:e + 1] == sq[s]).all()
        assert ((fl[s:e] & core.F_LAST) == 0).all()
    firsts = np.array([s for s, _ in bounds])
    assert np.all(np.diff(tr[firsts]) > 0), "ts_recv antar kelompok harus naik ketat"
    assert np.all(np.diff(te[firsts]) > 0)
    assert np.all(np.diff(sq[firsts]) == 1)
    assert np.all(te <= tr)
    assert tr[0] == core.to_ns("2026-01-05T14:30Z")
    assert np.array_equal(truth["ts_recv"].to_numpy(), tr[firsts])


def test_mbo_reference_replay_consistent(mbo_truth):
    """Replay independen: semantik A/C/M/R, T→F→C/M, FIFO, tak pernah menyilang, BBO = kebenaran."""
    mbo, truth = mbo_truth
    bbo = replay_and_check(mbo, truth)
    acts = mbo["action"].value_counts()
    assert acts["T"] > 1000 and acts["F"] >= acts["T"] and acts["M"] > 500 and acts["C"] > 5000
    spread_ticks = np.round((truth["ask_px"] - truth["bid_px"]).to_numpy() / 0.1).astype(int)
    assert spread_ticks.min() >= 1
    assert (spread_ticks == 1).mean() > 0.6                # GC: umumnya spread 1 tick
    # Ada trade yang menyapu > 1 level dan pengisian parsial (M setelah F).
    t_per_group = mbo[mbo["action"] == "T"].groupby("sequence").size()
    assert (t_per_group > 1).any()
    assert len(bbo) == len(truth)


def test_mbo_truth_depth_matches_reference_replay():
    """Kolom kebenaran 10 level (gaya MBP-10) = buku hasil replay independen di setiap F_LAST."""
    mbo, truth = synthetic_mbo_with_truth(4000, seed=13, truth_levels=10)
    replay_and_check(mbo, truth)
    book = RefBook()
    fl = mbo["flags"].to_numpy()
    rows = mbo[["action", "side", "price", "size", "order_id"]].itertuples(index=False)
    gi = 0
    filled = 0
    for i, (a, sd, px, sz, oid) in enumerate(rows):
        oid = int(oid)
        if a == "R":
            book.clear()
        elif a == "A":
            book.add(oid, sd, px, sz)
        elif a == "C":
            book.cancel(oid, sd, px, sz)
        elif a == "M":
            book.modify(oid, sd, px, sz)
        if fl[i] & core.F_LAST:
            t = truth.iloc[gi]
            for side, name in (("B", "bid"), ("A", "ask")):
                lv = book.levels(side)[:10]
                for k in range(10):
                    if k < len(lv):
                        q = book.queues[(side, lv[k])]
                        assert t[f"{name}_px_{k:02d}"] == lv[k]
                        assert t[f"{name}_sz_{k:02d}"] == sum(book.orders[o][2] for o in q)
                        assert t[f"{name}_ct_{k:02d}"] == len(q)
                        filled += 1
                    else:
                        assert np.isnan(t[f"{name}_px_{k:02d}"]) and t[f"{name}_sz_{k:02d}"] == 0
            gi += 1
    assert gi == len(truth)
    assert filled / (20 * len(truth)) > 0.9          # buku umumnya ≥ 10 level per sisi


def test_mbo_other_seed_and_params_consistent():
    mbo, truth = synthetic_mbo_with_truth(3000, seed=11, tick=0.25, price0=4000.0,
                                          instrument_id=42, symbol="MGCJ6", ofi_strength=2.0)
    replay_and_check(mbo, truth)
    fixed = np.rint(mbo["price"].dropna().to_numpy() * 1e9).astype(np.int64)
    assert np.all(fixed % 250_000_000 == 0)
    assert (mbo["instrument_id"] == 42).all() and (mbo["symbol"] == "MGCJ6").all()


@pytest.mark.parametrize("kw", [
    dict(n_levels=3, behavior={"min_levels": 0}),
    dict(ofi_strength=5.0, sigma_ticks=1.0),
    dict(behavior={"p_trade": 0.6, "p_add": 0.1, "p_cancel": 0.3, "sweep_base": 0.9}),
    dict(behavior={"p_trade": 0.0, "p_add": 0.05, "p_cancel": 0.95, "min_levels": 0}),
])
def test_mbo_robust_under_stress(kw):
    """Parameter ekstrem: tidak pernah crash, sisi buku tak pernah kosong, semantik tetap konsisten."""
    for sd in (0, 1):
        mbo, truth = synthetic_mbo_with_truth(1500, seed=sd, **kw)
        replay_and_check(mbo, truth)
        assert len(truth) == 1501


def test_mbo_prefix_stable_future_perturbation():
    """Memperpanjang simulasi (menambah 'masa depan') tidak mengubah rekaman masa lalu."""
    short, ts = synthetic_mbo_with_truth(800, seed=5)
    long, tl = synthetic_mbo_with_truth(3000, seed=5)
    pd.testing.assert_frame_equal(short, long.iloc[: len(short)])
    pd.testing.assert_frame_equal(ts, tl.iloc[: len(ts)])


def test_cont_ofi_helper_hand_computed():
    # bid naik (3.0→3.1): +q_b(n)=+4 ; ask tetap 3.3: −q_a(n)+q_a(n−1) = −5+7 = +2 → e1 = 6
    # bid tetap, q 4→2: +2−4 = −2 ; ask turun 3.3→3.2: −q_a(n) = −1 → e2 = −3
    e = cont_ofi([3.0, 3.1, 3.1], [3.3, 3.3, 3.2], [9, 4, 2], [7, 5, 1])
    assert e.tolist() == [0.0, 6.0, -3.0]


def _effect_corr(strength: float, seeds, m=20, h=50) -> float:
    xs, ys = [], []
    for sd in seeds:
        mbo, truth = synthetic_mbo_with_truth(20000, seed=sd, ofi_strength=strength)
        bbo = np.array(replay_and_check(mbo), dtype=float)       # BBO dari replay independen
        bp, ap, bs, as_ = bbo[:, 0], bbo[:, 1], bbo[:, 2], bbo[:, 3]
        e = cont_ofi(bp, ap, bs, as_)
        cs = np.cumsum(e)
        past = cs - np.concatenate([np.zeros(m), cs[:-m]])        # hanya data ≤ t
        mid = 0.5 * (bp + ap)
        fut = mid[h:] - mid[:-h]                                 # target: masa depan
        xs.append(past[m:-h])
        ys.append(fut[m:])
    x, y = np.concatenate(xs), np.concatenate(ys)
    return float(np.corrcoef(x, y)[0, 1])


def test_planted_ofi_effect_weak_but_real():
    seeds = (0, 1, 2)
    c1 = _effect_corr(1.0, seeds)
    c0 = _effect_corr(0.0, seeds)
    assert 0.08 < c1 < 0.35, c1          # efek ada tetapi lemah
    assert -0.12 < c0 < 0.02, c0         # tanpa efek tertanam: tidak ada prediktabilitas positif
    assert c1 - c0 > 0.10


# ---------------------------------------------------------------------------
# Bar sintetis
# ---------------------------------------------------------------------------

def test_synthetic_bars_structure_and_vol():
    n = 20000
    b = synthetic_bars(n, freq="1min", seed=3, start="2026-01-05T00:00Z", price0=2000.0,
                       vol=0.15, tick=0.0001)
    assert list(b.columns[:5]) == ["open", "high", "low", "close", "volume"]
    assert "spread" in b.columns and (b["spread"] > 0).all()
    assert str(b.index.dtype) == "datetime64[ns, UTC]" and b.index.name == "ts"
    assert b.index[0] == pd.Timestamp("2026-01-05T00:00Z")
    assert (np.diff(b.index.asi8) == 60 * core.NS_PER_SEC).all()
    o, h, l, c = (b[k].to_numpy() for k in ("open", "high", "low", "close"))
    assert (h >= np.maximum(o, c)).all() and (l <= np.minimum(o, c)).all()
    assert np.array_equal(o[1:], c[:-1])
    # σ_bar = 0,15·√(60 / (365,25·86400)) = 2,0683e-4 (dihitung tangan)
    sigma_bar = 0.15 * math.sqrt(60.0 / (365.25 * 86400.0))
    assert sigma_bar == pytest.approx(2.0683e-4, rel=1e-3)
    r = np.diff(np.log(c))
    assert np.std(r) == pytest.approx(sigma_bar, rel=0.03)
    assert b["volume"].dtype == np.int64 and (b["volume"] >= 0).all()


def test_synthetic_bars_deterministic_prefix_stable():
    a = synthetic_bars(500, seed=9)
    pd.testing.assert_frame_equal(a, synthetic_bars(500, seed=9))
    pd.testing.assert_frame_equal(a.iloc[:200], synthetic_bars(200, seed=9))
    assert not a["close"].equals(synthetic_bars(500, seed=10)["close"])
    # pembulatan tick bawaan 0,01
    assert np.allclose(np.round(a["close"] / 0.01) * 0.01, a["close"])


# ---------------------------------------------------------------------------
# Kurva harian GC
# ---------------------------------------------------------------------------

def test_gc_calendar_hand_checked():
    # GCJ5: FND = hari kerja terakhir Maret 2025 (Senin 31 Mar); LTD = 3 hari kerja terakhir April
    # (30, 29, 28 Apr) → 28 Apr 2025.
    assert gc_first_notice_date(2025, 4) == dt.date(2025, 3, 31)
    assert gc_last_trade_date(2025, 4) == dt.date(2025, 4, 28)
    # GCZ4: FND Jumat 29 Nov 2024 (setelah Thanksgiving); LTD 27 Des 2024 (25 Des libur).
    assert gc_first_notice_date(2024, 12) == dt.date(2024, 11, 29)
    assert gc_last_trade_date(2024, 12) == dt.date(2024, 12, 27)
    # GCG6: FND Jumat 30 Jan 2026; LTD Rabu 25 Feb 2026.
    assert gc_first_notice_date(2026, 2) == dt.date(2026, 1, 30)
    assert gc_last_trade_date(2026, 2) == dt.date(2026, 2, 25)
    # GCG5 (Januari sebelumnya → Desember tahun sebelumnya): FND 31 Jan 2025.
    assert gc_first_notice_date(2025, 2) == dt.date(2025, 1, 31)


@pytest.fixture(scope="module")
def curve():
    return synthetic_daily_curve("2024-06-01", "2026-06-30", seed=4)


def test_daily_curve_schema_and_calendar(curve):
    cols = ["trade_date", "symbol", "instrument_id", "open", "high", "low", "close", "settle",
            "volume", "open_interest"]
    assert list(curve.columns) == cols
    dates = sorted(set(curve["trade_date"]))
    assert all(isinstance(d, dt.date) for d in dates)
    assert all(core.is_business_day(d) for d in dates)
    assert dt.date(2024, 12, 25) not in dates and dt.date(2025, 4, 18) not in dates  # libur
    assert curve.groupby("trade_date").size().eq(6).all()
    assert set(s[2] for s in curve["symbol"]) <= set("GJMQVZ")
    for _, r in curve.iterrows():
        root, y, m = core.parse_futures_symbol(r.symbol, r.trade_date.year)
        assert r.instrument_id == y * 100 + m
        assert gc_last_trade_date(y, m) >= r.trade_date        # tidak ada kontrak kedaluwarsa
        assert r.high >= max(r.open, r.close, r.settle) - 1e-9
        assert r.low <= min(r.open, r.close, r.settle) + 1e-9
    assert (curve["volume"] >= 0).all() and (curve["open_interest"] >= 0).all()


def test_daily_curve_contango_carry(curve):
    """ln(F2/F1)/(τ2−τ1) ≈ r − lease = 0,045 − 0,005 = 0,04 (hari kalender/365)."""
    rows = []
    for d, g in curve.groupby("trade_date"):
        g = g.sort_values("instrument_id")
        ltd = [gc_last_trade_date(i // 100, i % 100) for i in g["instrument_id"]]
        tau = np.array([(x - d).days for x in ltd]) / 365.0
        f = g["settle"].to_numpy()
        assert np.all(np.diff(f) > 0), f"bukan contango pada {d}"
        rows.append(np.log(f[-1] / f[0]) / (tau[-1] - tau[0]))
    carry = np.array(rows)
    assert np.all(np.abs(carry - 0.04) < 0.002)
    assert carry.mean() == pytest.approx(0.04, abs=2e-4)


def test_daily_curve_oi_roll_pattern(curve):
    oi = curve.pivot(index="trade_date", columns="symbol", values="open_interest")
    vol = curve.pivot(index="trade_date", columns="symbol", values="volume")
    dates = list(oi.index)
    checked = 0
    for y, m in [(2024, 8), (2024, 10), (2024, 12), (2025, 2), (2025, 4), (2025, 6), (2025, 8),
                 (2025, 10), (2025, 12), (2026, 2), (2026, 4), (2026, 6)]:
        fnd = gc_first_notice_date(y, m)
        ny, nm = (y + 1, 2) if m == 12 else (y, m + 2)
        front, nxt = core.futures_symbol("GC", y, m), core.futures_symbol("GC", ny, nm)
        before = [d for d in dates if d < fnd]
        if len(before) < 16 or fnd not in dates:
            continue
        d1, d15 = before[-1], before[-15]
        assert oi.loc[d1, front] < 0.1 * oi.loc[d15, front], (front, "OI depan harus turun")
        assert oi.loc[d1, nxt] > 2.0 * oi.loc[d15, nxt], (nxt, "OI berikutnya harus naik")
        assert oi.loc[d15].idxmax() == front and oi.loc[d1].idxmax() == nxt
        assert vol.loc[d1, nxt] > vol.loc[d1, front]
        # setelah FND (periode pengiriman) OI depan kecil dan menurun ke LTD
        after = [d for d in dates if fnd <= d <= gc_last_trade_date(y, m)]
        s = oi.loc[after, front].to_numpy()
        assert s.max() < 0.02 * oi.loc[d15, front] and s[-1] <= s[0]
        checked += 1
    assert checked >= 8


def test_daily_curve_deterministic_and_prefix_stable():
    a = synthetic_daily_curve("2025-01-01", "2025-03-31", seed=2)
    b = synthetic_daily_curve("2025-01-01", "2025-09-30", seed=2)
    pd.testing.assert_frame_equal(a, b[b["trade_date"] <= dt.date(2025, 3, 31)].reset_index(drop=True))
    pd.testing.assert_frame_equal(a, synthetic_daily_curve("2025-01-01", "2025-03-31", seed=2))
    c = synthetic_daily_curve("2025-01-01", "2025-03-31", seed=3)
    assert not a["settle"].equals(c["settle"])
