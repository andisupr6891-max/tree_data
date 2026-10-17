"""Uji sumber data: pengaman biaya Databento (klien palsu, TANPA jaringan), pembaca DBN untuk
semua fixture, penulis DBN sintetis, LiveFeed, dan berkas lokal (M1 MT5, CSV harian, resample)."""
from __future__ import annotations

import datetime as dt
import json
import math
import shutil
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

db = pytest.importorskip("databento")
dbn = pytest.importorskip("databento_dbn")

from gcquant import core  # noqa: E402
from gcquant.core import BiayaDitolak, GcquantError  # noqa: E402
from gcquant.data import (  # noqa: E402
    BBO_COLUMNS, BOOK_COLUMNS, DEFS_COLUMNS, MBO_COLUMNS, STATS_COLUMNS, TRADES_COLUMNS,
    DatabentoSource, LiveFeed, infer_bar_len, load_daily_csv, load_dbn, load_m1_csv,
    normalize_request, record_to_dict, request_key, resample_bars, synthetic_mbo,
    write_synthetic_mbo_dbn,
)
from gcquant.data.dbn_io import _Interval, _Mapping  # noqa: E402

FIX = Path(__file__).parent / "data" / "databento"
REAL_M1_2016 = Path("/tmp/claude-0/-home-user-tree-data/85b87b5b-835d-5424-a3f8-e9958eb6b60e/"
                    "scratchpad/realdata/m1/XAUUSD_M1_2016.csv")
ESH1 = 5482


def fixture(schema: str) -> Path:
    return FIX / f"test_data.{schema}.dbn.zst"


# ---------------------------------------------------------------------------
# Klien palsu (tanpa jaringan)
# ---------------------------------------------------------------------------

class FakeMetadata:
    def __init__(self, log, cost):
        self.log, self.cost = log, cost

    def get_cost(self, **kw):
        self.log.append(("get_cost", kw))
        return self.cost

    def get_billable_size(self, **kw):
        self.log.append(("get_billable_size", kw))
        return 12_345

    def get_record_count(self, **kw):
        self.log.append(("get_record_count", kw))
        return 4

    def list_datasets(self, start_date=None, end_date=None):
        self.log.append(("list_datasets", {}))
        return ["GLBX.MDP3", "XNAS.ITCH"]

    def list_schemas(self, dataset):
        self.log.append(("list_schemas", {"dataset": dataset}))
        return ["mbo", "mbp-10", "trades", "definition", "statistics"]

    def get_dataset_range(self, dataset):
        self.log.append(("get_dataset_range", {"dataset": dataset}))
        return {"start": "2010-06-06T00:00:00.000000000Z", "end": "2026-10-16T00:00:00.000000000Z"}


class FakeTimeseries:
    def __init__(self, log, write_path=True):
        self.log, self.write_path = log, write_path

    def get_range(self, **kw):
        self.log.append(("get_range", kw))
        src = fixture(kw["schema"])
        if self.write_path:
            shutil.copyfile(src, kw["path"])
            return db.DBNStore.from_file(kw["path"])
        return db.DBNStore.from_bytes(src.read_bytes())     # klien yang tidak menulis ke path


class FakeHistorical:
    def __init__(self, cost=0.5, write_path=True):
        self.log: list = []
        self.metadata = FakeMetadata(self.log, cost)
        self.timeseries = FakeTimeseries(self.log, write_path)

    def names(self):
        return [n for n, _ in self.log]


class ExplodingClient:
    """Gagal pada SEGALA akses atribut: membuktikan cache hit tidak menyentuh klien."""

    def __init__(self):
        object.__setattr__(self, "touched", [])

    def __getattr__(self, name):
        self.touched.append(name)
        raise AssertionError(f"klien disentuh: {name}")


REQ = dict(dataset="GLBX.MDP3", schema="mbo", symbols=["ESH1"], start="2020-12-28",
           end="2020-12-29")


@pytest.fixture
def no_key(monkeypatch):
    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)


# ---------------------------------------------------------------------------
# DatabentoSource: pengaman biaya & cache
# ---------------------------------------------------------------------------

def test_refused_at_default_budget(tmp_path, no_key):
    fake = FakeHistorical(cost=0.5)
    src = DatabentoSource(cache_dir=tmp_path, client=fake)
    assert src.max_cost_usd == 0.0
    with pytest.raises(BiayaDitolak) as ei:
        src.get(**REQ)
    msg = str(ei.value)
    assert "0.5000" in msg and "max_cost_usd" in msg and "0.0000" in msg
    assert fake.names() == ["get_cost"]                       # get_range TIDAK pernah dipanggil
    assert list(tmp_path.iterdir()) == []                     # tidak ada berkas cache
    kw = fake.log[0][1]
    assert kw == {"dataset": "GLBX.MDP3", "schema": "mbo", "symbols": ["ESH1"],
                  "start": core.to_ns("2020-12-28"), "end": core.to_ns("2020-12-29"),
                  "stype_in": "raw_symbol"}


