"""Baca/tulis berkas DBN Databento sebagai frame kanonik gcquant (SPEC §2).

Semua fungsi di sini bekerja LURING (offline): hanya membaca berkas ``.dbn``/``.dbn.zst``
yang sudah ada di disk atau objek ``databento.DBNStore`` di memori. Tidak ada panggilan API.

Konvensi keluaran:
- ``ts_recv`` / ``ts_event``: int64 nanodetik UTC (jam analisis = ``ts_recv``).
- Harga: float USD; harga tak terdefinisi (``UNDEF_PRICE``) → NaN.
- Kuantitas tak terdefinisi (``UNDEF_ORDER_SIZE`` / ``UNDEF_STAT_QUANTITY``) → NaN.
- Kolom ``symbol``: simbol mentah dari pemetaan simbol metadata DBN; bila pemetaan
  tidak tersedia, diisi ``str(instrument_id)`` agar tidak pernah kosong diam-diam.
- BARS (ohlcv-*): indeks ``ts`` = waktu BUKA bar (``ts_event``), diketahui pada ``ts + bar_len``.
"""
from __future__ import annotations

import datetime as _dt
import os
import warnings
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .. import core

__all__ = [
    "load_dbn", "write_synthetic_mbo_dbn", "canonical_schema",
    "MBO_COLUMNS", "TRADES_COLUMNS", "BBO_COLUMNS", "BOOK_COLUMNS", "STATS_COLUMNS",
    "DEFS_COLUMNS", "BARS_COLUMNS", "BAR_LEN",
]

_I64_MAX = np.iinfo(np.int64).max
_U64_MAX = np.iinfo(np.uint64).max
UNDEF_TIMESTAMP = int(_U64_MAX)

N_LEVELS = 10

MBO_COLUMNS = ["ts_recv", "ts_event", "instrument_id", "order_id", "action", "side", "price",
               "size", "flags", "sequence", "channel_id", "publisher_id", "symbol"]
TRADES_COLUMNS = ["ts_recv", "ts_event", "instrument_id", "price", "size", "side", "sequence",
                  "symbol", "action", "depth", "flags", "publisher_id"]
_EVENT_COLS = ["action", "side", "depth", "price", "size", "flags", "sequence", "publisher_id"]
BBO_COLUMNS = ["ts_recv", "ts_event", "instrument_id", "symbol", "bid_px", "ask_px", "bid_sz",
               "ask_sz", "bid_ct", "ask_ct"] + _EVENT_COLS


def _book_level_cols(n: int = N_LEVELS) -> list[str]:
    cols: list[str] = []
    for kind in ("bid_px", "ask_px", "bid_sz", "ask_sz", "bid_ct", "ask_ct"):
        cols += [f"{kind}_{i:02d}" for i in range(n)]
    return cols


BOOK_COLUMNS = ["ts_recv", "ts_event", "instrument_id", "symbol"] + _book_level_cols() + _EVENT_COLS
STATS_COLUMNS = ["ts_recv", "ts_event", "ts_ref", "instrument_id", "symbol", "stat_type", "price",
                 "quantity", "update_action", "sequence", "stat_flags", "channel_id", "publisher_id"]
DEFS_COLUMNS = ["instrument_id", "raw_symbol", "instrument_class", "expiration", "activation",
                "min_price_increment", "unit_of_measure_qty", "strike_price", "underlying", "asset",
                "ts_recv", "ts_event", "symbol", "publisher_id", "security_update_action",
                "underlying_id", "display_factor", "currency", "strike_price_currency", "exchange",
                "group", "cfi", "security_type", "unit_of_measure", "high_limit_price",
                "low_limit_price", "min_price_increment_amount", "contract_multiplier",
                "maturity_year", "maturity_month", "maturity_day", "user_defined_instrument"]
BARS_COLUMNS = ["open", "high", "low", "close", "volume", "symbol", "instrument_id"]

# Panjang bar per skema OHLCV (dipakai untuk aturan "diketahui pada ts + bar_len").
BAR_LEN = {"ohlcv-1s": "1s", "ohlcv-1m": "1min", "ohlcv-1h": "1h", "ohlcv-1d": "1D",
           "ohlcv-eod": "1D"}

# Kolom definisi bertipe integer yang memakai nilai maksimum tipe sebagai "tak terdefinisi".
_DEF_INT_UNDEF = {"contract_multiplier": np.iinfo(np.int32).max,
                  "maturity_year": np.iinfo(np.uint16).max,
                  "maturity_month": np.iinfo(np.uint8).max,
                  "maturity_day": np.iinfo(np.uint8).max}


