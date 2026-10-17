"""Uji rekonstruksi order book MBO (gcquant.book)."""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gcquant.book import (
    BookError,
    Market,
    OrderBook,
    bbo_from_book,
    book_columns,
    mid,
    replay_mbo,
    spread,
    weighted_mid,
)
from gcquant.core import F_LAST, F_MAYBE_BAD_BOOK, F_SNAPSHOT, F_BAD_TS_RECV

FIXTURE = Path(__file__).parent / "data" / "databento" / "test_data.mbo.dbn.zst"
MBO_COLS = ["ts_recv", "ts_event", "instrument_id", "order_id", "action", "side", "price",
            "size", "flags", "sequence", "channel_id", "publisher_id", "symbol"]


def make_mbo(recs, instrument_id=1, symbol="GCG6", t0=1_767_600_000_000_000_000):
    """Bangun frame MBO kanonik dari daftar tuple (action, side, price, size, oid, flags)."""
    rows = []
    for k, r in enumerate(recs):
        a, s, p, q, o, f = r[:6]
        iid = r[6] if len(r) > 6 else instrument_id
        pub = r[7] if len(r) > 7 else 1
        rows.append(dict(ts_recv=t0 + 1000 * k, ts_event=t0 + 1000 * k - 10, instrument_id=iid,
                         order_id=o, action=a, side=s,
                         price=np.nan if p is None else float(p), size=q, flags=f,
                         sequence=k, channel_id=0, publisher_id=pub, symbol=symbol))
    df = pd.DataFrame(rows, columns=MBO_COLS)
    df["order_id"] = df["order_id"].astype("uint64")
    return df


L, S = F_LAST, F_SNAPSHOT

# Skenario tangan: (action, side, price, size, order_id, flags)
SCENARIO = [
    ("R", "N", None, 0, 0, S),                 # 0  clear awal snapshot
    ("A", "B", 2000.0, 5, 1, S),               # 1
    ("A", "B", 2000.0, 3, 2, S),               # 2
    ("A", "B", 1999.9, 4, 3, S),               # 3
    ("A", "A", 2000.1, 2, 4, S),               # 4
    ("A", "A", 2000.1, 6, 5, S),               # 5
    ("A", "A", 2000.2, 1, 6, S | L),           # 6  akhir snapshot → emit
    ("A", "B", 2000.0, 2, 7, L),               # 7
    ("M", "B", 2000.0, 4, 1, L),               # 8  ukuran turun → prioritas tetap
    ("M", "B", 2000.0, 6, 2, L),               # 9  ukuran naik → ke ekor
    ("C", "B", 2000.0, 1, 1, L),               # 10 cancel parsial → prioritas tetap
    ("M", "B", 1999.9, 2, 7, L),               # 11 harga berubah → ekor level baru
    ("T", "A", 2000.0, 3, 0, 0),               # 12 trade: tidak mengubah buku
    ("F", "B", 2000.0, 3, 1, 0),               # 13 fill: tidak mengubah buku
    ("C", "B", 2000.0, 3, 1, L),               # 14 sisa order 1 terisi penuh → hapus
    ("A", "N", 2000.0, 1, 99, L),              # 15 add sisi N → diabaikan
    ("M", "A", 2000.3, 7, 50, L),              # 16 modify order tak dikenal → add
    ("C", "A", 2000.1, 2, 4, L),               # 17 cancel penuh
    ("C", "A", 2000.1, 6, 5, 0),               # 18 level 2000.1 hilang (belum F_LAST)
    ("A", "A", 2000.1, 3, 8, L),               # 19 level 2000.1 muncul lagi
    ("M", "B", 1999.8, 4, 3, L),               # 20 order 3 pindah ke 1999.8
    ("N", "N", None, 0, 0, L),                 # 21 aksi none
    ("R", "N", None, 0, 0, L),                 # 22 clear
    ("A", "B", 2001.0, 1, 100, L),             # 23
]