def test_refused_when_over_explicit_budget(tmp_path, no_key):
    fake = FakeHistorical(cost=2.01)
    src = DatabentoSource(cache_dir=tmp_path, client=fake, max_cost_usd=5.0)
    with pytest.raises(BiayaDitolak, match="2.0100"):
        src.get(**REQ, max_cost_usd=2.0)                      # timpa per panggilan, lebih ketat
    assert "get_range" not in fake.names()


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0, "abc", None])
def test_invalid_cost_estimate_refused(tmp_path, no_key, bad):
    fake = FakeHistorical(cost=bad)
    src = DatabentoSource(cache_dir=tmp_path, client=fake, max_cost_usd=1e9)
    with pytest.raises(BiayaDitolak):
        src.get(**REQ)
    assert "get_range" not in fake.names()


def test_allowed_under_budget_writes_cache_and_sidecar(tmp_path, no_key):
    fake = FakeHistorical(cost=0.5)
    src = DatabentoSource(cache_dir=tmp_path, client=fake, max_cost_usd=1.0)
    store = src.get(**REQ)
    assert fake.names() == ["get_cost", "get_range"]           # biaya diperiksa SEBELUM unduh
    assert isinstance(store, db.DBNStore)
    pd.testing.assert_frame_equal(load_dbn(store), load_dbn(fixture("mbo")))
    key = request_key(normalize_request(**REQ))
    data, meta = tmp_path / f"{key}.dbn.zst", tmp_path / f"{key}.json"
    assert data.is_file() and meta.is_file()
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted([data.name, meta.name])
    side = json.loads(meta.read_text())
    assert side["request"] == normalize_request(**REQ)
    assert side["cost_usd"] == 0.5 and side["budget_usd"] == 1.0
    assert pd.Timestamp(side["created"]).tzinfo is not None
    assert len(key) == 64 and all(c in "0123456789abcdef" for c in key)


def test_per_call_budget_and_zero_cost(tmp_path, no_key):
    fake = FakeHistorical(cost=0.5)
    src = DatabentoSource(cache_dir=tmp_path, client=fake)               # anggaran objek 0
    src.get(**REQ, max_cost_usd=0.5)                                     # biaya == anggaran: boleh
    assert fake.names() == ["get_cost", "get_range"]
    free = FakeHistorical(cost=0.0)
    src2 = DatabentoSource(cache_dir=tmp_path / "b", client=free)
    src2.get(**{**REQ, "schema": "trades"})                              # biaya nol: boleh
    assert free.names() == ["get_cost", "get_range"]


def test_cache_hit_makes_zero_client_calls(tmp_path, no_key):
    fake = FakeHistorical(cost=0.5, write_path=False)          # jalur store.to_file
    DatabentoSource(cache_dir=tmp_path, client=fake, max_cost_usd=1.0).get(**REQ)
    n_before = len(fake.log)
    bomb = ExplodingClient()
    src = DatabentoSource(cache_dir=tmp_path, client=bomb)     # anggaran 0, klien meledak
    # Permintaan setara dalam bentuk lain → kunci sama → cache hit.
    store = src.get(dataset="glbx.mdp3", schema="MBO", symbols="ESH1",
                    start=pd.Timestamp("2020-12-28", tz="UTC"), end=core.to_ns("2020-12-29"))
    assert bomb.touched == [] and len(fake.log) == n_before
    pd.testing.assert_frame_equal(load_dbn(store), load_dbn(fixture("mbo")))
    # Tanpa klien & tanpa kunci pun cache tetap terbaca (tidak ada jaringan).
    store2 = DatabentoSource(cache_dir=tmp_path).get(**REQ)
    assert len(load_dbn(store2)) == 4
    assert src.is_cached(**REQ)


def test_cache_miss_without_key_never_reaches_network(tmp_path, no_key):
    src = DatabentoSource(cache_dir=tmp_path)
    with pytest.raises(GcquantError, match="DATABENTO_API_KEY"):
        src.get(**REQ)


def test_real_historical_constructed_lazily_offline(tmp_path):
    src = DatabentoSource(key="db-" + "x" * 29, cache_dir=tmp_path)
    assert src._client is None                                 # belum dibuat
    assert isinstance(src.client, db.Historical)               # konstruksi tanpa jaringan


