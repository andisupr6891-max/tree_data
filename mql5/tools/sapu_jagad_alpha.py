#!/usr/bin/env python3
"""
SAPU JAGAD ALPHA
================
Riset, validasi, dan ekspor model alpha ML (LightGBM) untuk Mesin ALPHA di EA SAPU JAGAD.

Alur (protokol anti-bias, semuanya otomatis):
  1. Data M1 dibagi: PENEMUAN (awal) dan HOLDOUT (akhir, default 30%).
  2. Di periode PENEMUAN saja: dua fold walk-forward memilih horizon & ambang keyakinan.
  3. Pengaturan dibekukan, lalu diuji SEKALI di HOLDOUT (model hanya dilatih dari data PENEMUAN).
  4. Vonis LOLOS bila holdout: total bersih > 0 DAN t-stat >= 2. Vonis ditulis ke file model.
  5. Model final dilatih ulang dengan seluruh data dan diekspor ke file teks untuk EA.
     EA menolak trading dengan model berstatus TIDAK LOLOS (kecuali dipaksa lewat input).

Fitur (dihitung identik di EA, dari candle M15 bid yang sudah tutup):
  anatomi 3 candle terakhir (badan, sumbu atas/bawah, posisi close, range/ATR, volume tick relatif,
  badan x volume), momentum 8 horizon, rasio volatilitas, Efficiency Ratio, variance ratio,
  z-score terhadap EMA 20/50/200, posisi di channel Donchian, waktu GMT & New York (DST), hari,
  menit sejak 08:30 New York.

Butuh: Python 3.9+, pandas, numpy, lightgbm  (pip install pandas numpy lightgbm)

Contoh (Windows):
  python sapu_jagad_alpha.py --data "D:\\dataset\\XAUUSD_M1.csv" --gmt-offset 2 --out "D:\\sapujagad\\alpha"
  Lalu salin alpha\\sapu_jagad_alpha.txt ke folder Common\\Files terminal MT5.
"""

import argparse
import json
import math
import os
import sys
import time as _time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sapu_jagad_forensik as fz  # noqa: E402  (pembaca format data)

MODEL_VERSION = 1
LGB_PARAMS = dict(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=400, subsample=0.7,
                  subsample_freq=1, colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, random_state=7)
HORIZONS = (60, 240, 480)
QUANTILES = (0.90, 0.95, 0.98)


# ----------------------------------------------------------------------------- data
def load_m1(paths, symbol_filter, gmt_offset, point, default_spread):
    """Muat data menjadi bar M1 (bid) berindeks UTC dengan kolom open/high/low/close/tickvol/spread."""
    files = fz.discover_files(paths, symbol_filter)
    frames = []
    for f in files:
        info = fz.inspect_file(f)
        if not info.ok:
            print("  --  dilewati %s: %s" % (f, info.reason))
            continue
        print("  OK  %-5s %s" % (info.kind, f))
        if info.kind == "bar":
            frames.append(_read_bars(info, point, default_spread))
        else:
            frames.append(_ticks_to_m1(info, point, default_spread))
    if not frames:
        raise SystemExit("Tidak ada file data yang bisa dibaca.")
    df = pd.concat(frames)
    df = df[~df.index.duplicated()].sort_index()
    df.index = df.index - pd.Timedelta(hours=gmt_offset)       # waktu server -> UTC
    df.index = df.index.tz_localize("UTC")
    return df


def _read_bars(info, point, default_spread):
    raw = pd.read_csv(info.path, sep=info.delim, header=0 if info.header else None, dtype=str,
                      encoding_errors="replace")
    c = info.cols
    if "datetime" in c:
        ts = raw.iloc[:, c["datetime"]]
    else:
        ts = raw.iloc[:, c["date"]].str.strip() + " " + raw.iloc[:, c["time"]].str.strip()
    t = pd.to_datetime(ts.map(fz.parse_dt), unit="s")
    out = pd.DataFrame({k: pd.to_numeric(raw.iloc[:, c[k]], errors="coerce") for k in ("open", "high", "low", "close")})
    out.index = t.values
    tv_idx = None
    if info.header:
        names = [fz._norm(x) for x in raw.columns]
        for name in ("tickvol", "tickvolume", "volume", "vol"):
            if name in names:
                tv_idx = names.index(name)
                break
    elif raw.shape[1] >= 7:
        tv_idx = 6
    out["tickvol"] = pd.to_numeric(raw.iloc[:, tv_idx], errors="coerce").values if tv_idx is not None else 1.0
    if "spread" in c:
        out["spread"] = pd.to_numeric(raw.iloc[:, c["spread"]], errors="coerce").values * point
        out.loc[out["spread"] <= 0, "spread"] = default_spread
    else:
        out["spread"] = default_spread
    return out.dropna(subset=["open", "high", "low", "close"])