def run_scenario(upto):
    bk = OrderBook()
    df = make_mbo(SCENARIO[: upto + 1])
    for _, row in df.iterrows():
        bk.apply(row)
    bk.check()
    return bk


def test_hand_scenario_book_states_and_queue():
    bk = run_scenario(6)
    assert bk.levels("B", 10) == [(2000.0, 8, 2), (1999.9, 4, 1)]
    assert bk.levels("A", 10) == [(2000.1, 8, 2), (2000.2, 1, 1)]
    assert bk.bbo() == (2000.0, 8, 2000.1, 8)
    assert bk.queue_ahead(1) == 0 and bk.queue_ahead(2) == 5 and bk.queue_ahead(5) == 2
    assert bk.depth("B", 1) == 8 and bk.depth("A", 2) == 9

    bk = run_scenario(7)
    assert bk.queue_ahead(7) == 8
    assert bk.queue("B", 2000.0) == [(1, 5), (2, 3), (7, 2)]

    bk = run_scenario(8)        # M turun: 1 tetap di depan
    assert bk.queue("B", 2000.0) == [(1, 4), (2, 3), (7, 2)]
    assert bk.queue_ahead(2) == 4 and bk.queue_ahead(7) == 7

    bk = run_scenario(9)        # M naik: 2 ke ekor
    assert bk.queue("B", 2000.0) == [(1, 4), (7, 2), (2, 6)]
    assert bk.queue_ahead(2) == 6 and bk.queue_ahead(7) == 4
    assert bk.levels("B", 1) == [(2000.0, 12, 3)]

    bk = run_scenario(10)       # cancel parsial: prioritas tetap
    assert bk.queue("B", 2000.0) == [(1, 3), (7, 2), (2, 6)]
    assert bk.queue_ahead(7) == 3

    bk = run_scenario(11)       # harga berubah: ekor level 1999.9
    assert bk.queue("B", 2000.0) == [(1, 3), (2, 6)]
    assert bk.queue("B", 1999.9) == [(3, 4), (7, 2)]
    assert bk.queue_ahead(7) == 4 and bk.queue_ahead(2) == 3
    assert bk.order(7) == {"side": "B", "price": 1999.9, "size": 2,
                           "queue_position": 1, "size_ahead": 4}

    before = run_scenario(11).levels("B", None)
    assert run_scenario(13).levels("B", None) == before     # T, F tidak mengubah buku

    bk = run_scenario(14)
    assert bk.queue("B", 2000.0) == [(2, 6)]
    assert bk.queue_ahead(2) == 0
    assert 1 not in bk.orders

    bk = run_scenario(15)
    assert 99 not in bk.orders and bk.n_ignored == 1

    bk = run_scenario(16)
    assert bk.levels("A", None) == [(2000.1, 8, 2), (2000.2, 1, 1), (2000.3, 7, 1)]

    bk = run_scenario(18)
    assert bk.levels("A", None) == [(2000.2, 1, 1), (2000.3, 7, 1)]
    bk = run_scenario(19)
    assert bk.levels("A", None) == [(2000.1, 3, 1), (2000.2, 1, 1), (2000.3, 7, 1)]

    bk = run_scenario(20)
    assert bk.levels("B", None) == [(2000.0, 6, 1), (1999.9, 2, 1), (1999.8, 4, 1)]

    bk = run_scenario(22)
    assert bk.levels("B", None) == [] and bk.levels("A", None) == [] and len(bk) == 0
    assert np.isnan(bk.bbo()[0]) and bk.bbo()[1] == 0

    bk = run_scenario(23)
    assert bk.bbo()[:2] == (2001.0, 1)