def test_request_normalization_and_key():
    a = normalize_request("glbx.mdp3", "MBO", ["GCJ6", "GCG6", "GCG6"], "2026-01-05",
                          "2026-01-06T00:00:00Z")
    b = normalize_request("GLBX.MDP3", "mbo", ["GCG6", "GCJ6"],
                          pd.Timestamp("2026-01-05", tz="UTC"), core.to_ns("2026-01-06"))
    assert a == b and request_key(a) == request_key(b)
    assert a["symbols"] == ["GCG6", "GCJ6"] and a["start_ns"] == 1_767_571_200_000_000_000
    c = normalize_request("GLBX.MDP3", "mbp-10", ["GCG6", "GCJ6"], "2026-01-05", "2026-01-06")
    assert request_key(c) != request_key(a)
    with pytest.raises(GcquantError):
        normalize_request("GLBX.MDP3", "mbo", "GCG6", "2026-01-05", None)
    with pytest.raises(GcquantError):
        normalize_request("GLBX.MDP3", "mbo", "GCG6", "2026-01-06", "2026-01-05")
    with pytest.raises(GcquantError):
        DatabentoSource(max_cost_usd=-1)


def test_estimate_and_free_metadata_only_free_calls(tmp_path, no_key):
    fake = FakeHistorical(cost=3.25)
    src = DatabentoSource(cache_dir=tmp_path, client=fake)
    est = src.estimate(**REQ)
    assert est["cost_usd"] == 3.25 and est["size_bytes"] == 12_345 and est["records"] == 4
    assert est["cached"] is False
    meta = src.free_metadata()
    assert meta["dataset"] == "GLBX.MDP3" and "mbo" in meta["schemas"]
    assert "start" in meta["dataset_range"]
    assert "get_range" not in fake.names()
    assert set(fake.names()) == {"get_cost", "get_billable_size", "get_record_count",
                                 "list_datasets", "list_schemas", "get_dataset_range"}


# ---------------------------------------------------------------------------
# LiveFeed
# ---------------------------------------------------------------------------

class FakeLive:
    def __init__(self):
        self.calls: list = []
        self.callbacks: list = []

    def subscribe(self, **kw):
        self.calls.append(("subscribe", kw))
        return 1

    def add_callback(self, fn, exception_callback=None):
        self.callbacks.append(fn)

    def start(self):
        self.calls.append(("start", {}))

    def stop(self):
        self.calls.append(("stop", {}))

    def block_for_close(self, timeout=None):
        self.calls.append(("block_for_close", {"timeout": timeout}))


def test_live_refused_unless_allowed(no_key):
    with pytest.raises(BiayaDitolak, match="allow_live=True"):
        LiveFeed()
    with pytest.raises(BiayaDitolak):
        LiveFeed(key="db-" + "x" * 29, allow_live=False)
    with pytest.raises(BiayaDitolak):
        LiveFeed(allow_live="ya")                                # hanya True yang diterima
    feed = LiveFeed(allow_live=True)                             # tanpa kunci & klien: tidak konek
    with pytest.raises(GcquantError):
        feed.subscribe("GLBX.MDP3", "mbo", ["GCG6"])


def test_live_subscribe_and_callback_with_fake_client():
    fake = FakeLive()
    feed = LiveFeed(allow_live=True, client=fake)
    feed.subscribe("GLBX.MDP3", "MBO", ["ESH1"], snapshot=True)
    assert fake.calls[0] == ("subscribe", {"dataset": "GLBX.MDP3", "schema": "mbo",
                                           "symbols": ["ESH1"], "stype_in": "raw_symbol",
                                           "start": None, "snapshot": True})
    with pytest.raises(GcquantError):
        feed.subscribe("GLBX.MDP3", "mbo", ["ESH1"], start="2020-12-28", snapshot=True)
    got: list = []
    feed.add_callback(got.append)
    cb = fake.callbacks[0]
    sm = dbn.SymbolMappingMsg(publisher_id=1, instrument_id=ESH1, ts_event=1, stype_in=dbn.SType.RAW_SYMBOL,
                              stype_in_symbol="ESH1", stype_out=dbn.SType.INSTRUMENT_ID,
                              stype_out_symbol="ESH1", start_ts=0, end_ts=2)
    cb(sm)
    assert got == [] and feed.symbol_map == {ESH1: "ESH1"}
    for rec in db.DBNStore.from_file(fixture("mbo")):
        cb(rec)
    frame = load_dbn(fixture("mbo"))
    assert len(got) == 4
    assert pd.DataFrame(got)[MBO_COLUMNS].astype(frame.dtypes.to_dict()).equals(frame)
    feed.start(); feed.stop(); feed.block_for_close(1.0)
    assert [c[0] for c in fake.calls[1:]] == ["start", "stop", "block_for_close"]


