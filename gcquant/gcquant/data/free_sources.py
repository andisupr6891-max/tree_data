"""Sumber data gratis/lokal: berkas M1 XAUUSD (ekspor MT5 / CSV generik) dan CSV harian.

Konvensi BARS (SPEC §2): indeks ``ts`` = waktu BUKA bar (UTC, ns), kolom
``open, high, low, close, volume`` dan opsional ``spread`` (USD). Bar diketahui pada
``ts + bar_len``.
"""
from __future__ import annotations

import os
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from .. import core

__all__ = ["load_m1_csv", "load_daily_csv", "resample_bars", "infer_bar_len"]

_TIME_NAMES = ("time", "timestamp", "datetime", "date_time", "gmt time", "utc", "ts")
_PRICE_NAMES = ("close", "settle", "price", "adj close", "adj_close", "last", "value", "px_last")


def _clean(name: str) -> str:
    return re.sub(r"[<>]", "", str(name)).strip().lower()


def _sniff_sep(first_line: str) -> str:
    if "\t" in first_line:
        return "\t"
    if ";" in first_line and first_line.count(";") >= first_line.count(","):
        return ";"
    return ","


def _read_head(path: Path) -> str:
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        return fh.readline()


def _localize(ts: pd.Series | pd.DatetimeIndex, tz) -> pd.DatetimeIndex:
    """Lokalisasi waktu naif ke ``tz`` lalu konversi ke UTC (ns). Waktu ambigu/tak ada → NaT."""
    idx = pd.DatetimeIndex(ts)
    if idx.tz is None:
        tzname = str(tz)
        if tzname.upper() in ("UTC", "GMT", "Z", "ETC/UTC"):
            idx = idx.tz_localize("UTC")
        else:
            idx = idx.tz_localize(tz, ambiguous="NaT", nonexistent="NaT")
    return idx.tz_convert("UTC").as_unit("ns")


