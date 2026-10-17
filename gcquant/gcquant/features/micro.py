"""Fitur mikrostruktur pasar dari frame kanonik BBO / BOOK / TRADES / BARS.

Prinsip (SPEC §0.2): setiap nilai pada waktu t hanya memakai record dengan
``ts_recv <= t``; jendela bergulir selalu ke belakang (trailing); estimator yang
perlu "fit" (micro-price Stoikov) hanya di-fit pada data latih.

Konvensi output:
- Fungsi per-baris (``ofi_l1``, ``mlofi``, ``queue_imbalance``, ``trade_flow``,
  ``roll_spread``, ``amihud``) → indeks SAMA dengan input. Nilai baris i hanya
  bergantung pada baris ≤ i. Untuk BARS (dilabeli waktu BUKA) nilai baris baru
  diketahui pada ``ts + bar_len``.
- Fungsi ber-grid (``on_grid``, ``kyle_lambda``, ``realized_measures``,
  ``feature_matrix``) dan ``vpin`` → ``DatetimeIndex`` UTC bernama ``ts`` =
  waktu ketika nilai itu DIKETAHUI.

Referensi:
- Cont, Kukanov, Stoikov (2014) "The price impact of order book events" (OFI).
- Xu, Gould, Howison (2018) "Multi-level order-flow imbalance in a limit order book".
- Stoikov (2018) "The micro-price: a high-frequency estimator of future prices".
- Easley, López de Prado, O'Hara (2012) "Flow toxicity and liquidity in a
  high-frequency world" (VPIN, bulk volume classification).
- Kyle (1985); Barndorff-Nielsen & Shephard (2004) (bipower variation);
  Barndorff-Nielsen, Kinnebrock, Shephard (2010) (semivariance);
  Roll (1984); Amihud (2002).
"""
from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd
from scipy.special import ndtr

from ..book.l1 import bbo_from_book, l1_arrays, weighted_mid
from ..core import GcquantError

__all__ = [
    "ofi_l1", "mlofi", "queue_imbalance", "depth_imbalance", "microprice_weighted",
    "StoikovMicroprice", "trade_flow", "vpin", "kyle_lambda", "realized_measures",
    "roll_spread", "amihud", "on_grid", "make_grid", "feature_matrix", "trade_sign",
]


# ---------------------------------------------------------------------------
# Utilitas waktu & jendela
# ---------------------------------------------------------------------------

def _to_ns_array(x) -> np.ndarray:
    """Array/Series/DatetimeIndex waktu → int64 ns UTC (naif dianggap UTC)."""
    if isinstance(x, pd.Series):
        if isinstance(x.dtype, pd.DatetimeTZDtype) or x.dtype.kind == "M":
            return pd.DatetimeIndex(x).as_unit("ns").asi8.copy()
        return x.to_numpy(dtype=np.int64)
    if isinstance(x, pd.DatetimeIndex):
        return x.as_unit("ns").asi8.copy()
    if isinstance(x, pd.Index):
        if x.dtype.kind == "M" or isinstance(x.dtype, pd.DatetimeTZDtype):
            return pd.DatetimeIndex(x).as_unit("ns").asi8.copy()
        return x.to_numpy(dtype=np.int64)
    arr = np.asarray(x)
    if arr.dtype.kind == "M":
        return pd.DatetimeIndex(arr).as_unit("ns").asi8.copy()
    if arr.dtype.kind == "O":
        return pd.DatetimeIndex(pd.to_datetime(arr, utc=True)).as_unit("ns").asi8.copy()
    return arr.astype(np.int64)


def _ts_of(obj, ts=None) -> np.ndarray:
    """Waktu observasi (int64 ns) tiap baris: ``ts`` > kolom ``ts_recv`` > DatetimeIndex."""
    if ts is not None:
        out = _to_ns_array(ts)
        if len(out) != len(obj):
            raise GcquantError("Panjang ts tidak sama dengan panjang data")
        return out
    if isinstance(obj, pd.DataFrame) and "ts_recv" in obj.columns:
        return _to_ns_array(obj["ts_recv"])
    if isinstance(obj.index, pd.DatetimeIndex):
        return _to_ns_array(obj.index)
    raise GcquantError("Waktu tidak ditemukan: berikan ts=..., kolom ts_recv, atau DatetimeIndex")


def _ns(td) -> int:
    """Durasi (str/Timedelta/int ns) → int ns."""
    if isinstance(td, (int, np.integer)):
        return int(td)
    return int(pd.Timedelta(td).as_unit("ns").value)


def _require_sorted(ts: np.ndarray, what: str) -> None:
    if len(ts) > 1 and np.any(np.diff(ts) < 0):
        raise GcquantError(f"{what} harus terurut naik menurut waktu (ts_recv)")