def _same(a, b) -> bool:
    if a is None or b is None or a is pd.NA or b is pd.NA:
        return (a is None or a is pd.NA or (isinstance(a, float) and math.isnan(a))) and \
               (b is None or b is pd.NA or (isinstance(b, float) and math.isnan(b)) or b is pd.NaT)
    if isinstance(a, float) and isinstance(b, (float, np.floating)) and math.isnan(a):
        return bool(np.isnan(b))
    if isinstance(a, pd.Timestamp) or isinstance(b, pd.Timestamp):
        return pd.Timestamp(a) == pd.Timestamp(b)
    return a == b


@pytest.mark.parametrize("schema", ["mbo", "trades", "mbp-1", "tbbo", "mbp-10", "statistics",
                                    "definition", "ohlcv-1m", "ohlcv-1d"])
def test_record_to_dict_matches_load_dbn(schema):
    store = db.DBNStore.from_file(fixture(schema))
    frame = load_dbn(store)
    recs = list(store)
    assert len(recs) == len(frame)
    for i, rec in enumerate(recs):
        d = record_to_dict(rec, {ESH1: "ESH1"})
        if schema.startswith("ohlcv"):
            assert d["ts"] == frame.index[i].value
            row = frame.iloc[i]
            keys = [k for k in d if k != "ts"]
        else:
            row = frame.iloc[i]
            keys = list(d)
            assert set(row.index) >= set(keys)
        for k in keys:
            assert _same(d[k], row[k]), (schema, i, k, d[k], row[k])


# ---------------------------------------------------------------------------
# load_dbn: semua fixture, nilai dicek tangan
# ---------------------------------------------------------------------------

def test_load_mbo_fixture():
    f = load_dbn(fixture("mbo"))
    assert list(f.columns) == MBO_COLUMNS and len(f) == 4
    r = f.iloc[0]
    assert r.ts_recv == 1_609_113_600_000_000_000 and r.ts_event == 1_609_099_225_061_045_683
    assert r.order_id == 647_784_248_135 and r.price == 3675.75 and r["size"] == 2
    assert r["flags"] == core.F_SNAPSHOT | core.F_BAD_TS_RECV and r["sequence"] == 1180
    assert r.action == "A" and r.side == "B" and r.symbol == "ESH1" and r.instrument_id == ESH1
    assert f["price"].tolist() == [3675.75, 3675.5, 3675.25, 3675.0]
    dtypes = {"ts_recv": "int64", "ts_event": "int64", "instrument_id": "int64",
              "order_id": "uint64", "price": "float64", "size": "int64", "flags": "int64",
              "sequence": "int64", "channel_id": "int64", "publisher_id": "int64"}
    for c, t in dtypes.items():
        assert str(f[c].dtype) == t, c
    for c in ("action", "side", "symbol"):
        assert pd.api.types.is_string_dtype(f[c])


def test_load_trades_and_tbbo_fixture():
    t = load_dbn(fixture("trades"))
    assert list(t.columns) == TRADES_COLUMNS
    assert t["price"].tolist() == [3702.75, 3702.75, 3702.5, 3702.75]
    assert t["side"].tolist() == ["B", "B", "A", "B"] and (t["action"] == "T").all()
    assert t["ts_recv"].iloc[0] == 1_609_113_600_246_821_748
    q = load_dbn(fixture("tbbo"))
    assert list(q.columns) == BBO_COLUMNS
    assert q["bid_px"].tolist() == [3702.5] * 4 and q["ask_px"].tolist() == [3702.75] * 4
    assert q["bid_sz"].tolist() == [8, 9, 7, 6] and q["ask_sz"].tolist() == [8, 5, 9, 10]
    assert q["price"].tolist() == t["price"].tolist()


def test_load_mbp1_and_mbp10_fixture():
    b = load_dbn(fixture("mbp-1"))
    assert list(b.columns) == BBO_COLUMNS
    assert b["bid_sz"].tolist() == [19, 20, 20, 21] and b["ask_ct"].tolist() == [13, 13, 14, 14]
    assert b["flags"].iloc[0] == core.F_LAST | 2
    k = load_dbn(fixture("mbp-10"))
    assert list(k.columns) == BOOK_COLUMNS
    row = k.iloc[0]
    assert [row[f"bid_px_{i:02d}"] for i in range(10)] == [3702.25 - 0.25 * i for i in range(10)]
    assert [row[f"ask_px_{i:02d}"] for i in range(10)] == [3702.75 + 0.25 * i for i in range(10)]
    assert row["bid_sz_09"] == 38 and row["ask_ct_09"] == 27
    # BBO MBP-10 level 0 = MBP-1
    assert (k["bid_px_00"].to_numpy() == b["bid_px"].to_numpy()).all()


