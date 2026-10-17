"""Data sintetis deterministik untuk uji & demo luring (tanpa biaya, tanpa jaringan).

Tiga generator:

``synthetic_mbo``
    Aliran MBO bergaya CME/Databento yang konsisten secara internal:
    ``R`` (clear) + snapshot ``A`` (flag ``F_SNAPSHOT``, ``F_LAST`` pada rekaman snapshot
    terakhir), lalu kelompok event A/C/M/T/F. Trade = ``T`` (sisi agresor, satu per level harga)
    diikuti ``F`` (sisi order yang diam/resting, satu per order yang terisi), lalu ``C``
    (order habis terisi) atau ``M`` (sisa ukuran) — buku HANYA berubah lewat A/C/M/R.
    Setiap kelompok event berbagi ``ts_recv``/``ts_event``/``sequence``; ``F_LAST`` hanya pada
    rekaman terakhir kelompok. Prioritas antrean FIFO: pengisian selalu dari depan antrean;
    ``M`` dengan perubahan harga atau kenaikan ukuran memindahkan order ke belakang antrean.

    EFEK YANG DITANAM (lemah tetapi nyata): nilai wajar laten ``F`` mengikuti random walk
    (σ = ``sigma_ticks`` = 0,2 tick per event; ≈ 0,9 % per hari bila ±1,5 juta event/hari).
    Arus order bergantung pada celah ``g = F − mid`` lewat ``s = tanh(β·g)``,
    ``β = 0,5·ofi_strength`` per tick: agresor beli (dan sapuan level terbaik) lebih sering bila
    ``g > 0``, pembatalan sisi ask lebih sering, penambahan bid/perbaikan harga bid lebih sering,
    dan sebaliknya. Karena mid mengejar ``F`` secara bertahap (sd celah ≈ 1,4 tick), imbalans
    arus order (OFI) SAAT INI memprediksi perubahan mid puluhan event KE DEPAN.
    Kekuatan terukur (20.000 event, seed 0..7, per kelompok event): korelasi Pearson antara
    OFI-L1 Cont-Kukanov-Stoikov kumulatif 20 event terakhir dan perubahan mid 50 event
    berikutnya ≈ 0,11–0,26 (rata-rata ≈ 0,16); untuk jendela 50 → 100 event ≈ 0,19.
    Dengan ``ofi_strength=0`` (model zero-intelligence) korelasi yang sama ≈ −0,11…+0,02
    (rata-rata ≈ −0,05): sedikit NEGATIF karena pembalikan mekanis (spread yang melebar diisi
    kembali dari kedua sisi), bukan efek tertanam. Buku: ≥10 level harga dalam 12 tick dari
    harga terbaik (isi ulang otomatis), order > 40 tick dari harga terbaik dibersihkan;
    spread 1 tick ±77 % waktu. Cukup untuk diuji fitur, tetapi jauh dari "uang gratis"
    setelah biaya.

``synthetic_bars``
    Bar OHLCV (indeks = waktu BUKA) dari GBM dengan sub-langkah intrabar, plus kolom spread USD.

``synthetic_daily_curve``
    Kurva harian beberapa kontrak GC (bulan aktif G J M Q V Z) dengan jadwal kedaluwarsa
    realistis (kalender ``core``): FND = hari kerja terakhir bulan sebelum bulan kontrak,
    LTD = hari kerja ke-3 dari akhir bulan kontrak. OI kontrak depan turun tajam pada ±10 hari
    kerja sebelum FND sementara OI kontrak berikutnya naik; harga contango
    ``F = S·exp((r − lease)·τ)``.

Semua generator deterministik per ``seed`` dan bersifat "prefiks-stabil": memperpanjang
keluaran (n lebih besar) tidak mengubah baris-baris awal (setiap aliran acak memakai
generator anak ``SeedSequence`` sendiri yang dikonsumsi berurutan).
"""
from __future__ import annotations

import datetime as _dt
import math
from collections import deque
from typing import Any

import numpy as np
import pandas as pd

from .. import core

__all__ = ["synthetic_mbo", "synthetic_mbo_with_truth", "synthetic_bars", "synthetic_daily_curve",
           "gc_first_notice_date", "gc_last_trade_date", "DEFAULT_PRICE0"]

DEFAULT_PRICE0 = {"GC": 2650.0, "MGC": 2650.0, "1OZ": 2650.0}