def make_grid(start, end, freq) -> np.ndarray:
    """Grid waktu reguler int64 ns: kelipatan ``freq`` dari ceil(start) s/d floor(end)."""
    f = _ns(freq)
    if f <= 0:
        raise ValueError("freq harus positif")
    s = int(_to_ns_array([start])[0]) if not isinstance(start, (int, np.integer)) else int(start)
    e = int(_to_ns_array([end])[0]) if not isinstance(end, (int, np.integer)) else int(end)
    g0 = -(-s // f) * f
    g1 = (e // f) * f
    if g1 < g0:
        return np.empty(0, dtype=np.int64)
    return np.arange(g0, g1 + 1, f, dtype=np.int64)


def _grid_array(grid) -> np.ndarray:
    g = _to_ns_array(grid)
    if len(g) > 1 and np.any(np.diff(g) <= 0):
        raise GcquantError("grid harus naik tegas (strictly increasing)")
    return g


def _ts_index(g: np.ndarray) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(g, unit="ns", utc=True), name="ts").as_unit("ns")


def _window_lo(ts: np.ndarray | None, window, n: int) -> np.ndarray:
    """Indeks awal (inklusif) jendela trailing yang berakhir di baris i.

    ``window`` int → n baris terakhir; durasi → baris dengan ts ∈ (t_i − w, t_i].
    """
    if isinstance(window, (int, np.integer)) and not isinstance(window, bool):
        w = int(window)
        if w < 1:
            raise ValueError("window minimal 1")
        return np.maximum(np.arange(n, dtype=np.int64) - w + 1, 0)
    if ts is None:
        raise GcquantError("Jendela berbasis waktu memerlukan stempel waktu")
    w = _ns(window)
    if w <= 0:
        raise ValueError("window harus positif")
    _require_sorted(ts, "Data")
    return np.searchsorted(ts, ts - w, side="right").astype(np.int64)


def _csum0(x: np.ndarray) -> np.ndarray:
    out = np.zeros(len(x) + 1, dtype=np.float64)
    np.cumsum(x, out=out[1:])
    return out


def _wsum(x: np.ndarray, lo: np.ndarray) -> np.ndarray:
    """Σ x[lo_i .. i] untuk setiap i (lo inklusif)."""
    c = _csum0(x)
    return c[np.arange(1, len(x) + 1)] - c[lo]


def _shift_ref(x: np.ndarray) -> float:
    """Konstanta penggeser kausal (nilai valid pertama) untuk stabilitas numerik."""
    fin = np.flatnonzero(np.isfinite(x))
    return float(x[fin[0]]) if len(fin) else 0.0


def _prev_index(keys: np.ndarray | None, n: int, h: int = 1) -> np.ndarray:
    """Indeks baris ke-h sebelumnya dengan kunci (instrumen) sama; −1 bila tidak ada."""
    if keys is None:
        idx = np.arange(n, dtype=np.int64) - h
        idx[idx < 0] = -1
        return idx
    order = np.argsort(keys, kind="stable")
    k = keys[order]
    pos = np.arange(n, dtype=np.int64)
    # posisi dalam grup
    starts = np.r_[0, np.flatnonzero(k[1:] != k[:-1]) + 1]
    grp_start = np.repeat(starts, np.diff(np.r_[starts, n]))
    within = pos - grp_start
    prev_sorted = np.where(within >= h, pos - h, -1)
    out = np.full(n, -1, dtype=np.int64)
    ok = prev_sorted >= 0
    out[order[ok]] = order[prev_sorted[ok]]
    return out


def _next_index(keys: np.ndarray | None, n: int, h: int = 1) -> np.ndarray:
    """Indeks baris ke-h berikutnya dengan kunci sama; −1 bila tidak ada."""
    prev = _prev_index(keys, n, h)
    nxt = np.full(n, -1, dtype=np.int64)
    ok = prev >= 0
    nxt[prev[ok]] = np.flatnonzero(ok)
    return nxt


def _instrument_keys(df: pd.DataFrame) -> np.ndarray | None:
    if isinstance(df, pd.DataFrame) and "instrument_id" in df.columns:
        k = df["instrument_id"].to_numpy()
        if len(k) and (k != k[0]).any():
            return k.astype(np.int64)
    return None


def _single_instrument(df: pd.DataFrame | None, what: str) -> None:
    if df is not None and _instrument_keys(df) is not None:
        raise GcquantError(f"{what}: data berisi >1 instrument_id; saring ke satu instrumen dulu")


# ---------------------------------------------------------------------------
# OFI (Cont-Kukanov-Stoikov 2014) & MLOFI (Xu-Gould-Howison 2018)
# ---------------------------------------------------------------------------

def _ofi_core(bp, ap, bs, as_, prev) -> np.ndarray:
    """e_n = 1{Pb_n ≥ Pb_{n−1}} qb_n − 1{Pb_n ≤ Pb_{n−1}} qb_{n−1}
             − 1{Pa_n ≤ Pa_{n−1}} qa_n + 1{Pa_n ≥ Pa_{n−1}} qa_{n−1}.

    Sisi kosong: harga bid = −∞, harga ask = +∞, ukuran 0 (konvensi LOBSTER),
    sehingga hilangnya seluruh sisi tercatat sebagai −q_{n−1} (bid) / +q_{n−1} (ask).
    """
    bnan = ~np.isfinite(bp)
    anan = ~np.isfinite(ap)
    bpi = np.where(bnan, -np.inf, bp)
    api = np.where(anan, np.inf, ap)
    bs0 = np.where(bnan, 0.0, bs)
    as0 = np.where(anan, 0.0, as_)
    has = prev >= 0
    pp = np.where(has, prev, 0)
    bp1, ap1, bs1, as1 = bpi[pp], api[pp], bs0[pp], as0[pp]
    e = ((bpi >= bp1) * bs0 - (bpi <= bp1) * bs1
         - (api <= ap1) * as0 + (api >= ap1) * as1)
    e = e.astype(np.float64)
    e[~has] = np.nan
    return e


def ofi_l1(bbo: pd.DataFrame) -> pd.Series:
    """Order-flow imbalance per event e_n (Cont, Kukanov & Stoikov 2014).

    Input frame BBO atau BOOK (dipakai level 0). Baris pertama tiap instrumen
    = NaN (tidak ada keadaan sebelumnya). OFI suatu interval = Σ e_n di
    interval tsb (lihat ``on_grid(..., how="sum")``).
    """
    bp, ap, bs, as_ = l1_arrays(bbo)
    prev = _prev_index(_instrument_keys(bbo), len(bbo))
    return pd.Series(_ofi_core(bp, ap, bs, as_, prev), index=bbo.index, name="ofi")


def mlofi(book: pd.DataFrame, levels: int = 5) -> pd.DataFrame:
    """OFI multi-level (Xu, Gould & Howison 2018): rumus e_n yang sama pada
    harga/ukuran level ke-m (m = 1..levels). Kolom ``mlofi_1 .. mlofi_L``;
    ``mlofi_1`` identik dengan :func:`ofi_l1`. Level kosong diperlakukan
    seperti sisi kosong pada OFI (harga ±∞, ukuran 0).
    """
    levels = int(levels)
    prev = _prev_index(_instrument_keys(book), len(book))
    out = {}
    for m in range(levels):
        c = f"{m:02d}"
        need = [f"bid_px_{c}", f"ask_px_{c}", f"bid_sz_{c}", f"ask_sz_{c}"]
        if any(x not in book.columns for x in need):
            raise GcquantError(f"Frame BOOK tidak memiliki level {m} (kolom {need[0]})")
        bp = book[need[0]].to_numpy(dtype=np.float64, na_value=np.nan)
        ap = book[need[1]].to_numpy(dtype=np.float64, na_value=np.nan)
        bs = np.nan_to_num(book[need[2]].to_numpy(dtype=np.float64, na_value=np.nan))
        as_ = np.nan_to_num(book[need[3]].to_numpy(dtype=np.float64, na_value=np.nan))
        out[f"mlofi_{m + 1}"] = _ofi_core(bp, ap, bs, as_, prev)
    return pd.DataFrame(out, index=book.index)


# ---------------------------------------------------------------------------
# Imbalance & micro-price
# ---------------------------------------------------------------------------

def queue_imbalance(bbo: pd.DataFrame) -> pd.Series:
    """Imbalance antrean L1: (Qb − Qa) / (Qb + Qa) ∈ [−1, 1]; NaN bila Qb+Qa = 0."""
    _, _, bs, as_ = l1_arrays(bbo)
    tot = bs + as_
    with np.errstate(invalid="ignore", divide="ignore"):
        q = np.where(tot > 0, (bs - as_) / tot, np.nan)
    return pd.Series(q, index=bbo.index, name="queue_imbalance")


def depth_imbalance(book: pd.DataFrame, levels: int = 5) -> pd.Series:
    """Imbalance kedalaman L level: (ΣQb − ΣQa)/(ΣQb + ΣQa); NaN bila total 0."""
    db = np.zeros(len(book))
    da = np.zeros(len(book))
    for m in range(int(levels)):
        db += np.nan_to_num(book[f"bid_sz_{m:02d}"].to_numpy(dtype=np.float64, na_value=np.nan))
        da += np.nan_to_num(book[f"ask_sz_{m:02d}"].to_numpy(dtype=np.float64, na_value=np.nan))
    tot = db + da
    with np.errstate(invalid="ignore", divide="ignore"):
        q = np.where(tot > 0, (db - da) / tot, np.nan)
    return pd.Series(q, index=book.index, name=f"depth_imbalance_{int(levels)}")


def microprice_weighted(bbo: pd.DataFrame) -> pd.Series:
    """Weighted mid = I·Pa + (1−I)·Pb, I = Qb/(Qb+Qa) (lihat ``book.l1.weighted_mid``)."""
    return weighted_mid(bbo).rename("microprice_weighted")


class StoikovMicroprice:
    """Estimator micro-price Stoikov (2018): P_micro = mid + g*(I, S).

    Keadaan X = (I, S): imbalance I = Qb/(Qb+Qa) didiskretkan ke ``n_imb``
    ember dan spread S (dalam tick) ∈ {1..n_spread}. Dari data LATIH:

    - Q[x,y] = P(mid tidak berubah, X_next = y | X = x)   (transisi transien)
    - R[x,k] = P(mid berubah sebesar K_k | X = x),  K = {−1, −½, ½, 1}·tick
    - T[x,y] = P(mid berubah, X_next = y | X = x)
    - G1 = (I − Q)⁻¹ R K,   B = (I − Q)⁻¹ T,   g* = Σ_{k≥0} B^k G1
      (diiterasi sampai konvergen).

    Data disimetrikan seperti di makalah: setiap transisi (x → y, ΔM) juga
    ditambahkan sebagai (flip x → flip y, −ΔM) dengan flip membalik ember
    imbalance (b → n_imb−1−b), sehingga g*(flip x) = −g*(x) dan deret konvergen.
    "Langkah" = ``horizon_events`` baris BBO ke depan (``dt`` pada kode Stoikov).
    Transisi yang keadaan awal/akhirnya di luar ruang keadaan, atau
    |ΔM| > ``max_move_ticks``, dibuang.

    ``bins="uniform"`` (bawaan) → ember lebar sama pada [0,1] (simetris, tidak
    bergantung data); ``"quantile"`` → batas kuantil dari imbalance latih yang
    disimetrikan (setara ``pd.qcut`` di kode asli Stoikov).
    Prediksi pada I tepat di batas ember memakai rata-rata ember kiri/kanan
    agar antisimetri g*(1−I) = −g*(I) tetap persis.
    """

    def __init__(self, n_imb: int = 10, n_spread: int = 2, *, tick_size: float | None = None,
                 bins: str = "uniform", max_move_ticks: float = 1.0, symmetrize: bool = True,
                 tol: float = 1e-12, max_iter: int = 100_000) -> None:
        if n_imb < 2 or n_spread < 1:
            raise ValueError("n_imb ≥ 2 dan n_spread ≥ 1")
        if bins not in ("uniform", "quantile"):
            raise ValueError("bins harus 'uniform' atau 'quantile'")
        self.n_imb = int(n_imb)
        self.n_spread = int(n_spread)
        self.tick_size = tick_size
        self.bins = bins
        self.max_move_ticks = float(max_move_ticks)
        self.symmetrize = symmetrize
        self.tol = tol
        self.max_iter = int(max_iter)
        self.fitted_ = False

    # -- keadaan ---------------------------------------------------------------
    def _bucket(self, imb: np.ndarray) -> np.ndarray:
        n = self.n_imb
        x = np.nan_to_num(imb, nan=0.0)
        if self.bins == "uniform":
            b = np.floor(x * n).astype(np.int64)
        else:
            b = np.searchsorted(self.imb_edges_, x, side="right").astype(np.int64)
        return np.clip(b, 0, n - 1)

    def _states(self, df: pd.DataFrame, tick: float):
        bp, ap, bs, as_ = l1_arrays(df)
        midv = (bp + ap) / 2.0
        tot = bs + as_
        with np.errstate(invalid="ignore", divide="ignore"):
            imb = bs / tot
            s_ticks = np.rint((ap - bp) / tick)
        valid = (np.isfinite(bp) & np.isfinite(ap) & (tot > 0)
                 & (s_ticks >= 1) & (s_ticks <= self.n_spread))
        s_idx = np.where(valid, np.nan_to_num(s_ticks, nan=1.0) - 1, 0).astype(np.int64)
        return midv, imb, s_idx, valid

    # -- fit -------------------------------------------------------------------
    def fit(self, bbo_train: pd.DataFrame, horizon_events: int = 1) -> "StoikovMicroprice":
        """Estimasi Q, R, T, G1, B, g* dari data latih (hanya data ini yang dipakai)."""
        h = int(horizon_events)
        if h < 1:
            raise ValueError("horizon_events minimal 1")
        n = len(bbo_train)
        bp, ap, _, _ = l1_arrays(bbo_train)
        if self.tick_size is None:
            spr = ap - bp
            pos = spr[np.isfinite(spr) & (spr > 1e-12)]
            if not len(pos):
                raise GcquantError("Tidak bisa menebak tick_size: tidak ada spread positif")
            tick = float(np.round(pos.min(), 9))
        else:
            tick = float(self.tick_size)
        self.tick_size_ = tick
        ni, ns = self.n_imb, self.n_spread
        midv, imb, s_idx, valid = self._states(bbo_train, tick)
        if self.bins == "quantile":
            iv = imb[valid]
            sample = np.concatenate([iv, 1.0 - iv]) if self.symmetrize else iv
            if not len(sample):
                raise GcquantError("Tidak ada keadaan valid pada data latih")
            self.imb_edges_ = np.quantile(sample, np.linspace(0, 1, ni + 1)[1:-1])
        b = self._bucket(imb)
        state = np.where(valid, s_idx * ni + b, -1)

        nxt = _next_index(_instrument_keys(bbo_train), n, h)
        ok = (state >= 0) & (nxt >= 0)
        nx = np.where(ok, nxt, 0)
        ok &= state[nx] >= 0
        with np.errstate(invalid="ignore"):
            d_half = np.rint((midv[nx] - midv) / tick * 2.0)
        maxh = int(round(self.max_move_ticks * 2))
        ok &= np.isfinite(d_half) & (np.abs(np.nan_to_num(d_half)) <= maxh)
        x = state[ok]
        y = state[nx][ok]
        d = d_half[ok].astype(np.int64)

        nS = ns * ni
        k_half = np.array([k for k in range(-maxh, maxh + 1) if k != 0], dtype=np.int64)
        nK = len(k_half)
        Qc = np.zeros((nS, nS))
        Rc = np.zeros((nS, nK))
        Tc = np.zeros((nS, nS))
        mv = d != 0
        np.add.at(Qc, (x[~mv], y[~mv]), 1.0)
        kidx = np.where(d < 0, d + maxh, d + maxh - 1)
        np.add.at(Rc, (x[mv], kidx[mv]), 1.0)
        np.add.at(Tc, (x[mv], y[mv]), 1.0)
        flip = (np.arange(nS) // ni) * ni + (ni - 1 - np.arange(nS) % ni)
        self.flip_ = flip
        if self.symmetrize:
            Qc = Qc + Qc[np.ix_(flip, flip)]
            Rc = Rc + Rc[flip][:, ::-1]          # K simetris → kolom dibalik = −ΔM
            Tc = Tc + Tc[np.ix_(flip, flip)]
        tot = Qc.sum(axis=1) + Rc.sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            inv = np.where(tot > 0, 1.0 / tot, 0.0)
        Q = Qc * inv[:, None]
        R = Rc * inv[:, None]
        T = Tc * inv[:, None]
        K = k_half * (tick / 2.0)
        A = np.eye(nS) - Q
        try:
            G1 = np.linalg.solve(A, R @ K)
            B = np.linalg.solve(A, T)
        except np.linalg.LinAlgError:
            warnings.warn("I − Q singular (ada keadaan yang tak pernah keluar); memakai pseudo-inverse",
                          RuntimeWarning, stacklevel=2)
            Ai = np.linalg.pinv(A)
            G1 = Ai @ (R @ K)
            B = Ai @ T
        G = G1.copy()
        term = G1.copy()
        converged = False
        it = 0
        for it in range(1, self.max_iter + 1):
            term = B @ term
            G += term
            if np.max(np.abs(term)) <= self.tol * tick:
                converged = True
                break
        if not converged:
            warnings.warn("Deret g* = Σ B^k G1 belum konvergen; hasil parsial dipakai",
                          RuntimeWarning, stacklevel=2)
        self.Q_, self.R_, self.T_, self.K_ = Q, R, T, K
        self.G1_, self.B_ = G1, B
        self.G_star_ = G.reshape(ns, ni)
        self.counts_ = tot.reshape(ns, ni)
        self.n_transitions_ = int(ok.sum())
        self.n_iter_ = it
        self.converged_ = converged
        self.horizon_events_ = h
        self.fitted_ = True
        return self

    # -- prediksi --------------------------------------------------------------
    def adjustment(self, bbo: pd.DataFrame) -> pd.Series:
        """g*(I, S) untuk tiap baris (USD); NaN bila keadaan di luar ruang keadaan."""
        if not self.fitted_:
            raise GcquantError("StoikovMicroprice belum di-fit")
        _, imb, s_idx, valid = self._states(bbo, self.tick_size_)
        G = self.G_star_
        b1 = self._bucket(imb)
        if self.symmetrize:
            b2 = self.n_imb - 1 - self._bucket(1.0 - imb)
            g = 0.5 * (G[s_idx, b1] + G[s_idx, b2])
        else:
            g = G[s_idx, b1]
        g = np.where(valid, g, np.nan)
        return pd.Series(g, index=bbo.index, name="microprice_adj")

    def predict(self, bbo: pd.DataFrame) -> pd.Series:
        """Micro-price Stoikov = mid + g*(I, S) per baris (tanpa melihat masa depan)."""
        bp, ap, _, _ = l1_arrays(bbo)
        adj = self.adjustment(bbo).to_numpy()
        return pd.Series((bp + ap) / 2.0 + adj, index=bbo.index, name="microprice_stoikov")


# ---------------------------------------------------------------------------
# Aliran trade
# ---------------------------------------------------------------------------

def trade_sign(trades: pd.DataFrame | pd.Series) -> np.ndarray:
    """Tanda agresor: 'B' → +1, 'A' → −1, lainnya ('N') → 0. Kolom numerik dipakai apa adanya."""
    s = trades["side"] if isinstance(trades, pd.DataFrame) else trades
    if s.dtype.kind in "iuf":
        return np.sign(s.to_numpy(dtype=np.float64, na_value=0.0))
    v = s.astype(object).to_numpy()
    return np.where(v == "B", 1.0, np.where(v == "A", -1.0, 0.0))


def _trade_flow_one(ts, sign, size, window) -> dict[str, np.ndarray]:
    n = len(size)
    lo = _window_lo(ts, window, n)
    sv = _wsum(sign * size, lo)
    vol = _wsum(size, lo)
    buy = _wsum(size * (sign > 0), lo)
    sell = _wsum(size * (sign < 0), lo)
    cnt = _wsum(np.ones(n), lo)
    # pasangan (s_{j−1}, s_j) untuk j ∈ [lo+1, i]
    xs = np.r_[0.0, sign[:-1]] if n else np.zeros(0)
    ys = sign.copy()
    if n:
        ys[0] = 0.0
    lo_p = lo + 1                                   # lo ≤ i → lo_p ≤ i+1
    cx, cy = _csum0(xs), _csum0(ys)
    cxx, cyy, cxy = _csum0(xs * xs), _csum0(ys * ys), _csum0(xs * ys)
    hi = np.arange(1, n + 1)
    m = (hi - lo_p).astype(np.float64)
    sx, sy = cx[hi] - cx[lo_p], cy[hi] - cy[lo_p]
    sxx, syy, sxy = cxx[hi] - cxx[lo_p], cyy[hi] - cyy[lo_p], cxy[hi] - cxy[lo_p]
    with np.errstate(invalid="ignore", divide="ignore"):
        num = m * sxy - sx * sy
        den = np.sqrt((m * sxx - sx * sx) * (m * syy - sy * sy))
        ac = np.where((m >= 2) & (den > 1e-12), num / den, np.nan)
        ratio = np.where(buy + sell > 0, buy / (buy + sell), np.nan)
    return {"signed_volume": sv, "volume": vol, "buy_volume": buy, "sell_volume": sell,
            "n_trades": cnt, "aggressor_ratio": ratio, "sign_autocorr": ac}


def trade_flow(trades: pd.DataFrame, window="1min") -> pd.DataFrame:
    """Statistik aliran trade pada jendela trailing yang berakhir di tiap trade.

    ``window``: durasi (mis. ``"30s"``) → trade dengan ts ∈ (t_i − w, t_i];
    int → n trade terakhir. Kolom: ``ts_recv``, ``signed_volume`` (Σ tanda·ukuran),
    ``volume``, ``buy_volume``, ``sell_volume``, ``n_trades``,
    ``aggressor_ratio`` = beli/(beli+jual) (trade 'N' tidak dihitung),
    ``sign_autocorr`` = korelasi Pearson lag-1 pasangan tanda (s_{j−1}, s_j)
    yang keduanya di dalam jendela (NaN bila < 2 pasangan atau varians 0).
    Hanya memakai trade ≤ baris i (urutan feed). Multi-instrumen dihitung per instrumen.
    """
    n = len(trades)
    ts = _ts_of(trades)
    sign = trade_sign(trades)
    size = np.nan_to_num(trades["size"].to_numpy(dtype=np.float64, na_value=np.nan))
    keys = _instrument_keys(trades)
    cols = ["signed_volume", "volume", "buy_volume", "sell_volume", "n_trades",
            "aggressor_ratio", "sign_autocorr"]
    res = {c: np.full(n, np.nan) for c in cols}
    groups = [np.arange(n)] if keys is None else [np.flatnonzero(keys == k) for k in pd.unique(keys)]
    for g in groups:
        r = _trade_flow_one(ts[g], sign[g], size[g], window)
        for c in cols:
            res[c][g] = r[c]
    out = pd.DataFrame({"ts_recv": ts, **res}, index=trades.index)
    out["n_trades"] = out["n_trades"].astype(np.int64)
    return out


# ---------------------------------------------------------------------------
# VPIN
# ---------------------------------------------------------------------------

def vpin(trades: pd.DataFrame, bucket_volume: float, n_buckets: int = 50,
         method: str = "aggressor", *, bvc_bar="1min", sigma_window: int | None = None,
         min_sigma_bars: int = 20) -> pd.DataFrame:
    """VPIN (Easley, López de Prado & O'Hara 2012) pada ember volume berukuran V.

    Volume dialirkan berurutan ke ember berukuran tepat ``bucket_volume``; trade
    (atau bar) yang melewati batas ember dipecah proporsional.
    ``VPIN_τ = Σ_{j=τ−n+1..τ} |V^B_j − V^S_j| / (n·V)``.

    method:
      - ``"aggressor"``: klasifikasi eksak dari sisi agresor ('B' beli, 'A'
        jual, 'N' dibagi 50/50). Ember selesai pada ``ts_recv`` trade yang
        mengisinya.
      - ``"bvc"``: bulk volume classification — trade diagregasi ke bar waktu
        ``bvc_bar``; ``V^B = V · Φ(ΔP/σ_ΔP)`` dengan ΔP = perubahan close antar
        bar (non-kosong) berurutan dan σ_ΔP simpangan baku TRAILING ΔP
        (``sigma_window`` bar terakhir, None = ekspansif, minimal
        ``min_sigma_bars``; makalah memakai σ seluruh sampel — itu look-ahead,
        di sini kausal). Ember selesai pada waktu TUTUP bar (open + bvc_bar),
        saat klasifikasi bar diketahui. Volume yang belum bisa diklasifikasi
        (σ belum tersedia) membuat embernya NaN.

    Kembalian: DataFrame ber-indeks ``ts`` (waktu ember selesai, UTC) dengan
    kolom ``ts_recv`` (int64 ns), ``bucket`` (1..), ``buy_volume``,
    ``sell_volume``, ``imbalance`` = |V^B − V^S|, ``vpin``.
    """
    _single_instrument(trades, "vpin")
    V = float(bucket_volume)
    if V <= 0:
        raise ValueError("bucket_volume harus positif")
    n_buckets = int(n_buckets)
    ts = _ts_of(trades)
    _require_sorted(ts, "Trades")
    size = np.nan_to_num(trades["size"].to_numpy(dtype=np.float64, na_value=np.nan))
    if method == "aggressor":
        sgn = trade_sign(trades)
        frac = np.where(sgn > 0, 1.0, np.where(sgn < 0, 0.0, 0.5))
        uvol, ufrac, utime = size, frac, ts
    elif method == "bvc":
        f = _ns(bvc_bar)
        px = trades["price"].to_numpy(dtype=np.float64, na_value=np.nan)
        keep = (size > 0) & np.isfinite(px)
        tsk, szk, pxk = ts[keep], size[keep], px[keep]
        if len(tsk) == 0:
            uvol = ufrac = np.zeros(0)
            utime = np.zeros(0, dtype=np.int64)
        else:
            bar = tsk // f
            starts = np.r_[0, np.flatnonzero(bar[1:] != bar[:-1]) + 1]
            ends = np.r_[starts[1:] - 1, len(bar) - 1]
            uvol = np.add.reduceat(szk, starts)
            close = pxk[ends]
            dP = np.r_[np.nan, np.diff(close)]
            s = pd.Series(dP)
            roll = s.expanding(min_periods=min_sigma_bars) if sigma_window is None else \
                s.rolling(int(sigma_window), min_periods=min_sigma_bars)
            sig = roll.std(ddof=1).to_numpy()
            with np.errstate(invalid="ignore", divide="ignore"):
                z = dP / sig
            ufrac = np.where(np.isfinite(z) & (sig > 0), ndtr(z), np.nan)
            utime = (bar[starts] + 1) * f
    else:
        raise ValueError("method harus 'aggressor' atau 'bvc'")

    nz = uvol > 0
    uvol, ufrac, utime = uvol[nz], ufrac[nz], utime[nz]
    unk = ~np.isfinite(ufrac)
    cv = np.cumsum(uvol)
    cb = np.cumsum(uvol * np.where(unk, 0.0, ufrac))
    cu = np.cumsum(uvol * unk)
    total = cv[-1] if len(cv) else 0.0
    nb = int(math.floor(total / V + 1e-9))
    bounds = V * np.arange(1, nb + 1, dtype=np.float64)
    xp = np.r_[0.0, cv]
    bcum = np.interp(bounds, xp, np.r_[0.0, cb])
    ucum = np.interp(bounds, xp, np.r_[0.0, cu])
    buy = np.diff(np.r_[0.0, bcum])
    unk_v = np.diff(np.r_[0.0, ucum])
    buy = np.where(unk_v > 1e-9 * V, np.nan, buy)
    sell = V - buy
    done = np.searchsorted(cv, bounds - 1e-9 * V, side="left")
    tdone = utime[np.minimum(done, max(len(utime) - 1, 0))] if nb else np.zeros(0, dtype=np.int64)
    imbal = np.abs(buy - sell)
    vp = pd.Series(imbal).rolling(n_buckets, min_periods=n_buckets).sum().to_numpy() / (n_buckets * V)
    out = pd.DataFrame({"ts_recv": tdone.astype(np.int64), "bucket": np.arange(1, nb + 1),
                        "buy_volume": buy, "sell_volume": sell, "imbalance": imbal, "vpin": vp},
                       index=_ts_index(tdone.astype(np.int64)))
    return out


# ---------------------------------------------------------------------------
# Kyle lambda, ukuran realisasi, Roll, Amihud
# ---------------------------------------------------------------------------

def _asof(ts: np.ndarray, values: np.ndarray, grid: np.ndarray, max_age: int | None = None):
    pos = np.searchsorted(ts, grid, side="right") - 1
    ok = pos >= 0
    out = np.full(len(grid), np.nan)
    out[ok] = values[pos[ok]]
    if max_age is not None:
        stale = ok & (grid - ts[np.maximum(pos, 0)] > max_age)
        out[stale] = np.nan
    return out


def _interval_sum(ts: np.ndarray, values: np.ndarray, grid: np.ndarray) -> np.ndarray:
    """Σ values dengan ts ∈ (g_{k−1}, g_k] (interval pertama: ts ≤ g_0)."""
    c = _csum0(np.nan_to_num(values))
    pos = np.searchsorted(ts, grid, side="right")
    tot = c[pos]
    return np.diff(np.r_[0.0, tot])


def _rolling_ols(x: np.ndarray, y: np.ndarray, lo: np.ndarray, min_periods: int):
    """Slope & intercept OLS y = a + b x pada jendela [lo_i, i] (pasangan non-NaN)."""
    ok = np.isfinite(x) & np.isfinite(y)
    x0 = _shift_ref(np.where(ok, x, np.nan))
    y0 = _shift_ref(np.where(ok, y, np.nan))
    xs = np.where(ok, x - x0, 0.0)
    ys = np.where(ok, y - y0, 0.0)
    n = _wsum(ok.astype(np.float64), lo)
    sx, sy = _wsum(xs, lo), _wsum(ys, lo)
    sxx, sxy = _wsum(xs * xs, lo), _wsum(xs * ys, lo)
    with np.errstate(invalid="ignore", divide="ignore"):
        den = n * sxx - sx * sx
        b = (n * sxy - sx * sy) / den
        a = (sy - b * sx) / n + y0 - b * x0
    bad = (n < max(min_periods, 2)) | ~(np.abs(den) > 1e-12 * np.maximum(n * sxx, 1e-300))
    b = np.where(bad, np.nan, b)
    a = np.where(bad, np.nan, a)
    return b, a, n


def kyle_lambda(bbo: pd.DataFrame, trades: pd.DataFrame, window=30, interval="1min",
                min_periods: int | None = None) -> pd.Series:
    """λ Kyle: slope OLS bergulir ΔMid_k = α + λ·SV_k + ε pada interval ``interval``.

    Grid g_k = kelipatan ``interval``; ΔMid_k = mid(g_k) − mid(g_{k−1}) dengan
    mid as-of (BBO terakhir ber-ts_recv ≤ g); SV_k = Σ tanda·ukuran trade dengan
    ts ∈ (g_{k−1}, g_k]. Regresi memakai ``window`` interval terakhir (int, atau
    durasi yang dibagi ``interval``); ``min_periods`` bawaan = window.
    Hasil (USD per kontrak bertanda) ber-indeks ``ts`` = akhir interval.
    """
    _single_instrument(bbo, "kyle_lambda")
    _single_instrument(trades, "kyle_lambda")
    f = _ns(interval)
    if isinstance(window, (int, np.integer)):
        w = int(window)
    else:
        w = max(int(_ns(window) // f), 1)
    mp = w if min_periods is None else int(min_periods)
    tq = _ts_of(bbo)
    tt = _ts_of(trades)
    _require_sorted(tq, "BBO")
    _require_sorted(tt, "Trades")
    bp, ap, _, _ = l1_arrays(bbo)
    midv = (bp + ap) / 2.0
    fin = np.isfinite(midv)
    tq_f, mid_f = tq[fin], midv[fin]
    if not len(tq_f) and not len(tt):
        return pd.Series([], dtype=float, name="kyle_lambda", index=_ts_index(np.zeros(0, np.int64)))
    lo_t = min(tq_f[0] if len(tq_f) else tt[0], tt[0] if len(tt) else tq_f[0])
    hi_t = max(tq_f[-1] if len(tq_f) else tt[-1], tt[-1] if len(tt) else tq_f[-1])
    grid = make_grid(int(lo_t), int(hi_t), f)
    mg = _asof(tq_f, mid_f, grid)
    dmid = np.r_[np.nan, np.diff(mg)]
    sv = trade_sign(trades) * np.nan_to_num(trades["size"].to_numpy(dtype=np.float64, na_value=np.nan))
    svg = _interval_sum(tt, sv, grid)
    svg[0] = np.nan                            # interval pertama tidak lengkap
    lo = _window_lo(None, w, len(grid))
    b, _, _ = _rolling_ols(svg, dmid, lo, mp)
    return pd.Series(b, index=_ts_index(grid), name="kyle_lambda")


def _price_and_known_time(x, bar_len=None):
    """Harga & waktu-diketahui dari BARS / BBO / BOOK / Series."""
    if isinstance(x, pd.DataFrame):
        if "close" in x.columns:
            if not isinstance(x.index, pd.DatetimeIndex):
                raise GcquantError("BARS harus ber-indeks DatetimeIndex (waktu buka bar)")
            t = _to_ns_array(x.index)
            if bar_len is None:
                d = np.diff(t)
                d = d[d > 0]
                if not len(d):
                    raise GcquantError("Tidak bisa menebak bar_len; berikan bar_len=...")
                bl = int(np.median(d))
            else:
                bl = _ns(bar_len)
            return x["close"].to_numpy(dtype=np.float64, na_value=np.nan), t + bl
        bp, ap, _, _ = l1_arrays(x)
        return (bp + ap) / 2.0, _ts_of(x)
    if isinstance(x, pd.Series):
        return x.to_numpy(dtype=np.float64, na_value=np.nan), _ts_of(x)
    raise GcquantError("Input harus BARS, BBO/BOOK, atau Series harga")


def realized_measures(bars_or_mid, rule="5min", window="1D", *, bar_len=None) -> pd.DataFrame:
    """Ukuran volatilitas realisasi dari return log ber-sampel ``rule``.

    Harga disampel kausal pada grid kelipatan ``rule`` (harga terakhir yang
    sudah diketahui; untuk BARS close diketahui pada open + bar_len). Return
    r_k = ln(P_k / P_{k−1}). Pada jendela trailing ``window`` (durasi atau
    jumlah return):

    - ``rv``   = Σ r²
    - ``bv``   = (π/2) Σ |r_j||r_{j−1}|  (pasangan yang keduanya di jendela)
    - ``jump`` = max(rv − bv, 0)
    - ``rs_pos`` = Σ r² 1{r>0},  ``rs_neg`` = Σ r² 1{r<0}
    - ``n`` = jumlah return valid; ``ret`` = return interval itu sendiri.

    Indeks ``ts`` = akhir interval (waktu diketahui).
    """
    price, known = _price_and_known_time(bars_or_mid, bar_len)
    ok = np.isfinite(price) & (price > 0)
    price, known = price[ok], known[ok]
    if len(known) > 1 and np.any(np.diff(known) < 0):
        o = np.argsort(known, kind="stable")
        price, known = price[o], known[o]
    if not len(known):
        return pd.DataFrame(columns=["ret", "rv", "bv", "jump", "rs_pos", "rs_neg", "n"],
                            index=_ts_index(np.zeros(0, np.int64)))
    grid = make_grid(int(known[0]), int(known[-1]), rule)
    pg = _asof(known, price, grid)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.r_[np.nan, np.diff(np.log(pg))]
    valid = np.isfinite(r)
    r0 = np.where(valid, r, 0.0)
    lo = _window_lo(grid, window, len(grid))
    rv = _wsum(r0 * r0, lo)
    rsp = _wsum(np.where(r0 > 0, r0 * r0, 0.0), lo)
    rsn = _wsum(np.where(r0 < 0, r0 * r0, 0.0), lo)
    nn = _wsum(valid.astype(np.float64), lo)
    pair = np.r_[0.0, np.abs(r0[1:]) * np.abs(r0[:-1])]       # pasangan (j−1, j) di indeks j
    lo_p = lo + 1                                            # pasangan j ∈ [lo+1, i]
    cp = _csum0(pair)
    bv = (math.pi / 2.0) * (cp[np.arange(1, len(grid) + 1)] - cp[lo_p])
    out = pd.DataFrame({"ret": r, "rv": rv, "bv": bv, "jump": np.maximum(rv - bv, 0.0),
                        "rs_pos": rsp, "rs_neg": rsn, "n": nn.astype(np.int64)},
                       index=_ts_index(grid))
    return out


def roll_spread(prices, window=100) -> pd.Series:
    """Spread efektif Roll (1984): s = 2·√(−Cov(Δp_t, Δp_{t−1})), NaN bila Cov ≥ 0.

    ``prices``: Series harga, frame TRADES (kolom ``price``) atau BARS
    (``close``). Jendela trailing ``window`` (jumlah baris, atau durasi bila
    ada waktu) berisi baris [lo, i]; kovarians sampel (penyebut n−1) atas
    pasangan perubahan harga berurutan yang seluruhnya di dalam jendela.
    """
    if isinstance(prices, pd.DataFrame):
        col = "price" if "price" in prices.columns else "close"
        p = prices[col].to_numpy(dtype=np.float64, na_value=np.nan)
    else:
        p = prices.to_numpy(dtype=np.float64, na_value=np.nan)
    n = len(p)
    ts = None
    if not isinstance(window, (int, np.integer)):
        ts = _ts_of(prices)
    lo = _window_lo(ts, window, n)
    dp = np.r_[np.nan, np.diff(p)] if n else np.zeros(0)
    x = np.r_[np.nan, dp[:-1]] if n else np.zeros(0)     # Δp_{j−1} di indeks j
    y = dp
    ok = np.isfinite(x) & np.isfinite(y)
    x0 = _shift_ref(np.where(ok, x, np.nan))
    y0 = _shift_ref(np.where(ok, y, np.nan))
    xs, ys = np.where(ok, x - x0, 0.0), np.where(ok, y - y0, 0.0)
    lo_p = np.minimum(lo + 2, np.arange(n) + 1)          # pasangan j ∈ [lo+2, i]
    hi = np.arange(1, n + 1)

    def ws(a):
        c = _csum0(a)
        return c[hi] - c[lo_p]

    m = ws(ok.astype(np.float64))
    sx, sy, sxy = ws(xs), ws(ys), ws(xs * ys)
    with np.errstate(invalid="ignore", divide="ignore"):
        cov = (sxy - sx * sy / m) / (m - 1)
        s = np.where((m >= 2) & (cov < 0), 2.0 * np.sqrt(-cov), np.nan)
    idx = prices.index
    return pd.Series(s, index=idx, name="roll_spread")


def amihud(bars: pd.DataFrame, window=20, multiplier: float = 1.0, min_periods: int = 1) -> pd.Series:
    """Ilikuiditas Amihud (2002): rata-rata trailing |r_t| / DVOL_t.

    r_t = close_t/close_{t−1} − 1, DVOL_t = volume_t · close_t · ``multiplier``
    (mis. ``SPECS['GC'].multiplier`` untuk nilai nosional USD). Bar ber-DVOL 0
    dilewati. ``window`` jumlah bar atau durasi. Sejajar baris input (BARS:
    nilai diketahui pada open + bar_len).
    """
    c = bars["close"].astype(float)
    r = c / c.shift(1) - 1.0
    dvol = bars["volume"].astype(float) * c * float(multiplier)
    il = (r.abs() / dvol).where(dvol > 0)
    if isinstance(window, (int, np.integer)):
        out = il.rolling(int(window), min_periods=min_periods).mean()
    else:
        out = il.rolling(pd.Timedelta(window), min_periods=min_periods).mean()
    return out.rename("amihud")


# ---------------------------------------------------------------------------
# Penjajaran grid kausal & bundel fitur
# ---------------------------------------------------------------------------

def on_grid(x, grid_ns, how: str = "last", *, ts=None, max_age=None):
    """Penjajaran as-of KAUSAL ke grid waktu.

    ``how="last"``: nilai di g = baris terakhir dengan ts ≤ g (``max_age``
    opsional → NaN bila baris itu lebih tua dari max_age). ``how`` agregasi
    (``"sum"``, ``"count"``, ``"mean"``, ``"max"``, ``"min"``, ``"first"``):
    atas baris dengan ts ∈ (g_{k−1}, g_k] (interval pertama: ts ≤ g_0);
    sum/count interval kosong = 0, lainnya NaN.

    Waktu baris: argumen ``ts`` > kolom ``ts_recv`` > DatetimeIndex. Untuk BARS
    (dilabeli waktu buka) berikan ``ts=bars.index + bar_len``.
    Kembalian ber-indeks ``ts`` (DatetimeIndex UTC).
    """
    g = _grid_array(grid_ns)
    t = _ts_of(x, ts)
    is_series = isinstance(x, pd.Series)
    frame = x.to_frame() if is_series else x
    if len(t) > 1 and np.any(np.diff(t) < 0):
        o = np.argsort(t, kind="stable")
        t = t[o]
        frame = frame.iloc[o]
    idx = _ts_index(g)
    if how == "last" and len(frame) == 0:
        out = pd.DataFrame(np.nan, index=idx, columns=frame.columns)
    elif how == "last":
        pos = np.searchsorted(t, g, side="right") - 1
        ok = pos >= 0
        if max_age is not None:
            ok &= (g - t[np.maximum(pos, 0)]) <= _ns(max_age)
        take = frame.iloc[np.maximum(pos, 0)].reset_index(drop=True)
        take.index = idx
        if not ok.all():
            take = take.astype({c: "float64" for c in take.columns
                                if take[c].dtype.kind in "iub"})
            take.loc[~ok, :] = np.nan
        out = take
    elif how in ("sum", "count", "mean", "max", "min", "first"):
        num = frame.select_dtypes(include=[np.number, "bool"])
        lab = np.searchsorted(g, t, side="left")          # ts ∈ (g_{k−1}, g_k] → k
        keep = lab < len(g)
        grp = num[keep].groupby(lab[keep])
        agg = getattr(grp, how)()
        agg = agg.reindex(np.arange(len(g)))
        if how in ("sum", "count"):
            agg = agg.fillna(0)
            if how == "count":
                agg = agg.astype(np.int64)
        agg.index = idx
        out = agg
    else:
        raise ValueError("how harus last/sum/count/mean/max/min/first")
    if is_series:
        s = out.iloc[:, 0]
        s.name = x.name
        return s
    return out


def feature_matrix(bbo: pd.DataFrame | None = None, book: pd.DataFrame | None = None,
                   trades: pd.DataFrame | None = None, grid="1s", *, book_levels: int = 5,
                   flow_window="1min", max_age=None) -> pd.DataFrame:
    """Bundel fitur mikrostruktur standar pada grid waktu (kausal).

    Pada setiap titik grid g (interval (g_prev, g]):

    - dari BBO (as-of): ``mid``, ``spread``, ``bid_sz``, ``ask_sz``,
      ``queue_imbalance``, ``wmid_adj`` (weighted mid − mid), ``quote_age_s``;
      ``ret_mid`` = ln(mid_g / mid_prev); ``ofi`` = Σ e_n di interval;
      ``ofi_norm`` = ofi / rata-rata (Qb+Qa)/2 as-of.
    - dari BOOK: ``mlofi_1..L`` (Σ di interval), ``depth_imbalance_L`` (as-of).
    - dari TRADES: ``signed_volume``, ``volume``, ``n_trades`` di interval;
      ``flow_signed_volume``, ``flow_volume``, ``flow_aggressor_ratio`` pada
      jendela trailing (g − flow_window, g].

    ``bbo`` boleh None bila ``book`` diberikan (L1 diambil dari book). ``grid``:
    frekuensi (mis. "1s") atau array waktu. Data harus satu instrumen.
    """
    if bbo is None and book is not None:
        bbo = bbo_from_book(book)
    if bbo is None and trades is None:
        raise GcquantError("Berikan minimal bbo/book atau trades")
    for d, nm in ((bbo, "bbo"), (book, "book"), (trades, "trades")):
        _single_instrument(d, f"feature_matrix({nm})")
    times = [(_ts_of(d)) for d in (bbo, trades) if d is not None and len(d)]
    if isinstance(grid, (str, pd.Timedelta)):
        if not times:
            return pd.DataFrame(index=_ts_index(np.zeros(0, np.int64)))
        g = make_grid(int(min(t.min() for t in times)), int(max(t.max() for t in times)), grid)
    else:
        g = _grid_array(grid)
    out = pd.DataFrame(index=_ts_index(g))
    if bbo is not None:
        tq = _ts_of(bbo)
        _require_sorted(tq, "BBO")
        bp, ap, bs, as_ = l1_arrays(bbo)
        midv = (bp + ap) / 2.0
        ma = None if max_age is None else _ns(max_age)
        out["mid"] = _asof(tq, midv, g, ma)
        out["spread"] = _asof(tq, ap - bp, g, ma)
        out["bid_sz"] = _asof(tq, bs, g, ma)
        out["ask_sz"] = _asof(tq, as_, g, ma)
        out["queue_imbalance"] = _asof(tq, queue_imbalance(bbo).to_numpy(), g, ma)
        out["wmid_adj"] = _asof(tq, weighted_mid(bbo).to_numpy() - midv, g, ma)
        pos = np.searchsorted(tq, g, side="right") - 1
        out["quote_age_s"] = np.where(pos >= 0, (g - tq[np.maximum(pos, 0)]) / 1e9, np.nan)
        with np.errstate(invalid="ignore", divide="ignore"):
            out["ret_mid"] = np.r_[np.nan, np.diff(np.log(out["mid"].to_numpy()))]
        e = ofi_l1(bbo).to_numpy()
        out["ofi"] = _interval_sum(tq, e, g)
        depth = (out["bid_sz"] + out["ask_sz"]) / 2.0
        out["ofi_norm"] = out["ofi"] / depth.where(depth > 0)
    if book is not None:
        tb = _ts_of(book)
        _require_sorted(tb, "BOOK")
        ml = mlofi(book, book_levels)
        for c in ml.columns:
            out[c] = _interval_sum(tb, ml[c].to_numpy(), g)
        di = depth_imbalance(book, book_levels)
        out[di.name] = _asof(tb, di.to_numpy(), g)
    if trades is not None:
        tt = _ts_of(trades)
        _require_sorted(tt, "Trades")
        sgn = trade_sign(trades)
        sz = np.nan_to_num(trades["size"].to_numpy(dtype=np.float64, na_value=np.nan))
        out["signed_volume"] = _interval_sum(tt, sgn * sz, g)
        out["volume"] = _interval_sum(tt, sz, g)
        out["n_trades"] = _interval_sum(tt, np.ones(len(tt)), g).astype(np.int64)
        w = _ns(flow_window)
        c_sv, c_v = _csum0(sgn * sz), _csum0(sz)
        c_b, c_s = _csum0(sz * (sgn > 0)), _csum0(sz * (sgn < 0))
        hi = np.searchsorted(tt, g, side="right")
        lo = np.searchsorted(tt, g - w, side="right")
        out["flow_signed_volume"] = c_sv[hi] - c_sv[lo]
        out["flow_volume"] = c_v[hi] - c_v[lo]
        bb, ss = c_b[hi] - c_b[lo], c_s[hi] - c_s[lo]
        with np.errstate(invalid="ignore", divide="ignore"):
            out["flow_aggressor_ratio"] = np.where(bb + ss > 0, bb / (bb + ss), np.nan)
    return out
