"""Uji fitur mikrostruktur (gcquant.features.micro) dengan nilai hitung tangan."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

from gcquant.features import (
    StoikovMicroprice,
    amihud,
    depth_imbalance,
    feature_matrix,
    kyle_lambda,
    make_grid,
    microprice_weighted,
    mlofi,
    ofi_l1,
    on_grid,
    queue_imbalance,
    realized_measures,
    roll_spread,
    trade_flow,
    vpin,
)

NS = 1_000_000_000
T0 = 1_767_600_000 * NS          # 2026-01-05 08:00 UTC (kelipatan menit)


def bbo_frame(rows, t0=T0, dt=NS):
    """rows: (bid_px, bid_sz, ask_px, ask_sz)."""
    df = pd.DataFrame(rows, columns=["bid_px", "bid_sz", "ask_px", "ask_sz"])
    df.insert(0, "ts_recv", t0 + dt * np.arange(len(df), dtype=np.int64))
    df.insert(1, "instrument_id", 1)
    return df


def trades_frame(times_ns, prices, sizes, sides):
    return pd.DataFrame({"ts_recv": np.asarray(times_ns, dtype=np.int64), "instrument_id": 1,
                         "price": np.asarray(prices, dtype=float),
                         "size": np.asarray(sizes, dtype=np.int64), "side": list(sides)})


# ---------------------------------------------------------------------------
# OFI & MLOFI
# ---------------------------------------------------------------------------

OFI_ROWS = [
    (100.0, 5, 100.5, 4),
    (100.0, 7, 100.5, 4),    # bid tetap: +7−5 ; ask tetap: −4+4      → 2
    (100.1, 3, 100.5, 2),    # bid naik: +3 ; ask tetap: −2+4          → 5
    (100.0, 6, 100.4, 1),    # bid turun: −3 ; ask turun: −1           → −4
    (100.0, 6, 100.6, 9),    # bid tetap: 0 ; ask naik: +1             → 1
    (np.nan, 0, 100.6, 9),   # bid kosong (−∞): −6 ; ask tetap: 0      → −6
    (99.9, 2, 100.6, 9),     # bid muncul: +2                          → 2
]


def test_ofi_l1_hand_values():
    e = ofi_l1(bbo_frame(OFI_ROWS))
    assert np.isnan(e.iloc[0])
    assert e.iloc[1:].tolist() == [2.0, 5.0, -4.0, 1.0, -6.0, 2.0]


def test_ofi_per_instrument():
    df = bbo_frame(OFI_ROWS + OFI_ROWS)
    df["instrument_id"] = [1] * 7 + [2] * 7
    df = df.iloc[np.r_[0:3, 7:10, 3:7, 10:14]].reset_index(drop=True)  # diselang
    e = ofi_l1(df)
    got1 = e[df["instrument_id"] == 1].tolist()
    assert np.isnan(got1[0]) and got1[1:] == [2.0, 5.0, -4.0, 1.0, -6.0, 2.0]


def test_mlofi_hand_values():
    book = pd.DataFrame({
        "ts_recv": T0 + np.arange(3) * NS,
        "bid_px_00": [100.0, 100.0, 100.1], "bid_sz_00": [5, 7, 3],
        "ask_px_00": [100.5, 100.5, 100.5], "ask_sz_00": [4, 4, 2],
        "bid_px_01": [99.9, 99.9, 100.0], "bid_sz_01": [2, 1, 7],
        "ask_px_01": [100.6, 100.7, 100.6], "ask_sz_01": [3, 8, 6],
    })
    m = mlofi(book, levels=2)
    assert list(m.columns) == ["mlofi_1", "mlofi_2"]
    pd.testing.assert_series_equal(m["mlofi_1"], ofi_l1(book), check_names=False)
    # level 2, baris 1: bid tetap 99.9 → +1−2 = −1 ; ask naik 100.6→100.7 → +3   ⇒ 2
    # level 2, baris 2: bid naik → +7 ; ask turun 100.7→100.6 → −6               ⇒ 1
    assert np.isnan(m["mlofi_2"].iloc[0])
    assert m["mlofi_2"].iloc[1:].tolist() == [2.0, 1.0]


def test_imbalances_and_weighted_mid():
    df = bbo_frame([(100.0, 5, 100.5, 4), (100.0, 0, 100.5, 0)])
    qi = queue_imbalance(df)
    assert qi.iloc[0] == pytest.approx(1 / 9) and np.isnan(qi.iloc[1])
    # (100*4 + 100.5*5)/9
    assert microprice_weighted(df).iloc[0] == pytest.approx((400 + 502.5) / 9)
    book = pd.DataFrame({"bid_sz_00": [5], "bid_sz_01": [3], "ask_sz_00": [4], "ask_sz_01": [10]})
    assert depth_imbalance(book, 2).iloc[0] == pytest.approx((8 - 14) / 22)
    assert depth_imbalance(book, 1).iloc[0] == pytest.approx(1 / 9)


# ---------------------------------------------------------------------------
# Micro-price Stoikov
# ---------------------------------------------------------------------------

def _stoikov_rows(seq):
    """seq: (mid, bucket) dengan tick 1, spread 1; bucket 1 → I=0.75, bucket 0 → I=0.25."""
    rows = []
    for m, b in seq:
        bs, as_ = (3, 1) if b == 1 else (1, 3)
        rows.append((m - 0.5, bs, m + 0.5, as_))
    return bbo_frame(rows)


def test_stoikov_hand_computed_two_state():
    seq = [(100.5, 1), (100.5, 1), (101.5, 0), (101.5, 1), (100.5, 0), (101.5, 1)]
    mp = StoikovMicroprice(n_imb=2, n_spread=1).fit(_stoikov_rows(seq), horizon_events=1)
    assert mp.tick_size_ == 1.0
    # Hitungan tersimetri dari keadaan 1 (I tinggi), total 5:
    # tanpa gerak→1:1, tanpa gerak→0:1, naik 1→0:1, turun 1→0:2
    np.testing.assert_allclose(mp.Q_[1], [0.2, 0.2])
    np.testing.assert_allclose(mp.R_[1], [0.4, 0.0, 0.0, 0.2])   # K = −1, −½, ½, 1
    np.testing.assert_allclose(mp.T_[1], [0.6, 0.0])
    # G1 = d/(1 − q_s + q_c) = −0.2 ; g* = d/(1 − q_s + q_c − t_s + t_c) = −0.2/1.6
    assert mp.G1_[1] == pytest.approx(-0.2, abs=1e-12)
    assert mp.G_star_[0, 1] == pytest.approx(-0.125, abs=1e-10)
    assert mp.G_star_[0, 0] == pytest.approx(0.125, abs=1e-10)
    assert mp.converged_
    test = _stoikov_rows([(200.5, 1), (200.5, 0)])
    pred = mp.predict(test)
    assert pred.tolist() == pytest.approx([200.5 - 0.125, 200.5 + 0.125])


def _simulate_bbo(n, seed, tick=0.1):
    """Kuotasi sintetis: imbalance memprediksi arah mid (agar g* tak nol)."""
    rng = np.random.default_rng(seed)
    mid = 2000.05
    spr = 1
    rows = []
    for _ in range(n):
        bs, as_ = rng.integers(1, 20, 2)
        imb = bs / (bs + as_)
        rows.append((mid - spr * tick / 2, bs, mid + spr * tick / 2, as_))
        u = rng.random()
        if u < 0.3:
            step = 1 if rng.random() < imb else -1
            mid += step * tick / 2 * (1 if spr == 1 else 1)
            spr = 2 if spr == 1 else 1
            mid = round(mid / (tick / 2)) * (tick / 2)
    df = bbo_frame(rows)
    return df


def test_stoikov_fixed_point_antisymmetry_and_no_lookahead():
    df = _simulate_bbo(6000, 3)
    train, test = df.iloc[:4000], df.iloc[4000:].reset_index(drop=True)
    mp = StoikovMicroprice(n_imb=6, n_spread=2, tick_size=0.1).fit(train, horizon_events=1)
    G = mp.G_star_.ravel()
    # g* adalah titik tetap g* = G1 + B g*  dan antisimetris terhadap flip imbalance
    np.testing.assert_allclose(G, mp.G1_ + mp.B_ @ G, atol=1e-10)
    np.testing.assert_allclose(mp.G_star_, -mp.G_star_[:, ::-1], atol=1e-12)
    assert mp.G_star_[0, -1] > 0 > mp.G_star_[0, 0]
    # prediksi antisimetris pada I tepat 0.5 (batas ember) → mid persis
    half = bbo_frame([(2000.0, 5, 2000.1, 5)])
    assert mp.predict(half).iloc[0] == pytest.approx(2000.05, abs=1e-12)
    # future-perturbation: ubah test setelah baris k → prediksi ≤ k sama
    p1 = mp.predict(test)
    t2 = test.copy()
    t2.loc[1000:, ["bid_sz", "ask_sz"]] = 1
    t2.loc[1000:, ["bid_px", "ask_px"]] += 5.0
    p2 = mp.predict(t2)
    pd.testing.assert_series_equal(p1.iloc[:1000], p2.iloc[:1000])
    # fit hanya dari data latih: mengubah data uji tidak mengubah model
    mp2 = StoikovMicroprice(n_imb=6, n_spread=2, tick_size=0.1).fit(train, horizon_events=1)
    np.testing.assert_array_equal(mp.G_star_, mp2.G_star_)
    # keadaan di luar ruang keadaan (spread 3 tick) → NaN
    wide = bbo_frame([(2000.0, 5, 2000.3, 5)])
    assert np.isnan(mp.predict(wide).iloc[0])
    with pytest.raises(Exception):
        StoikovMicroprice().predict(half)


def test_stoikov_quantile_bins_runs():
    df = _simulate_bbo(3000, 5)
    mp = StoikovMicroprice(n_imb=5, n_spread=2, tick_size=0.1, bins="quantile").fit(df, 2)
    assert mp.converged_ and np.isfinite(mp.G_star_).all()
    np.testing.assert_allclose(mp.G_star_, -mp.G_star_[:, ::-1], atol=1e-12)


# ---------------------------------------------------------------------------
# Aliran trade
# ---------------------------------------------------------------------------

def test_trade_flow_hand_values():
    tr = trades_frame(T0 + np.array([0, 1, 2, 5, 6]) * NS, [1] * 5, [1, 2, 3, 4, 5],
                      ["B", "B", "A", "B", "N"])
    f = trade_flow(tr, window="3s")
    assert f["signed_volume"].tolist() == [1, 3, 0, 4, 4]
    assert f["volume"].tolist() == [1, 3, 6, 4, 9]
    assert f["n_trades"].tolist() == [1, 2, 3, 1, 2]
    assert f["aggressor_ratio"].tolist() == [1.0, 1.0, 0.5, 1.0, 1.0]
    assert f["sign_autocorr"].isna().all()
    # jendela jumlah-trade
    f2 = trade_flow(tr, window=2)
    assert f2["signed_volume"].tolist() == [1, 3, -1, 1, 4]


def test_trade_sign_autocorr_hand_value():
    s = ["B", "B", "A", "A", "B", "B", "A", "A"]
    tr = trades_frame(T0 + np.arange(8) * NS, [1] * 8, [1] * 8, s)
    f = trade_flow(tr, window=8)
    # pasangan x=s[0:7], y=s[1:8]: Σxy=1, x̄=1/7, ȳ=−1/7 → (8/7)/(48/7) = 1/6
    assert f["sign_autocorr"].iloc[-1] == pytest.approx(1 / 6)
    x = np.array([1, 1, -1, -1, 1, 1, -1, -1], float)
    assert f["sign_autocorr"].iloc[-1] == pytest.approx(np.corrcoef(x[:-1], x[1:])[0, 1])


def test_trade_flow_future_perturbation():
    rng = np.random.default_rng(0)
    n = 500
    ts = T0 + np.cumsum(rng.integers(1, 3 * NS, n))
    tr = trades_frame(ts, 2000 + rng.normal(0, 1, n), rng.integers(1, 9, n),
                      rng.choice(["A", "B", "N"], n))
    f1 = trade_flow(tr, "20s")
    tr2 = tr.copy()
    tr2.loc[300:, "size"] = 99
    tr2.loc[300:, "side"] = "A"
    f2 = trade_flow(tr2, "20s")
    pd.testing.assert_frame_equal(f1.iloc[:300], f2.iloc[:300])


# ---------------------------------------------------------------------------
# VPIN
# ---------------------------------------------------------------------------

def test_vpin_aggressor_hand_values():
    t = T0 + np.array([0, 1, 2]) * NS
    tr = trades_frame(t, [10, 10, 10], [3, 4, 5], ["B", "A", "B"])
    v = vpin(tr, bucket_volume=4, n_buckets=2)
    # ember: [B3,S1], [S3,B1], [B4]
    assert v["buy_volume"].tolist() == [3, 1, 4]
    assert v["sell_volume"].tolist() == [1, 3, 0]
    assert v["imbalance"].tolist() == [2, 2, 4]
    assert np.isnan(v["vpin"].iloc[0])
    assert v["vpin"].iloc[1:].tolist() == pytest.approx([0.5, 0.75])
    assert v["ts_recv"].tolist() == [t[1], t[2], t[2]]
    assert isinstance(v.index, pd.DatetimeIndex) and v.index.name == "ts"


def test_vpin_bvc_hand_values():
    minute = 60 * NS
    # 4 bar 1-menit, close 100, 101, 100, 102, volume 10 per bar (dua trade per bar)
    times = np.array([T0 + NS, T0 + 50 * NS, T0 + minute + NS, T0 + minute + 40 * NS,
                      T0 + 2 * minute + 5 * NS, T0 + 2 * minute + 9 * NS,
                      T0 + 3 * minute + 2 * NS, T0 + 3 * minute + 30 * NS])
    prices = [99, 100, 100.5, 101, 101, 100, 101, 102]
    tr = trades_frame(times, prices, [4, 6, 5, 5, 2, 8, 3, 7], ["N"] * 8)
    v = vpin(tr, bucket_volume=10, n_buckets=2, method="bvc", bvc_bar="1min", min_sigma_bars=2)
    # dP = [nan, 1, −1, 2]; σ ekspansif (ddof=1): bar2 √2, bar3 √(7/3)
    f2 = norm.cdf(-1 / math.sqrt(2))
    f3 = norm.cdf(2 / math.sqrt(7 / 3))
    assert v["buy_volume"].iloc[:2].isna().all()
    assert v["buy_volume"].iloc[2:].tolist() == pytest.approx([10 * f2, 10 * f3])
    exp_vpin = (abs(10 * f2 - 10 * (1 - f2)) + abs(10 * f3 - 10 * (1 - f3))) / 20
    assert v["vpin"].iloc[3] == pytest.approx(exp_vpin)
    assert np.isnan(v["vpin"].iloc[2])
    # ember selesai pada waktu TUTUP bar
    assert v["ts_recv"].tolist() == [T0 + k * minute for k in (1, 2, 3, 4)]


def test_vpin_future_perturbation():
    rng = np.random.default_rng(1)
    n = 2000
    ts = T0 + np.cumsum(rng.integers(1, 2 * NS, n))
    tr = trades_frame(ts, 2000 + np.cumsum(rng.normal(0, 0.1, n)), rng.integers(1, 9, n),
                      rng.choice(["A", "B"], n))
    for method in ("aggressor", "bvc"):
        v1 = vpin(tr, 50, 10, method=method, min_sigma_bars=3)
        cut = ts[1200]
        tr2 = tr.copy()
        tr2.loc[1201:, "side"] = "B"
        tr2.loc[1201:, "price"] += 3.0
        v2 = vpin(tr2, 50, 10, method=method, min_sigma_bars=3)
        a = v1[v1["ts_recv"] <= cut]
        b = v2[v2["ts_recv"] <= cut]
        assert len(a) > 20
        pd.testing.assert_frame_equal(a, b)


# ---------------------------------------------------------------------------
# Kyle lambda
# ---------------------------------------------------------------------------

def _kyle_data(n_int, lam, alpha, noise, seed):
    rng = np.random.default_rng(seed)
    minute = 60 * NS
    sv = rng.integers(-20, 21, n_int).astype(float)
    sv[sv == 0] = 1
    eps = rng.normal(0, noise, n_int) if noise else np.zeros(n_int)
    dmid = alpha + lam * sv + eps
    mids = 2000.0 + np.r_[0.0, np.cumsum(dmid)]
    # kuotasi tepat pada setiap batas grid g_k (k = 0..n), trade di tengah interval
    q_t = T0 + minute * np.arange(n_int + 1)
    bbo = pd.DataFrame({"ts_recv": q_t, "instrument_id": 1, "bid_px": mids - 0.05,
                        "ask_px": mids + 0.05, "bid_sz": 5, "ask_sz": 5})
    tr_t = T0 + minute * np.arange(n_int) + 30 * NS
    tr = trades_frame(tr_t, [2000.0] * n_int, np.abs(sv).astype(int),
                      np.where(sv > 0, "B", "A"))
    return bbo, tr, sv, dmid


def test_kyle_lambda_exact_and_textbook_ols():
    bbo, tr, sv, dmid = _kyle_data(80, lam=0.004, alpha=0.01, noise=0.0, seed=0)
    lam = kyle_lambda(bbo, tr, window=20, interval="1min")
    assert lam.index[0] == pd.Timestamp(T0, unit="ns", tz="UTC")
    valid = lam.dropna()
    assert len(valid) == 80 - 20 + 1
    np.testing.assert_allclose(valid.to_numpy(), 0.004, atol=1e-10)
    # dengan noise: sama dengan OLS buku teks (np.polyfit) pada 20 interval terakhir
    bbo, tr, sv, dmid = _kyle_data(80, lam=0.004, alpha=0.0, noise=0.02, seed=1)
    lam = kyle_lambda(bbo, tr, window=20, interval="1min")
    k = 50                                  # indeks grid; interval k memakai sv[k−1]
    slope = np.polyfit(sv[k - 20:k], dmid[k - 20:k], 1)[0]
    assert lam.iloc[k] == pytest.approx(slope, rel=1e-9)
    # future-perturbation
    bbo2 = bbo.copy()
    bbo2.loc[60:, ["bid_px", "ask_px"]] += 7.0
    tr2 = tr.copy()
    tr2.loc[60:, "side"] = "B"
    lam2 = kyle_lambda(bbo2, tr2, window=20, interval="1min")
    pd.testing.assert_series_equal(lam.iloc[:60], lam2.iloc[:60])


# ---------------------------------------------------------------------------
# Ukuran realisasi, Roll, Amihud
# ---------------------------------------------------------------------------

def test_realized_measures_hand_values():
    five = 5 * 60 * NS
    idx = pd.DatetimeIndex(pd.to_datetime(T0 + five * np.arange(5), unit="ns", utc=True))
    px = pd.Series([100.0, 101.0, 100.0, 102.0, 102.0], index=idx)
    rm = realized_measures(px, rule="5min", window=4)
    r1, r2, r3, r4 = math.log(1.01), math.log(100 / 101), math.log(1.02), 0.0
    last = rm.iloc[-1]
    rv = r1 ** 2 + r2 ** 2 + r3 ** 2 + r4 ** 2
    bv = math.pi / 2 * (abs(r2) * abs(r1) + abs(r3) * abs(r2) + abs(r4) * abs(r3))
    assert last["rv"] == pytest.approx(rv, rel=1e-12)
    assert last["bv"] == pytest.approx(bv, rel=1e-12)
    assert last["jump"] == pytest.approx(max(rv - bv, 0.0), rel=1e-12)
    assert last["rs_pos"] == pytest.approx(r1 ** 2 + r3 ** 2, rel=1e-12)
    assert last["rs_neg"] == pytest.approx(r2 ** 2, rel=1e-12)
    assert last["rs_pos"] + last["rs_neg"] == pytest.approx(last["rv"])
    assert last["n"] == 4
    # jendela 2 return: pasangan hanya (r3, r4)
    rm2 = realized_measures(px, rule="5min", window=2)
    assert rm2["bv"].iloc[-1] == pytest.approx(math.pi / 2 * abs(r3) * abs(r4))
    assert rm2["rv"].iloc[-1] == pytest.approx(r3 ** 2)
    # jendela 1 return: tidak ada pasangan → bv 0
    assert realized_measures(px, rule="5min", window=1)["bv"].iloc[2] == 0.0


def test_realized_measures_bars_known_at_close():
    one = 60 * NS
    idx = pd.DatetimeIndex(pd.to_datetime(T0 + one * np.arange(10), unit="ns", utc=True))
    bars = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0,
                         "close": 100.0 + np.arange(10) * 0.5, "volume": 10}, index=idx)
    rm = realized_measures(bars, rule="1min", window=3)
    # close bar yang dibuka T0 baru diketahui T0+1menit → grid pertama = T0+1menit
    assert rm.index[0] == pd.Timestamp(T0 + one, unit="ns", tz="UTC")
    assert rm["ret"].iloc[1] == pytest.approx(math.log(100.5 / 100.0))


def test_realized_future_perturbation():
    rng = np.random.default_rng(2)
    n = 3000
    t = T0 + np.cumsum(rng.integers(1, 5 * NS, n))
    px = pd.Series(2000 * np.exp(np.cumsum(rng.normal(0, 1e-4, n))),
                   index=pd.DatetimeIndex(pd.to_datetime(t, unit="ns", utc=True)))
    a = realized_measures(px, "1min", "30min")
    px2 = px.copy()
    px2.iloc[2000:] *= 1.05
    b = realized_measures(px2, "1min", "30min")
    cut = pd.Timestamp(t[1999], unit="ns", tz="UTC")
    pd.testing.assert_frame_equal(a[a.index <= cut], b[b.index <= cut])


def test_roll_spread_hand_value():
    p = pd.Series([10.0, 11.0, 10.0, 11.0, 10.0])
    s = roll_spread(p, window=5)
    # Δp = [1,−1,1,−1]; pasangan x=[1,−1,1], y=[−1,1,−1]; cov sampel = −4/3
    assert s.iloc[-1] == pytest.approx(2 * math.sqrt(4 / 3))
    x, y = pd.Series([1.0, -1.0, 1.0]), pd.Series([-1.0, 1.0, -1.0])
    assert s.iloc[-1] == pytest.approx(2 * math.sqrt(-x.cov(y)))
    assert s.iloc[:3].isna().all()          # < 2 pasangan
    # kovarians positif (tren) → NaN
    assert np.isnan(roll_spread(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 7.0]), 6).iloc[-1])
    # jendela bergulir = pandas rolling cov pada pasangan
    rng = np.random.default_rng(0)
    # model Roll: harga efisien acak + pantulan bid/ask ±1 (bilangan bulat → aritmetika eksak)
    q = pd.Series(1000.0 + np.cumsum(rng.choice([-1.0, 0.0, 1.0], 300))
                  + rng.choice([-1.0, 1.0], 300))
    rs = roll_spread(q, window=50)
    dp = q.diff()
    cov = dp.rolling(48).cov(dp.shift(1))
    exp = 2 * np.sqrt(-cov.where(cov < 0))
    assert rs.iloc[60:].notna().sum() > 200
    np.testing.assert_allclose(rs.iloc[60:].to_numpy(), exp.iloc[60:].to_numpy(), rtol=1e-8)


def test_amihud_hand_value():
    bars = pd.DataFrame({"close": [100.0, 101.0, 99.99], "volume": [10, 20, 0]},
                        index=pd.date_range("2026-01-05", periods=3, freq="1D", tz="UTC"))
    a = amihud(bars, window=2, multiplier=1.0)
    assert np.isnan(a.iloc[0])
    assert a.iloc[1] == pytest.approx(0.01 / 2020)
    assert a.iloc[2] == pytest.approx(0.01 / 2020)       # bar ber-volume 0 dilewati
    a100 = amihud(bars, window=2, multiplier=100.0)
    assert a100.iloc[1] == pytest.approx(0.01 / 202000)


# ---------------------------------------------------------------------------
# on_grid & feature_matrix
# ---------------------------------------------------------------------------

def test_on_grid_hand_values():
    df = pd.DataFrame({"ts_recv": np.array([1, 3, 3, 7], dtype=np.int64),
                       "v": [10.0, 20.0, 30.0, 40.0], "k": [1, 2, 3, 4]})
    g = np.array([0, 3, 5, 7, 8], dtype=np.int64)
    last = on_grid(df, g)
    assert np.isnan(last["v"].iloc[0])
    assert last["v"].tolist()[1:] == [30.0, 30.0, 40.0, 40.0]
    assert last["ts_recv"].tolist()[1:] == [3, 3, 7, 7]
    s = on_grid(df, g, how="sum")
    assert s["v"].tolist() == [0.0, 60.0, 0.0, 40.0, 0.0]
    c = on_grid(df, g, how="count")
    assert c["v"].tolist() == [0, 3, 0, 1, 0]
    old = on_grid(df, g, max_age=1)
    assert np.isnan(old["v"].iloc[2]) and old["v"].iloc[1] == 30.0 and old["v"].iloc[4] == 40.0
    ser = pd.Series([1.0, 2.0], index=pd.DatetimeIndex(pd.to_datetime([5, 9], unit="ns", utc=True)),
                    name="x")
    og = on_grid(ser, np.array([4, 5, 8, 9], dtype=np.int64))
    assert og.name == "x" and np.isnan(og.iloc[0]) and og.iloc[1:].tolist() == [1.0, 1.0, 2.0]
    assert isinstance(og.index, pd.DatetimeIndex) and og.index.name == "ts"


def test_on_grid_future_perturbation():
    rng = np.random.default_rng(4)
    ts = np.sort(rng.integers(0, 10_000, 400)).astype(np.int64)
    df = pd.DataFrame({"ts_recv": ts, "v": rng.normal(size=400)})
    g = np.arange(0, 10_001, 250, dtype=np.int64)
    t_cut = 5000
    df2 = df.copy()
    df2.loc[df2["ts_recv"] > t_cut, "v"] = 1e6
    for how in ("last", "sum", "mean", "max"):
        a = on_grid(df, g, how=how)
        b = on_grid(df2, g, how=how)
        pd.testing.assert_frame_equal(a[g <= t_cut], b[g <= t_cut])


def _synthetic_book(n, seed, levels=5, tick=0.1):
    rng = np.random.default_rng(seed)
    ts = T0 + np.cumsum(rng.integers(1, 400_000_000, n)).astype(np.int64)
    mid_ticks = 20000 + np.cumsum(rng.choice([-1, 0, 0, 0, 1], n))
    spr = rng.choice([1, 1, 1, 2], n)
    bb = mid_ticks
    ba = mid_ticks + spr
    data = {"ts_recv": ts, "ts_event": ts - 1000, "instrument_id": 1, "symbol": "GCG6"}
    for m in range(levels):
        data[f"bid_px_{m:02d}"] = (bb - m) * tick
        data[f"ask_px_{m:02d}"] = (ba + m) * tick
    for m in range(levels):
        data[f"bid_sz_{m:02d}"] = rng.integers(1, 30, n)
        data[f"ask_sz_{m:02d}"] = rng.integers(1, 30, n)
        data[f"bid_ct_{m:02d}"] = rng.integers(1, 5, n)
        data[f"ask_ct_{m:02d}"] = rng.integers(1, 5, n)
    book = pd.DataFrame(data)
    tt = np.sort(rng.integers(ts[0], ts[-1], n // 3)).astype(np.int64)
    tr = trades_frame(tt, np.full(len(tt), 2000.0), rng.integers(1, 6, len(tt)),
                      rng.choice(["A", "B"], len(tt)))
    return book, tr


def test_feature_matrix_values_and_no_lookahead():
    book, tr = _synthetic_book(3000, 9)
    fm = feature_matrix(book=book, trades=tr, grid="1s", book_levels=3, flow_window="5s")
    for c in ["mid", "spread", "queue_imbalance", "ofi", "ret_mid", "mlofi_1", "mlofi_3",
              "depth_imbalance_3", "signed_volume", "flow_signed_volume", "flow_aggressor_ratio"]:
        assert c in fm.columns
    # ofi per interval = Σ ofi_l1 baris dalam (g−1s, g]; mlofi_1 = ofi
    e = ofi_l1(book)
    g = fm.index.as_unit("ns").asi8
    k = 100
    sel = (book["ts_recv"] > g[k - 1]) & (book["ts_recv"] <= g[k])
    assert fm["ofi"].iloc[k] == pytest.approx(e[sel].sum())
    np.testing.assert_allclose(fm["mlofi_1"], fm["ofi"])
    # mid as-of
    pos = np.searchsorted(book["ts_recv"].to_numpy(), g[k], side="right") - 1
    assert fm["mid"].iloc[k] == pytest.approx((book["bid_px_00"].iloc[pos] + book["ask_px_00"].iloc[pos]) / 2)
    # flow trailing 5s
    tt = tr["ts_recv"].to_numpy()
    w = (tt > g[k] - 5 * NS) & (tt <= g[k])
    sgn = np.where(tr["side"] == "B", 1, -1)
    assert fm["flow_signed_volume"].iloc[k] == (sgn * tr["size"])[w].sum()
    # future-perturbation pada grid eksplisit
    cut = g[len(g) // 2]
    book2, tr2 = book.copy(), tr.copy()
    late = book2["ts_recv"] > cut
    for c in [c for c in book2.columns if c.startswith(("bid_sz", "ask_sz"))]:
        book2.loc[late, c] = 1
    book2.loc[late, "bid_px_00"] -= 1.0
    tr2.loc[tr2["ts_recv"] > cut, "side"] = "B"
    fa = feature_matrix(book=book, trades=tr, grid=g, book_levels=3, flow_window="5s")
    fb = feature_matrix(book=book2, trades=tr2, grid=g, book_levels=3, flow_window="5s")
    pd.testing.assert_frame_equal(fa[g <= cut], fb[g <= cut])
    assert not fa[g > cut].equals(fb[g > cut])


def test_make_grid():
    g = make_grid(T0 + 1, T0 + 3 * NS + 5, "1s")
    assert g.tolist() == [T0 + NS, T0 + 2 * NS, T0 + 3 * NS]