def canonical_schema(schema: Any) -> str:
    """Nama skema Databento sebagai string huruf kecil, mis. ``Schema.MBP_10`` → ``'mbp-10'``."""
    if schema is None:
        raise core.GcquantError("Skema tidak diketahui; berikan argumen schema=...")
    val = getattr(schema, "value", schema)
    return str(val).strip().lower()


# ---------------------------------------------------------------------------
# Helper konversi
# ---------------------------------------------------------------------------

def _open_store(path_or_store):
    """Kembalikan ``databento.DBNStore`` dari path, bytes, atau store yang sudah ada."""
    try:
        import databento as db
    except ImportError as exc:  # pragma: no cover - databento terpasang di lingkungan uji
        raise core.GcquantError(
            "Paket 'databento' belum terpasang. Pasang dengan: pip install 'gcquant[databento]'"
        ) from exc
    if isinstance(path_or_store, db.DBNStore):
        return path_or_store
    if isinstance(path_or_store, (bytes, bytearray, memoryview)):
        return db.DBNStore.from_bytes(bytes(path_or_store))
    path = Path(os.fspath(path_or_store)).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Berkas DBN tidak ditemukan: {path}")
    return db.DBNStore.from_file(path)


def _ts_int(values, name: str, allow_undef: bool = False) -> np.ndarray:
    """Kolom timestamp DBN (uint64 ns) → int64 ns. UNDEF_TIMESTAMP ditolak kecuali allow_undef."""
    arr = np.asarray(values)
    if arr.dtype.kind == "M":
        return pd.DatetimeIndex(arr).as_unit("ns").asi8.copy()
    arr = arr.astype(np.uint64, copy=False)
    undef = arr == np.uint64(UNDEF_TIMESTAMP)
    if undef.any() and not allow_undef:
        raise core.GcquantError(f"Kolom {name} berisi timestamp tak terdefinisi (UNDEF_TIMESTAMP).")
    too_big = (arr > np.uint64(_I64_MAX)) & ~undef
    if too_big.any():
        raise core.GcquantError(f"Kolom {name} berisi nilai di luar rentang int64.")
    return np.where(undef, 0, arr).astype(np.int64)


def _ts_nullable(values) -> pd.Series:
    """Timestamp opsional (mis. ``ts_ref``) → pandas ``Int64`` dengan <NA> untuk UNDEF."""
    arr = np.asarray(values).astype(np.uint64, copy=False)
    undef = arr == np.uint64(UNDEF_TIMESTAMP)
    ints = np.where(undef, 0, arr).astype(np.int64)
    out = pd.array(ints, dtype="Int64")
    out[undef] = pd.NA
    return pd.Series(out)


def _ts_datetime(values) -> pd.Series:
    """Timestamp opsional → ``datetime64[ns, UTC]`` dengan NaT untuk UNDEF (dipakai DEFS)."""
    if isinstance(values, pd.Series) and isinstance(values.dtype, pd.DatetimeTZDtype):
        return pd.Series(pd.DatetimeIndex(values).tz_convert("UTC").as_unit("ns"))
    arr = np.asarray(values).astype(np.uint64, copy=False)
    undef = arr == np.uint64(UNDEF_TIMESTAMP)
    ints = np.where(undef, 0, arr).astype(np.int64)
    idx = core.ns_to_ts(ints)
    s = pd.Series(idx)
    s[undef] = pd.NaT
    return s


def _size_col(values, undef_value: int, name: str) -> np.ndarray:
    """Kolom kuantitas → int64; bila ada nilai UNDEF, menjadi float64 dengan NaN (+ peringatan)."""
    arr = np.asarray(values)
    undef = arr == undef_value
    if undef.any():
        warnings.warn(f"Kolom {name}: {int(undef.sum())} nilai tak terdefinisi diubah menjadi NaN "
                      "(kolom menjadi float64).", stacklevel=3)
        out = arr.astype(np.float64)
        out[undef] = np.nan
        return out
    return arr.astype(np.int64)


def _float_px(values) -> np.ndarray:
    """Harga dari to_df(price_type='float') → float64 (UNDEF sudah NaN oleh databento)."""
    return np.asarray(values, dtype=np.float64)


def _str_col(values) -> pd.Series:
    return pd.Series(np.asarray(values, dtype=object)).fillna("").astype(str)