def test_replay_emits_only_on_f_last():
    df = make_mbo(SCENARIO)
    out = replay_mbo(df, n_levels=3)
    last_idx = [k for k, r in enumerate(SCENARIO) if r[5] & L]
    assert len(out) == len(last_idx)
    assert list(out.columns) == book_columns(3)
    assert out["ts_recv"].tolist() == df["ts_recv"].iloc[last_idx].tolist()
    assert out["ts_event"].tolist() == df["ts_event"].iloc[last_idx].tolist()
    assert out["ts_recv"].dtype == np.int64 and out["bid_sz_00"].dtype == np.int64
    r0 = out.iloc[0]                              # akhir snapshot (record 6)
    assert [r0[f"bid_px_{i:02d}"] for i in range(2)] == [2000.0, 1999.9]
    assert np.isnan(r0["bid_px_02"]) and r0["bid_sz_02"] == 0 and r0["bid_ct_02"] == 0
    assert [r0[f"bid_sz_{i:02d}"] for i in range(2)] == [8, 4]
    assert [r0[f"bid_ct_{i:02d}"] for i in range(2)] == [2, 1]
    assert [r0[f"ask_px_{i:02d}"] for i in range(2)] == [2000.1, 2000.2]
    assert [r0[f"ask_sz_{i:02d}"] for i in range(2)] == [8, 1]
    # record 19 (setelah 18 tanpa F_LAST): snapshot konsisten, bukan keadaan antara
    r19 = out.iloc[last_idx.index(19)]
    assert (r19["ask_px_00"], r19["ask_sz_00"], r19["ask_ct_00"]) == (2000.1, 3, 1)
    rlast = out.iloc[-1]
    assert rlast["bid_px_00"] == 2001.0 and np.isnan(rlast["ask_px_00"])
    assert out.attrs["replay"]["n_ignored"] == 1
    assert (out["symbol"] == "GCG6").all()


def test_replay_tob_change_and_every():
    df = make_mbo(SCENARIO)
    last = replay_mbo(df, n_levels=2, emit="last")
    tob = replay_mbo(df, n_levels=2, emit="tob_change")
    l1c = ["bid_px_00", "bid_sz_00", "ask_px_00", "ask_sz_00"]
    l1 = last[l1c].fillna(-1.0)
    changed = (l1 != l1.shift()).any(axis=1)
    changed.iloc[0] = True
    # R pada record 22 memaksa emisi berikutnya (buku kosong ≠ sebelumnya juga)
    exp = last[changed.to_numpy()].reset_index(drop=True)
    pd.testing.assert_frame_equal(tob.reset_index(drop=True), exp, check_dtype=True)
    every = replay_mbo(df, n_levels=2, emit="every")
    assert len(every) == len(df)
    # keadaan antara pada record 18: level 2000.1 kosong, ask terbaik 2000.2
    assert every.iloc[18]["ask_px_00"] == 2000.2


def test_side_mismatch_and_strictness():
    bk = OrderBook()
    bk.apply(dict(action="A", side="B", price=2000.0, size=1, order_id=1, flags=L))
    with pytest.raises(BookError):
        bk.apply(dict(action="M", side="A", price=2000.0, size=1, order_id=1, flags=L))
    with pytest.raises(BookError):
        bk.apply(dict(action="C", side="A", price=2000.0, size=1, order_id=1, flags=L))
    with pytest.raises(BookError):
        bk.apply(dict(action="C", side="B", price=2000.0, size=1, order_id=999, flags=L))
    with pytest.raises(BookError):
        bk.apply(dict(action="C", side="B", price=2000.0, size=5, order_id=1, flags=L))
    with pytest.raises(BookError):
        bk.apply(dict(action="A", side="B", price=2000.0, size=1, order_id=1, flags=L))
    with pytest.raises(BookError):
        bk.apply(dict(action="Z", side="B", price=2000.0, size=1, order_id=1, flags=L))
    # mode lunak: anomali dihitung & buku ditandai basi
    soft = OrderBook(strict=False)
    soft.apply(dict(action="A", side="B", price=2000.0, size=2, order_id=1, flags=L))
    soft.apply(dict(action="C", side="B", price=2000.0, size=1, order_id=999, flags=L))
    assert soft.n_anomalies == 1 and soft.stale
    soft.apply(dict(action="C", side="B", price=2000.0, size=9, order_id=1, flags=L))
    assert 1 not in soft.orders and soft.n_anomalies == 2
    with pytest.raises(BookError):  # perubahan sisi tetap fatal
        soft.apply(dict(action="A", side="A", price=2001.0, size=1, order_id=5, flags=L))
        soft.apply(dict(action="M", side="B", price=2001.0, size=1, order_id=5, flags=L))
    # cancel/modify bersisi N diabaikan aman
    bk2 = OrderBook()
    bk2.apply(dict(action="A", side="B", price=2000.0, size=1, order_id=1, flags=L))
    bk2.apply(dict(action="C", side="N", price=2000.0, size=1, order_id=1, flags=L))
    assert 1 in bk2.orders and bk2.n_ignored == 1


