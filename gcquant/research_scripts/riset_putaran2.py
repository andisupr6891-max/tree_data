"""Riset alpha putaran 2 (hipotesis dari literatur), data gratis XAUUSD M1 2011-05..2018-06.

Protokol (ditetapkan SEBELUM melihat hasil):
- discover: 2011-05-10 .. 2014-12-31; validate: 2015-01-01 .. 2018-06-19 (hanya kandidat beku).
- Lolos penemuan: t >= 3 (net, spread asli). Lolos holdout: total net > 0 dan t >= 2.
- Semua konfigurasi dihitung (lanjutan dari 149 konfigurasi putaran 1).
Harga data = bid; ask = bid + spread. Masuk/keluar di open bar menit.
"""
import json
import sys

import numpy as np
import pandas as pd

S, MODE = sys.argv[1], sys.argv[2]
SPLIT = pd.Timestamp("2015-01-01", tz="UTC")
df = pd.read_pickle(S + "/alpha/m1.pkl")
df = df[df.index < SPLIT] if MODE == "discover" else df[df.index >= SPLIT]
idx = df.index
o = df["open"].to_numpy()
sp = df["spread"].to_numpy()
ns = idx.as_unit("ns").asi8
RESULTS = []


def bar_at(ts, tol_min=3):
    """Indeks bar pertama dengan waktu >= ts dan <= ts + tol (None jika tidak ada)."""
    t = pd.Timestamp(ts).tz_convert("UTC").as_unit("ns").value
    i = np.searchsorted(ns, t)
    if i >= len(ns) or ns[i] - t > tol_min * 60 * 1_000_000_000:
        return None
    return int(i)


def pnl_one(i_in, i_out, d):
    if d > 0:
        return o[i_out] - (o[i_in] + sp[i_in])
    return o[i_in] - (o[i_out] + sp[i_out])


def record(family, name, rows):
    if not rows:
        RESULTS.append(dict(family=family, name=name, n=0))
        return
    pnl = np.array([r[1] for r in rows])
    gross = np.array([r[2] for r in rows])
    times = pd.DatetimeIndex([r[0] for r in rows])
    n = len(pnl)
    m, s = pnl.mean(), pnl.std(ddof=1) if n > 1 else 0.0
    t = m / s * np.sqrt(n) if s > 0 else 0.0
    gm, gs = gross.mean(), gross.std(ddof=1) if n > 1 else 0.0
    yrs = pd.Series(pnl, index=times).groupby(times.year).sum()
    RESULTS.append(dict(family=family, name=name, n=n, mean=round(m, 4), t=round(t, 2),
                        gross_mean=round(gm, 4), gross_t=round(gm / gs * np.sqrt(n), 2) if gs > 0 else 0,
                        total=round(pnl.sum(), 1), win=round((pnl > 0).mean() * 100, 1),
                        pos_years=int((yrs > 0).sum()), years=int(len(yrs)),
                        per_year={int(k): round(v, 1) for k, v in yrs.items()}))


def gross_one(i_in, i_out, d):
    return d * (o[i_out] - o[i_in])


days = pd.DatetimeIndex(sorted(set(idx.tz_convert("America/New_York").normalize())))


def local(day, hh, mm, tz):
    return pd.Timestamp(year=day.year, month=day.month, day=day.day, hour=hh, minute=mm, tz=tz)


# --- F1 momentum intraday (Gao, Han, Li, Zhou 2018 diadaptasi ke jam COMEX) ---
f1 = {"r1": [], "ron_r1": [], "r1_big": []}
abs_hist = []
prev_close_i = None
for d in days:
    if d.weekday() >= 5:
        continue
    a = bar_at(local(d, 8, 20, "America/New_York"))
    b = bar_at(local(d, 8, 50, "America/New_York"))
    e = bar_at(local(d, 13, 0, "America/New_York"))
    x = bar_at(local(d, 13, 30, "America/New_York"))
    if None in (a, b, e, x) or not (a < b < e < x):
        prev_close_i = x
        continue
    r1 = o[b] - o[a]
    ron = (o[a] - o[prev_close_i]) if prev_close_i is not None and prev_close_i < a else 0.0
    for key, sig in (("r1", r1), ("ron_r1", ron + r1)):
        if sig != 0:
            dd = 1 if sig > 0 else -1
            f1[key].append((idx[e], pnl_one(e, x, dd), gross_one(e, x, dd)))
    if len(abs_hist) >= 60 and abs(r1) > np.median(abs_hist[-250:]) and r1 != 0:
        dd = 1 if r1 > 0 else -1
        f1["r1_big"].append((idx[e], pnl_one(e, x, dd), gross_one(e, x, dd)))
    abs_hist.append(abs(r1))
    prev_close_i = x
for k, v in f1.items():
    record("F1 momentum intraday", k, v)