def _symbols(raw: pd.DataFrame) -> pd.Series:
    """Kolom simbol; nilai yang tak terpetakan diisi str(instrument_id)."""
    iid = raw["instrument_id"].astype(np.int64)
    if "symbol" in raw.columns:
        sym = pd.Series(np.asarray(raw["symbol"], dtype=object), index=raw.index)
        missing = sym.isna() | (sym.astype(str) == "") | (sym.astype(str) == "None")
        sym = sym.where(~missing, iid.astype(str))
    else:
        sym = iid.astype(str)
    return sym.astype(str).reset_index(drop=True)


def _empty_frame(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series([], dtype="float64") for c in columns})


# ---------------------------------------------------------------------------
# Pembentuk frame kanonik per skema
# ---------------------------------------------------------------------------

def _mbo(raw: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "ts_recv": _ts_int(raw["ts_recv"], "ts_recv"),
        "ts_event": _ts_int(raw["ts_event"], "ts_event"),
        "instrument_id": raw["instrument_id"].to_numpy().astype(np.int64),
        "order_id": raw["order_id"].to_numpy().astype(np.uint64),
        "action": _str_col(raw["action"]),
        "side": _str_col(raw["side"]),
        "price": _float_px(raw["price"]),
        "size": _size_col(raw["size"].to_numpy(), core.UNDEF_ORDER_SIZE, "size"),
        "flags": raw["flags"].to_numpy().astype(np.int64),
        "sequence": raw["sequence"].to_numpy().astype(np.int64),
        "channel_id": raw["channel_id"].to_numpy().astype(np.int64),
        "publisher_id": raw["publisher_id"].to_numpy().astype(np.int64),
        "symbol": _symbols(raw),
    })[MBO_COLUMNS]


def _event_cols(raw: pd.DataFrame) -> dict[str, Any]:
    return {
        "action": _str_col(raw["action"]),
        "side": _str_col(raw["side"]),
        "depth": raw["depth"].to_numpy().astype(np.int64),
        "price": _float_px(raw["price"]),
        "size": _size_col(raw["size"].to_numpy(), core.UNDEF_ORDER_SIZE, "size"),
        "flags": raw["flags"].to_numpy().astype(np.int64),
        "sequence": raw["sequence"].to_numpy().astype(np.int64),
        "publisher_id": raw["publisher_id"].to_numpy().astype(np.int64),
    }


def _base_cols(raw: pd.DataFrame) -> dict[str, Any]:
    return {
        "ts_recv": _ts_int(raw["ts_recv"], "ts_recv"),
        "ts_event": _ts_int(raw["ts_event"], "ts_event"),
        "instrument_id": raw["instrument_id"].to_numpy().astype(np.int64),
        "symbol": _symbols(raw),
    }


def _trades(raw: pd.DataFrame) -> pd.DataFrame:
    d = _base_cols(raw)
    d.update(_event_cols(raw))
    return pd.DataFrame(d)[TRADES_COLUMNS]


def _bbo(raw: pd.DataFrame) -> pd.DataFrame:
    d = _base_cols(raw)
    d.update({
        "bid_px": _float_px(raw["bid_px_00"]),
        "ask_px": _float_px(raw["ask_px_00"]),
        "bid_sz": raw["bid_sz_00"].to_numpy().astype(np.int64),
        "ask_sz": raw["ask_sz_00"].to_numpy().astype(np.int64),
        "bid_ct": raw["bid_ct_00"].to_numpy().astype(np.int64),
        "ask_ct": raw["ask_ct_00"].to_numpy().astype(np.int64),
    })
    d.update(_event_cols(raw))
    return pd.DataFrame(d)[BBO_COLUMNS]


def _book(raw: pd.DataFrame) -> pd.DataFrame:
    d = _base_cols(raw)
    for i in range(N_LEVELS):
        for side in ("bid", "ask"):
            d[f"{side}_px_{i:02d}"] = _float_px(raw[f"{side}_px_{i:02d}"])
            d[f"{side}_sz_{i:02d}"] = raw[f"{side}_sz_{i:02d}"].to_numpy().astype(np.int64)
            d[f"{side}_ct_{i:02d}"] = raw[f"{side}_ct_{i:02d}"].to_numpy().astype(np.int64)
    d.update(_event_cols(raw))
    return pd.DataFrame(d)[BOOK_COLUMNS]


