"""Riset payoff asimetris (R-multiple) untuk konsep AMT / SMC / ICT pada XAUUSD M1 2011-2018.

Protokol pra-registrasi (ditetapkan sebelum melihat hasil):
- Hipotesis & parameter dibekukan di HYPOTHESES (berkas hipotesis_rr.py); jumlah kombinasi dicatat.
- Penemuan: 2011-05-10 .. 2014-12-31. Holdout: 2015-01-01 .. 2018-06-19, hanya untuk kandidat.
- Lolos penemuan: rata-rata R bersih > 0, t(R) >= 3, profit factor >= 1.2, n >= 60,
  positif di >= 3 dari 4 tahun.
- Lolos holdout: rata-rata R bersih > 0 dan t(R) >= 2.
- TAHAP 2 (deviasi yang diumumkan 2026-10-17 setelah putaran pertama, SEBELUM holdout dibuka):
  payoff 1:3 punya varians besar (sd ≈ 1,9R), sehingga t >= 3 untuk edge +0,1R butuh ±3.000 trade
  — lebih banyak dari yang mungkin dalam 4 tahun. Maka kandidat dengan t >= 1,5, PF >= 1,15,
  positif >= 3 dari 4 tahun, dan n >= 100 di periode penemuan juga diuji SEKALI di holdout dengan
  ambang yang sama (avgR > 0, t >= 2), dan hasilnya dikoreksi untuk jumlah total konfigurasi.
- Biaya: spread asli per menit (masuk long di ask, keluar di bid; short sebaliknya).
  Hasil kotor (spread 0) dilaporkan berdampingan agar terlihat berapa R yang dimakan biaya.

Pemakaian:
  python riset_rr.py <m1.pkl atau folder CSV M1> discover [--only ID,...]
  python riset_rr.py <...> validate --only ID,...
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from gcquant.rr import Bars, simulate, summarize          # noqa: E402
from gcquant.rr import concepts as C                     # noqa: E402

SPLIT = pd.Timestamp("2015-01-01", tz="UTC")


def load_m1(path: str) -> pd.DataFrame:
    if path.endswith(".pkl"):
        df = pd.read_pickle(path)
    else:
        from gcquant.data.free_sources import load_m1_csv
        files = sorted(f for f in os.listdir(path) if f.lower().endswith(".csv"))
        df = pd.concat([load_m1_csv(os.path.join(path, f)) for f in files])
    df = df[~df.index.duplicated()].sort_index()
    if "tickvol" not in df and "volume" in df:
        df = df.rename(columns={"volume": "tickvol"})
    return df


class Ctx:
    """Data + fitur yang dihitung sekali dan dipakai bersama oleh semua hipotesis."""

    def __init__(self, m1: pd.DataFrame):
        self.df = m1
        self.t = m1.index.as_unit("ns").asi8
        self.o, self.h, self.l, self.c = (m1[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        self.sp = m1["spread"].to_numpy(float)
        self.v = m1["tickvol"].to_numpy(float)
        self.net = Bars.from_frame(m1)
        self.gross = Bars.from_frame(m1, zero_spread=True)
        self._cache: dict = {}

    def cached(self, key, fn):
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    def ny(self):
        return self.cached("ny", lambda: C.local_clock(self.t, "America/New_York"))

    def ldn(self):
        return self.cached("ldn", lambda: C.local_clock(self.t, "Europe/London"))

    def htf(self, rule: str):
        """Bar timeframe lebih tinggi + indeks bar M1 terakhir di dalam tiap bar HTF.

        Sinyal pada bar HTF k diketahui saat bar M1 ``last_m1[k]`` tutup; entry di M1 berikutnya.
        Bar HTF yang belum lengkap di akhir data tetap dipakai karena last_m1 menunjuk bar M1
        terakhir yang benar-benar ada (tidak ada data masa depan).
        """
        def build():
            g = self.df.resample(rule, label="left", closed="left")
            out = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                                "close": g["close"].last(), "tickvol": g["tickvol"].sum()}).dropna()
            pos = pd.Series(np.arange(len(self.df)), index=self.df.index)
            last = pos.resample(rule, label="left", closed="left").last().reindex(out.index)
            out["last_m1"] = last.to_numpy().astype(np.int64)
            return out
        return self.cached(("htf", rule), build)

    def atr_m1(self, n=14):
        return self.cached(("atr_m1", n), lambda: C.atr(self.h, self.l, self.c, n))


def run(ctx: Ctx, hyps: dict, only: list[str] | None, period: str):
    results = []
    for hid, (meta, fn) in hyps.items():
        if only and hid not in only:
            continue
        t0 = time.time()
        brackets = fn(ctx)
        net = simulate(ctx.net, brackets)
        gross = simulate(ctx.gross, brackets)
        s = summarize(net, gross)
        s.update(id=hid, period=period, n_signals=len(brackets), secs=round(time.time() - t0, 1), **meta)
        results.append(s)
        print(f"{hid:28s} n={s.get('n', 0):5d} win={s.get('win_pct')}% avgR={s.get('avg_r')} t={s.get('t')} "
              f"PF={s.get('pf')} grossR={s.get('gross_avg_r')} costR={s.get('cost_r')} yrs={s.get('pos_years')}/{s.get('years')}",
              flush=True)
    return results


def verdict_discovery(s: dict) -> bool:
    return (s.get("n", 0) >= 60 and s.get("avg_r", -1) > 0 and s.get("t", 0) >= 3
            and s.get("pf", 0) >= 1.2 and s.get("pos_years", 0) >= 3)


def verdict_stage2(s: dict) -> bool:
    return (s.get("n", 0) >= 100 and s.get("avg_r", -1) > 0 and s.get("t", 0) >= 1.5
            and s.get("pf", 0) >= 1.15 and s.get("pos_years", 0) >= 3)


def verdict_holdout(s: dict) -> bool:
    return s.get("n", 0) >= 30 and s.get("avg_r", -1) > 0 and s.get("t", 0) >= 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("mode", choices=["discover", "validate"])
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default="hasil_rr.json")
    a = ap.parse_args()
    from hipotesis_rr import HYPOTHESES   # noqa: E402  (berkas pra-registrasi)
    m1 = load_m1(a.data)
    m1 = m1[m1.index < SPLIT] if a.mode == "discover" else m1[m1.index >= SPLIT]
    ctx = Ctx(m1)
    only = [x for x in a.only.split(",") if x]
    res = run(ctx, HYPOTHESES, only, a.mode)
    for s in res:
        s["lolos"] = verdict_discovery(s) if a.mode == "discover" else verdict_holdout(s)
        if a.mode == "discover":
            s["kandidat_tahap2"] = verdict_stage2(s)
    with open(a.out, "w") as f:
        json.dump(dict(mode=a.mode, n_configs=len(res), results=res), f, indent=1, default=str)
    print("lolos:", [s["id"] for s in res if s["lolos"]])
    if a.mode == "discover":
        print("kandidat tahap 2:", [s["id"] for s in res if s.get("kandidat_tahap2")])


if __name__ == "__main__":
    main()
