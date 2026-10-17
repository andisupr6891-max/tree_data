"""Detektor konsep AMT / SMC / ICT yang KAUSAL (tanpa look-ahead), untuk bar bid.

Prinsip: setiap keluaran pada indeks i hanya memakai bar 0..i (bar yang sudah tutup).
Banyak pustaka SMC memakai jendela terpusat (swing di bar j memakai bar j+1..j+k) dan
menandainya di bar j — itu mengintip masa depan. Di sini swing baru "diketahui" pada
bar konfirmasi j + right, dan semua level yang diturunkan darinya juga baru berlaku di sana.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

NS_MIN = 60_000_000_000


# ---------------------------------------------------------------------------
# Dasar
# ---------------------------------------------------------------------------

def atr(h: np.ndarray, l: np.ndarray, c: np.ndarray, n: int = 14) -> np.ndarray:
    """ATR Wilder; nilai di i memakai bar ≤ i. NaN sampai ada n bar."""
    prev = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev), np.abs(l - prev)))
    out = np.full(len(tr), np.nan)
    if len(tr) < n:
        return out
    out[n - 1] = tr[:n].mean()
    a = 1.0 / n
    for i in range(n, len(tr)):
        out[i] = out[i - 1] + a * (tr[i] - out[i - 1])
    return out


def local_clock(t_ns: np.ndarray, tz: str) -> pd.DataFrame:
    """Jam/menit/tanggal lokal untuk tiap bar (zona waktu IANA, DST otomatis)."""
    idx = pd.DatetimeIndex(pd.to_datetime(t_ns, unit="ns", utc=True)).tz_convert(tz)
    return pd.DataFrame({"date": idx.normalize().tz_localize(None).values.astype("datetime64[D]"),
                         "hour": idx.hour.to_numpy(), "minute": idx.minute.to_numpy(),
                         "hm": (idx.hour * 60 + idx.minute).to_numpy(), "weekday": idx.weekday.to_numpy()})


def trading_day_id(t_ns: np.ndarray, roll_hour_ny: int = 17) -> np.ndarray:
    """ID hari perdagangan (gaya CME/forex): hari baru mulai pukul 17:00 New York.

    Nilai = tanggal (datetime64[D]) hari perdagangan tempat bar itu berada.
    """
    idx = pd.DatetimeIndex(pd.to_datetime(t_ns, unit="ns", utc=True)).tz_convert("America/New_York")
    shifted = idx + pd.to_timedelta(np.where(idx.hour >= roll_hour_ny, 1, 0), unit="D")
    return shifted.normalize().tz_localize(None).values.astype("datetime64[D]")


# ---------------------------------------------------------------------------
# Struktur pasar (SMC)
# ---------------------------------------------------------------------------

def swings(h: np.ndarray, l: np.ndarray, left: int = 3, right: int = 3):
    """Swing high/low fraktal yang dikonfirmasi secara kausal.

    Swing high di bar j: h[j] > max(h[j-left:j]) dan h[j] >= max(h[j+1:j+right+1]).
    Baru diketahui pada bar konfirmasi k = j + right.
    Mengembalikan dict array panjang n (nilai berlaku SEJAK bar konfirmasi, di-ffill):
    ``sh_px``/``sh_idx`` swing high terakhir yang terkonfirmasi, ``sl_px``/``sl_idx`` swing low,
    serta ``sh_new``/``sl_new`` boolean di bar konfirmasi.
    """
    from numpy.lib.stride_tricks import sliding_window_view as swv
    n = len(h)
    is_sh = np.zeros(n, bool)
    is_sl = np.zeros(n, bool)
    if n >= left + right + 1:
        js = np.arange(left, n - right)
        lmax = swv(h, left)[:n - left][js - left].max(axis=1)      # h[j-left:j]
        rmax = swv(h, right)[js + 1].max(axis=1)                   # h[j+1:j+right+1]
        lmin = swv(l, left)[:n - left][js - left].min(axis=1)
        rmin = swv(l, right)[js + 1].min(axis=1)
        is_sh[js] = (h[js] > lmax) & (h[js] >= rmax)
        is_sl[js] = (l[js] < lmin) & (l[js] <= rmin)
    sh_new = np.zeros(n, bool)
    sl_new = np.zeros(n, bool)
    sh_new[np.flatnonzero(is_sh) + right] = True
    sl_new[np.flatnonzero(is_sl) + right] = True

    def ffill(new, src_px):
        idx = np.where(new, np.arange(n) - right, -1)
        idx = np.maximum.accumulate(idx)
        px = np.where(idx >= 0, src_px[np.maximum(idx, 0)], np.nan)
        return px, idx

    sh_px, sh_idx = ffill(sh_new, h)
    sl_px, sl_idx = ffill(sl_new, l)
    return dict(sh_px=sh_px, sh_idx=sh_idx, sl_px=sl_px, sl_idx=sl_idx, sh_new=sh_new, sl_new=sl_new)


def structure_breaks(c: np.ndarray, sw: dict):
    """Break of Structure (BOS) & Change of Character (CHoCH) berbasis CLOSE.

    BOS naik di bar i: close[i] > swing high terkonfirmasi terakhir (yang belum ditembus).
    ``trend`` = arah break terakhir (+1/−1/0). CHoCH = break yang berlawanan dengan trend
    sebelumnya. Keluaran: arrays ``bos`` (+1/−1/0), ``choch`` (+1/−1/0), ``trend``,
    ``broken_level`` (level yang ditembus).
    """
    n = len(c)
    bos = np.zeros(n, int)
    choch = np.zeros(n, int)
    trend = np.zeros(n, int)
    lvl = np.full(n, np.nan)
    used_h = used_l = -1
    t = 0
    for i in range(n):
        shi, sli = sw["sh_idx"][i], sw["sl_idx"][i]
        if shi >= 0 and shi != used_h and c[i] > sw["sh_px"][i]:
            bos[i] = 1
            choch[i] = 1 if t == -1 else 0
            lvl[i] = sw["sh_px"][i]
            t = 1
            used_h = shi
        elif sli >= 0 and sli != used_l and c[i] < sw["sl_px"][i]:
            bos[i] = -1
            choch[i] = -1 if t == 1 else 0
            lvl[i] = sw["sl_px"][i]
            t = -1
            used_l = sli
        trend[i] = t
    return dict(bos=bos, choch=choch, trend=trend, broken_level=lvl)


def fvg(h: np.ndarray, l: np.ndarray, o: np.ndarray, c: np.ndarray, atr_arr: np.ndarray | None = None,
        min_gap_atr: float = 0.0, min_body_atr: float = 0.0):
    """Fair Value Gap 3-candle, diketahui di close bar k.

    Bullish di k: l[k] > h[k-2] → zona [h[k-2], l[k]]; bearish: h[k] < l[k-2] → zona [h[k], l[k-2]].
    Filter opsional: lebar gap ≥ min_gap_atr × ATR[k] dan badan candle tengah ≥ min_body_atr × ATR[k]
    (displacement). Keluaran: arrays ``dir`` (+1/−1/0), ``top``, ``bottom``.
    """
    n = len(h)
    d = np.zeros(n, int)
    top = np.full(n, np.nan)
    bot = np.full(n, np.nan)
    if n < 3:
        return dict(dir=d, top=top, bottom=bot)
    a = atr_arr if atr_arr is not None else np.full(n, np.nan)
    k = np.arange(2, n)
    body = np.abs(c[k - 1] - o[k - 1])
    with np.errstate(invalid="ignore"):
        ok_body = np.ones(len(k), bool) if min_body_atr <= 0 else (body >= min_body_atr * a[k])
        up_gap = l[k] - h[k - 2]
        dn_gap = l[k - 2] - h[k]
        ok_up = (up_gap > 0) & ok_body & ((min_gap_atr <= 0) | (up_gap >= min_gap_atr * a[k]))
        ok_dn = (dn_gap > 0) & ok_body & ((min_gap_atr <= 0) | (dn_gap >= min_gap_atr * a[k]))
    ku, kd = k[ok_up], k[ok_dn]
    d[ku], top[ku], bot[ku] = 1, l[ku], h[ku - 2]
    d[kd], top[kd], bot[kd] = -1, l[kd - 2], h[kd]
    return dict(dir=d, top=top, bottom=bot)


def order_block_before(o: np.ndarray, c: np.ndarray, i_break: int, direction: int, lookback: int = 20):
    """Order block: candle berlawanan arah terakhir sebelum gerakan yang menembus struktur.

    Untuk break naik (+1) dicari candle bearish (c<o) terakhir dalam ``lookback`` bar sebelum
    ``i_break``; untuk break turun dicari candle bullish. Mengembalikan indeks atau −1.
    Hanya memakai bar ≤ i_break (kausal bila dipanggil pada saat break diketahui).
    """
    lo = max(0, i_break - lookback)
    for j in range(i_break - 1, lo - 1, -1):
        if direction > 0 and c[j] < o[j]:
            return j
        if direction < 0 and c[j] > o[j]:
            return j
    return -1


# ---------------------------------------------------------------------------
# Sesi & level referensi (ICT / likuiditas)
# ---------------------------------------------------------------------------

def session_range(t_ns: np.ndarray, h: np.ndarray, l: np.ndarray, start_hm: int, end_hm: int,
                  tz: str = "America/New_York"):
    """High/low suatu jendela sesi harian (menit lokal [start_hm, end_hm)), boleh lewat tengah malam.

    Nilai hanya tersedia SETELAH sesi selesai (mulai bar pertama dengan jam ≥ end_hm) dan
    berlaku sampai sesi berikutnya selesai. Keluaran arrays ``hi``, ``lo``, ``valid``.
    """
    clk = local_clock(t_ns, tz)
    hm = clk["hm"].to_numpy()
    n = len(h)
    hi = np.full(n, np.nan)
    lo = np.full(n, np.nan)
    in_sess = (hm >= start_hm) & (hm < end_hm) if start_hm < end_hm else (hm >= start_hm) | (hm < end_hm)
    cur_h = cur_l = np.nan
    run_h, run_l = -np.inf, np.inf
    active = False
    for i in range(n):
        if in_sess[i]:
            if not active:
                run_h, run_l = -np.inf, np.inf
                active = True
            run_h = max(run_h, h[i])
            run_l = min(run_l, l[i])
        elif active:
            cur_h, cur_l = run_h, run_l
            active = False
        hi[i], lo[i] = cur_h, cur_l
    return dict(hi=hi, lo=lo, valid=np.isfinite(hi))


def prior_day_levels(t_ns: np.ndarray, o, h, l, c, roll_hour_ny: int = 17):
    """High/low/close/open hari perdagangan SEBELUMNYA (hari mulai 17:00 New York).

    Berlaku sejak bar pertama hari berjalan. Juga ``day_open`` (open hari berjalan) dan ``day_id``.
    """
    day = trading_day_id(t_ns, roll_hour_ny)
    n = len(day)
    out = {k: np.full(n, np.nan) for k in ("pdh", "pdl", "pdc", "pdo", "day_open")}
    cur_day = None
    run = None
    prev = None
    for i in range(n):
        if day[i] != cur_day:
            if run is not None:
                prev = run
            cur_day = day[i]
            run = [o[i], h[i], l[i], c[i]]
        else:
            run[1] = max(run[1], h[i])
            run[2] = min(run[2], l[i])
            run[3] = c[i]
        out["day_open"][i] = run[0]
        if prev is not None:
            out["pdo"][i], out["pdh"][i], out["pdl"][i], out["pdc"][i] = prev
    out["day_id"] = day
    return out


def equal_levels(px: np.ndarray, idx: np.ndarray, tol: float):
    """Deteksi 'equal highs/lows' (kolam likuiditas): dua swing terkonfirmasi berturut-turut
    yang selisihnya ≤ tol. Masukan: deret swing (mis. sw['sh_px'], sw['sh_idx']).
    Keluaran array level (NaN bila tidak ada) yang berlaku sejak swing kedua terkonfirmasi.
    """
    n = len(px)
    out = np.full(n, np.nan)
    last_idx, last_px, prev_px = -1, np.nan, np.nan
    cur = np.nan
    for i in range(n):
        if idx[i] != last_idx and idx[i] >= 0:
            prev_px, last_px, last_idx = last_px, px[i], idx[i]
            if np.isfinite(prev_px) and abs(last_px - prev_px) <= tol:
                cur = max(last_px, prev_px)
            else:
                cur = np.nan
        out[i] = cur
    return out


def sweep(h: np.ndarray, l: np.ndarray, c: np.ndarray, level_hi: np.ndarray, level_lo: np.ndarray):
    """Sapuan likuiditas di bar i (diketahui saat close i):

    ``-1`` (sapu atas, bias turun): h[i] > level_hi[i] dan c[i] < level_hi[i].
    ``+1`` (sapu bawah, bias naik): l[i] < level_lo[i] dan c[i] > level_lo[i].
    """
    up = np.isfinite(level_hi) & (h > level_hi) & (c < level_hi)
    dn = np.isfinite(level_lo) & (l < level_lo) & (c > level_lo)
    out = np.zeros(len(h), int)
    out[up] = -1
    out[dn & ~up] = 1
    return out


# ---------------------------------------------------------------------------
# Auction Market Theory / Market Profile (proksi volume tick M1)
# ---------------------------------------------------------------------------

def volume_profile(h: np.ndarray, l: np.ndarray, vol: np.ndarray, bin_size: float, va_frac: float = 0.70):
    """Profil volume dari bar: volume tiap bar dibagi rata di rentang [low, high].

    Mengembalikan dict(poc, vah, val, edges, hist). Value area dibangun dengan algoritma
    CBOT: mulai dari POC, tambahkan sisi (dua bin di atas vs dua bin di bawah) yang volumenya
    lebih besar sampai mencapai ``va_frac`` dari total.
    """
    lo_all, hi_all = np.nanmin(l), np.nanmax(h)
    nb = max(1, int(np.ceil((hi_all - lo_all) / bin_size)) + 1)
    edges = lo_all + bin_size * np.arange(nb + 1)
    hist = np.zeros(nb)
    for hh, ll, v in zip(h, l, vol):
        if not np.isfinite(v) or v <= 0:
            continue
        a = int((ll - lo_all) // bin_size)
        b = int((hh - lo_all) // bin_size)
        a, b = max(0, min(a, nb - 1)), max(0, min(b, nb - 1))
        hist[a:b + 1] += v / (b - a + 1)
    poc_i = int(np.argmax(hist))
    total = hist.sum()
    lo_i = hi_i = poc_i
    acc = hist[poc_i]
    while total > 0 and acc < va_frac * total and (lo_i > 0 or hi_i < nb - 1):
        up = hist[hi_i + 1:hi_i + 3].sum() if hi_i < nb - 1 else -1
        dn = hist[max(0, lo_i - 2):lo_i].sum() if lo_i > 0 else -1
        if up >= dn:
            step = min(2, nb - 1 - hi_i)
            acc += hist[hi_i + 1:hi_i + 1 + step].sum()
            hi_i += step
        else:
            step = min(2, lo_i)
            acc += hist[lo_i - step:lo_i].sum()
            lo_i -= step
    mid = lambda i: edges[i] + bin_size / 2
    return dict(poc=mid(poc_i), vah=edges[hi_i + 1], val=edges[lo_i], edges=edges, hist=hist)


def prior_day_profile(t_ns: np.ndarray, h, l, vol, bin_size: float = 0.5, va_frac: float = 0.70,
                      roll_hour_ny: int = 17):
    """POC/VAH/VAL hari perdagangan sebelumnya, berlaku sejak bar pertama hari berjalan."""
    day = trading_day_id(t_ns, roll_hour_ny)
    n = len(day)
    poc = np.full(n, np.nan)
    vah = np.full(n, np.nan)
    val = np.full(n, np.nan)
    starts = np.flatnonzero(np.concatenate([[True], day[1:] != day[:-1]]))
    ends = np.concatenate([starts[1:], [n]])
    prev = None
    for s, e in zip(starts, ends):
        if prev is not None:
            poc[s:e], vah[s:e], val[s:e] = prev
        if e - s >= 30:
            vp = volume_profile(h[s:e], l[s:e], vol[s:e], bin_size, va_frac)
            prev = (vp["poc"], vp["vah"], vp["val"])
        else:
            prev = None
    return dict(poc=poc, vah=vah, val=val, day_id=day)


def initial_balance(t_ns: np.ndarray, h, l, start_hm: int = 8 * 60 + 20, minutes: int = 60,
                    tz: str = "America/New_York"):
    """Initial balance (rentang jam pertama sesi utama; bawaan pembukaan COMEX 08:20 NY).

    ``ib_hi``/``ib_lo`` hanya tersedia pada bar hari kalender lokal yang sama dengan jam ≥ akhir IB.
    """
    clk = local_clock(t_ns, tz)
    hm = clk["hm"].to_numpy()
    date = clk["date"].to_numpy()
    end_hm = start_hm + minutes
    inside = (hm >= start_hm) & (hm < end_hm)
    df = pd.DataFrame({"date": date[inside], "h": h[inside], "l": l[inside]})
    g = df.groupby("date").agg(hi=("h", "max"), lo=("l", "min"))
    hi = pd.Series(date).map(g["hi"]).to_numpy(float, copy=True)
    lo = pd.Series(date).map(g["lo"]).to_numpy(float, copy=True)
    after = hm >= end_hm
    hi[~after] = np.nan
    lo[~after] = np.nan
    return dict(ib_hi=hi, ib_lo=lo)