# Parameter perilaku bawaan generator MBO (dikalibrasi; lihat docstring modul).
_BEHAVIOR: dict[str, float] = {
    "beta": 0.5,          # kepekaan arus order terhadap celah F − mid (per tick), × ofi_strength
    "p_trade": 0.10, "p_add": 0.48, "p_cancel": 0.34,   # sisanya modify
    "agg_bias": 0.8,      # bias sisi agresor
    "add_bias": 0.4,      # bias sisi penambahan order
    "cancel_bias": 0.5,   # bias sisi pembatalan
    "impr_bias": 0.8,     # bias perbaikan harga di dalam spread
    "p_improve": 0.4,     # peluang perbaikan per tick spread di atas 1 tick
    "sweep_base": 0.08, "sweep_dir": 0.35,   # peluang agresor menyapu seluruh level terbaik
    "add_depth": 1.5, "cancel_depth": 2.5,   # rata-rata kedalaman (level) penambahan/pembatalan
    "min_levels": 10,     # minimal level harga dalam 12 tick dari harga terbaik (isi ulang)
}

_F_LAST = core.F_LAST
_F_SNAPSHOT = core.F_SNAPSHOT


class _Uniform:
    """Aliran uniform [0,1) prefiks-stabil (blok tetap dari satu generator)."""

    __slots__ = ("_rng", "_buf", "_pos")

    def __init__(self, seed_seq: np.random.SeedSequence):
        self._rng = np.random.Generator(np.random.PCG64(seed_seq))
        self._buf: list[float] = []
        self._pos = 0

    def __call__(self) -> float:
        if self._pos >= len(self._buf):
            self._buf = self._rng.random(65536).tolist()
            self._pos = 0
        v = self._buf[self._pos]
        self._pos += 1
        return v


# ---------------------------------------------------------------------------
# MBO
# ---------------------------------------------------------------------------

