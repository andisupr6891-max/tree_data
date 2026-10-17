import numpy as np
import pandas as pd
import pytest

from gcquant.rr import Bars, Bracket, simulate, summarize, breakeven_winrate
from gcquant.rr import concepts as C


def make_bars(rows, spread=0.2, start="2026-01-05 14:00"):
    t = pd.date_range(start, periods=len(rows), freq="1min", tz="UTC")
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=t)
    df["spread"] = spread
    return df


def test_long_target_tepat_3R_dikurangi_spread():
    # sinyal di bar 0; entry di open bar 1 = 100 (bid), ask 100.2; stop 99 → R = 1
    df = make_bars([(100, 100, 100, 100), (100, 100.5, 99.5, 100.4), (100.4, 103.2, 100.3, 103)])
    tr = simulate(Bars.from_frame(df), [Bracket(0, +1, stop=99.0, r_target=3.0)])
    assert len(tr) == 1
    row = tr.iloc[0]
    assert row.outcome == "target"
    assert row.pnl == pytest.approx(103.0 - 100.2)     # keluar di bid 103, masuk di ask 100.2
    assert row.r == pytest.approx(2.8)


def test_stop_dan_target_bar_sama_dianggap_stop():
    df = make_bars([(100, 100, 100, 100), (100, 100, 100, 100), (100, 104, 98, 100)])
    tr = simulate(Bars.from_frame(df), [Bracket(0, +1, stop=99.0, r_target=3.0)])
    assert tr.iloc[0].outcome == "stop"
    assert tr.iloc[0].r == pytest.approx(-(1 + 0.2))


def test_gap_melewati_stop_diisi_di_open():
    df = make_bars([(100, 100, 100, 100), (100, 100.1, 99.9, 100), (97, 97.5, 96, 97)])
    tr = simulate(Bars.from_frame(df), [Bracket(0, +1, stop=99.0, r_target=3.0)])
    assert tr.iloc[0].exit == pytest.approx(97.0)
    assert tr.iloc[0].r == pytest.approx((97 - 100.2) / 1.0)


def test_short_simetris_dengan_long():
    # short: entry di bid open 100, ask 100.2 = ref; stop 101.2 (skala ask) → R = 1
    df = make_bars([(100, 100, 100, 100), (100, 100.1, 99.9, 100), (99.9, 99.9, 96.8, 97)])
    tr = simulate(Bars.from_frame(df), [Bracket(0, -1, stop=101.2, r_target=3.0)])
    row = tr.iloc[0]
    assert row.outcome == "target"
    assert row.r == pytest.approx(2.8)     # sama dengan kasus long: 3R − spread


def test_tanpa_spread_hasil_kotor():
    df = make_bars([(100, 100, 100, 100), (100, 100.5, 99.5, 100.4), (100.4, 103.2, 100.3, 103)])
    tr = simulate(Bars.from_frame(df, zero_spread=True), [Bracket(0, +1, stop=99.0, r_target=3.0)])
    assert tr.iloc[0].r == pytest.approx(3.0)


def test_impas_berlaku_bar_berikutnya():
    df = make_bars([(100, 100, 100, 100), (100, 101.6, 99.9, 101.5), (101.5, 101.5, 99.0, 99.5)])
    tr = simulate(Bars.from_frame(df, zero_spread=True),
                  [Bracket(0, +1, stop=99.0, r_target=3.0, be_at_r=1.5)])
    assert tr.iloc[0].outcome == "impas"
    assert tr.iloc[0].r == pytest.approx(0.0)


def test_batas_waktu_dan_tanpa_tumpang_tindih():
    rows = [(100, 100.1, 99.9, 100)] * 20
    df = make_bars(rows)
    br = [Bracket(0, +1, stop=99.0, r_target=3.0, max_bars=5), Bracket(2, +1, stop=99.0, max_bars=5),
          Bracket(10, +1, stop=99.0, max_bars=5)]
    tr = simulate(Bars.from_frame(df), br)
    assert list(tr.i_signal) == [0, 10]
    assert (tr.outcome == "waktu").all()


def test_order_limit():
    df = make_bars([(100, 100, 100, 100), (100, 100.2, 99.8, 100), (99.6, 99.7, 99.2, 99.5),
                    (99.5, 103, 99.4, 102.9)], spread=0.1)
    # limit beli di 99.5 (ask): ask low bar2 = 99.3 ≤ 99.5 → isi di min(99.5, ask open 99.7)
    tr = simulate(Bars.from_frame(df), [Bracket(0, +1, stop=98.4, r_target=3.0, entry_limit=99.5, limit_bars=3)])
    row = tr.iloc[0]
    assert row.i_entry == 2 and row.fill == pytest.approx(99.5)
    assert row.ref == pytest.approx(99.4) and row.risk == pytest.approx(1.0)