def _ticks_to_m1(info, point, default_spread):
    rows, cur = [], None
    for t, bid, ask in fz.iter_file_ticks(info, point, default_spread):
        m = int(t // 60) * 60
        if cur is None or m != cur[0]:
            if cur is not None:
                rows.append(cur)
            cur = [m, bid, bid, bid, bid, 1, ask - bid]
        else:
            cur[2] = max(cur[2], bid)
            cur[3] = min(cur[3], bid)
            cur[4] = bid
            cur[5] += 1
            cur[6] += ask - bid
    if cur is not None:
        rows.append(cur)
    a = np.array(rows, dtype=float)
    out = pd.DataFrame({"open": a[:, 1], "high": a[:, 2], "low": a[:, 3], "close": a[:, 4],
                        "tickvol": a[:, 5], "spread": a[:, 6] / a[:, 5]}, index=pd.to_datetime(a[:, 0], unit="s"))
    return out


def ns(times):
    """Waktu -> int64 nanodetik (pandas 3 bisa memakai resolusi mikrodetik)."""
    return pd.DatetimeIndex(times).as_unit("ns").asi8


# ----------------------------------------------------------------------------- fitur
FEATURES = []
for _k in range(3):
    FEATURES += ["body_%d" % _k, "uwick_%d" % _k, "lwick_%d" % _k, "clv_%d" % _k, "rngatr_%d" % _k,
                 "vol_%d" % _k, "wbody_%d" % _k]
FEATURES += ["ret_%d" % k for k in (1, 2, 4, 8, 16, 32, 96, 480)]
FEATURES += ["volratio", "er_16", "er_96", "vr_4", "z_ema_20", "z_ema_50", "z_ema_200", "don_32", "don_96",
             "don_480", "gmt_sin", "gmt_cos", "ny_sin", "ny_cos", "dow", "min_since_830"]
WARMUP = 500


def m15_bars(m1):
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "tickvol": "sum", "spread": "mean"}
    return m1.resample("15min", label="left", closed="left").agg(agg).dropna(subset=["open"])