def test_maybe_bad_book_marks_stale_until_r_and_snapshot():
    recs = [
        ("A", "B", 2000.0, 1, 1, L),            # emit
        ("A", "B", 2000.0, 1, 2, L | F_MAYBE_BAD_BOOK),   # basi → tidak emit
        ("A", "B", 1999.0, 1, 3, L),            # masih basi
        ("R", "N", None, 0, 0, S),               # clear, snapshot mulai
        ("A", "B", 1998.0, 2, 4, S),
        ("A", "A", 1998.5, 3, 5, S | L),         # snapshot selesai → emit
        ("A", "A", 1998.6, 1, 6, L),             # emit
    ]
    df = make_mbo(recs)
    out = replay_mbo(df, n_levels=2)
    assert out.attrs["replay"]["n_stale_skipped"] == 2
    assert out["ts_recv"].tolist() == df["ts_recv"].iloc[[0, 5, 6]].tolist()
    assert out.iloc[1]["bid_px_00"] == 1998.0 and out.iloc[1]["ask_sz_00"] == 3
    with_stale = replay_mbo(df, n_levels=2, emit_stale=True)
    assert len(with_stale) == 5


def test_tob_flag_add_replaces_side():
    from gcquant.core import F_TOB
    bk = OrderBook()
    bk.apply(dict(action="A", side="B", price=10.0, size=3, order_id=0, flags=F_TOB | L))
    bk.apply(dict(action="A", side="B", price=10.5, size=2, order_id=0, flags=F_TOB | L))
    assert bk.levels("B", None) == [(10.5, 2, 1)]
    bk.apply(dict(action="A", side="B", price=None, size=0, order_id=0, flags=F_TOB | L))
    assert bk.levels("B", None) == []
    bk.check()


def _fixture_frame():
    import databento as db
    raw = db.DBNStore.from_file(FIXTURE).to_df().reset_index()
    df = pd.DataFrame({
        "ts_recv": pd.DatetimeIndex(raw["ts_recv"]).as_unit("ns").asi8,
        "ts_event": pd.DatetimeIndex(raw["ts_event"]).as_unit("ns").asi8,
        "instrument_id": raw["instrument_id"].astype("int64"),
        "order_id": raw["order_id"].astype("uint64"),
        "action": raw["action"].astype(str),
        "side": raw["side"].astype(str),
        "price": raw["price"].astype("float64"),
        "size": raw["size"].astype("int64"),
        "flags": raw["flags"].astype("int64"),
        "sequence": raw["sequence"].astype("int64"),
        "channel_id": raw["channel_id"].astype("int64"),
        "publisher_id": raw["publisher_id"].astype("int64"),
        "symbol": raw["symbol"].astype(str),
    })
    return df