def test_ringkasan_dan_impas():
    tr = pd.DataFrame({"r": [3.0, -1.0, -1.0, -1.0], "risk": 1.0, "outcome": "x",
                       "t_entry": pd.date_range("2020-01-01", periods=4, freq="200D", tz="UTC")})
    s = summarize(tr)
    assert s["avg_r"] == 0.0 and s["pf"] == 1.0 and s["max_loss_streak"] == 3
    assert breakeven_winrate(3.0) == pytest.approx(0.25)
    assert breakeven_winrate(3.0, 0.2) == pytest.approx(0.30)


# --------------------------- konsep ---------------------------------------

def rand_bars(n=4000, seed=0):
    rng = np.random.default_rng(seed)
    c = 2000 + np.cumsum(rng.normal(0, 0.3, n))
    o = np.concatenate([[c[0]], c[:-1]])
    h = np.maximum(o, c) + rng.random(n) * 0.3
    l = np.minimum(o, c) - rng.random(n) * 0.3
    t = pd.date_range("2026-01-05", periods=n, freq="1min", tz="UTC").as_unit("ns").asi8
    v = rng.integers(1, 100, n).astype(float)
    return t, o, h, l, c, v


def _perturb(arrs, k):
    out = [a.copy() for a in arrs]
    for a in out[1:]:
        a[k:] += 37.0
    return out


@pytest.mark.parametrize("k", [1500, 2999])
def test_semua_detektor_kausal(k):
    t, o, h, l, c, v = rand_bars()
    t2, o2, h2, l2, c2 = _perturb([t, o, h, l, c], k)
    a1, a2 = C.atr(h, l, c), C.atr(h2, l2, c2)
    assert np.allclose(a1[:k], a2[:k], equal_nan=True)
    s1, s2 = C.swings(h, l), C.swings(h2, l2)
    for key in s1:
        assert np.array_equal(s1[key][:k], s2[key][:k], equal_nan=key.endswith("px"))
    b1, b2 = C.structure_breaks(c, s1), C.structure_breaks(c2, s2)
    assert np.array_equal(b1["bos"][:k], b2["bos"][:k])
    f1, f2 = C.fvg(h, l, o, c, a1, 0.1), C.fvg(h2, l2, o2, c2, a2, 0.1)
    assert np.array_equal(f1["dir"][:k], f2["dir"][:k])
    r1 = C.session_range(t, h, l, 20 * 60, 0)
    r2 = C.session_range(t2, h2, l2, 20 * 60, 0)
    assert np.allclose(r1["hi"][:k], r2["hi"][:k], equal_nan=True)
    p1 = C.prior_day_levels(t, o, h, l, c)
    p2 = C.prior_day_levels(t2, o2, h2, l2, c2)
    assert np.allclose(p1["pdh"][:k], p2["pdh"][:k], equal_nan=True)
    v1 = C.prior_day_profile(t, h, l, v)
    v2 = C.prior_day_profile(t2, h2, l2, v)
    assert np.allclose(v1["poc"][:k], v2["poc"][:k], equal_nan=True)
    i1 = C.initial_balance(t, h, l)
    i2 = C.initial_balance(t2, h2, l2)
    assert np.allclose(i1["ib_hi"][:k], i2["ib_hi"][:k], equal_nan=True)


def test_fvg_dan_bos_contoh_manual():
    h = np.array([10, 11, 13, 14, 15.0])
    l = np.array([9, 10, 11.5, 13, 14.0])
    o = np.array([9.5, 10, 11.6, 13.1, 14.1])
    c = np.array([10, 11, 12.9, 13.9, 14.9])
    f = C.fvg(h, l, o, c)
    assert f["dir"][2] == 1 and f["bottom"][2] == 10 and f["top"][2] == 11.5
    assert f["dir"][3] == 1 and f["bottom"][3] == 11 and f["top"][3] == 13


def test_volume_profile_value_area():
    # semua volume di satu bar sempit → POC di sana, VA mencakup ≥70%
    h = np.array([101.0, 105.0, 100.6])
    l = np.array([100.0, 104.0, 100.4])
    v = np.array([10.0, 1.0, 50.0])
    vp = C.volume_profile(h, l, v, bin_size=0.5)
    assert 100.0 <= vp["poc"] <= 101.0
    inside = vp["hist"][(vp["edges"][:-1] >= vp["val"] - 1e-9) & (vp["edges"][1:] <= vp["vah"] + 1e-9)].sum()
    assert inside >= 0.7 * vp["hist"].sum()


def test_sapuan_likuiditas():
    h = np.array([10.0, 12.0, 11.0])
    l = np.array([9.0, 9.5, 8.0])
    c = np.array([9.5, 10.5, 9.2])
    lvl_hi = np.array([np.nan, 11.0, 11.5])
    lvl_lo = np.array([np.nan, 9.0, 8.5])
    s = C.sweep(h, l, c, lvl_hi, lvl_lo)
    assert list(s) == [0, -1, 1]