def compute_features(b):
    """b: candle M15 (indeks = waktu buka UTC). Hasil: fitur per candle, dihitung saat candle tutup.
    Definisi ini WAJIB sama dengan fungsi AlphaFeatures() di EA."""
    o, h, l, c, tv = b["open"], b["high"], b["low"], b["close"], b["tickvol"].astype(float)
    rng = h - l
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean()
    atr96 = tr.rolling(96).mean()
    tvm = tv.rolling(96).mean()
    F = pd.DataFrame(index=b.index)

    def div(a, d):
        return (a / d).where(d > 0, 0.0)
    for k in range(3):
        bo, bh, bl, bc, br = o.shift(k), h.shift(k), l.shift(k), c.shift(k), rng.shift(k)
        F["body_%d" % k] = div(bc - bo, br)
        F["uwick_%d" % k] = div(bh - np.maximum(bo, bc), br)
        F["lwick_%d" % k] = div(np.minimum(bo, bc) - bl, br)
        F["clv_%d" % k] = div((bc - bl) - (bh - bc), br)
        F["rngatr_%d" % k] = div(br, atr96.shift(k))
        F["vol_%d" % k] = div(tv.shift(k), tvm.shift(k))
        F["wbody_%d" % k] = F["body_%d" % k] * F["vol_%d" % k]
    for k in (1, 2, 4, 8, 16, 32, 96, 480):
        F["ret_%d" % k] = div(c - c.shift(k), atr96)
    F["volratio"] = div(atr14, atr96)
    for n in (16, 96):
        path = c.diff().abs().rolling(n).sum()
        F["er_%d" % n] = div((c - c.shift(n)).abs(), path)
    d4 = (c - c.shift(4)).rolling(96).var()
    d1 = c.diff().rolling(96).var()
    F["vr_4"] = div(d4, 4 * d1)
    for n in (20, 50, 200):
        F["z_ema_%d" % n] = div(c - c.ewm(span=n, adjust=False).mean(), atr96)
    for n in (32, 96, 480):
        hi, lo = h.rolling(n).max(), l.rolling(n).min()
        F["don_%d" % n] = div(c - lo, hi - lo)
    dec = b.index + pd.Timedelta(minutes=15)
    ny = dec.tz_convert("America/New_York")
    gm = dec.hour + dec.minute / 60.0
    nyh = ny.hour + ny.minute / 60.0
    F["gmt_sin"], F["gmt_cos"] = np.sin(2 * np.pi * gm / 24), np.cos(2 * np.pi * gm / 24)
    F["ny_sin"], F["ny_cos"] = np.sin(2 * np.pi * nyh / 24), np.cos(2 * np.pi * nyh / 24)
    F["dow"] = ny.dayofweek
    since = (ny.hour * 60 + ny.minute) - 510
    F["min_since_830"] = np.where((since >= 0) & (since <= 180) & (ny.dayofweek < 5), since, -1)
    F = F.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    F["atr96"] = atr96
    F["dec_time"] = dec
    return F.iloc[WARMUP:]


def add_targets(F, m1):
    t_m1 = ns(m1.index)
    dec = ns(F["dec_time"])
    mid = (m1["open"] + m1["spread"] / 2).to_numpy()
    p_in = np.minimum(np.searchsorted(t_m1, dec), len(t_m1) - 1)
    F["p_in"] = p_in
    for H in HORIZONS:
        tgt = dec + H * 60_000_000_000
        p_out = np.minimum(np.searchsorted(t_m1, tgt), len(t_m1) - 1)
        ok = (t_m1[p_out] - t_m1[p_in]) <= (H + 30) * 60_000_000_000
        F["p_out_%d" % H] = p_out
        F["fwd_%d" % H] = np.where(ok, mid[p_out] - mid[p_in], np.nan)
    return F


# ----------------------------------------------------------------------------- model & simulasi
def train(F, H):
    import lightgbm as lgb
    d = F[F["fwd_%d" % H].notna()]
    m = lgb.LGBMClassifier(**LGB_PARAMS)
    m.fit(d[FEATURES], (d["fwd_%d" % H] > 0).astype(int))
    return m


def scores(model, F):
    return pd.Series(model.predict_proba(F[FEATURES])[:, 1] - 0.5, index=F.index)


def simulate(F, sc, H, cut, m1, sl_atr, slip=0.0):
    """Satu posisi pada satu waktu. Masuk di open M1 setelah candle M15 tutup, keluar H menit kemudian
    atau saat stop pengaman (sl_atr x ATR96 M15) tersentuh. P/L per 1 oz (= per 0.01 lot), bersih spread."""
    o, hi, lo, sp = (m1[k].to_numpy() for k in ("open", "high", "low", "spread"))
    t_m1 = ns(m1.index)
    p_in = F["p_in"].to_numpy()
    p_out = F["p_out_%d" % H].to_numpy()
    atr = F["atr96"].to_numpy()
    s = sc.reindex(F.index).to_numpy()
    busy, out = -1, []
    for i in range(len(s)):
        a, b = p_in[i], p_out[i]
        if a <= busy or not np.isfinite(s[i]) or abs(s[i]) < cut:
            continue
        if b <= a or (t_m1[b] - t_m1[a]) > (H + 30) * 60_000_000_000:
            continue
        d = 1 if s[i] > 0 else -1
        entry = o[a] + (sp[a] if d > 0 else 0.0)          # beli di ask, jual di bid
        exit_px = None
        if sl_atr > 0 and atr[i] > 0:
            stop = entry - d * sl_atr * atr[i]
            seg_hi, seg_lo = hi[a:b], lo[a:b]
            hit = np.where(seg_lo <= stop)[0] if d > 0 else np.where(seg_hi + sp[a:b] >= stop)[0]
            if len(hit):
                exit_px = stop
                b = a + hit[0]
        if exit_px is None:
            exit_px = o[b] + (sp[b] if d < 0 else 0.0)
        pnl = d * (exit_px - entry) - 2 * slip
        out.append((F.index[i], d, pnl))
        busy = b
    return pd.DataFrame(out, columns=["time", "dir", "pnl"]).set_index("time")