def load_m1_csv(path, tz="UTC", *, point: float = 0.01, spread_in_points: bool | None = None,
                validate: bool = True) -> pd.DataFrame:
    """Muat berkas bar menit XAUUSD menjadi BARS (indeks = waktu buka, UTC ns).

    Format yang dikenali dari baris header:

    1. Ekspor MetaTrader 5 (dipisah tab): ``<DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE>
       <TICKVOL> <VOL> <SPREAD>``, tanggal ``2016.01.03``, jam ``23:00:00``.
    2. CSV generik (koma/titik koma/tab) dengan kolom waktu (``time``/``timestamp``/
       ``datetime`` atau ``date`` + ``time``), ``open, high, low, close`` dan opsional
       ``volume``/``tickvol``/``vol``, ``spread``/``spread_points``.

    ``tz``: zona waktu jam di berkas (bawaan UTC; mis. ``"Europe/Athens"`` untuk jam server
    broker). Waktu ambigu/tidak ada saat pergantian DST dibuang dengan peringatan.

    ``volume``: kolom ``VOL`` bila ada isinya (bukan nol semua), selain itu ``TICKVOL``
    (volume tick broker — BUKAN volume bursa). ``tick_volume`` selalu disertakan bila ada.

    ``spread`` (USD) = spread_points × ``point`` (bawaan 0,01 USD untuk XAUUSD 2 desimal).
    ``spread_in_points=None`` → otomatis: kolom ``spread``/``spread_points`` dianggap dalam
    point; berikan ``False`` bila berkas generik sudah memakai USD.

    Validasi (``validate=True``): baris harga tak valid (≤0/NaN) dibuang, timestamp duplikat
    dibuang (simpan yang pertama), data diurutkan; pelanggaran high/low dilaporkan sebagai
    peringatan (baris tetap disimpan).
    """
    path = Path(os.fspath(path)).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"Berkas tidak ditemukan: {path}")
    head = _read_head(path)
    sep = _sniff_sep(head)
    names = [c for c in head.rstrip("\r\n").split(sep)]
    text_cols = {n: str for n in names if _clean(n) in ("date", "time") + _TIME_NAMES}
    raw = pd.read_csv(path, sep=sep, dtype=text_cols, encoding="utf-8-sig", skipinitialspace=True)
    raw.columns = [_clean(c) for c in raw.columns]
    cols = set(raw.columns)

    # --- waktu ---------------------------------------------------------------------
    if "date" in cols and "time" in cols:
        stamp = raw["date"].str.strip() + " " + raw["time"].str.strip()
    else:
        tcol = next((c for c in _TIME_NAMES if c in cols), None)
        if tcol is None and "date" in cols:
            tcol = "date"
        if tcol is None:
            raise core.GcquantError(f"Kolom waktu tidak ditemukan di {path.name}; kolom: "
                                    f"{list(raw.columns)}")
        stamp = raw[tcol].str.strip()
    stamp = stamp.str.replace(r"^(\d{4})\.(\d{2})\.(\d{2})", r"\1-\2-\3", regex=True)
    try:
        ts = pd.to_datetime(stamp, format="%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        ts = pd.to_datetime(stamp, format="mixed", errors="coerce")
    idx = _localize(ts, tz)

    # --- harga, volume, spread --------------------------------------------------------
    need = ["open", "high", "low", "close"]
    miss = [c for c in need if c not in cols]
    if miss:
        raise core.GcquantError(f"Kolom harga hilang di {path.name}: {miss}")
    out = pd.DataFrame({c: pd.to_numeric(raw[c], errors="coerce").to_numpy(np.float64)
                        for c in need}, index=idx)
    tickvol = next((c for c in ("tickvol", "tick_volume", "tickvolume") if c in cols), None)
    realvol = next((c for c in ("vol", "volume", "real_volume") if c in cols), None)
    tv = pd.to_numeric(raw[tickvol], errors="coerce").fillna(0).to_numpy() if tickvol else None
    rv = pd.to_numeric(raw[realvol], errors="coerce").fillna(0).to_numpy() if realvol else None
    if rv is not None and (np.nansum(rv) > 0 or tv is None):
        out["volume"] = rv.astype(np.int64)
    elif tv is not None:
        out["volume"] = tv.astype(np.int64)
    else:
        out["volume"] = np.zeros(len(out), dtype=np.int64)
    if tv is not None:
        out["tick_volume"] = tv.astype(np.int64)
    spcol = next((c for c in ("spread_points", "spread") if c in cols), None)
    if spcol is not None:
        sp = pd.to_numeric(raw[spcol], errors="coerce").to_numpy(np.float64)
        in_points = True if spread_in_points is None else bool(spread_in_points)
        out["spread"] = np.round(sp * point, 10) if in_points else sp
    out.index.name = "ts"

    # --- validasi ----------------------------------------------------------------------
    if validate:
        bad_ts = out.index.isna()
        px = out[need].to_numpy()
        bad_px = ~np.isfinite(px).all(axis=1) | (px <= 0).any(axis=1)
        drop = bad_ts | bad_px
        if drop.any():
            warnings.warn(f"{path.name}: {int(drop.sum())} baris dibuang (waktu/harga tidak valid).",
                          stacklevel=2)
            out = out[~drop]
        if not out.index.is_monotonic_increasing:
            out = out.sort_index(kind="stable")
        dup = out.index.duplicated(keep="first")
        if dup.any():
            warnings.warn(f"{path.name}: {int(dup.sum())} timestamp duplikat dibuang.", stacklevel=2)
            out = out[~dup]
        o, h, l, c = (out[k].to_numpy() for k in need)
        viol = (h < np.maximum(o, c) - 1e-9) | (l > np.minimum(o, c) + 1e-9) | (h < l)
        if viol.any():
            warnings.warn(f"{path.name}: {int(viol.sum())} bar melanggar konsistensi high/low.",
                          stacklevel=2)
    out.attrs["bar_len"] = "1min"
    out.attrs["source"] = str(path)
    return out


def load_daily_csv(path, date_col: str | None = None, price_col: str | None = None,
                   tz="UTC") -> pd.DataFrame:
    """Muat CSV harian generik → DataFrame berindeks tanggal (``datetime64[ns, UTC]``, 00:00).

    - Pemisah dideteksi dari header (koma, titik koma, tab); header MT5 ``<DATE>`` dikenali.
    - ``date_col`` bawaan: kolom pertama bernama date/time/timestamp/datetime/tanggal.
    - Kolom numerik dikonversi ke float; nama kolom di-lowercase (tanpa ``<>``).
    - Bila ``price_col`` diberikan atau terdeteksi (close/settle/price/adj close/last/value),
      kolom ``price`` ditambahkan sebagai salinannya.
    Baris dengan tanggal tak valid dibuang; tanggal duplikat → simpan yang terakhir
    (koreksi data biasanya ditambahkan belakangan).
    """
    path = Path(os.fspath(path)).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"Berkas tidak ditemukan: {path}")
    sep = _sniff_sep(_read_head(path))
    raw = pd.read_csv(path, sep=sep, dtype=str, encoding="utf-8-sig", skipinitialspace=True)
    orig = list(raw.columns)
    raw.columns = [_clean(c) for c in raw.columns]
    if date_col is not None:
        dcol = _clean(date_col)
        if dcol not in raw.columns:
            raise core.GcquantError(f"Kolom tanggal '{date_col}' tidak ada; kolom: {orig}")
    else:
        dcol = next((c for c in ("date", "tanggal", "time", "timestamp", "datetime", "day")
                     if c in raw.columns), None)
        if dcol is None:
            raise core.GcquantError(f"Kolom tanggal tidak ditemukan; kolom: {orig}")
    s = raw[dcol].astype(str).str.strip()
    s = s.str.replace(r"^(\d{4})\.(\d{2})\.(\d{2})", r"\1-\2-\3", regex=True)
    dates = pd.to_datetime(s, errors="coerce", format="mixed")
    idx = _localize(dates, tz).normalize()
    out = pd.DataFrame(index=idx)
    for c in raw.columns:
        if c == dcol:
            continue
        num = pd.to_numeric(raw[c].str.replace(",", "", regex=False) if sep != "," else raw[c],
                            errors="coerce")
        out[c] = num.to_numpy(np.float64) if num.notna().any() else raw[c].to_numpy()
    out = out[~out.index.isna()]
    out = out.sort_index(kind="stable")
    out = out[~out.index.duplicated(keep="last")]
    pcol = _clean(price_col) if price_col is not None else next(
        (c for c in _PRICE_NAMES if c in out.columns), None)
    if price_col is not None and pcol not in out.columns:
        raise core.GcquantError(f"Kolom harga '{price_col}' tidak ada; kolom: {orig}")
    if pcol is not None:
        out["price"] = out[pcol].astype(np.float64)
    out.index.name = "date"
    return out