def test_load_ohlcv_fixtures_index_is_bar_open():
    m = load_dbn(fixture("ohlcv-1m"))
    assert list(m.columns) == ["open", "high", "low", "close", "volume", "symbol", "instrument_id"]
    assert str(m.index.dtype) == "datetime64[ns, UTC]" and m.index.name == "ts"
    assert m.index[0] == pd.Timestamp("2020-12-28 00:00:00", tz="UTC")
    assert (np.diff(m.index.asi8) == 60 * core.NS_PER_SEC).all()
    assert m["open"].tolist() == [3702.75, 3704.75, 3704.25, 3704.5]
    assert m["volume"].tolist() == [306, 214, 192, 158] and m["volume"].dtype == np.int64
    assert m.attrs["bar_len"] == "1min"
    d = load_dbn(fixture("ohlcv-1d"))
    assert d.index[0] == pd.Timestamp("2020-12-28", tz="UTC") and d["volume"].iloc[0] == 718174
    assert d.attrs["bar_len"] == "1D"


def test_load_definition_statistics_status_fixtures():
    defs = load_dbn(fixture("definition"))
    assert list(defs.columns) == DEFS_COLUMNS
    r = defs.iloc[0]
    assert r.raw_symbol == "ESH1" and r.instrument_class == "F" and r.asset == "ES"
    assert r.expiration == pd.Timestamp("2021-03-19 13:30", tz="UTC")
    assert r.activation == pd.Timestamp("2019-12-20 14:30", tz="UTC")
    assert r.min_price_increment == 0.25 and r.unit_of_measure_qty == 50.0
    assert np.isnan(r.strike_price) and np.isnan(r.contract_multiplier)    # UNDEF → NaN
    assert r.maturity_year == 2021 and r.maturity_month == 3 and np.isnan(r.maturity_day)
    assert str(defs["expiration"].dtype) == "datetime64[ns, UTC]"
    st = load_dbn(fixture("statistics"))
    assert list(st.columns) == STATS_COLUMNS
    assert st["quantity"].isna().all()                     # UNDEF_STAT_QUANTITY → NaN
    assert st["ts_ref"].isna().all() and str(st["ts_ref"].dtype) == "Int64"
    assert st["stat_type"].tolist() == [8, 8, 5, 8] and st["price"].iloc[0] == 3707.75
    s = load_dbn(fixture("status"))
    assert {"ts_recv", "ts_event", "instrument_id", "symbol", "action", "is_trading"} <= set(s.columns)
    assert s["ts_recv"].dtype == np.int64 and s["action"].tolist() == [7, 1, 1, 6]
    assert s["is_trading"].tolist() == ["Y", "N", "N", "Y"]


def test_load_dbn_accepts_store_bytes_and_errors(tmp_path):
    p = fixture("trades")
    a = load_dbn(p)
    pd.testing.assert_frame_equal(a, load_dbn(db.DBNStore.from_file(p)))
    pd.testing.assert_frame_equal(a, load_dbn(p.read_bytes()))
    pd.testing.assert_frame_equal(a, load_dbn(str(p), schema="trades"))
    with pytest.raises(FileNotFoundError):
        load_dbn(tmp_path / "tidak_ada.dbn.zst")


# ---------------------------------------------------------------------------
# UNDEF & pemetaan simbol pada DBN buatan sendiri (databento_dbn encoder)
# ---------------------------------------------------------------------------

T0 = 1_767_623_400_000_000_000          # 2026-01-05 14:30 UTC


def _meta(schema, mappings):
    return dbn.Metadata(dataset="GLBX.MDP3", start=T0, end=T0 + 10**9, stype_in=dbn.SType.RAW_SYMBOL,
                        stype_out=dbn.SType.INSTRUMENT_ID, schema=schema, symbols=["GCG6"],
                        mappings=mappings)


MAP7 = [_Mapping("GCG6", [_Interval(dt.date(2026, 1, 5), dt.date(2026, 1, 6), "7")])]