def stats(tr):
    if len(tr) < 2:
        return dict(n=len(tr), mean=0.0, t=0.0, total=0.0, win=0.0)
    p = tr["pnl"]
    sd = p.std(ddof=1)
    t = p.mean() / sd * math.sqrt(len(p)) if sd > 0 else 0.0
    return dict(n=int(len(p)), mean=round(float(p.mean()), 3), t=round(float(t), 2), total=round(float(p.sum()), 1),
                win=round(float((p > 0).mean() * 100), 1))


# ----------------------------------------------------------------------------- ekspor ke EA
def num(x):
    """Angka desimal tanpa notasi ilmiah, presisi round-trip (aman untuk StringToDouble MQL5)."""
    return np.format_float_positional(float(x), unique=True, trim="-")


def export_model(model, H, cut, validated, summary, path):
    """Tulis pohon LightGBM ke file teks yang dibaca Mesin ALPHA di EA."""
    dump = model.booster_.dump_model()
    names = dump["feature_names"]
    assert names == FEATURES, "urutan fitur tidak cocok"
    lines = ["SAPUJAGAD_ALPHA %d" % MODEL_VERSION,
             "validated=%d" % (1 if validated else 0),
             "horizon_min=%d" % H,
             "cut=" + num(cut),
             "n_features=%d" % len(FEATURES),
             "features=" + ",".join(FEATURES),
             "summary=" + json.dumps(summary, separators=(",", ":")),
             "trees=%d" % len(dump["tree_info"])]
    for tree in dump["tree_info"]:
        nodes, leaves = [], []

        def walk(nd):
            if "leaf_index" in nd or "split_index" not in nd:
                leaves.append(nd.get("leaf_value", 0.0))
                return -len(leaves)                      # rujukan daun: -(indeks+1)
            k = len(nodes)
            nodes.append(None)
            left = walk(nd["left_child"])
            right = walk(nd["right_child"])
            if nd.get("decision_type", "<=") != "<=":
                raise ValueError("decision_type tidak didukung: %s" % nd.get("decision_type"))
            nodes[k] = (nd["split_feature"], float(nd["threshold"]), left, right,
                        1 if nd.get("default_left", True) else 0,
                        {"None": 0, "Zero": 1, "NaN": 2}.get(nd.get("missing_type", "None"), 0))
            return k
        root = walk(tree["tree_structure"])
        lines.append("TREE %d %d %d" % (len(nodes), len(leaves), root))
        for f, thr, le, ri, dl, mt in nodes:
            lines.append("N %d %s %d %d %d %d" % (f, num(thr), le, ri, dl, mt))
        for v in leaves:
            lines.append("L " + num(v))
    lines.append("END")
    with open(path, "w", encoding="ascii") as fh:
        fh.write("\n".join(lines) + "\n")