def synthetic_mbo_with_truth(n_events: int = 20000, seed: int = 0, root: str = "GC",
                             tick: float = 0.10, start="2026-01-05T14:30Z", instrument_id: int = 1,
                             symbol: str = "GCG6", *, price0: float | None = None,
                             ofi_strength: float = 1.0, sigma_ticks: float = 0.2,
                             mean_gap_ms: float = 20.0, n_levels: int = 10,
                             publisher_id: int = 1, channel_id: int = 0,
                             behavior: dict[str, float] | None = None, truth_levels: int = 1
                             ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Seperti ``synthetic_mbo`` tetapi juga mengembalikan "kebenaran" per kelompok event.

    Kembalian ``(mbo, truth)``; ``truth`` berisi satu baris per kelompok event (baris 0 =
    snapshot) dengan kolom ``ts_recv, ts_event, bid_px, ask_px, bid_sz, ask_sz, bid_ct, ask_ct,
    fair_value, last_row`` (``last_row`` = indeks baris MBO berflag ``F_LAST``). ``fair_value``
    adalah nilai wajar laten (TIDAK teramati pasar; hanya untuk diagnosis/uji).

    ``truth_levels > 1`` menambahkan kolom buku bergaya BOOK/MBP-10
    (``bid_px_00..``, ``ask_px_00..``, ``bid_sz_..``, ``ask_sz_..``, ``bid_ct_..``, ``ask_ct_..``;
    NaN harga / 0 ukuran untuk level kosong) setelah setiap kelompok event — acuan untuk
    menguji rekonstruksi MBO → MBP-10. ``behavior`` menimpa parameter perilaku (lanjutan).
    """
    if n_events < 0:
        raise ValueError("n_events harus ≥ 0")
    if tick <= 0:
        raise ValueError("tick harus > 0")
    if n_levels < 3:
        raise ValueError("n_levels minimal 3")
    if price0 is None:
        price0 = DEFAULT_PRICE0.get(root, 2000.0)
    tick_fixed = int(round(tick * core.FIXED_PRICE_SCALE))

    ss = np.random.SeedSequence(seed)
    s_u, s_z, s_gap, s_lat = ss.spawn(4)
    U = _Uniform(s_u)
    log = math.log
    tanh = math.tanh
    z = np.random.Generator(np.random.PCG64(s_z)).standard_normal(n_events).tolist()
    gap_ns = np.maximum(1_000, np.random.Generator(np.random.PCG64(s_gap)).exponential(
        mean_gap_ms * 1e6, n_events)).astype(np.int64).tolist()
    lat_ns = (15_000 + np.random.Generator(np.random.PCG64(s_lat)).exponential(
        10_000.0, n_events)).astype(np.int64).tolist()

    # Parameter perilaku (lihat docstring modul); dapat ditimpa lewat ``behavior``.
    bp = dict(_BEHAVIOR)
    if behavior:
        unknown = set(behavior) - set(bp)
        if unknown:
            raise ValueError(f"Parameter behavior tidak dikenal: {sorted(unknown)}")
        bp.update(behavior)
    beta = bp["beta"] * float(ofi_strength)
    p_trade, p_add, p_cancel = bp["p_trade"], bp["p_add"], bp["p_cancel"]   # sisanya modify
    agg_bias, add_bias, cancel_bias, impr_bias = (bp["agg_bias"], bp["add_bias"],
                                                  bp["cancel_bias"], bp["impr_bias"])
    p_improve, sweep_base, sweep_dir = bp["p_improve"], bp["sweep_base"], bp["sweep_dir"]
    add_depth, cancel_depth = bp["add_depth"], bp["cancel_depth"]
    min_near, near_win, far_win = int(bp["min_levels"]), 12, 40

    bids: dict[int, deque] = {}
    asks: dict[int, deque] = {}
    orders: dict[int, list] = {}          # oid -> [side, px_ticks, size]
    recs: list[tuple] = []                # (ts_recv, ts_event, oid, action, side, px, size, flags, seq)
    truth: list[tuple] = []
    next_oid = 6_400_000_000_000
    seq = 1_000_000

    t0 = int(core.to_ns(start))
    t_ev = t_rc = t0
    bb0 = int(round(price0 / tick))

    def best_stats(book: dict, px: int) -> tuple[int, int]:
        q = book[px]
        return sum(orders[o][2] for o in q), len(q)

    depth_rows: list[tuple] = []
    n_depth = int(truth_levels)

    def record_truth(F: float) -> None:
        bb = max(bids)
        ba = min(asks)
        bsz, bct = best_stats(bids, bb)
        asz, act = best_stats(asks, ba)
        truth.append((t_rc, t_ev, bb, ba, bsz, asz, bct, act, F, len(recs) - 1))
        if n_depth > 1:
            row: list = []
            for book, rev in ((bids, True), (asks, False)):
                lv = sorted(book, reverse=rev)[:n_depth]
                st = [best_stats(book, px) for px in lv]
                pad = n_depth - len(lv)
                row.append(lv + [-1] * pad)
                row.append([x[0] for x in st] + [0] * pad)
                row.append([x[1] for x in st] + [0] * pad)
            depth_rows.append(tuple(row))

    # --- snapshot: R + A (F_SNAPSHOT), F_LAST pada rekaman terakhir ---------------------
    recs.append((t_rc, t_ev, 0, "R", "N", -1, 0, _F_SNAPSHOT, seq))
    for side, sgn, book, best in (("B", -1, bids, bb0), ("A", 1, asks, bb0 + 1)):
        for i in range(n_levels):
            px = best + sgn * i
            q = book.setdefault(px, deque())
            for _ in range(1 + int(-log(1.0 - U()) * (1.0 + 0.3 * i))):
                sz = 1 + int(-log(1.0 - U()) * 1.5)
                oid = next_oid
                next_oid += 1
                orders[oid] = [side, px, sz]
                q.append(oid)
                recs.append((t_rc, t_ev, oid, "A", side, px, sz, _F_SNAPSHOT, seq))
    r = recs[-1]
    recs[-1] = r[:7] + (r[7] | _F_LAST, r[8])
    F = bb0 + 0.5
    record_truth(F)

    # --- helper aksi buku ------------------------------------------------------------
    def add(side: str, px: int, sz: int) -> None:
        nonlocal next_oid
        oid = next_oid
        next_oid += 1
        orders[oid] = [side, px, sz]
        (bids if side == "B" else asks).setdefault(px, deque()).append(oid)
        recs.append((t_rc, t_ev, oid, "A", side, px, sz, 0, seq))

    def cancel(oid: int) -> None:
        side, px, sz = orders.pop(oid)
        book = bids if side == "B" else asks
        q = book[px]
        q.remove(oid)
        if not q:
            del book[px]
        recs.append((t_rc, t_ev, oid, "C", side, px, sz, 0, seq))

    def modify(oid: int, new_px: int, new_sz: int) -> None:
        o = orders[oid]
        side, px, sz = o
        book = bids if side == "B" else asks
        if new_px != px or new_sz > sz:          # kehilangan prioritas → ke belakang antrean
            q = book[px]
            q.remove(oid)
            if not q:
                del book[px]
            book.setdefault(new_px, deque()).append(oid)
        o[1] = new_px
        o[2] = new_sz
        recs.append((t_rc, t_ev, oid, "M", side, new_px, new_sz, 0, seq))

    def pick_order(book: dict, is_bid: bool, depth_mean: float) -> int:
        lv = sorted(book, reverse=is_bid)
        j = min(int(-log(1.0 - U()) * depth_mean), len(lv) - 1)
        q = book[lv[j]]
        return q[int(U() * len(q))]

    def trade(buy: bool, s: float) -> None:
        book = asks if buy else bids
        agg_side, rest_side = ("B", "A") if buy else ("A", "B")
        lv = sorted(book, reverse=not buy)
        walkable = lv[:max(1, len(lv) - 3)]       # selalu sisakan ≥3 level di sisi lawan
        top = sum(orders[o][2] for o in book[lv[0]])
        if len(lv) == 1 and top <= 1:
            return                                # jangan kosongkan sisi lawan
        s_dir = s if buy else -s
        if U() < sweep_base + sweep_dir * max(0.0, s_dir):   # sapu level terbaik
            qty = top + (int(-log(1.0 - U()) * 1.0) if U() < 0.3 else 0)
        else:
            qty = 1 + int(-log(1.0 - U()) * 1.2)
        cap = sum(orders[o][2] for px in walkable for o in book[px])
        if len(lv) == 1:
            cap -= 1                              # sisakan minimal 1 kontrak
        rem = min(qty, cap)
        fills: list[tuple[int, int, int]] = []
        for px in walkable:
            if rem <= 0:
                break
            lvl: list[tuple[int, int]] = []
            for oid in book[px]:
                if rem <= 0:
                    break
                osz = orders[oid][2]
                f = osz if osz <= rem else rem
                lvl.append((oid, f))
                rem -= f
            recs.append((t_rc, t_ev, 0, "T", agg_side, px, sum(f for _, f in lvl), 0, seq))
            for oid, f in lvl:
                recs.append((t_rc, t_ev, oid, "F", rest_side, px, f, 0, seq))
                fills.append((oid, px, f))
        # Pembaruan buku untuk order resting yang terisi: C (habis) atau M (sisa).
        for oid, px, f in fills:
            o = orders[oid]
            if f == o[2]:
                q = book[px]
                if q[0] == oid:
                    q.popleft()
                else:
                    q.remove(oid)
                if not q:
                    del book[px]
                del orders[oid]
                recs.append((t_rc, t_ev, oid, "C", rest_side, px, f, 0, seq))
            else:
                o[2] -= f
                recs.append((t_rc, t_ev, oid, "M", rest_side, px, o[2], 0, seq))

    # --- loop event ------------------------------------------------------------------
    for k in range(n_events):
        t_ev += gap_ns[k]
        t_rc = max(t_rc + 1, t_ev + lat_ns[k])
        seq += 1
        F += sigma_ticks * z[k]
        bb = max(bids)
        ba = min(asks)
        s = tanh(beta * (F - 0.5 * (bb + ba)))
        lo_b, hi_a = bb - near_win, ba + near_win
        nb = sum(1 for p in bids if p > lo_b)          # level bid dalam jendela dekat
        na = sum(1 for p in asks if p < hi_a)
        if nb < min_near or na < min_near:
            # Isi ulang sisi yang tipis di dalam jendela dekat harga terbaik (atau di dalam
            # spread bila spread lebar); tidak pernah menyilang.
            sz_new = 1 + int(-log(1.0 - U()) * 1.5)
            if ba - bb > 2:
                dk = 1 + int(U() * (ba - bb - 1))
                px = bb + dk if nb <= na else ba - dk
            else:
                dk = 1 + int(U() * (near_win - 1))
                px = bb - dk if nb <= na else ba + dk
            add("B" if nb <= na else "A", px, sz_new)
        elif min(bids) < bb - far_win or max(asks) > ba + far_win:
            # Bersihkan order basi yang terlalu jauh dari harga terbaik.
            if min(bids) < bb - far_win:
                cancel(bids[min(bids)][-1])
            else:
                cancel(asks[max(asks)][-1])
        else:
            u = U()
            if u < p_trade:
                trade(U() < 0.5 * (1.0 + agg_bias * s), s)
            elif u < p_trade + p_add:
                is_bid = U() < 0.5 * (1.0 + add_bias * s)
                s_side = s if is_bid else -s
                spr = ba - bb
                if spr > 1 and U() < min(1.0, p_improve * (spr - 1)) * (1.0 + impr_bias * s_side):
                    step = 1 + int(U() * (spr - 1))          # harga baru di dalam spread
                    px = bb + step if is_bid else ba - step
                else:
                    dk = int(-log(1.0 - U()) * add_depth)
                    px = bb - dk if is_bid else ba + dk
                add("B" if is_bid else "A", px, 1 + int(-log(1.0 - U()) * 1.2))
            elif u < p_trade + p_add + p_cancel:
                is_ask = U() < 0.5 * (1.0 + cancel_bias * s)
                book = asks if is_ask else bids
                oid = pick_order(book, not is_ask, cancel_depth)
                if len(book) > 1 or len(book[orders[oid][1]]) > 1:   # jangan kosongkan sisi
                    cancel(oid)
            else:
                is_bid = U() < 0.5
                book = bids if is_bid else asks
                oid = pick_order(book, is_bid, 1.5)
                _, px, sz = orders[oid]
                rr = U()
                if rr < 0.5 and sz > 1:
                    modify(oid, px, sz - 1 - int(U() * (sz - 1)))      # turun ukuran: prioritas tetap
                elif rr < 0.75:
                    modify(oid, px, sz + 1 + int(U() * 2))             # naik ukuran: ke belakang
                else:
                    modify(oid, px - 1 if is_bid else px + 1, sz)      # geser menjauh: ke belakang
        if recs[-1][8] != seq:
            # Kelompok tanpa rekaman (aksi dibatalkan oleh pengaman): ganti dengan penambahan
            # order 1 lot di sisi yang lebih tipis agar setiap kelompok punya rekaman F_LAST.
            if len(bids) <= len(asks):
                add("B", min(bids) - 1, 1)
            else:
                add("A", max(asks) + 1, 1)
        r = recs[-1]
        recs[-1] = r[:7] + (r[7] | _F_LAST, r[8])
        record_truth(F)

    # --- susun DataFrame ---------------------------------------------------------------
    cols = list(zip(*recs))
    px_t = np.asarray(cols[5], dtype=np.int64)
    price = (px_t * tick_fixed) / core.FIXED_PRICE_SCALE
    price = np.where(px_t < 0, np.nan, price)
    n = len(recs)
    mbo = pd.DataFrame({
        "ts_recv": np.asarray(cols[0], dtype=np.int64),
        "ts_event": np.asarray(cols[1], dtype=np.int64),
        "instrument_id": np.full(n, instrument_id, dtype=np.int64),
        "order_id": np.asarray(cols[2], dtype=np.uint64),
        "action": pd.Series(cols[3], dtype=str),
        "side": pd.Series(cols[4], dtype=str),
        "price": price,
        "size": np.asarray(cols[6], dtype=np.int64),
        "flags": np.asarray(cols[7], dtype=np.int64),
        "sequence": np.asarray(cols[8], dtype=np.int64),
        "channel_id": np.full(n, channel_id, dtype=np.int64),
        "publisher_id": np.full(n, publisher_id, dtype=np.int64),
        "symbol": pd.Series([symbol] * n, dtype=str),
    })
    tc = list(zip(*truth))
    to_px = lambda a: (np.asarray(a, dtype=np.int64) * tick_fixed) / core.FIXED_PRICE_SCALE  # noqa: E731
    tr = pd.DataFrame({
        "ts_recv": np.asarray(tc[0], dtype=np.int64),
        "ts_event": np.asarray(tc[1], dtype=np.int64),
        "bid_px": to_px(tc[2]), "ask_px": to_px(tc[3]),
        "bid_sz": np.asarray(tc[4], dtype=np.int64), "ask_sz": np.asarray(tc[5], dtype=np.int64),
        "bid_ct": np.asarray(tc[6], dtype=np.int64), "ask_ct": np.asarray(tc[7], dtype=np.int64),
        "fair_value": np.asarray(tc[8], dtype=np.float64) * tick,
        "last_row": np.asarray(tc[9], dtype=np.int64),
    })
    if n_depth > 1:
        arr = {k: np.array([r[j] for r in depth_rows], dtype=np.int64).reshape(len(depth_rows), n_depth)
               for j, k in enumerate(("bpx", "bsz", "bct", "apx", "asz", "act"))}
        extra: dict[str, np.ndarray] = {}
        for kind, key in (("bid_px", "bpx"), ("ask_px", "apx")):
            for i in range(n_depth):
                v = arr[key][:, i]
                extra[f"{kind}_{i:02d}"] = np.where(v < 0, np.nan, (v * tick_fixed) / core.FIXED_PRICE_SCALE)
        for kind, key in (("bid_sz", "bsz"), ("ask_sz", "asz"), ("bid_ct", "bct"), ("ask_ct", "act")):
            for i in range(n_depth):
                extra[f"{kind}_{i:02d}"] = arr[key][:, i]
        tr = pd.concat([tr, pd.DataFrame(extra)], axis=1)
    mbo.attrs.update({"synthetic": True, "tick": tick, "root": root, "seed": seed,
                      "ofi_strength": ofi_strength})
    return mbo, tr


def synthetic_mbo(n_events: int = 20000, seed: int = 0, root: str = "GC", tick: float = 0.10,
                  start="2026-01-05T14:30Z", instrument_id: int = 1, symbol: str = "GCG6",
                  **kwargs: Any) -> pd.DataFrame:
    """Aliran MBO sintetis bergaya Databento CME (frame MBO kanonik, SPEC §2).

    ``n_events`` = jumlah kelompok event setelah snapshot (jumlah baris lebih banyak karena
    trade menghasilkan T + F + C/M). Argumen kata kunci tambahan: ``price0``,
    ``ofi_strength`` (0 = tanpa efek tertanam), ``sigma_ticks``, ``mean_gap_ms``,
    ``n_levels``, ``publisher_id``, ``channel_id``. Lihat docstring modul untuk mekanisme dan
    kekuatan efek OFI → perubahan mid. Deterministik per ``seed``; 20.000 event < 2 detik.
    """
    mbo, _ = synthetic_mbo_with_truth(n_events, seed, root, tick, start, instrument_id, symbol,
                                      **kwargs)
    return mbo


# ---------------------------------------------------------------------------
# Bar
# ---------------------------------------------------------------------------

def synthetic_bars(n: int, freq: str = "1min", seed: int = 0, start="2026-01-05T00:00Z",
                   price0: float = 2000.0, vol: float = 0.15, drift: float = 0.0, *,
                   tick: float = 0.01, spread: float = 0.25, substeps: int = 8,
                   base_volume: float = 120.0, symbol: str | None = None) -> pd.DataFrame:
    """Bar OHLCV sintetis (BARS): indeks = waktu BUKA bar (UTC ns), diketahui pada ts + freq.

    Model: log-harga GBM dengan ``substeps`` sub-langkah per bar; ``open`` bar i = ``close``
    bar i−1; high/low = ekstrem jalur sub-langkah (setelah dibulatkan ke ``tick``, sehingga
    selalu konsisten). ``vol``/``drift`` tahunan dengan waktu kalender kontinu:
    σ_bar = vol·√(freq / 365,25 hari). Kolom ``spread`` (USD) = ``spread``·(1 + Exp(0,5)),
    dibulatkan ke tick. ``volume`` ~ Poisson(base_volume·lognormal).
    """
    if n < 0:
        raise ValueError("n harus ≥ 0")
    bar_ns = int(pd.Timedelta(freq).value)
    if bar_ns <= 0:
        raise ValueError("freq harus positif")
    year_ns = 365.25 * 86400 * 1e9
    dt_sub = bar_ns / year_ns / substeps
    ss = np.random.SeedSequence(seed)
    s_path, s_vol, s_poi, s_spr = ss.spawn(4)
    eps = np.random.Generator(np.random.PCG64(s_path)).standard_normal((n, substeps))
    incr = (drift - 0.5 * vol * vol) * dt_sub + vol * math.sqrt(dt_sub) * eps
    logp = math.log(price0) + np.cumsum(incr.ravel()).reshape(n, substeps)
    path = np.exp(logp)
    path = np.round(path / tick) * tick
    p0 = round(price0 / tick) * tick
    opens = np.concatenate([[p0], path[:-1, -1]]) if n else np.empty(0)
    closes = path[:, -1] if n else np.empty(0)
    highs = np.maximum(path.max(axis=1), opens) if n else np.empty(0)
    lows = np.minimum(path.min(axis=1), opens) if n else np.empty(0)
    lam = base_volume * np.exp(0.5 * np.random.Generator(np.random.PCG64(s_vol)).standard_normal(n))
    volume = np.random.Generator(np.random.PCG64(s_poi)).poisson(lam).astype(np.int64)
    rs = np.random.Generator(np.random.PCG64(s_spr))
    spr = np.round(spread * (1.0 + rs.exponential(0.5, n)) / tick) * tick
    idx = core.ns_to_ts(int(core.to_ns(start)) + bar_ns * np.arange(n, dtype=np.int64))
    out = pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes,
                        "volume": volume, "spread": spr}, index=idx)
    out.index.name = "ts"
    if symbol is not None:
        out["symbol"] = symbol
    out.attrs["bar_len"] = freq
    return out


# ---------------------------------------------------------------------------
# Kurva harian GC
# ---------------------------------------------------------------------------

_GC_ACTIVE = (2, 4, 6, 8, 10, 12)


def gc_first_notice_date(year: int, month: int) -> _dt.date:
    """FND GC/MGC: hari kerja terakhir bulan sebelum bulan kontrak (kalender ``core``)."""
    py, pm = (year - 1, 12) if month == 1 else (year, month - 1)
    return core.business_days_in_month(py, pm)[-1]


def gc_last_trade_date(year: int, month: int) -> _dt.date:
    """LTD GC/MGC: hari kerja ke-3 dari akhir bulan kontrak (kalender ``core``)."""
    return core.business_days_in_month(year, month)[-3]


def _active_after(d: _dt.date, n: int, months=_GC_ACTIVE) -> list[tuple[int, int]]:
    """n kontrak bulan aktif pertama dengan LTD ≥ d."""
    out: list[tuple[int, int]] = []
    y, m = d.year, d.month
    while len(out) < n:
        if m in months and gc_last_trade_date(y, m) >= d:
            out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _to_date(x) -> _dt.date:
    if isinstance(x, _dt.datetime):
        return x.date()
    if isinstance(x, _dt.date):
        return x
    return pd.Timestamp(x).date()


def synthetic_daily_curve(start, end, seed: int = 0, *, root: str = "GC", spot0: float = 2000.0,
                          r: float = 0.045, lease: float = 0.005, vol: float = 0.15,
                          n_contracts: int = 6, total_oi: float = 500_000,
                          total_volume: float = 250_000, tick: float = 0.10,
                          roll_center_bd: float = 6.0, roll_width_bd: float = 1.3) -> pd.DataFrame:
    """Kurva harian multi-kontrak GC (frame DAILY) dengan pola roll OI yang realistis.

    - Hari perdagangan: hari kerja CME di [start, end] (``core.is_business_day``).
    - Kontrak terdaftar: ``n_contracts`` bulan aktif (G J M Q V Z) terdekat dengan LTD ≥ hari ini.
    - Harga: spot GBM harian (ACT/365,25); ``settle = S·exp((r − lease)·τ)``, τ = hari kalender
      menuju LTD / 365, dibulatkan ke tick → contango dengan carry ≈ r − lease.
    - OI: pangsa per peringkat kontrak pra-notice ``[0,62, 0,16, 0,07, 0,05, 0,04, 0,03, ...]``;
      selama roll, fraksi ρ(n) = 1/(1+exp((n − roll_center_bd)/roll_width_bd)) (n = hari kerja
      menuju FND kontrak depan) berpindah ke kontrak berikutnya. Setelah FND, sisa OI kecil
      (periode pengiriman) menurun linear ke 0 pada LTD.
    - Volume: pola serupa tetapi roll volume mendahului OI (pusat 8 hari kerja).
    Kolom: ``trade_date, symbol, instrument_id, open, high, low, close, settle, volume,
    open_interest`` (diurutkan menurut tanggal lalu jatuh tempo).
    """
    d0, d1 = _to_date(start), _to_date(end)
    if d1 < d0:
        raise ValueError("end harus ≥ start")
    days: list[_dt.date] = []
    d = d0
    while d <= d1:
        if core.is_business_day(d):
            days.append(d)
        d += _dt.timedelta(days=1)
    cols = ["trade_date", "symbol", "instrument_id", "open", "high", "low", "close", "settle",
            "volume", "open_interest"]
    if not days:
        return pd.DataFrame({c: [] for c in cols})

    ss = np.random.SeedSequence(seed)
    s_spot, s_intra, s_oi, s_vol, s_tot = ss.spawn(5)
    nd = len(days)
    # Spot GBM pada waktu kalender antar hari kerja.
    gaps = np.array([0] + [(days[i] - days[i - 1]).days for i in range(1, nd)], dtype=float) / 365.25
    eps = np.random.Generator(np.random.PCG64(s_spot)).standard_normal(nd)
    eps[0] = 0.0
    logS = math.log(spot0) + np.cumsum(-0.5 * vol * vol * gaps + vol * np.sqrt(gaps) * eps)
    spot = np.exp(logS)
    # Guncangan intrahari bersama (semua kontrak emas bergerak bersama).
    # Satu matriks (hari × komponen) per aliran agar prefiks-stabil terhadap panjang periode.
    sig_d = vol / math.sqrt(252.0)
    intra = np.random.Generator(np.random.PCG64(s_intra)).standard_normal((nd, 4))
    o_shock = 0.3 * sig_d * intra[:, 0]
    c_shock = 0.1 * sig_d * intra[:, 1]
    h_ext = np.abs(0.5 * sig_d * intra[:, 2])
    l_ext = np.abs(0.5 * sig_d * intra[:, 3])
    r_oi = np.random.Generator(np.random.PCG64(s_oi))
    r_vo = np.random.Generator(np.random.PCG64(s_vol))
    tot = np.random.Generator(np.random.PCG64(s_tot)).standard_normal((nd, 2))
    tot_oi = total_oi * np.exp(np.cumsum(0.01 * tot[:, 0]) * 0.5)
    tot_v = total_volume * np.exp(0.25 * tot[:, 1])

    oi_share0 = [0.62, 0.16, 0.07, 0.05, 0.04, 0.03, 0.03, 0.02, 0.02, 0.02, 0.02, 0.02]
    v_share0 = [0.86, 0.09, 0.025, 0.012, 0.008, 0.005, 0.004, 0.003, 0.003, 0.003, 0.003, 0.003]
    carry = r - lease

    def n_bd_between(a: _dt.date, b: _dt.date) -> int:
        """Jumlah hari kerja dalam (a, b]."""
        cnt, x = 0, a
        while x < b:
            x += _dt.timedelta(days=1)
            if core.is_business_day(x):
                cnt += 1
        return cnt

    rows: list[tuple] = []
    for i, d in enumerate(days):
        listed = _active_after(d, n_contracts)
        pre = [(y, m) for (y, m) in listed if gc_first_notice_date(y, m) > d]
        dlv = [(y, m) for (y, m) in listed if gc_first_notice_date(y, m) <= d]
        n_fnd = n_bd_between(d, gc_first_notice_date(*pre[0]))
        rho = 1.0 / (1.0 + math.exp((n_fnd - roll_center_bd) / roll_width_bd))
        rho_v = 1.0 / (1.0 + math.exp((n_fnd - (roll_center_bd + 2.0)) / (roll_width_bd + 0.2)))
        shares: dict[tuple[int, int], tuple[float, float]] = {}
        for j, c in enumerate(pre):
            if j == 0:
                so = oi_share0[0] * (1.0 - rho)
                sv = v_share0[0] * (1.0 - rho_v)
            else:
                so = oi_share0[j] * (1.0 - rho) + oi_share0[j - 1] * rho
                sv = v_share0[j] * (1.0 - rho_v) + v_share0[j - 1] * rho_v
            shares[c] = (so, sv)
        for c in dlv:
            fnd, ltd = gc_first_notice_date(*c), gc_last_trade_date(*c)
            frac = n_bd_between(d, ltd) / max(1, n_bd_between(fnd, ltd))
            shares[c] = (0.004 * frac, 0.0008 * frac)
        S = spot[i]
        for (y, m) in listed:
            ltd = gc_last_trade_date(y, m)
            tau = (ltd - d).days / 365.0
            Fv = S * math.exp(carry * tau)
            settle = round(Fv / tick) * tick
            op = Fv * math.exp(o_shock[i])
            cl = Fv * math.exp(c_shock[i])
            hi = max(op, cl, Fv) * math.exp(h_ext[i])
            lo = min(op, cl, Fv) * math.exp(-l_ext[i])
            op_r, cl_r = round(op / tick) * tick, round(cl / tick) * tick
            hi_r = max(math.ceil(hi / tick - 1e-9) * tick, op_r, cl_r, settle)
            lo_r = min(math.floor(lo / tick + 1e-9) * tick, op_r, cl_r, settle)
            so, sv = shares[(y, m)]
            oi = int(round(tot_oi[i] * so * math.exp(0.02 * r_oi.standard_normal())))
            vv = int(round(tot_v[i] * sv * math.exp(0.3 * r_vo.standard_normal())))
            rows.append((d, core.futures_symbol(root, y, m, 1), int(f"{y}{m:02d}"),
                         round(op_r, 10), round(hi_r, 10), round(lo_r, 10), round(cl_r, 10),
                         round(settle, 10), max(vv, 0), max(oi, 0)))
    out = pd.DataFrame(rows, columns=cols)
    out["instrument_id"] = out["instrument_id"].astype(np.int64)
    out["volume"] = out["volume"].astype(np.int64)
    out["open_interest"] = out["open_interest"].astype(np.int64)
    out = out.sort_values(["trade_date", "instrument_id"], kind="stable").reset_index(drop=True)
    out.attrs.update({"synthetic": True, "r": r, "lease": lease, "carry": carry})
    return out