def test_databento_fixture_replays():
    pytest.importorskip("databento")
    df = _fixture_frame()
    assert len(df) == 4 and (df["flags"] == F_SNAPSHOT | F_BAD_TS_RECV).all()
    mk = Market()
    out = replay_mbo(df, market=mk)
    assert len(out) == 0                     # tidak ada F_LAST di fixture
    bk = mk[5482]
    assert bk.levels("B", None) == [(3675.75, 2, 1), (3675.5, 1, 1), (3675.25, 1, 1), (3675.0, 1, 1)]
    assert bk.levels("A", None) == []
    every = replay_mbo(df, emit="every")
    assert len(every) == 4 and (every["symbol"] == "ESH1").all()
    assert every.iloc[-1]["bid_px_03"] == 3675.0
    assert every.iloc[0]["ts_recv"] == 1609113600000000000

    # jalur record mentah Databento (harga fixed-point int, aksi enum)
    import databento as db
    mk2 = Market()
    for rec in db.DBNStore.from_file(FIXTURE):
        mk2.apply(rec)
    assert mk2[5482].levels("B", None) == bk.levels("B", None)
    mk2[5482].check()


# ---------------------------------------------------------------------------
# Uji properti acak: buku teragregasi = hitung ulang brute force dari dict order
# ---------------------------------------------------------------------------

class RefBook:
    """Model rujukan sederhana: dict order + nomor prioritas."""

    def __init__(self):
        self.orders = {}     # oid -> [side, px_key, size, prio]
        self.ctr = 0

    def apply(self, a, s, pk, q, o):
        if a in "TFN":
            return
        if a == "R":
            self.orders.clear()
            return
        if s not in ("A", "B"):
            return
        if a == "A" or (a == "M" and o not in self.orders):
            self.ctr += 1
            self.orders[o] = [s, pk, q, self.ctr]
        elif a == "C":
            od = self.orders[o]
            od[2] -= q
            if od[2] == 0:
                del self.orders[o]
        elif a == "M":
            od = self.orders[o]
            if pk != od[1] or q > od[2]:
                self.ctr += 1
                od[3] = self.ctr
            od[1], od[2] = pk, q

    def levels(self, side, n):
        agg = {}
        for s, pk, q, _ in self.orders.values():
            if s == side:
                a = agg.setdefault(pk, [0, 0])
                a[0] += q
                a[1] += 1
        keys = sorted(agg, reverse=(side == "B"))[:n]
        return [(k, agg[k][0], agg[k][1]) for k in keys]

    def queue_ahead(self, o):
        s, pk, _, pr = self.orders[o]
        return sum(q for (s2, pk2, q, pr2) in self.orders.values()
                   if s2 == s and pk2 == pk and pr2 < pr)


def random_stream(n, seed, n_inst=2, n_pub=1, p_last=0.7, depth=15):
    """Aliran MBO acak yang valid (tanpa anomali) untuk beberapa instrumen/publisher."""
    rng = np.random.default_rng(seed)
    refs = {(i, p): RefBook() for i in range(1, n_inst + 1) for p in range(1, n_pub + 1)}
    recs = []
    next_oid = 1
    for _ in range(n):
        key = (int(rng.integers(1, n_inst + 1)), int(rng.integers(1, n_pub + 1)))
        ref = refs[key]
        live = list(ref.orders)
        u = rng.random()
        flags = F_LAST if rng.random() < p_last else 0
        if u < 0.005:
            rec = ("R", "N", None, 0, 0, flags)
        elif u < 0.02:
            rec = (str(rng.choice(["T", "F", "N"])), str(rng.choice(["A", "B", "N"])),
                   2000.0, int(rng.integers(1, 5)), 0, flags)
        elif u < 0.03:
            rec = ("A", "N", 2000.0, 1, next_oid, flags)
            next_oid += 1
        elif u < 0.45 or not live:
            side = "B" if rng.random() < 0.5 else "A"
            tick = int(rng.integers(0, depth))
            px = round(2000.0 - 0.1 * tick, 1) if side == "B" else round(2000.1 + 0.1 * tick, 1)
            rec = ("A", side, px, int(rng.integers(1, 10)), next_oid, flags)
            next_oid += 1
        else:
            o = live[int(rng.integers(len(live)))]
            s, pk, q, _ = ref.orders[o]
            px = pk / 1e9
            v = rng.random()
            if v < 0.3:
                rec = ("C", s, px, q, o, flags)                      # cancel penuh
            elif v < 0.45 and q > 1:
                rec = ("C", s, px, int(rng.integers(1, q)), o, flags)  # parsial
            elif v < 0.6 and q > 1:
                rec = ("M", s, px, int(rng.integers(1, q)), o, flags)  # turun
            elif v < 0.7:
                rec = ("M", s, px, q + int(rng.integers(1, 5)), o, flags)  # naik
            elif v < 0.85:
                step = 0.1 * int(rng.integers(1, 4)) * (1 if rng.random() < 0.5 else -1)
                rec = ("M", s, round(px + step, 1), int(rng.integers(1, 10)), o, flags)
            elif v < 0.9:
                rec = ("M", s, px, q, o, flags)                      # tak berubah
            else:
                rec = ("F", s, px, q, o, flags)
        a, s, p, q, o, f = rec
        pk = None if p is None else int(round(p * 1e9))
        ref.apply(a, s, pk, q, o)
        recs.append(rec + key)
    return recs


