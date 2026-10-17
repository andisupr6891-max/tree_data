"""PRA-REGISTRASI hipotesis payoff asimetris AMT / SMC / ICT (dibekukan sebelum melihat hasil).

Aturan umum untuk SEMUA hipotesis:
- Sinyal hanya dari bar yang sudah tutup; entry di open M1 berikutnya (atau order limit).
- Target 3R (kecuali H6 yang targetnya level struktur, dengan syarat RR ≥ 2,5).
- Buffer stop = 0,1 × ATR(M15, 14) (+ spread untuk short karena stop short dinilai di ask).
- Filter biaya: trade dilewati bila R < 8 × spread saat sinyal (biaya ≤ ~1/8 R).
- Satu posisi pada satu waktu per hipotesis; maksimal satu sinyal per hari per hipotesis
  kecuali disebut lain.
- Zona waktu: America/New_York (DST otomatis). Hari ICT = tanggal kalender New York.
Catatan data: berkas M1 ini tidak punya jam 00:00-00:59 GMT (lubang harian) sehingga rentang
Asia (20:00-00:00 NY) kehilangan sebagian bar pada musim dingin/panas tertentu.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from gcquant.rr import Bracket
from gcquant.rr import concepts as C

NS_MIN = 60_000_000_000
TARGET_R = 3.0
MIN_R_OVER_SPREAD = 8.0


# ---------------------------------------------------------------------------
# alat bantu
# ---------------------------------------------------------------------------

def _htf(ctx, rule):
    f = ctx.htf(rule)
    t = f.index.as_unit("ns").asi8
    return dict(f=f, t=t, o=f["open"].to_numpy(float), h=f["high"].to_numpy(float),
                l=f["low"].to_numpy(float), c=f["close"].to_numpy(float), v=f["tickvol"].to_numpy(float),
                m1=f["last_m1"].to_numpy(np.int64), clk=C.local_clock(t, "America/New_York"))


def _atr15_at_m1(ctx):
    def build():
        x = _htf(ctx, "15min")
        a = C.atr(x["h"], x["l"], x["c"], 14)
        out = np.full(len(ctx.t), np.nan)
        out[x["m1"]] = a
        return pd.Series(out).ffill().to_numpy()
    return ctx.cached("atr15_m1", build)


def _ny_ns(date64, hh, mm=0):
    ts = pd.Timestamp(date64).tz_localize("America/New_York") + pd.Timedelta(hours=hh, minutes=mm)
    return int(ts.tz_convert("UTC").value)


def _mk(ctx, i_m1, d, stop_bid_level, *, target=None, r_target=TARGET_R, max_bars=1440,
        exit_at_ns=None, entry_limit=None, limit_bars=0, tag=""):
    """Bangun Bracket dengan buffer & filter biaya standar. ``stop_bid_level`` = level struktur
    (skala bid). Untuk short, stop dinaikkan sebesar spread agar dinilai di ask."""
    a15 = _atr15_at_m1(ctx)[i_m1]
    if not np.isfinite(a15):
        return None
    sp = ctx.sp[i_m1]
    buf = 0.1 * a15
    stop = stop_bid_level - buf if d > 0 else stop_bid_level + buf + sp
    ref_est = entry_limit if entry_limit is not None else (ctx.c[i_m1] if d > 0 else ctx.c[i_m1] + sp)
    r_est = d * (ref_est - stop)
    if not np.isfinite(r_est) or r_est <= 0 or r_est < MIN_R_OVER_SPREAD * sp:
        return None
    if target is not None:
        if d * (target - ref_est) < 2.5 * r_est:
            return None
        r_target = None
    return Bracket(int(i_m1), int(d), stop=float(stop), r_target=r_target, target=target,
                   max_bars=max_bars, exit_at_ns=exit_at_ns, entry_limit=entry_limit,
                   limit_bars=limit_bars, tag=tag)


def _keep(lst, b):
    if b is not None:
        lst.append(b)


# ---------------------------------------------------------------------------
# ICT
# ---------------------------------------------------------------------------

def h1_judas(ctx, need_mss: bool):
    """Sapuan rentang Asia (20:00-00:00 NY) di killzone London (02:00-05:00 NY), M5.
    a) tutup kembali ke dalam rentang → masuk berlawanan arah sapuan.
    b) + konfirmasi MSS: close M5 menembus swing M5 (L=R=2) terakhir sebelum sapuan, ≤ 6 bar.
    Stop: ekstrem sapuan. Target 3R. Keluar paksa 12:00 NY."""
    x = _htf(ctx, "5min")
    asia = C.session_range(x["t"], x["h"], x["l"], 20 * 60, 0)
    sw = C.swings(x["h"], x["l"], 2, 2)
    hm, date = x["clk"]["hm"].to_numpy(), x["clk"]["date"].to_numpy()
    out, used = [], set()
    n = len(x["c"])
    for k in range(n):
        if not (120 <= hm[k] < 300) or date[k] in used or not np.isfinite(asia["hi"][k]):
            continue
        for d, swept in ((-1, x["h"][k] > asia["hi"][k] and x["c"][k] < asia["hi"][k]),
                         (1, x["l"][k] < asia["lo"][k] and x["c"][k] > asia["lo"][k])):
            if not swept:
                continue
            ext = x["h"][k] if d < 0 else x["l"][k]
            exit_ns = _ny_ns(date[k], 12)
            if not need_mss:
                _keep(out, _mk(ctx, x["m1"][k], d, ext, max_bars=600, exit_at_ns=exit_ns, tag="judas"))
                used.add(date[k])
                break
            lvl = sw["sl_px"][k] if d < 0 else sw["sh_px"][k]
            if not np.isfinite(lvl):
                continue
            for j in range(k + 1, min(n, k + 7)):
                ext = max(ext, x["h"][j]) if d < 0 else min(ext, x["l"][j])
                if (d < 0 and x["c"][j] < lvl) or (d > 0 and x["c"][j] > lvl):
                    _keep(out, _mk(ctx, x["m1"][j], d, ext, max_bars=600, exit_at_ns=exit_ns, tag="judas_mss"))
                    used.add(date[k])
                    break
            if date[k] in used:
                break
    return out


def h2_silver_bullet(ctx, start_hm: int, exit_hh: int):
    """Silver Bullet: FVG M5 pertama (displacement: badan candle tengah ≥ 1 ATR M5, celah ≥ 0,05 ATR)
    yang terbentuk di jendela [start, start+60) NY → limit di tepi FVG (bullish: top), berlaku s/d
    akhir jendela. Stop di bawah low dua candle pertama formasi. Target 3R."""
    x = _htf(ctx, "5min")
    a5 = C.atr(x["h"], x["l"], x["c"], 14)
    g = C.fvg(x["h"], x["l"], x["o"], x["c"], a5, min_gap_atr=0.05, min_body_atr=1.0)
    hm, date = x["clk"]["hm"].to_numpy(), x["clk"]["date"].to_numpy()
    out, used = [], set()
    for k in np.flatnonzero(g["dir"] != 0):
        if not (start_hm <= hm[k] < start_hm + 55) or date[k] in used:
            continue
        d = int(g["dir"][k])
        if d > 0:
            stop_lvl, lim = min(x["l"][k - 2], x["l"][k - 1]), g["top"][k]
        else:
            stop_lvl, lim = max(x["h"][k - 2], x["h"][k - 1]), g["bottom"][k]
        left = (start_hm + 60 - hm[k] - 5)          # menit tersisa di jendela setelah bar k tutup
        if left <= 0:
            continue
        lim_m1 = lim + ctx.sp[x["m1"][k]] if d > 0 else lim   # limit beli dinilai di ask
        _keep(out, _mk(ctx, x["m1"][k], d, stop_lvl, max_bars=720, exit_at_ns=_ny_ns(date[k], exit_hh),
                       entry_limit=lim_m1, limit_bars=int(left), tag="silver_bullet"))
        used.add(date[k])
    return out


def h10_power_of_3(ctx):
    """Power of 3 / AMD harian: open tengah malam NY (mo). Bila sampai sebelum sinyal harga sudah
    turun ≥ 0,5 × ATR harian (14, hari-hari sebelumnya) di bawah mo (manipulasi), lalu close M15
    kembali di atas mo antara 07:00-10:00 NY → long; stop low sejak 00:00 NY; target 3R; keluar 16:00.
    Cermin untuk short."""
    x = _htf(ctx, "15min")
    hm, date = x["clk"]["hm"].to_numpy(), x["clk"]["date"].to_numpy()
    dfd = pd.DataFrame({"d": date, "h": x["h"], "l": x["l"]}).groupby("d").agg(h=("h", "max"), l=("l", "min"))
    atr_d = (dfd["h"] - dfd["l"]).rolling(14).mean().shift(1)     # hanya hari yang sudah selesai
    atr_map = pd.Series(date).map(atr_d).to_numpy(float)
    out = []
    cur, mo, lo, hi, done = None, np.nan, np.inf, -np.inf, False
    for k in range(len(x["c"])):
        if date[k] != cur:
            cur, mo, lo, hi, done = date[k], (x["o"][k] if hm[k] < 15 else np.nan), np.inf, -np.inf, False
        if not np.isfinite(mo) or done:
            continue
        lo, hi = min(lo, x["l"][k]), max(hi, x["h"][k])
        if 7 * 60 <= hm[k] < 10 * 60 and np.isfinite(atr_map[k]):
            th = 0.5 * atr_map[k]
            if lo <= mo - th and x["c"][k] > mo:
                _keep(out, _mk(ctx, x["m1"][k], 1, lo, max_bars=720, exit_at_ns=_ny_ns(date[k], 16), tag="po3"))
                done = True
            elif hi >= mo + th and x["c"][k] < mo:
                _keep(out, _mk(ctx, x["m1"][k], -1, hi, max_bars=720, exit_at_ns=_ny_ns(date[k], 16), tag="po3"))
                done = True
    return out


def h11_ote(ctx):
    """OTE: setelah BOS M15 (swing L=R=3) dengan kaki ≥ 3 ATR15, limit di retracement 70,5% kaki,
    stop di luar asal kaki (100%), target 3R, limit berlaku 24 bar M15 (360 menit)."""
    x = _htf(ctx, "15min")
    a = C.atr(x["h"], x["l"], x["c"], 14)
    sw = C.swings(x["h"], x["l"], 3, 3)
    br = C.structure_breaks(x["c"], sw)
    out = []
    for i in np.flatnonzero(br["bos"] != 0):
        d = int(br["bos"][i])
        if d > 0:
            j0 = sw["sl_idx"][i]
            if j0 < 0:
                continue
            leg_lo, leg_hi = x["l"][j0], x["h"][j0:i + 1].max()
        else:
            j0 = sw["sh_idx"][i]
            if j0 < 0:
                continue
            leg_hi, leg_lo = x["h"][j0], x["l"][j0:i + 1].min()
        leg = leg_hi - leg_lo
        if not np.isfinite(a[i]) or leg < 3 * a[i]:
            continue
        if d > 0:
            lim, stop_lvl = leg_hi - 0.705 * leg, leg_lo
            lim_m1 = lim + ctx.sp[x["m1"][i]]
        else:
            lim, stop_lvl = leg_lo + 0.705 * leg, leg_hi
            lim_m1 = lim
        _keep(out, _mk(ctx, x["m1"][i], d, stop_lvl, max_bars=2880, entry_limit=lim_m1, limit_bars=360, tag="ote"))
    return out


# ---------------------------------------------------------------------------
# SMC
# ---------------------------------------------------------------------------

def h3_sweep_pdh_pdl(ctx):
    """Sapuan high/low hari sebelumnya (hari 17:00 NY) di M15: high > PDH & close < PDH → short;
    stop high bar sapuan; target 3R; maks 24 jam. Satu sinyal per hari per sisi."""
    x = _htf(ctx, "15min")
    lv = C.prior_day_levels(x["t"], x["o"], x["h"], x["l"], x["c"])
    sw = C.sweep(x["h"], x["l"], x["c"], lv["pdh"], lv["pdl"])
    out, used = [], set()
    for k in np.flatnonzero(sw != 0):
        d = int(sw[k])
        key = (lv["day_id"][k], d)
        if key in used:
            continue
        used.add(key)
        _keep(out, _mk(ctx, x["m1"][k], d, x["h"][k] if d < 0 else x["l"][k], max_bars=1440, tag="pdhl_sweep"))
    return out


def h4_bos_fvg(ctx, structural_stop: bool):
    """BOS M15 (swing L=R=3) dengan displacement (badan bar BOS ≥ 1,2 ATR15) yang meninggalkan FVG
    searah di bar BOS atau bar sebelumnya → limit di tepi FVG, berlaku 16 bar M15.
    a) stop struktural: swing berlawanan terakhir sebelum BOS; b) stop rapat: sisi jauh FVG − 0,25 ATR."""
    x = _htf(ctx, "15min")
    a = C.atr(x["h"], x["l"], x["c"], 14)
    sw = C.swings(x["h"], x["l"], 3, 3)
    br = C.structure_breaks(x["c"], sw)
    g = C.fvg(x["h"], x["l"], x["o"], x["c"])
    out = []
    for i in np.flatnonzero(br["bos"] != 0):
        d = int(br["bos"][i])
        if not np.isfinite(a[i]) or abs(x["c"][i] - x["o"][i]) < 1.2 * a[i]:
            continue
        ks = [k for k in (i, i - 1) if k >= 2 and g["dir"][k] == d]
        if not ks:
            continue
        k = ks[0]
        top, bot = g["top"][k], g["bottom"][k]
        if d > 0:
            lim = top + ctx.sp[x["m1"][i]]
            stop_lvl = sw["sl_px"][i] if structural_stop else bot - 0.25 * a[i]
        else:
            lim = bot
            stop_lvl = sw["sh_px"][i] if structural_stop else top + 0.25 * a[i]
        if not np.isfinite(stop_lvl):
            continue
        _keep(out, _mk(ctx, x["m1"][i], d, stop_lvl, max_bars=2880, entry_limit=lim, limit_bars=240,
                       tag="bos_fvg"))
    return out


def h5_order_block(ctx):
    """Order block H1: setelah BOS H1 (L=R=3) dengan badan ≥ 1 ATR(H1), OB = candle berlawanan
    terakhir dalam 10 bar sebelum BOS. Limit di tepi OB (bull: high OB), berlaku 24 bar H1.
    Stop di sisi jauh OB. Target 3R. Maks 5 hari."""
    x = _htf(ctx, "1h")
    a = C.atr(x["h"], x["l"], x["c"], 14)
    sw = C.swings(x["h"], x["l"], 3, 3)
    br = C.structure_breaks(x["c"], sw)
    out = []
    for i in np.flatnonzero(br["bos"] != 0):
        d = int(br["bos"][i])
        if not np.isfinite(a[i]) or abs(x["c"][i] - x["o"][i]) < a[i]:
            continue
        j = C.order_block_before(x["o"], x["c"], i, d, 10)
        if j < 0:
            continue
        if d > 0:
            lim, stop_lvl = x["h"][j] + ctx.sp[x["m1"][i]], x["l"][j]
        else:
            lim, stop_lvl = x["l"][j], x["h"][j]
        if (d > 0 and x["c"][i] <= lim) or (d < 0 and x["c"][i] >= lim):
            continue
        _keep(out, _mk(ctx, x["m1"][i], d, stop_lvl, max_bars=7200, entry_limit=lim, limit_bars=1440, tag="ob"))
    return out


def h13_turtle_soup(ctx):
    """Turtle Soup (Connors & Raschke 1995) dengan pemicu M15: low 20 hari (hari 17:00 NY yang
    sudah selesai) dan low itu terjadi ≥ 4 hari lalu. Harga menembus di bawahnya lalu close M15
    kembali di atasnya dalam ≤ 4 bar → long; stop low terendah sejak tembus; target 3R; maks 3 hari."""
    x = _htf(ctx, "15min")
    day = C.trading_day_id(x["t"])
    dfd = pd.DataFrame({"d": day, "h": x["h"], "l": x["l"]}).groupby("d").agg(h=("h", "max"), l=("l", "min"))
    L, H = dfd["l"].to_numpy(), dfd["h"].to_numpy()
    lo20 = np.full(len(dfd), np.nan)
    hi20 = np.full(len(dfd), np.nan)
    lo_age = np.zeros(len(dfd), int)
    hi_age = np.zeros(len(dfd), int)
    for q in range(20, len(dfd)):
        wl, wh = L[q - 20:q], H[q - 20:q]
        lo20[q], hi20[q] = wl.min(), wh.max()
        lo_age[q], hi_age[q] = 20 - int(np.argmin(wl)), 20 - int(np.argmax(wh))
    pos = pd.Series(np.arange(len(dfd)), index=dfd.index)
    qi = pd.Series(day).map(pos).to_numpy()
    out, used = [], set()
    n = len(x["c"])
    for k in range(n):
        q = qi[k]
        if not np.isfinite(lo20[q]) or (day[k], 0) in used:
            continue
        for d, lvl, age, broke in ((1, lo20[q], lo_age[q], x["l"][k] < lo20[q]),
                                   (-1, hi20[q], hi_age[q], x["h"][k] > hi20[q])):
            if not broke or age < 4:
                continue
            ext = x["l"][k] if d > 0 else x["h"][k]
            for j in range(k, min(n, k + 4)):
                if day[j] != day[k]:
                    break
                ext = min(ext, x["l"][j]) if d > 0 else max(ext, x["h"][j])
                if (d > 0 and x["c"][j] > lvl) or (d < 0 and x["c"][j] < lvl):
                    _keep(out, _mk(ctx, x["m1"][j], d, ext, max_bars=4320, tag="turtle_soup"))
                    used.add((day[k], 0))
                    break
            if (day[k], 0) in used:
                break
    return out


def h14_equal_levels_sweep(ctx):
    """Kolam likuiditas: dua swing H1 (L=R=3) berurutan selisih ≤ $0,50 (equal highs/lows).
    Sapuan di M15: high > level & close < level → short; stop high bar; target 3R; maks 24 jam."""
    x1 = _htf(ctx, "1h")
    sw = C.swings(x1["h"], x1["l"], 3, 3)
    eqh = C.equal_levels(sw["sh_px"], sw["sh_idx"], 0.50)
    eql = C.equal_levels(sw["sl_px"], sw["sl_idx"], 0.50)
    x = _htf(ctx, "15min")
    # level H1 yang berlaku saat bar M15 tutup: bar H1 terakhir yang SUDAH TUTUP sebelum/pada akhir bar M15
    h1_close = x1["t"] + 3600 * 10**9
    m15_close = x["t"] + 15 * NS_MIN
    j = np.searchsorted(h1_close, m15_close, side="right") - 1
    ok = j >= 0
    lv_hi = np.where(ok, eqh[np.maximum(j, 0)], np.nan)
    lv_lo = np.where(ok, eql[np.maximum(j, 0)], np.nan)
    s = C.sweep(x["h"], x["l"], x["c"], lv_hi, lv_lo)
    out, used = [], set()
    for k in np.flatnonzero(s != 0):
        d = int(s[k])
        key = (round(float(lv_hi[k] if d < 0 else lv_lo[k]), 2), d)
        if key in used:
            continue
        used.add(key)
        _keep(out, _mk(ctx, x["m1"][k], d, x["h"][k] if d < 0 else x["l"][k], max_bars=1440, tag="eq_sweep"))
    return out


# ---------------------------------------------------------------------------
# AMT / Market Profile
# ---------------------------------------------------------------------------

def h6_80_rule(ctx):
    """Aturan 80% (Dalton): open sesi utama (08:20 NY) di luar value area hari sebelumnya, lalu
    dua close M30 berturut-turut di dalam VA (setelah 08:20) → masuk menuju tepi VA seberang.
    Stop: ekstrem sejak 08:20. Target: tepi VA seberang (syarat RR ≥ 2,5). Keluar 16:00 NY."""
    prof = ctx.cached("prof", lambda: C.prior_day_profile(ctx.t, ctx.h, ctx.l, ctx.v, 0.5))
    x = _htf(ctx, "30min")
    hm, date = x["clk"]["hm"].to_numpy(), x["clk"]["date"].to_numpy()
    ny = ctx.ny()
    m1hm, m1date = ny["hm"].to_numpy(), ny["date"].to_numpy()
    open_idx = {}
    for i in np.flatnonzero(m1hm == 8 * 60 + 20):
        open_idx.setdefault(m1date[i], i)
    out = []
    for dte, i0 in open_idx.items():
        vah, val = prof["vah"][i0], prof["val"][i0]
        if not (np.isfinite(vah) and np.isfinite(val)):
            continue
        op = ctx.o[i0]
        if val <= op <= vah:
            continue
        d = -1 if op > vah else 1
        ks = np.flatnonzero((date == dte) & (hm >= 8 * 60 + 30) & (hm < 15 * 60))
        inside_run, ext = 0, op
        for k in ks:
            m1k = x["m1"][k]
            seg = slice(i0, m1k + 1)
            ext = ctx.h[seg].max() if d < 0 else ctx.l[seg].min()
            inside = val < x["c"][k] < vah
            inside_run = inside_run + 1 if inside else 0
            if inside_run >= 2:
                tgt = val if d < 0 else vah
                tgt_scale = tgt + ctx.sp[m1k] if d < 0 else tgt     # target short dinilai di ask
                _keep(out, _mk(ctx, m1k, d, ext, target=tgt_scale, max_bars=600,
                               exit_at_ns=_ny_ns(dte, 16), tag="80pct"))
                break
    return out


def h7_initial_balance(ctx, mode: str):
    """IB = 08:20-09:20 NY (pembukaan COMEX). Sinyal M5 antara 09:20-12:00 NY, satu per hari.
    breakout: close M5 pertama di luar IB → searah; stop di tengah IB; target 3R.
    failure: high/low M5 menembus IB lalu close kembali di dalam ≤ 3 bar → berlawanan;
    stop ekstrem sejak tembus; target 3R. Keluar 16:00 NY."""
    x = _htf(ctx, "5min")
    ib = C.initial_balance(x["t"], x["h"], x["l"], 8 * 60 + 20, 60)
    hm, date = x["clk"]["hm"].to_numpy(), x["clk"]["date"].to_numpy()
    out, used = [], set()
    n = len(x["c"])
    for k in range(n):
        if date[k] in used or not (9 * 60 + 20 <= hm[k] < 12 * 60) or not np.isfinite(ib["ib_hi"][k]):
            continue
        hi, lo = ib["ib_hi"][k], ib["ib_lo"][k]
        mid = 0.5 * (hi + lo)
        if mode == "breakout":
            d = 1 if x["c"][k] > hi else (-1 if x["c"][k] < lo else 0)
            if d:
                _keep(out, _mk(ctx, x["m1"][k], d, mid, max_bars=600, exit_at_ns=_ny_ns(date[k], 16), tag="ib_bo"))
                used.add(date[k])
        else:
            d = -1 if x["h"][k] > hi else (1 if x["l"][k] < lo else 0)
            if not d:
                continue
            used.add(date[k])
            ext = x["h"][k] if d < 0 else x["l"][k]
            for j in range(k, min(n, k + 3)):
                if date[j] != date[k]:
                    break
                ext = max(ext, x["h"][j]) if d < 0 else min(ext, x["l"][j])
                if (d < 0 and x["c"][j] < hi) or (d > 0 and x["c"][j] > lo):
                    _keep(out, _mk(ctx, x["m1"][j], d, ext, max_bars=600, exit_at_ns=_ny_ns(date[k], 16), tag="ib_fail"))
                    break
    return out


def h8_open_drive(ctx):
    """Open-drive (Dalton): 30 menit pertama setelah 08:20 NY — rentang ≥ rata-rata 20 hari
    sebelumnya untuk jendela yang sama, open di 15% bawah rentang dan close di 20% atas (bull) → long
    di 08:50; stop low jendela; target 3R; keluar 13:30 NY. Cermin untuk bear."""
    ny = ctx.ny()
    hm, date = ny["hm"].to_numpy(), ny["date"].to_numpy()
    win = (hm >= 8 * 60 + 20) & (hm < 8 * 60 + 50)
    df = pd.DataFrame({"d": date[win], "o": ctx.o[win], "h": ctx.h[win], "l": ctx.l[win], "c": ctx.c[win],
                       "i": np.flatnonzero(win)})
    g = df.groupby("d").agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"), i=("i", "last"),
                            n=("o", "size"))
    g = g[g["n"] >= 25]
    rng = g["h"] - g["l"]
    avg = rng.rolling(20).mean().shift(1)
    out = []
    for dte, r in g.iterrows():
        a = avg.loc[dte]
        R = r["h"] - r["l"]
        if not np.isfinite(a) or R < a or R <= 0:
            continue
        po, pc = (r["o"] - r["l"]) / R, (r["c"] - r["l"]) / R
        exit_ns = _ny_ns(dte, 13, 30)
        if po <= 0.15 and pc >= 0.80:
            _keep(out, _mk(ctx, int(r["i"]), 1, r["l"], max_bars=600, exit_at_ns=exit_ns, tag="open_drive"))
        elif po >= 0.85 and pc <= 0.20:
            _keep(out, _mk(ctx, int(r["i"]), -1, r["h"], max_bars=600, exit_at_ns=exit_ns, tag="open_drive"))
    return out


# ---------------------------------------------------------------------------
# Sesi
# ---------------------------------------------------------------------------

def h12_asia_breakout_london(ctx):
    """Breakout rentang Asia (20:00-00:00 NY) di London (02:00-05:00 NY), M15: close pertama di luar
    rentang → searah; stop di tengah rentang; target 3R; keluar 12:00 NY."""
    x = _htf(ctx, "15min")
    asia = C.session_range(x["t"], x["h"], x["l"], 20 * 60, 0)
    hm, date = x["clk"]["hm"].to_numpy(), x["clk"]["date"].to_numpy()
    out, used = [], set()
    for k in range(len(x["c"])):
        if date[k] in used or not (120 <= hm[k] < 300) or not np.isfinite(asia["hi"][k]):
            continue
        hi, lo = asia["hi"][k], asia["lo"][k]
        d = 1 if x["c"][k] > hi else (-1 if x["c"][k] < lo else 0)
        if d:
            used.add(date[k])
            _keep(out, _mk(ctx, x["m1"][k], d, 0.5 * (hi + lo), max_bars=600, exit_at_ns=_ny_ns(date[k], 12),
                           tag="asia_bo"))
    return out


HYPOTHESES = {
    "ICT_judas_sweep":        (dict(family="ICT", tf="M5"), lambda c: h1_judas(c, False)),
    "ICT_judas_sweep_mss":    (dict(family="ICT", tf="M5"), lambda c: h1_judas(c, True)),
    "ICT_silver_bullet_ldn":  (dict(family="ICT", tf="M5"), lambda c: h2_silver_bullet(c, 3 * 60, 12)),
    "ICT_silver_bullet_am":   (dict(family="ICT", tf="M5"), lambda c: h2_silver_bullet(c, 10 * 60, 16)),
    "ICT_silver_bullet_pm":   (dict(family="ICT", tf="M5"), lambda c: h2_silver_bullet(c, 14 * 60, 16)),
    "ICT_power_of_3":         (dict(family="ICT", tf="M15"), h10_power_of_3),
    "ICT_ote":                (dict(family="ICT", tf="M15"), h11_ote),
    "SMC_sweep_pdh_pdl":      (dict(family="SMC", tf="M15"), h3_sweep_pdh_pdl),
    "SMC_bos_fvg_struct":     (dict(family="SMC", tf="M15"), lambda c: h4_bos_fvg(c, True)),
    "SMC_bos_fvg_tight":      (dict(family="SMC", tf="M15"), lambda c: h4_bos_fvg(c, False)),
    "SMC_order_block_h1":     (dict(family="SMC", tf="H1"), h5_order_block),
    "SMC_turtle_soup":        (dict(family="SMC", tf="M15/D"), h13_turtle_soup),
    "SMC_equal_levels_sweep": (dict(family="SMC", tf="H1/M15"), h14_equal_levels_sweep),
    "AMT_80_rule":            (dict(family="AMT", tf="M30"), h6_80_rule),
    "AMT_ib_breakout":        (dict(family="AMT", tf="M5"), lambda c: h7_initial_balance(c, "breakout")),
    "AMT_ib_failure":         (dict(family="AMT", tf="M5"), lambda c: h7_initial_balance(c, "failure")),
    "AMT_open_drive":         (dict(family="AMT", tf="M1"), h8_open_drive),
    "SES_asia_breakout_ldn":  (dict(family="SESSION", tf="M15"), h12_asia_breakout_london),
}