def test_undefined_prices_and_quantities_become_nan():
    lv = dbn.BidAskPair(bid_px=dbn.UNDEF_PRICE, ask_px=2_650_100_000_000, bid_sz=0, ask_sz=3,
                        bid_ct=0, ask_ct=1)
    m1 = dbn.MBP1Msg(publisher_id=1, instrument_id=7, ts_event=T0, price=2_650_100_000_000, size=3,
                     action=dbn.Action("A"), side=dbn.Side("A"), depth=0, ts_recv=T0 + 5, flags=128,
                     sequence=9, levels=lv)
    b = load_dbn(_meta(dbn.Schema.MBP_1, MAP7).encode() + bytes(m1))
    assert np.isnan(b["bid_px"].iloc[0]) and b["bid_sz"].iloc[0] == 0
    assert b["ask_px"].iloc[0] == 2650.1 and b["symbol"].iloc[0] == "GCG6"
    s1 = dbn.StatMsg(publisher_id=1, instrument_id=7, ts_event=T0, ts_recv=T0 + 5,
                     ts_ref=dbn.UNDEF_TIMESTAMP, price=dbn.UNDEF_PRICE,
                     quantity=dbn.UNDEF_STAT_QUANTITY, stat_type=dbn.StatType.OPEN_INTEREST,
                     sequence=1, update_action=dbn.StatUpdateAction.NEW)
    s2 = dbn.StatMsg(publisher_id=1, instrument_id=7, ts_event=T0 + 1, ts_recv=T0 + 6,
                     ts_ref=T0 - 86_400 * 10**9, price=2_650_100_000_000, quantity=1234,
                     stat_type=dbn.StatType.SETTLEMENT_PRICE, sequence=2,
                     update_action=dbn.StatUpdateAction.NEW)
    st = load_dbn(_meta(dbn.Schema.STATISTICS, []).encode() + bytes(s1) + bytes(s2))
    assert np.isnan(st["price"].iloc[0]) and np.isnan(st["quantity"].iloc[0])
    assert st["ts_ref"].iloc[0] is pd.NA and st["ts_ref"].iloc[1] == T0 - 86_400 * 10**9
    assert st["price"].iloc[1] == 2650.1 and st["quantity"].iloc[1] == 1234.0
    assert st["stat_type"].tolist() == [9, 3]
    assert st["symbol"].tolist() == ["7", "7"]            # tanpa pemetaan → str(instrument_id)
    st2 = load_dbn(_meta(dbn.Schema.STATISTICS, []).encode() + bytes(s1) + bytes(s2),
                   symbol_map={7: "GCG6"})
    assert st2["symbol"].tolist() == ["GCG6", "GCG6"]      # peta eksplisit (mis. dari DEFS)
    mb = dbn.MBOMsg(publisher_id=1, instrument_id=7, ts_event=T0, order_id=1, price=dbn.UNDEF_PRICE,
                    size=dbn.UNDEF_ORDER_SIZE, action=dbn.Action("R"), side=dbn.Side("N"),
                    ts_recv=T0, flags=128)
    with pytest.warns(UserWarning, match="tak terdefinisi"):
        mbo = load_dbn(_meta(dbn.Schema.MBO, MAP7).encode() + bytes(mb))
    assert np.isnan(mbo["price"].iloc[0]) and np.isnan(mbo["size"].iloc[0])
    d = record_to_dict(s1)
    assert math.isnan(d["price"]) and math.isnan(d["quantity"]) and d["ts_ref"] is None


@pytest.mark.parametrize("name", ["syn.dbn.zst", "syn.dbn"])
def test_write_synthetic_mbo_dbn_roundtrip(tmp_path, name):
    m = synthetic_mbo(1500, seed=2)
    p = write_synthetic_mbo_dbn(tmp_path / name, m)
    raw = p.read_bytes()
    assert raw[:4] == b"\x28\xb5\x2f\xfd" if name.endswith(".zst") else raw[:3] == b"DBN"
    back = load_dbn(p)
    pd.testing.assert_frame_equal(back, m)
    assert np.isnan(back["price"].iloc[0]) and back["action"].iloc[0] == "R"
    store = db.DBNStore.from_file(p)
    assert str(store.schema) == "mbo" and store.symbols == ["GCG6"]
    # Rekaman pertama identik dengan encoder resmi MBOMsg
    first = next(iter(store))
    assert first.order_id == 0 and first.price == core.UNDEF_PRICE and int(first.flags) == core.F_SNAPSHOT


# ---------------------------------------------------------------------------
# Berkas lokal gratis
# ---------------------------------------------------------------------------

MT5_SAMPLE = (
    "<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>\n"
    "2016.01.03\t23:00:00\t1062.34\t1066.32\t1062.23\t1066.04\t75\t0\t51\n"
    "2016.01.03\t23:01:00\t1066.00\t1066.00\t1064.35\t1064.46\t164\t0\t46\n"
    "2016.01.03\t23:02:00\t1064.46\t1065.16\t1064.46\t1064.86\t102\t0\t49\n"
)