def _ref_rows(recs, n_levels, n_inst, n_pub):
    refs = {(i, p): RefBook() for i in range(1, n_inst + 1) for p in range(1, n_pub + 1)}
    out = []
    for a, s, p, q, o, f, iid, pub in recs:
        pk = None if p is None else int(round(p * 1e9))
        refs[(iid, pub)].apply(a, s, pk, q, o)
        row = {}
        for side, nm in (("B", "bid"), ("A", "ask")):
            agg = {}
            for pb in range(1, n_pub + 1):
                for k, sz, ct in refs[(iid, pb)].levels(side, 10 ** 9):
                    x = agg.setdefault(k, [0, 0])
                    x[0] += sz
                    x[1] += ct
            keys = sorted(agg, reverse=(side == "B"))[:n_levels]
            for j in range(n_levels):
                if j < len(keys):
                    row[f"{nm}_px_{j:02d}"] = keys[j] / 1e9
                    row[f"{nm}_sz_{j:02d}"] = agg[keys[j]][0]
                    row[f"{nm}_ct_{j:02d}"] = agg[keys[j]][1]
                else:
                    row[f"{nm}_px_{j:02d}"] = np.nan
                    row[f"{nm}_sz_{j:02d}"] = 0
                    row[f"{nm}_ct_{j:02d}"] = 0
        out.append(row)
    return pd.DataFrame(out)


@pytest.mark.parametrize("seed,n_pub", [(0, 1), (1, 1), (2, 2)])
def test_random_streams_match_bruteforce(seed, n_pub):
    n_inst = 2
    recs = random_stream(3000, seed, n_inst=n_inst, n_pub=n_pub)
    df = make_mbo(recs)
    # (a) penerapan inkremental + invarian + queue_ahead vs brute force
    mk = Market()
    refs = {(i, p): RefBook() for i in range(1, n_inst + 1) for p in range(1, n_pub + 1)}
    rng = np.random.default_rng(seed + 100)
    for k, row in enumerate(df.itertuples(index=False)):
        mk.apply(row)
        a, s, p, q, o, f, iid, pub = recs[k]
        ref = refs[(iid, pub)]
        ref.apply(a, s, None if p is None else int(round(p * 1e9)), q, o)
        bk = mk[(iid, pub)]
        if k % 50 == 0:
            bk.check()
        assert bk.levels("B", None) == [(pk / 1e9, sz, ct) for pk, sz, ct in ref.levels("B", 10 ** 9)]
        assert bk.levels("A", None) == [(pk / 1e9, sz, ct) for pk, sz, ct in ref.levels("A", 10 ** 9)]
        if ref.orders and k % 7 == 0:
            for oo in rng.choice(list(ref.orders), size=min(3, len(ref.orders)), replace=False):
                assert bk.queue_ahead(int(oo)) == ref.queue_ahead(int(oo))
    # (b) replay emit="every" = brute force setelah setiap record (teragregasi lintas publisher)
    every = replay_mbo(df, n_levels=5, emit="every")
    exp = _ref_rows(recs, 5, n_inst, n_pub)
    got = every[exp.columns].reset_index(drop=True)
    pd.testing.assert_frame_equal(got, exp, check_dtype=False)
    # (c) emit="last" = subset baris ber-F_LAST
    last = replay_mbo(df, n_levels=5, emit="last")
    mask = (df["flags"] & F_LAST).to_numpy() > 0
    pd.testing.assert_frame_equal(last.reset_index(drop=True),
                                  every[mask].reset_index(drop=True))