def eval_model_file(path, X):
    """Evaluator independen (logika yang sama dengan EA) untuk membuktikan file model = LightGBM."""
    trees, i = [], 0
    lines = open(path).read().split("\n")
    while not lines[i].startswith("TREE"):
        i += 1
    while lines[i].startswith("TREE"):
        nn, nl, root = (int(x) for x in lines[i].split()[1:])
        nodes = [lines[i + 1 + k].split()[1:] for k in range(nn)]
        leaves = [float(lines[i + 1 + nn + k].split()[1]) for k in range(nl)]
        trees.append(([(int(a), float(b), int(c), int(d), int(e), int(f)) for a, b, c, d, e, f in nodes], leaves, root))
        i += 1 + nn + nl
    out = np.zeros(len(X))
    for r, x in enumerate(X):
        tot = 0.0
        for nodes, leaves, root in trees:
            k = root
            while k >= 0:
                f, thr, le, ri, dl, mt = nodes[k]
                v = x[f]
                if mt == 2 and math.isnan(v):
                    k = le if dl else ri
                    continue
                if mt == 1 and (v == 0.0 or math.isnan(v)):
                    k = le if dl else ri
                    continue
                if math.isnan(v):
                    v = 0.0
                k = le if v <= thr else ri
            tot += leaves[-k - 1]
        out[r] = 1.0 / (1.0 + math.exp(-tot))
    return out