# ---------------------------------------------------------------------------
# Resampling kausal
# ---------------------------------------------------------------------------

def infer_bar_len(index: pd.DatetimeIndex) -> pd.Timedelta:
    """Perkirakan panjang bar sumber = selisih positif yang paling sering (modus)."""
    ns = pd.DatetimeIndex(index).as_unit("ns").asi8
    d = np.diff(np.unique(ns))
    if len(d) == 0:
        raise core.GcquantError("Tidak dapat menebak panjang bar dari < 2 timestamp; "
                                "berikan source_bar_len.")
    vals, counts = np.unique(d, return_counts=True)
    return pd.Timedelta(int(vals[np.argmax(counts)]), unit="ns")


def _rule_ns(rule) -> int:
    """Durasi tetap sebuah aturan resample dalam ns; aturan kalender (bulan, hari kerja) ditolak."""
    import datetime as _dt
    from pandas.tseries.frequencies import to_offset

    if isinstance(rule, (pd.Timedelta, _dt.timedelta, np.timedelta64)):
        return int(pd.Timedelta(rule).value)
    try:
        off = to_offset(rule)
    except (ValueError, TypeError):
        off = None
    if off is None:
        try:
            return int(pd.to_timedelta(rule).value)
        except (ValueError, TypeError) as exc:
            raise core.GcquantError(f"rule '{rule}' tidak dikenali (gunakan mis. '5min', '1h', "
                                    "'1D').") from exc
    if isinstance(off, pd.offsets.Tick):
        return int(off.nanos)
    if type(off) is pd.offsets.Day:
        return int(off.n) * 86_400 * core.NS_PER_SEC          # UTC: satu hari = 24 jam tetap
    if type(off) is pd.offsets.Week and off.weekday is None:
        return int(off.n) * 7 * 86_400 * core.NS_PER_SEC
    raise core.GcquantError(f"rule '{rule}' adalah aturan kalender ({type(off).__name__}), bukan "
                            "durasi tetap; gunakan mis. '5min', '1h', '1D'.")