@pytest.mark.parametrize("n_levels,p_last,depth", [(1, 0.5, 6), (3, 0.02, 10), (10, 0.9, 8),
                                                    (20, 0.002, 30)])
def test_random_streams_levels_and_sparse_f_last(n_levels, p_last, depth):
    # banyak perubahan menumpuk di antara F_LAST (termasuk > 512 sentuhan) dan
    # buku lebih dangkal/dalam dari n_levels → menguji cache inkremental level
    recs = random_stream(4000, 11 + n_levels, n_inst=1, p_last=p_last, depth=depth)
    df = make_mbo(recs)
    every = replay_mbo(df, n_levels=n_levels, emit="every")
    exp = _ref_rows(recs, n_levels, 1, 1)
    pd.testing.assert_frame_equal(every[exp.columns].reset_index(drop=True), exp, check_dtype=False)
    last = replay_mbo(df, n_levels=n_levels, emit="last")
    mask = (df["flags"] & F_LAST).to_numpy() > 0
    pd.testing.assert_frame_equal(last.reset_index(drop=True), every[mask].reset_index(drop=True))
    # tob_change = baris "last" yang L1-nya berbeda dari baris tob terakhir
    tob = replay_mbo(df, n_levels=n_levels, emit="tob_change")
    l1 = last[["bid_px_00", "bid_sz_00", "ask_px_00", "ask_sz_00"]].fillna(-1.0).to_numpy()
    keep, prev = [], None
    for k in range(len(l1)):
        cur = tuple(l1[k])
        if cur != prev:
            keep.append(k)
            prev = cur
    pd.testing.assert_frame_equal(tob.reset_index(drop=True), last.iloc[keep].reset_index(drop=True))


def test_chunked_replay_with_market_reuse_equals_single_pass():
    recs = random_stream(3000, 21, n_inst=2, n_pub=1)
    df = make_mbo(recs)
    full = replay_mbo(df, n_levels=4)
    mk = Market()
    parts = [replay_mbo(df.iloc[a:b], n_levels=4, market=mk) for a, b in
             ((0, 1000), (1000, 1001), (1001, 2500), (2500, 3000))]
    joined = pd.concat(parts, ignore_index=True)
    pd.testing.assert_frame_equal(joined, full)
    # n_levels berbeda pada Market yang sama → cache dibangun ulang dengan benar
    mk2 = Market()
    replay_mbo(df.iloc[:1500], n_levels=2, market=mk2)
    tail = replay_mbo(df.iloc[1500:], n_levels=4, market=mk2)
    exp = full[full["ts_recv"] > df["ts_recv"].iloc[1499]].reset_index(drop=True)
    pd.testing.assert_frame_equal(tail.reset_index(drop=True), exp)


def test_replay_no_lookahead_future_perturbation():
    recs = random_stream(2000, 7)
    df = make_mbo(recs)
    out = replay_mbo(df, n_levels=5)
    k = 1200
    t_cut = df["ts_recv"].iloc[k]
    df2 = df.copy()
    # ubah semua record setelah k (harga, ukuran, aksi) → buku pada t <= t_cut tidak boleh berubah
    rng = np.random.default_rng(1)
    tail = df2.index > k
    df2.loc[tail, "size"] = rng.integers(1, 50, tail.sum())
    df2.loc[tail, "action"] = "A"
    df2.loc[tail, "side"] = rng.choice(["A", "B"], tail.sum())
    df2.loc[tail, "price"] = np.round(1990.0 + 0.1 * rng.integers(0, 200, tail.sum()), 1)
    df2.loc[tail, "order_id"] = np.arange(10 ** 9, 10 ** 9 + tail.sum(), dtype="uint64")
    out2 = replay_mbo(df2, n_levels=5)
    a = out[out["ts_recv"] <= t_cut].reset_index(drop=True)
    b = out2[out2["ts_recv"] <= t_cut].reset_index(drop=True)
    assert len(a) > 100
    pd.testing.assert_frame_equal(a, b)