def test_load_m1_csv_mt5_sample(tmp_path):
    p = tmp_path / "XAUUSD_M1_2016.csv"
    p.write_text(MT5_SAMPLE)
    b = load_m1_csv(p)
    assert list(b.columns) == ["open", "high", "low", "close", "volume", "tick_volume", "spread"]
    assert str(b.index.dtype) == "datetime64[ns, UTC]" and b.index.name == "ts"
    assert b.index[0] == pd.Timestamp("2016-01-03 23:00", tz="UTC")
    assert b["open"].iloc[0] == 1062.34 and b["close"].iloc[2] == 1064.86
    assert b["volume"].tolist() == [75, 164, 102]           # VOL nol semua → TICKVOL
    assert b["spread"].tolist() == [0.51, 0.46, 0.49]       # point 0,01 USD
    # zona waktu server broker UTC+2 (musim dingin) → UTC mundur 2 jam
    b2 = load_m1_csv(p, tz="Europe/Athens")
    assert b2.index[0] == pd.Timestamp("2016-01-03 21:00", tz="UTC")


def test_load_m1_csv_generic_comma(tmp_path):
    p = tmp_path / "gen.csv"
    p.write_text("time,open,high,low,close,volume,spread_points\n"
                 "2024-03-01 10:01:00,2050.10,2051.00,2049.90,2050.50,12,25\n"
                 "2024-03-01 10:00:00,2049.00,2050.20,2048.80,2050.10,10,30\n"
                 "2024-03-01 10:00:00,2049.00,2050.20,2048.80,2050.10,10,30\n"
                 "2024-03-01 10:02:00,0,0,0,0,0,0\n")
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        b = load_m1_csv(p)
    msgs = " ".join(str(x.message) for x in w)
    assert "duplikat" in msgs and "dibuang" in msgs
    assert list(b.index) == [pd.Timestamp("2024-03-01 10:00", tz="UTC"),
                             pd.Timestamp("2024-03-01 10:01", tz="UTC")]
    assert b["spread"].tolist() == [0.30, 0.25] and b["volume"].tolist() == [10, 12]
    with pytest.warns(UserWarning):
        usd = load_m1_csv(p, spread_in_points=False)
    assert usd["spread"].tolist() == [30.0, 25.0]


@pytest.mark.skipif(not REAL_M1_2016.is_file(), reason="berkas M1 2016 asli tidak tersedia")
def test_load_m1_csv_real_2016_file():
    b = load_m1_csv(REAL_M1_2016)
    assert len(b) > 300_000
    assert b.index.is_monotonic_increasing and b.index.is_unique
    assert b.index[0] == pd.Timestamp("2016-01-03 23:00", tz="UTC")
    assert b.index[-1] == pd.Timestamp("2016-12-30 21:59", tz="UTC")
    assert b["spread"].iloc[0] == 0.51 and b["open"].iloc[0] == 1062.34
    assert 1000 < b["close"].min() < b["close"].max() < 1400       # emas 2016
    assert 0.1 < b["spread"].median() < 1.0
    assert infer_bar_len(b.index) == pd.Timedelta("1min")
    h = resample_bars(b, "1h")
    assert h.index[-1] == pd.Timestamp("2016-12-30 21:00", tz="UTC")
    assert h["volume"].sum() == b["volume"].sum()


def test_load_daily_csv(tmp_path):
    p = tmp_path / "d.csv"
    p.write_text("Date,Open,High,Low,Close,Volume\n"
                 "2024-01-03,2040.0,2045.0,2030.0,2041.5,1000\n"
                 "2024-01-02,2060.0,2070.0,2055.0,2063.0,900\n"
                 "2024-01-03,2040.0,2045.0,2030.0,2042.0,1000\n")
    d = load_daily_csv(p)
    assert list(d.index) == [pd.Timestamp("2024-01-02", tz="UTC"), pd.Timestamp("2024-01-03", tz="UTC")]
    assert d["price"].tolist() == [2063.0, 2042.0]               # duplikat → yang terakhir
    q = tmp_path / "mt5d.csv"
    q.write_text("<DATE>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\n2016.01.04\t1062\t1080\t1060\t1075\n")
    e = load_daily_csv(q, price_col="<OPEN>")
    assert e.index[0] == pd.Timestamp("2016-01-04", tz="UTC") and e["price"].iloc[0] == 1062.0


# ---------------------------------------------------------------------------
# resample_bars: kausal, label waktu buka, kiri-tertutup
# ---------------------------------------------------------------------------