# ----------------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description="Riset & ekspor alpha ML untuk EA SAPU JAGAD")
    ap.add_argument("--data", nargs="+", required=True)
    ap.add_argument("--symbol-filter", default=r"xau|gold")
    ap.add_argument("--gmt-offset", type=float, default=0.0, help="selisih jam waktu data terhadap GMT")
    ap.add_argument("--point", type=float, default=0.01)
    ap.add_argument("--spread", type=float, default=0.20, help="spread bawaan bila data tanpa spread")
    ap.add_argument("--holdout", type=float, default=0.30, help="porsi data terakhir untuk holdout")
    ap.add_argument("--sl-atr", type=float, default=6.0, help="stop pengaman = X x ATR96 M15 (0 = mati)")
    ap.add_argument("--out", default="hasil_alpha")
    ap.add_argument("--cek-paritas", metavar="CSV_EA",
                    help="bandingkan sapu_jagad_alpha_fitur_ea.csv (InpAlphaDumpFeatures=true) dengan fitur Python")
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)

    print("Memuat data...")
    m1 = load_m1(args.data, args.symbol_filter, args.gmt_offset, args.point, args.spread)
    print("  %d bar M1, %s s/d %s, spread median %.3f" % (len(m1), m1.index[0], m1.index[-1], m1["spread"].median()))
    F = compute_features(m15_bars(m1))
    if args.cek_paritas:
        ea = pd.read_csv(args.cek_paritas)
        ea["dec_time"] = pd.to_datetime(ea["dec_time"], format="%Y.%m.%d %H:%M:%S", utc=True)
        py = F.set_index("dec_time")[FEATURES]
        both = ea.set_index("dec_time")[FEATURES].join(py, rsuffix="_py", how="inner")
        if both.empty:
            print("Tidak ada waktu yang sama antara dump EA dan data Python (cek --gmt-offset).")
            return 1
        print("Paritas fitur EA vs Python pada %d candle:" % len(both))
        for name in FEATURES:
            d = (both[name] - both[name + "_py"]).abs().max()
            print("  %-14s selisih maks %.3e %s" % (name, d, "" if d < 1e-4 else "<-- PERIKSA"))
        return 0
    F = add_targets(F, m1)
    t0, t1 = F["dec_time"].iloc[0], F["dec_time"].iloc[-1]
    split = t0 + (t1 - t0) * (1 - args.holdout)
    disc, hold = F[F["dec_time"] < split], F[F["dec_time"] >= split]
    # dua fold walk-forward di dalam periode penemuan: uji di 1/3 tengah dan 1/3 akhir
    d0, d1 = disc["dec_time"].iloc[0], disc["dec_time"].iloc[-1]
    b1, b2 = d0 + (d1 - d0) / 3, d0 + (d1 - d0) * 2 / 3
    folds = [(disc["dec_time"] < b1, (disc["dec_time"] >= b1) & (disc["dec_time"] < b2)),
             (disc["dec_time"] < b2, disc["dec_time"] >= b2)]
    print("Penemuan: %s s/d %s | Holdout: %s s/d %s" % (d0, d1, split, t1))

    rows = []
    for H in HORIZONS:
        fitted = []
        for tr_mask, te_mask in folds:
            te = disc[te_mask]
            tr = disc[tr_mask & (disc["dec_time"] + pd.Timedelta(minutes=H + 30) < te["dec_time"].min())]
            m = train(tr, H)
            fitted.append((te, scores(m, te), scores(m, tr)))
        for q in QUANTILES:
            row = dict(H=H, q=q)
            for j, (te, sc_te, sc_tr) in enumerate(fitted):
                cut = float(np.quantile(np.abs(sc_tr), q))
                st = stats(simulate(te, sc_te, H, cut, m1, args.sl_atr))
                row.update({"n%d" % j: st["n"], "mean%d" % j: st["mean"], "t%d" % j: st["t"], "tot%d" % j: st["total"]})
            rows.append(row)
            print("  H=%d q=%.2f | fold1 n=%d rata2=%+.3f t=%+.2f | fold2 n=%d rata2=%+.3f t=%+.2f" % (
                H, q, row["n0"], row["mean0"], row["t0"], row["n1"], row["mean1"], row["t1"]))
    R = pd.DataFrame(rows)
    R["tmin"] = R[["t0", "t1"]].min(axis=1)
    ok = R[(R.tot0 > 0) & (R.tot1 > 0)]
    report = {"data": [str(m1.index[0]), str(m1.index[-1])], "configs_tested": len(R),
              "discovery": R.to_dict("records")}
    if ok.empty:
        best = R.sort_values("tmin", ascending=False).iloc[0]
        report["frozen"] = None
        print("Tidak ada pengaturan yang positif di kedua fold penemuan -> holdout tetap dijalankan sebagai info.")
    else:
        best = ok.sort_values("tmin", ascending=False).iloc[0]
        report["frozen"] = {"H": int(best.H), "q": float(best.q)}
    H, q = int(best.H), float(best.q)

    # holdout: model dilatih HANYA dari data penemuan (dipurge), diuji sekali
    tr = disc[disc["dec_time"] + pd.Timedelta(minutes=H + 30) < split]
    m = train(tr, H)
    cut = float(np.quantile(np.abs(scores(m, tr)), q))
    trades = simulate(hold, scores(m, hold), H, cut, m1, args.sl_atr)
    trades_slip = simulate(hold, scores(m, hold), H, cut, m1, args.sl_atr, slip=0.05)
    hs, hss = stats(trades), stats(trades_slip)
    per_year = trades["pnl"].groupby(trades.index.year).sum().round(1).to_dict() if len(trades) else {}
    validated = report["frozen"] is not None and hs["total"] > 0 and hs["t"] >= 2.0
    report.update({"holdout": hs, "holdout_slip_0.05": hss, "holdout_per_year": per_year,
                   "verdict": "LOLOS" if validated else "TIDAK LOLOS"})
    trades.to_csv(os.path.join(args.out, "alpha_holdout_trades.csv"))
    print("HOLDOUT (H=%d, q=%.2f): %s | slip 0.05: %s" % (H, q, hs, hss))
    print("VONIS: %s" % report["verdict"])

    # model final: dilatih dengan seluruh data, ambang dari skor latih
    final = train(F, H)
    final_cut = float(np.quantile(np.abs(scores(final, F)), q))
    summary = {"verdict": report["verdict"], "holdout_t": hs["t"], "holdout_mean": hs["mean"], "H": H, "q": q,
               "data_to": str(m1.index[-1])[:10]}
    path = os.path.join(args.out, "sapu_jagad_alpha.txt")
    export_model(final, H, final_cut, validated, summary, path)
    # bukti paritas: evaluator file model (logika EA) == LightGBM
    sample = F[FEATURES].iloc[-500:].to_numpy()
    diff = np.abs(eval_model_file(path, sample) - final.predict_proba(F[FEATURES].iloc[-500:])[:, 1]).max()
    report["parity_max_abs_diff"] = float(diff)
    print("Paritas evaluator file model vs LightGBM: selisih maks %.2e" % diff)
    F.iloc[-300:][FEATURES + ["dec_time"]].to_csv(os.path.join(args.out, "alpha_fitur_terakhir.csv"))
    with open(os.path.join(args.out, "alpha_laporan.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=str)
    print("Model: %s (status %s). Salin ke folder Common\\Files MT5." % (path, report["verdict"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