# --- F2 London fix (Caminschi & Heaney 2014; Abrantes-Metz & Metz 2018) ---
f2 = {"pm_fade_post": [], "pm_follow_pre": [], "am_fade_post": [], "am_follow_pre": []}
for d in days:
    if d.weekday() >= 5:
        continue
    for tag, hh, mm in (("pm", 15, 0), ("am", 10, 30)):
        fix = local(d, hh, mm, "Europe/London")
        i_m30 = bar_at(fix - pd.Timedelta(minutes=30))
        i_m10 = bar_at(fix - pd.Timedelta(minutes=10))
        i_fix = bar_at(fix)
        i_p30 = bar_at(fix + pd.Timedelta(minutes=30))
        if None in (i_m30, i_m10, i_fix, i_p30) or not (i_m30 < i_m10 < i_fix < i_p30):
            continue
        pre = o[i_fix] - o[i_m30]
        if pre != 0:
            dd = -1 if pre > 0 else 1
            f2[f"{tag}_fade_post"].append((idx[i_fix], pnl_one(i_fix, i_p30, dd), gross_one(i_fix, i_p30, dd)))
        pre20 = o[i_m10] - o[i_m30]
        if pre20 != 0:
            dd = 1 if pre20 > 0 else -1
            f2[f"{tag}_follow_pre"].append((idx[i_m10], pnl_one(i_m10, i_fix, dd), gross_one(i_m10, i_fix, dd)))
for k, v in f2.items():
    record("F2 London fix", k, v)

# --- F3 gap akhir pekan: pudarkan gap Minggu bila |gap| > 0,5 x ATR harian (20 hari, trailing) ---
daily = df["close"].resample("1D").last().dropna()
dh = df["high"].resample("1D").max().dropna()
dl = df["low"].resample("1D").min().dropna()
atr = (dh - dl).rolling(20).mean().shift(1)          # hanya hari yang sudah lewat
gaps_i = np.where(np.diff(ns) > 24 * 3600 * 1_000_000_000)[0] + 1
f3 = {"gap_fade_60": [], "gap_fade_240": []}
for gi in gaps_i:
    t0 = idx[gi]
    a_ = atr[atr.index < t0.normalize()]
    if a_.empty or np.isnan(a_.iloc[-1]):
        continue
    gap = o[gi] - o[gi - 1]
    if abs(gap) <= 0.5 * a_.iloc[-1]:
        continue
    i_in = bar_at(t0 + pd.Timedelta(minutes=5))
    for hold, key in ((60, "gap_fade_60"), (240, "gap_fade_240")):
        i_out = bar_at(t0 + pd.Timedelta(minutes=5 + hold))
        if i_in is None or i_out is None or i_out <= i_in:
            continue
        dd = -1 if gap > 0 else 1
        f3[key].append((idx[i_in], pnl_one(i_in, i_out, dd), gross_one(i_in, i_out, dd)))
for k, v in f3.items():
    record("F3 gap akhir pekan", k, v)

# --- F4 pergantian bulan: long dari 20:00 GMT hari kerja terakhir s/d 20:00 GMT hari kerja ke-3 ---
f4 = []
bdays = pd.DatetimeIndex(sorted({t.normalize() for t in idx[idx.weekday < 5]}))
by_month = pd.Series(bdays, index=bdays).groupby([bdays.year, bdays.month])
months = list(by_month)
for (k, g), (k2, g2) in zip(months[:-1], months[1:]):
    if len(g2) < 3:
        continue
    t_in = g.iloc[-1] + pd.Timedelta(hours=20)
    t_out = g2.iloc[2] + pd.Timedelta(hours=20)
    i_in, i_out = bar_at(t_in, 30), bar_at(t_out, 30)
    if i_in is None or i_out is None or i_out <= i_in:
        continue
    f4.append((idx[i_in], pnl_one(i_in, i_out, 1), gross_one(i_in, i_out, 1)))
record("F4 pergantian bulan", "tom_long", f4)

# --- F5 dekomposisi sesi: long sesi Asia (22:00-07:00 GMT), short sesi AS (13:30-20:00 GMT) ---
f5 = {"asia_long": [], "us_short": []}
for d in pd.date_range(idx[0].normalize(), idx[-1].normalize(), freq="1D", tz="UTC"):
    if d.weekday() in (5,):
        continue
    if d.weekday() != 4:    # sesi Asia mulai 22:00 hari d (bukan Jumat)
        i_in = bar_at(d + pd.Timedelta(hours=22), 10)
        i_out = bar_at(d + pd.Timedelta(hours=31), 10)
        if i_in is not None and i_out is not None and i_out > i_in:
            f5["asia_long"].append((idx[i_in], pnl_one(i_in, i_out, 1), gross_one(i_in, i_out, 1)))
    if d.weekday() < 5:
        i_in = bar_at(d + pd.Timedelta(hours=13, minutes=30), 10)
        i_out = bar_at(d + pd.Timedelta(hours=20), 10)
        if i_in is not None and i_out is not None and i_out > i_in:
            f5["us_short"].append((idx[i_in], pnl_one(i_in, i_out, -1), gross_one(i_in, i_out, -1)))
for k, v in f5.items():
    record("F5 sesi", k, v)

# --- F6 pembukaan Shanghai: ikuti gerak 01:00-01:30 UTC sampai 07:00 UTC ---
f6 = []
for d in pd.date_range(idx[0].normalize(), idx[-1].normalize(), freq="1D", tz="UTC"):
    if d.weekday() >= 5:
        continue
    a, b, x = bar_at(d + pd.Timedelta(hours=1)), bar_at(d + pd.Timedelta(hours=1, minutes=30)), bar_at(d + pd.Timedelta(hours=7))
    if None in (a, b, x) or not (a < b < x):
        continue
    r = o[b] - o[a]
    if r == 0:
        continue
    dd = 1 if r > 0 else -1
    f6.append((idx[b], pnl_one(b, x, dd), gross_one(b, x, dd)))
record("F6 pembukaan Shanghai", "sge_follow", f6)

out = dict(mode=MODE, n_configs=len(RESULTS), results=RESULTS)
print(json.dumps(out, indent=1))