def resample_bars(bars: pd.DataFrame, rule, *, source_bar_len=None, offset=None,
                  drop_partial: bool = True, spread_agg: str = "mean") -> pd.DataFrame:
    """Agregasi BARS ke bar yang lebih panjang secara KAUSAL (label = waktu buka, kiri-tertutup).

    - Bin ``[t, t + rule)`` diberi label ``t`` (waktu BUKA); jangkar = epoch UTC (+``offset``,
      mis. ``"22h"`` agar hari dimulai 22:00 UTC). Bar hasil diketahui pada ``t + rule``.
    - Bar sumber berlabel ``s`` dengan panjang ``L`` masuk bin ``t`` hanya bila seluruh
      rentangnya ``[s, s + L)`` berada di dalam bin. Bila ada bar sumber yang menjorok melewati
      akhir bin (``s + L > t + rule``, data "dari masa depan" relatif terhadap akhir label),
      bin tersebut DIBUANG beserta peringatan.
    - ``drop_partial=True``: bin terakhir yang belum lengkap (akhir data sumber
      ``s_last + L < t + rule``) dibuang — bar itu belum final pada akhir data.
    - Bin tanpa data (akhir pekan, jeda) tidak dibuat (bukan baris NaN).
    Agregasi: open=first, high=max, low=min, close=last, volume/tick_volume=sum,
    spread=``spread_agg`` (bawaan mean), kolom lain=last. ``rule`` harus durasi tetap
    (mis. "5min", "1h", "1D"); aturan kalender (bulan, kuartal) ditolak. Catatan: "1W" diartikan
    7 hari tetap yang berjangkar pada epoch (Kamis 00:00 UTC) — atur ``offset`` bila perlu.
    """
    if not isinstance(bars.index, pd.DatetimeIndex):
        raise core.GcquantError("bars harus berindeks DatetimeIndex (waktu buka bar).")
    rule_ns = _rule_ns(rule)
    rule_td = pd.Timedelta(rule_ns, unit="ns")
    if rule_ns <= 0:
        raise core.GcquantError("rule harus positif.")
    df = core.ensure_utc_index(bars)
    if len(df) == 0:
        return df.copy()
    if "symbol" in df.columns and df["symbol"].nunique(dropna=True) > 1:
        raise core.GcquantError("resample_bars hanya untuk satu instrumen; pisahkan per simbol dulu.")
    if df.index.has_duplicates:
        raise core.GcquantError("Indeks bar berisi timestamp duplikat; bersihkan dulu.")
    src_len = pd.to_timedelta(source_bar_len) if source_bar_len is not None else (
        pd.to_timedelta(bars.attrs["bar_len"]) if bars.attrs.get("bar_len") else
        infer_bar_len(df.index))
    src_ns = int(src_len.value)
    if src_ns > rule_ns:
        raise core.GcquantError(f"Bar sumber ({src_len}) lebih panjang dari rule ({rule_td}).")
    off_ns = int(pd.to_timedelta(offset).value) if offset is not None else 0

    ts = df.index.asi8
    label = (ts - off_ns) // rule_ns * rule_ns + off_ns
    bin_end = label + rule_ns
    leak = ts + src_ns > bin_end
    keep_bin = pd.Series(~leak).groupby(label).all()
    bad_labels = keep_bin.index[~keep_bin.to_numpy()]
    if len(bad_labels):
        warnings.warn(f"resample_bars: {len(bad_labels)} bin dibuang karena berisi bar sumber yang "
                      "melewati akhir bin (data masa depan relatif terhadap label).", stacklevel=2)

    agg: dict[str, str] = {}
    for c in df.columns:
        if c == "open":
            agg[c] = "first"
        elif c == "high":
            agg[c] = "max"
        elif c == "low":
            agg[c] = "min"
        elif c == "close":
            agg[c] = "last"
        elif c in ("volume", "tick_volume"):
            agg[c] = "sum"
        elif c == "spread":
            agg[c] = spread_agg
        else:
            agg[c] = "last"
    g = df.groupby(label, sort=True)
    out = g.agg(agg)
    last_end = pd.Series(ts + src_ns).groupby(label).max()
    valid = keep_bin.reindex(out.index).to_numpy(dtype=bool, copy=True)
    if drop_partial:
        lab = out.index.to_numpy()
        is_last = lab == lab.max()
        incomplete = last_end.reindex(out.index).to_numpy() < lab + rule_ns
        valid &= ~(is_last & incomplete)
    out = out[valid]
    out.index = core.ns_to_ts(out.index.to_numpy(np.int64))
    out.index.name = "ts"
    for c in ("volume", "tick_volume"):
        if c in out.columns and df[c].dtype.kind in "iu":
            out[c] = out[c].astype(np.int64)
    out.attrs = dict(bars.attrs)
    out.attrs["bar_len"] = str(rule)
    return out