def _bars(raw: pd.DataFrame, schema: str) -> pd.DataFrame:
    ts = _ts_int(raw["ts_event"], "ts_event")
    out = pd.DataFrame({
        "open": _float_px(raw["open"]),
        "high": _float_px(raw["high"]),
        "low": _float_px(raw["low"]),
        "close": _float_px(raw["close"]),
        "volume": raw["volume"].to_numpy().astype(np.int64),
        "symbol": _symbols(raw).to_numpy(),
        "instrument_id": raw["instrument_id"].to_numpy().astype(np.int64),
    }, index=core.ns_to_ts(ts))
    out.index.name = "ts"
    out = core.ensure_utc_index(out)
    out.attrs["bar_len"] = BAR_LEN.get(schema)
    out.attrs["schema"] = schema
    return out


def _stats(raw: pd.DataFrame) -> pd.DataFrame:
    q = raw["quantity"].to_numpy()
    undef_q = core.UNDEF_STAT_QUANTITY if q.dtype.itemsize >= 8 else np.iinfo(q.dtype).max
    qty = q.astype(np.float64)
    qty[q == undef_q] = np.nan
    d = {
        "ts_recv": _ts_int(raw["ts_recv"], "ts_recv"),
        "ts_event": _ts_int(raw["ts_event"], "ts_event"),
        "ts_ref": _ts_nullable(raw["ts_ref"]),
        "instrument_id": raw["instrument_id"].to_numpy().astype(np.int64),
        "symbol": _symbols(raw),
        "stat_type": np.asarray(raw["stat_type"]).astype(np.int64),
        "price": _float_px(raw["price"]),
        "quantity": qty,
        "update_action": np.asarray(raw["update_action"]).astype(np.int64),
        "sequence": raw["sequence"].to_numpy().astype(np.int64),
        "stat_flags": raw["stat_flags"].to_numpy().astype(np.int64),
        "channel_id": raw["channel_id"].to_numpy().astype(np.int64),
        "publisher_id": raw["publisher_id"].to_numpy().astype(np.int64),
    }
    return pd.DataFrame(d)[STATS_COLUMNS]


def _defs(raw: pd.DataFrame) -> pd.DataFrame:
    d: dict[str, Any] = {
        "instrument_id": raw["instrument_id"].to_numpy().astype(np.int64),
        "raw_symbol": _str_col(raw["raw_symbol"]),
        "instrument_class": _str_col(raw["instrument_class"]),
        "expiration": _ts_datetime(raw["expiration"]),
        "activation": _ts_datetime(raw["activation"]),
        "ts_recv": _ts_int(raw["ts_recv"], "ts_recv"),
        "ts_event": _ts_int(raw["ts_event"], "ts_event"),
        "symbol": _symbols(raw),
        "publisher_id": raw["publisher_id"].to_numpy().astype(np.int64),
        "underlying_id": raw["underlying_id"].to_numpy().astype(np.int64),
    }
    for c in ("min_price_increment", "unit_of_measure_qty", "strike_price", "display_factor",
              "high_limit_price", "low_limit_price", "min_price_increment_amount"):
        d[c] = _float_px(raw[c])
    for c in ("underlying", "asset", "security_update_action", "currency", "strike_price_currency",
              "exchange", "group", "cfi", "security_type", "unit_of_measure",
              "user_defined_instrument"):
        d[c] = _str_col(raw[c])
    for c, undef in _DEF_INT_UNDEF.items():
        v = raw[c].to_numpy()
        f = v.astype(np.float64)
        f[v == undef] = np.nan
        d[c] = f
    return pd.DataFrame(d)[DEFS_COLUMNS]


def _generic(raw: pd.DataFrame) -> pd.DataFrame:
    """Skema lain (status, imbalance, bbo-*, ...): kolom mentah, ts → int64, simbol diisi."""
    out = raw.copy()
    for c in ("ts_recv", "ts_event"):
        if c in out.columns:
            out[c] = _ts_int(out[c], c)
    if "instrument_id" in out.columns:
        out["instrument_id"] = out["instrument_id"].to_numpy().astype(np.int64)
        out["symbol"] = _symbols(raw).to_numpy()
    for c in ("rtype", "publisher_id", "action", "reason", "trading_event"):
        if c in out.columns and out[c].dtype.kind in "iu":
            out[c] = out[c].astype(np.int64)
    return out.reset_index(drop=True)


_EMPTY_COLUMNS = {
    "mbo": MBO_COLUMNS, "trades": TRADES_COLUMNS, "mbp-1": BBO_COLUMNS, "tbbo": BBO_COLUMNS,
    "mbp-10": BOOK_COLUMNS, "statistics": STATS_COLUMNS, "definition": DEFS_COLUMNS,
}