def _minute_bars(n, start="2026-01-05 10:00"):
    idx = pd.date_range(start, periods=n, freq="1min", tz="UTC").as_unit("ns")
    i = np.arange(n, dtype=float)
    return pd.DataFrame({"open": 100 + i, "high": 100.5 + i, "low": 99.5 + i, "close": 100.2 + i,
                         "volume": np.arange(1, n + 1, dtype=np.int64),
                         "spread": 0.1 * (i + 1)}, index=idx)


def test_resample_hand_computed():
    r = resample_bars(_minute_bars(10), "5min")
    assert list(r.index) == [pd.Timestamp("2026-01-05 10:00", tz="UTC"),
                             pd.Timestamp("2026-01-05 10:05", tz="UTC")]
    assert r["open"].tolist() == [100.0, 105.0] and r["high"].tolist() == [104.5, 109.5]
    assert r["low"].tolist() == [99.5, 104.5] and r["close"].tolist() == [104.2, 109.2]
    assert r["volume"].tolist() == [15, 40] and r["volume"].dtype == np.int64
    assert r["spread"].tolist() == pytest.approx([0.3, 0.8])
    assert str(r.index.dtype) == "datetime64[ns, UTC]"


def test_resample_drops_partial_last_bar():
    b = _minute_bars(8)                                   # 10:00..10:07 → bin 10:05 belum lengkap
    r = resample_bars(b, "5min")
    assert list(r.index) == [pd.Timestamp("2026-01-05 10:00", tz="UTC")]
    r2 = resample_bars(b, "5min", drop_partial=False)
    assert len(r2) == 2 and r2["close"].iloc[-1] == 107.2


def test_resample_future_perturbation_no_lookahead():
    full = _minute_bars(30)
    base = resample_bars(full, "5min")
    t_cut = pd.Timestamp("2026-01-05 10:12", tz="UTC")
    # (1) Ubah semua data SETELAH t_cut → bar yang sudah final pada t_cut tidak berubah.
    pert = full.copy()
    after = pert.index >= t_cut
    pert.loc[after, ["open", "high", "low", "close"]] *= 3.0
    pert.loc[after, "volume"] += 999
    alt = resample_bars(pert, "5min")
    known = base.index + pd.Timedelta("5min") <= t_cut
    assert alt.index.equals(base.index)
    pd.testing.assert_frame_equal(base[known], alt[known])
    assert not base[~known].equals(alt[~known])            # kontrol: bar sesudahnya memang berubah
    # (2) Hanya data yang tersedia sampai t_cut → hasilnya = bar final yang diketahui pada t_cut.
    trunc = resample_bars(full[full.index < t_cut], "5min")
    pd.testing.assert_frame_equal(trunc, base[known])


def test_resample_drops_bins_with_leaking_source_bars():
    b = _minute_bars(10)
    extra = b.iloc[[4]].copy()
    extra.index = extra.index + pd.Timedelta("30s")      # bar 10:04:30 berakhir 10:05:30 > 10:05
    mixed = pd.concat([b, extra]).sort_index()
    with pytest.warns(UserWarning, match="melewati akhir bin"):
        r = resample_bars(mixed, "5min", source_bar_len="1min")
    assert list(r.index) == [pd.Timestamp("2026-01-05 10:05", tz="UTC")]
    two = pd.concat([b.assign(symbol="A"), b.assign(symbol="B")])
    with pytest.raises(GcquantError):
        resample_bars(two, "5min")                        # dua instrumen / timestamp duplikat
    for cal in ("1MS", "1ME", "1B"):                     # aturan kalender ditolak
        with pytest.raises(GcquantError, match="kalender"):
            resample_bars(b, cal)
    with pytest.raises(GcquantError):
        resample_bars(b, "30s")                           # lebih pendek dari bar sumber


def test_resample_daily_with_offset():
    idx = pd.date_range("2026-01-05 20:00", "2026-01-07 23:00", freq="1h", tz="UTC").as_unit("ns")
    h = pd.DataFrame({"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5,
                      "volume": np.ones(len(idx), dtype=np.int64)}, index=idx)
    r = resample_bars(h, "1D", offset="22h")
    assert list(r.index) == [pd.Timestamp("2026-01-04 22:00", tz="UTC"),
                             pd.Timestamp("2026-01-05 22:00", tz="UTC"),
                             pd.Timestamp("2026-01-06 22:00", tz="UTC")]
    assert r["volume"].tolist() == [2, 24, 24]            # bin terakhir (22:00, 23:00) parsial
    assert infer_bar_len(idx) == pd.Timedelta("1h")
    pd.testing.assert_frame_equal(r, resample_bars(h, pd.Timedelta(days=1), offset="22h"))