def test_market_aggregates_publishers():
    mk = Market()
    mk.apply(dict(action="A", side="B", price=100.0, size=2, order_id=1, flags=L,
                  instrument_id=7, publisher_id=1))
    mk.apply(dict(action="A", side="B", price=100.0, size=3, order_id=1, flags=L,
                  instrument_id=7, publisher_id=2))
    mk.apply(dict(action="A", side="B", price=101.0, size=1, order_id=2, flags=L,
                  instrument_id=7, publisher_id=2))
    mk.apply(dict(action="A", side="A", price=102.0, size=4, order_id=3, flags=L,
                  instrument_id=7, publisher_id=1))
    assert mk.levels(7, "B", 5) == [(101.0, 1, 1), (100.0, 5, 2)]
    assert mk.bbo(7) == (101.0, 1, 102.0, 4)
    assert mk.depth(7, "B", 2) == 6
    with pytest.raises(BookError):
        mk.book(7)
    assert mk[(7, 1)].bbo() == (100.0, 2, 102.0, 4)
    assert 7 in mk and list(mk) == [7]


def test_l1_helpers_hand_values():
    df = make_mbo([("A", "B", 100.0, 3, 1, L), ("A", "A", 100.5, 1, 2, L),
                   ("C", "A", 100.5, 1, 2, L)])
    book = replay_mbo(df, n_levels=2)
    bbo = bbo_from_book(book)
    assert list(bbo.columns) == ["ts_recv", "ts_event", "instrument_id", "symbol",
                                 "bid_px", "ask_px", "bid_sz", "ask_sz"]
    m = mid(bbo)
    assert np.isnan(m.iloc[0]) and m.iloc[1] == 100.25 and np.isnan(m.iloc[2])
    assert spread(bbo).iloc[1] == 0.5
    # weighted mid: (100*1 + 100.5*3)/4 = 100.375
    assert weighted_mid(bbo).iloc[1] == pytest.approx(100.375, abs=1e-12)
    assert weighted_mid(book).iloc[1] == pytest.approx(100.375, abs=1e-12)
    dup = book.iloc[[0, 1, 1, 2]].reset_index(drop=True)
    ch = bbo_from_book(dup, only_changes=True)
    assert ch.index.tolist() == [0, 1, 3]


def test_replay_performance():
    # ~300k record dalam waktu wajar (pure Python)
    rng = np.random.default_rng(3)
    n = 300_000
    side = rng.choice(np.array(["A", "B"]), n)
    tick = rng.integers(0, 40, n)
    price = np.where(side == "B", 2000.0 - 0.1 * tick, 2000.1 + 0.1 * tick)
    # add semua lalu cancel separuhnya dengan urutan acak
    oid = np.arange(1, n + 1, dtype="uint64")
    k = n // 2
    canc = rng.permutation(k)
    df = pd.DataFrame({
        "ts_recv": np.arange(n + k, dtype="int64"),
        "instrument_id": 1,
        "order_id": np.concatenate([oid, oid[canc]]),
        "action": np.concatenate([np.full(n, "A"), np.full(k, "C")]),
        "side": np.concatenate([side, side[canc]]),
        "price": np.concatenate([price, price[canc]]),
        "size": np.concatenate([np.full(n, 2), np.full(k, 2)]),
        "flags": F_LAST,
    })
    t = time.perf_counter()
    out = replay_mbo(df, n_levels=10)
    dt = time.perf_counter() - t
    assert len(out) == n + k
    assert dt < 30, f"replay terlalu lambat: {dt:.1f}s"