def load_dbn(path_or_store, schema: str | None = None, *,
             symbol_map: dict[int, str] | None = None) -> pd.DataFrame:
    """Muat berkas/objek DBN menjadi frame kanonik sesuai skemanya (SPEC §2).

    Parameter
    ---------
    path_or_store : str | Path | bytes | databento.DBNStore
        Berkas ``.dbn`` / ``.dbn.zst`` (kompresi dideteksi otomatis), isi bytes, atau store.
    schema : str, opsional
        Skema yang dibaca. Wajib bila metadata berkas tidak menyebut skema tunggal.

    Keluaran per skema
    ------------------
    - ``mbo`` → MBO; ``trades`` → TRADES; ``mbp-1``/``tbbo`` → BBO + kolom trade/event
      (catatan: pada TBBO, kolom bid/ask adalah kondisi buku SEBELUM trade);
    - ``mbp-10`` → BOOK (+ kolom event); ``ohlcv-*`` → BARS (indeks waktu buka bar, UTC ns);
    - ``definition`` → DEFS; ``statistics`` → STATS (``ts_ref`` bertipe Int64 nullable);
    - ``status`` dan skema lain → kolom mentah dengan ts int64 dan kolom ``symbol``.

    Urutan baris mengikuti urutan rekaman di berkas (urutan replay), tidak diurutkan ulang,
    kecuali BARS yang diurutkan stabil menurut indeks waktu.

    ``symbol_map`` (opsional, ``instrument_id → simbol``) menimpa pemetaan dari metadata.
    Penting untuk permintaan ``stype_in="parent"`` (mis. ``GC.FUT``): pemetaan metadata
    Databento memberi simbol induk untuk semua kontrak, sehingga gunakan peta dari DEFS
    (``dict(zip(defs.instrument_id, defs.raw_symbol))``) untuk simbol per kontrak.
    """
    store = _open_store(path_or_store)
    sch = canonical_schema(schema if schema is not None else store.schema)
    try:
        raw = store.to_df(price_type="float", pretty_ts=False, map_symbols=True, schema=sch)
    except ValueError as exc:
        raise core.GcquantError(f"Gagal membaca skema '{sch}' dari DBN: {exc}") from exc
    raw = raw.reset_index()
    if symbol_map and len(raw):
        iid = raw["instrument_id"].astype(np.int64)
        mapped = iid.map({int(k): str(v) for k, v in symbol_map.items()})
        base = raw["symbol"] if "symbol" in raw.columns else pd.Series(None, index=raw.index)
        raw["symbol"] = mapped.where(mapped.notna(), base)
    if len(raw) == 0:
        if sch.startswith("ohlcv"):
            out = _empty_frame(BARS_COLUMNS)
            out.index = pd.DatetimeIndex([], tz="UTC", name="ts").as_unit("ns")
            return out
        return _empty_frame(_EMPTY_COLUMNS.get(sch, ["ts_recv", "ts_event", "instrument_id",
                                                     "symbol"]))
    if sch == "mbo":
        return _mbo(raw)
    if sch == "trades":
        return _trades(raw)
    if sch in ("mbp-1", "tbbo"):
        return _bbo(raw)
    if sch == "mbp-10":
        return _book(raw)
    if sch.startswith("ohlcv"):
        return _bars(raw, sch)
    if sch == "statistics":
        return _stats(raw)
    if sch == "definition":
        return _defs(raw)
    return _generic(raw)


# ---------------------------------------------------------------------------
# Penulis DBN untuk data MBO sintetis (uji end-to-end tanpa jaringan)
# ---------------------------------------------------------------------------

def _price_to_fixed(price: np.ndarray) -> np.ndarray:
    px = np.asarray(price, dtype=np.float64)
    nan = ~np.isfinite(px)
    fixed = np.rint(np.where(nan, 0.0, px) * core.FIXED_PRICE_SCALE).astype(np.int64)
    fixed[nan] = core.UNDEF_PRICE
    return fixed


