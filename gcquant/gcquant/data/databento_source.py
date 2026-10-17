"""Sumber data Databento dengan PENGAMAN BIAYA (SPEC §0.1) dan cache disk.

Aturan yang ditegakkan modul ini:

1. Bawaan ``max_cost_usd = 0.0``: tidak ada unduhan berbayar tanpa anggaran eksplisit.
2. ``metadata.get_cost`` (gratis) SELALU dipanggil sebelum ``timeseries.get_range``; bila
   perkiraan biaya > anggaran → ``core.BiayaDitolak`` dan ``get_range`` tidak pernah dipanggil.
3. Hasil unduhan disimpan ke ``<cache_dir>/<sha256>.dbn.zst`` + sidecar ``<sha256>.json``
   (permintaan, biaya, waktu dibuat). Cache hit TIDAK menyentuh klien sama sekali —
   bahkan kunci API tidak diperlukan.
4. Langganan live (``LiveFeed``) ditolak kecuali ``allow_live=True``.

Klien ``databento.Historical`` dibuat secara malas (lazy) hanya saat benar-benar diperlukan;
membuatnya sendiri tidak melakukan koneksi jaringan.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import logging
import math
import os
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np

from .. import core
from .dbn_io import canonical_schema

__all__ = ["DatabentoSource", "LiveFeed", "record_to_dict", "normalize_request", "request_key"]

log = logging.getLogger(__name__)

_I64_MAX = np.iinfo(np.int64).max
_UNDEF_TS = int(np.iinfo(np.uint64).max)


# ---------------------------------------------------------------------------
# Normalisasi permintaan & kunci cache
# ---------------------------------------------------------------------------

def _norm_symbols(symbols) -> list[str]:
    if symbols is None:
        raise core.GcquantError("symbols wajib diisi (gunakan 'ALL_SYMBOLS' secara eksplisit "
                                "bila memang ingin semua simbol).")
    if isinstance(symbols, (str, int, np.integer)):
        symbols = [symbols]
    out = sorted({str(s).strip() for s in symbols if str(s).strip()})
    if not out:
        raise core.GcquantError("Daftar symbols kosong.")
    return out


def normalize_request(dataset: str, schema: str, symbols, start, end,
                      stype_in: str = "raw_symbol") -> dict[str, Any]:
    """Bentuk normal permintaan historis (dasar kunci cache dan argumen API).

    ``start``/``end`` diubah ke int64 ns UTC (string tanpa zona dianggap UTC), simbol
    diurutkan & dideduplikasi, nama dataset huruf besar, skema/stype huruf kecil.
    ``end`` wajib diisi agar permintaan deterministik (``end=None`` berarti "sampai data
    terbaru" yang berubah dari waktu ke waktu, sehingga tidak boleh di-cache).
    """
    if end is None:
        raise core.GcquantError("end wajib diisi: permintaan tanpa batas akhir tidak deterministik "
                                "sehingga tidak dapat di-cache maupun diperkirakan biayanya.")
    start_ns = int(core.to_ns(start))
    end_ns = int(core.to_ns(end))
    if end_ns <= start_ns:
        raise core.GcquantError(f"end harus setelah start (start={start!r}, end={end!r}).")
    return {
        "dataset": str(dataset).strip().upper(),
        "schema": canonical_schema(schema),
        "symbols": _norm_symbols(symbols),
        "stype_in": canonical_schema(stype_in),
        "start_ns": start_ns,
        "end_ns": end_ns,
    }


def request_key(req: dict[str, Any]) -> str:
    """sha256 heksadesimal dari permintaan ter-normalisasi (JSON kunci terurut)."""
    blob = json.dumps(req, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _api_kwargs(req: dict[str, Any]) -> dict[str, Any]:
    return dict(dataset=req["dataset"], schema=req["schema"], symbols=list(req["symbols"]),
                start=req["start_ns"], end=req["end_ns"], stype_in=req["stype_in"])


def _iso(ns: int) -> str:
    return core.ns_to_ts(ns).isoformat()


def _check_budget(value, name: str = "max_cost_usd") -> float:
    try:
        v = float(value)
    except (TypeError, ValueError) as exc:
        raise core.GcquantError(f"{name} harus angka (USD), bukan {value!r}.") from exc
    if not math.isfinite(v) or v < 0:
        raise core.GcquantError(f"{name} harus angka hingga (finite) ≥ 0, bukan {value!r}.")
    return v


class DatabentoSource:
    """Akses historis Databento dengan pengaman biaya dan cache.

    Parameter
    ---------
    key : str, opsional
        Kunci API; bila kosong dibaca dari ``DATABENTO_API_KEY``. Tidak diperlukan untuk
        cache hit maupun bila ``client`` disuntikkan.
    cache_dir : str | Path
        Direktori cache (bawaan ``~/.gcquant/cache``).
    max_cost_usd : float
        Anggaran per permintaan dalam USD. Bawaan 0.0 = hanya data berbiaya nol yang boleh.
    client : objek mirip ``databento.Historical``, opsional
        Untuk uji (klien palsu tanpa jaringan) atau klien yang sudah dikonfigurasi.

    Contoh
    ------
    >>> src = DatabentoSource()                      # anggaran 0 USD
    >>> src.estimate("GLBX.MDP3", "mbo", "GCG6", "2026-01-05", "2026-01-06")  # gratis
    >>> src.get(..., max_cost_usd=2.5)               # izin eksplisit hingga 2,50 USD
    """

    def __init__(self, key: str | None = None, cache_dir: str | os.PathLike = "~/.gcquant/cache",
                 max_cost_usd: float = 0.0, client: Any = None):
        self._key = key if key is not None else os.environ.get("DATABENTO_API_KEY")
        self.cache_dir = Path(os.fspath(cache_dir)).expanduser()
        self.max_cost_usd = _check_budget(max_cost_usd)
        self._client = client
        self.api_log: list[tuple[str, dict[str, Any]]] = []   # jejak audit panggilan API

    # -- klien ---------------------------------------------------------------
    @property
    def client(self):
        """Klien ``databento.Historical`` (dibuat saat pertama dibutuhkan, tanpa jaringan)."""
        if self._client is None:
            if not self._key or not str(self._key).strip():
                raise core.GcquantError(
                    "Kunci API Databento tidak ditemukan. Berikan key=... atau set variabel "
                    "lingkungan DATABENTO_API_KEY. (Data yang sudah ada di cache tetap bisa dibaca "
                    "tanpa kunci.)")
            import databento as db
            self._client = db.Historical(self._key)
        return self._client

    # -- cache ---------------------------------------------------------------
    def cache_paths(self, key: str) -> tuple[Path, Path]:
        """Path berkas data ``.dbn.zst`` dan sidecar ``.json`` untuk sebuah kunci cache."""
        return self.cache_dir / f"{key}.dbn.zst", self.cache_dir / f"{key}.json"

    def is_cached(self, dataset, schema, symbols, start, end, stype_in="raw_symbol") -> bool:
        """True bila permintaan ini sudah ada di cache (tanpa memanggil API)."""
        key = request_key(normalize_request(dataset, schema, symbols, start, end, stype_in))
        data, meta = self.cache_paths(key)
        return data.is_file() and meta.is_file() and data.stat().st_size > 0

    # -- metadata gratis -----------------------------------------------------
    def _cost(self, req: dict[str, Any]) -> float:
        kw = _api_kwargs(req)
        self.api_log.append(("metadata.get_cost", kw))
        cost = self.client.metadata.get_cost(**kw)
        try:
            cost = float(cost)
        except (TypeError, ValueError) as exc:
            raise core.BiayaDitolak(f"Perkiraan biaya Databento tidak valid ({cost!r}); "
                                    "permintaan ditolak demi keamanan.") from exc
        if not math.isfinite(cost) or cost < 0:
            raise core.BiayaDitolak(f"Perkiraan biaya Databento tidak valid ({cost!r}); "
                                    "permintaan ditolak demi keamanan.")
        return cost

    def estimate(self, dataset, schema, symbols, start, end, stype_in="raw_symbol") -> dict:
        """Perkiraan biaya, ukuran, dan jumlah rekaman — HANYA panggilan metadata gratis.

        Mengembalikan ``dict(cost_usd, size_bytes, records, cached, request)``.
        """
        req = normalize_request(dataset, schema, symbols, start, end, stype_in)
        kw = _api_kwargs(req)
        cost = self._cost(req)
        self.api_log.append(("metadata.get_billable_size", kw))
        size = int(self.client.metadata.get_billable_size(**kw))
        self.api_log.append(("metadata.get_record_count", kw))
        records = int(self.client.metadata.get_record_count(**kw))
        data, meta = self.cache_paths(request_key(req))
        return {"cost_usd": cost, "size_bytes": size, "records": records,
                "cached": data.is_file() and meta.is_file(), "request": req}

    def free_metadata(self, dataset: str = core.DATASET_CME) -> dict:
        """Daftar dataset, skema, dan rentang waktu dataset (semuanya endpoint gratis)."""
        c = self.client.metadata
        self.api_log.append(("metadata.list_datasets", {}))
        datasets = c.list_datasets()
        self.api_log.append(("metadata.list_schemas", {"dataset": dataset}))
        schemas = c.list_schemas(dataset=dataset)
        self.api_log.append(("metadata.get_dataset_range", {"dataset": dataset}))
        rng = c.get_dataset_range(dataset=dataset)
        return {"dataset": dataset, "datasets": list(datasets), "schemas": list(schemas),
                "dataset_range": dict(rng) if isinstance(rng, dict) else rng}

    # -- unduhan berpengaman ---------------------------------------------------
    def get(self, dataset, schema, symbols, start, end, stype_in="raw_symbol",
            max_cost_usd: float | None = None):
        """Ambil data historis sebagai ``databento.DBNStore`` (cache → pengaman biaya → unduh).

        Urutan: (1) cache hit → langsung dibaca dari disk, nol panggilan API;
        (2) ``metadata.get_cost`` gratis; (3) bila biaya > anggaran → ``BiayaDitolak``;
        (4) ``timeseries.get_range`` ditulis atomik ke cache + sidecar JSON.

        ``max_cost_usd`` menimpa anggaran objek untuk satu panggilan ini saja.
        """
        import databento as db

        req = normalize_request(dataset, schema, symbols, start, end, stype_in)
        key = request_key(req)
        data_path, meta_path = self.cache_paths(key)
        if data_path.is_file() and meta_path.is_file() and data_path.stat().st_size > 0:
            log.info("cache hit %s", data_path)
            return db.DBNStore.from_file(data_path)

        budget = self.max_cost_usd if max_cost_usd is None else _check_budget(max_cost_usd)
        cost = self._cost(req)
        if cost > budget:
            saran = math.ceil(cost * 100.0) / 100.0
            raise core.BiayaDitolak(
                f"Unduhan DITOLAK: perkiraan biaya Databento US${cost:,.4f} untuk "
                f"{req['dataset']}/{req['schema']} simbol={req['symbols']} "
                f"{_iso(req['start_ns'])} s.d. {_iso(req['end_ns'])} melebihi anggaran "
                f"US${budget:,.4f}. Tidak ada data yang diunduh dan tidak ada biaya yang dikenakan. "
                f"Bila Anda memang bersedia membayar, naikkan anggaran secara eksplisit, mis. "
                f"DatabentoSource(max_cost_usd={saran:.2f}) atau .get(..., max_cost_usd={saran:.2f})."
            )

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = data_path.with_name(f"{data_path.name}.{os.getpid()}.part")
        kw = _api_kwargs(req)
        self.api_log.append(("timeseries.get_range", kw))
        try:
            store = self.client.timeseries.get_range(**kw, path=str(tmp))
            if not tmp.is_file() or tmp.stat().st_size == 0:
                store.to_file(tmp)
            os.replace(tmp, data_path)
        finally:
            if tmp.exists():
                tmp.unlink()
        sidecar = {
            "request": req,
            "request_iso": {"start": _iso(req["start_ns"]), "end": _iso(req["end_ns"])},
            "cost_usd": cost,
            "budget_usd": budget,
            "created": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "file": data_path.name,
            "bytes": data_path.stat().st_size,
        }
        tmp_meta = meta_path.with_name(meta_path.name + ".tmp")
        tmp_meta.write_text(json.dumps(sidecar, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp_meta, meta_path)
        return db.DBNStore.from_file(data_path)


# ---------------------------------------------------------------------------
# Konversi rekaman DBN → dict baris kanonik (dipakai LiveFeed dan uji)
# ---------------------------------------------------------------------------

def _px(v: int) -> float:
    v = int(v)
    return float("nan") if v == core.UNDEF_PRICE else v / core.FIXED_PRICE_SCALE


def _enum_str(v) -> str:
    val = getattr(v, "value", v)
    return "" if val is None else str(val)


def _enum_int(v) -> int:
    val = getattr(v, "value", v)
    return int(val)


def _ts(v: int, allow_undef: bool = False):
    v = int(v)
    if v == _UNDEF_TS:
        if allow_undef:
            return None
        raise core.GcquantError("Timestamp tak terdefinisi pada rekaman.")
    return v


def _size(v: int, undef: int = core.UNDEF_ORDER_SIZE):
    v = int(v)
    return float("nan") if v == undef else v


def record_to_dict(rec, symbol_map: dict[int, str] | None = None) -> dict[str, Any] | None:
    """Ubah satu rekaman ``databento_dbn`` menjadi dict baris kanonik (kolom = SPEC §2).

    Isi dict sama dengan baris yang dihasilkan ``load_dbn`` untuk skema yang sama
    (MBO, TRADES, BBO untuk MBP-1/TBBO, BOOK untuk MBP-10, STATS, DEFS, BARS: ``ts`` = waktu
    buka bar dalam int64 ns). ``SymbolMappingMsg``/``SystemMsg``/``ErrorMsg`` → None.
    Simbol diambil dari ``symbol_map[instrument_id]``, bila tidak ada → ``str(instrument_id)``.
    """
    import databento_dbn as dbn

    if isinstance(rec, (dbn.SymbolMappingMsg, dbn.SystemMsg, dbn.ErrorMsg)):
        return None
    iid = int(rec.instrument_id)
    sym = (symbol_map or {}).get(iid)
    sym = str(sym) if sym is not None else str(iid)

    def base() -> dict[str, Any]:
        return {"ts_recv": _ts(rec.ts_recv), "ts_event": _ts(rec.ts_event),
                "instrument_id": iid, "symbol": sym}

    def event() -> dict[str, Any]:
        return {"action": _enum_str(rec.action), "side": _enum_str(rec.side),
                "depth": int(rec.depth), "price": _px(rec.price), "size": _size(rec.size),
                "flags": int(rec.flags), "sequence": int(rec.sequence),
                "publisher_id": int(rec.publisher_id)}

    if isinstance(rec, dbn.MBOMsg):
        return {"ts_recv": _ts(rec.ts_recv), "ts_event": _ts(rec.ts_event), "instrument_id": iid,
                "order_id": int(rec.order_id), "action": _enum_str(rec.action),
                "side": _enum_str(rec.side), "price": _px(rec.price), "size": _size(rec.size),
                "flags": int(rec.flags), "sequence": int(rec.sequence),
                "channel_id": int(rec.channel_id), "publisher_id": int(rec.publisher_id),
                "symbol": sym}
    if isinstance(rec, dbn.TradeMsg):
        d = base()
        d.update(event())
        return d
    if isinstance(rec, dbn.MBP10Msg):
        d = base()
        for i, lv in enumerate(rec.levels):
            d[f"bid_px_{i:02d}"] = _px(lv.bid_px)
            d[f"ask_px_{i:02d}"] = _px(lv.ask_px)
            d[f"bid_sz_{i:02d}"] = int(lv.bid_sz)
            d[f"ask_sz_{i:02d}"] = int(lv.ask_sz)
            d[f"bid_ct_{i:02d}"] = int(lv.bid_ct)
            d[f"ask_ct_{i:02d}"] = int(lv.ask_ct)
        d.update(event())
        return d
    if isinstance(rec, dbn.MBP1Msg):
        lv = rec.levels[0]
        d = base()
        d.update({"bid_px": _px(lv.bid_px), "ask_px": _px(lv.ask_px), "bid_sz": int(lv.bid_sz),
                  "ask_sz": int(lv.ask_sz), "bid_ct": int(lv.bid_ct), "ask_ct": int(lv.ask_ct)})
        d.update(event())
        return d
    if isinstance(rec, dbn.OHLCVMsg):
        return {"ts": _ts(rec.ts_event), "open": _px(rec.open), "high": _px(rec.high),
                "low": _px(rec.low), "close": _px(rec.close), "volume": int(rec.volume),
                "symbol": sym, "instrument_id": iid}
    if isinstance(rec, dbn.StatMsg):
        d = {"ts_recv": _ts(rec.ts_recv), "ts_event": _ts(rec.ts_event),
             "ts_ref": _ts(rec.ts_ref, allow_undef=True), "instrument_id": iid, "symbol": sym,
             "stat_type": _enum_int(rec.stat_type), "price": _px(rec.price),
             "quantity": _size(rec.quantity, core.UNDEF_STAT_QUANTITY),
             "update_action": _enum_int(rec.update_action), "sequence": int(rec.sequence),
             "stat_flags": int(rec.stat_flags), "channel_id": int(rec.channel_id),
             "publisher_id": int(rec.publisher_id)}
        if isinstance(d["quantity"], int):
            d["quantity"] = float(d["quantity"])
        return d
    if isinstance(rec, dbn.InstrumentDefMsg):
        exp = _ts(rec.expiration, allow_undef=True)
        act = _ts(rec.activation, allow_undef=True)
        return {"instrument_id": iid, "raw_symbol": str(rec.raw_symbol),
                "instrument_class": _enum_str(rec.instrument_class),
                "expiration": core.ns_to_ts(exp) if exp is not None else None,
                "activation": core.ns_to_ts(act) if act is not None else None,
                "min_price_increment": _px(rec.min_price_increment),
                "unit_of_measure_qty": _px(rec.unit_of_measure_qty),
                "strike_price": _px(rec.strike_price), "underlying": str(rec.underlying),
                "asset": str(rec.asset), "ts_recv": _ts(rec.ts_recv),
                "ts_event": _ts(rec.ts_event), "symbol": sym,
                "publisher_id": int(rec.publisher_id),
                "security_update_action": _enum_str(rec.security_update_action),
                "underlying_id": int(rec.underlying_id)}
    # Rekaman lain (status, imbalance, ...): atribut publik apa adanya.
    out: dict[str, Any] = {"rtype": _enum_str(rec.rtype), "symbol": sym, "instrument_id": iid}
    for name in getattr(type(rec), "_ordered_fields", []):
        if name != "rtype":
            val = getattr(rec, name, None)
            out[name] = getattr(val, "value", val)
    return out


# ---------------------------------------------------------------------------
# Live
# ---------------------------------------------------------------------------

class LiveFeed:
    """Pembungkus tipis ``databento.Live``; DITOLAK kecuali ``allow_live=True``.

    Langganan live (termasuk intraday replay dengan ``start``) ditagih per pemakaian,
    sehingga harus diizinkan secara eksplisit. Callback menerima dict baris kanonik
    (lihat ``record_to_dict``); pemetaan simbol diperbarui dari ``SymbolMappingMsg``.
    Tidak ada koneksi yang dibuka sebelum ``subscribe``.
    """

    def __init__(self, key: str | None = None, allow_live: bool = False, client: Any = None):
        if allow_live is not True:
            raise core.BiayaDitolak(
                "Langganan live Databento DITOLAK: data live ditagih per pemakaian. "
                "Bila Anda memang bersedia membayar, buat ulang dengan LiveFeed(allow_live=True).")
        self._key = key if key is not None else os.environ.get("DATABENTO_API_KEY")
        self._client = client
        self.symbol_map: dict[int, str] = {}
        self.subscriptions: list[dict[str, Any]] = []

    @property
    def client(self):
        if self._client is None:
            if not self._key or not str(self._key).strip():
                raise core.GcquantError("Kunci API Databento tidak ditemukan (key=... atau "
                                        "DATABENTO_API_KEY).")
            import databento as db
            self._client = db.Live(key=self._key)
        return self._client

    def subscribe(self, dataset: str = core.DATASET_CME, schema: str = "mbo",
                  symbols: Iterable[str] | str = "ALL_SYMBOLS", stype_in: str = "raw_symbol",
                  start=None, snapshot: bool = False):
        """Tambah langganan (membuka koneksi TCP pada langganan pertama)."""
        if snapshot and start is not None:
            raise core.GcquantError("snapshot=True mensyaratkan start=None.")
        kw = dict(dataset=dataset, schema=canonical_schema(schema), symbols=symbols,
                  stype_in=canonical_schema(stype_in), start=start, snapshot=snapshot)
        self.subscriptions.append(kw)
        return self.client.subscribe(**kw)

    def handle(self, rec) -> dict[str, Any] | None:
        """Proses satu rekaman: perbarui peta simbol; kembalikan dict kanonik atau None."""
        import databento_dbn as dbn
        if isinstance(rec, dbn.SymbolMappingMsg):
            self.symbol_map[int(rec.instrument_id)] = str(rec.stype_out_symbol)
            return None
        if isinstance(rec, dbn.ErrorMsg):
            log.warning("Galat dari gateway live Databento: %s", rec.err)
        return record_to_dict(rec, self.symbol_map)

    def add_callback(self, fn: Callable[[dict[str, Any]], None],
                     exception_callback: Callable[[Exception], None] | None = None) -> None:
        """Daftarkan ``fn(row_dict)`` yang dipanggil untuk setiap rekaman data pasar."""
        def _cb(rec):
            row = self.handle(rec)
            if row is not None:
                fn(row)
        self.client.add_callback(_cb, exception_callback)

    def start(self) -> None:
        self.client.start()

    def stop(self) -> None:
        self.client.stop()

    def block_for_close(self, timeout: float | None = None) -> None:
        self.client.block_for_close(timeout=timeout)