def write_synthetic_mbo_dbn(path, frame: pd.DataFrame, dataset: str = core.DATASET_CME) -> Path:
    """Tulis frame MBO kanonik ke berkas DBN (versi DBN terpasang) memakai ``databento_dbn``.

    Bila ``path`` berakhiran ``.zst`` isi dikompresi zstd. Metadata berisi pemetaan
    ``raw_symbol → instrument_id`` per tanggal (UTC) sehingga ``load_dbn`` mengembalikan kolom
    ``symbol`` yang sama. Harga NaN ditulis sebagai ``UNDEF_PRICE``. Dipakai untuk uji
    end-to-end dan contoh; BUKAN untuk memalsukan data bursa.
    """
    import databento_dbn as dbn

    missing = [c for c in MBO_COLUMNS if c not in frame.columns]
    if missing:
        raise core.GcquantError(f"Frame MBO tidak lengkap, kolom hilang: {missing}")
    if len(frame) == 0:
        raise core.GcquantError("Frame MBO kosong; tidak ada yang ditulis.")
    path = Path(os.fspath(path)).expanduser()
    ts_recv = frame["ts_recv"].to_numpy(np.int64)
    ts_event = frame["ts_event"].to_numpy(np.int64)
    size = frame["size"].to_numpy()
    if not np.all(np.isfinite(size.astype(np.float64))):
        raise core.GcquantError("Kolom size berisi NaN; tidak dapat ditulis ke DBN.")
    start_ns = int(min(ts_recv.min(), ts_event.min()))
    end_ns = int(max(ts_recv.max(), ts_event.max())) + 1

    # Pemetaan simbol per tanggal UTC (berdasarkan ts_recv, seperti DBNStore.to_df).
    days = pd.to_datetime(ts_recv, unit="ns", utc=True).date
    pairs = pd.DataFrame({"symbol": frame["symbol"].astype(str).to_numpy(),
                          "iid": frame["instrument_id"].to_numpy(np.int64), "day": days})
    mappings = []
    for sym, g in pairs.groupby("symbol", sort=True):
        intervals = []
        for iid, gg in g.groupby("iid", sort=True):
            d0, d1 = min(gg["day"]), max(gg["day"])
            intervals.append(_Interval(d0, d1 + _dt.timedelta(days=1), str(int(iid))))
        mappings.append(_Mapping(str(sym), intervals))
    meta = dbn.Metadata(
        dataset=dataset, start=start_ns, end=end_ns,
        stype_in=dbn.SType.RAW_SYMBOL, stype_out=dbn.SType.INSTRUMENT_ID,
        schema=dbn.Schema.MBO, symbols=sorted(pairs["symbol"].unique().tolist()),
        mappings=mappings,
    )

    price = _price_to_fixed(frame["price"].to_numpy())
    order_id = frame["order_id"].to_numpy().astype(np.uint64)
    iid = frame["instrument_id"].to_numpy(np.int64)
    flags = frame["flags"].to_numpy(np.int64)
    seq = frame["sequence"].to_numpy(np.int64)
    chan = frame["channel_id"].to_numpy(np.int64)
    pub = frame["publisher_id"].to_numpy(np.int64)
    action = frame["action"].astype(str).to_numpy()
    side = frame["side"].astype(str).to_numpy()
    size_i = size.astype(np.int64)
    delta = np.clip(ts_recv - ts_event, -(2**31), 2**31 - 1).astype(np.int64)
    act_map = {a: dbn.Action(a) for a in np.unique(action)}
    side_map = {s: dbn.Side(s) for s in np.unique(side)}

    chunks = [meta.encode()]
    for i in range(len(frame)):
        rec = dbn.MBOMsg(
            publisher_id=int(pub[i]), instrument_id=int(iid[i]), ts_event=int(ts_event[i]),
            order_id=int(order_id[i]), price=int(price[i]), size=int(size_i[i]),
            action=act_map[action[i]], side=side_map[side[i]], ts_recv=int(ts_recv[i]),
            flags=int(flags[i]), channel_id=int(chan[i]), ts_in_delta=int(delta[i]),
            sequence=int(seq[i]),
        )
        chunks.append(bytes(rec))
    data = b"".join(chunks)
    if path.name.endswith(".zst"):
        import zstandard
        data = zstandard.ZstdCompressor(level=3).compress(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return path


class _Interval:
    """Objek interval pemetaan simbol (protokol ``databento_dbn.MappingInterval``)."""

    def __init__(self, start_date: _dt.date, end_date: _dt.date, symbol: str):
        self.start_date = start_date
        self.end_date = end_date
        self.symbol = symbol


class _Mapping:
    """Objek pemetaan simbol (protokol ``databento_dbn.SymbolMapping``)."""

    def __init__(self, raw_symbol: str, intervals: Iterable[_Interval]):
        self.raw_symbol = raw_symbol
        self.intervals = list(intervals)
