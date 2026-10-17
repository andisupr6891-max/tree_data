"""Utilitas level-1 (BBO): turunan dari frame BOOK, mid, spread, weighted mid.

Semua fungsi menerima frame BBO kanonik (``bid_px, ask_px, bid_sz, ask_sz``)
ATAU frame BOOK/MBP (``bid_px_00, ask_px_00, bid_sz_00, ask_sz_00``) dan
mengembalikan ``pd.Series`` yang sejajar dengan baris input (indeks sama).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..core import GcquantError

__all__ = ["bbo_from_book", "l1_arrays", "mid", "spread", "weighted_mid"]

_BBO_META = ["ts_recv", "ts_event", "instrument_id", "symbol"]


def l1_arrays(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Ambil ``(bid_px, ask_px, bid_sz, ask_sz)`` sebagai array float64.

    Harga kosong → NaN; ukuran kosong/NaN → 0.
    """
    if "bid_px" in df.columns:
        names = ("bid_px", "ask_px", "bid_sz", "ask_sz")
    elif "bid_px_00" in df.columns:
        names = ("bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00")
    else:
        raise GcquantError("Frame tidak memiliki kolom L1 (bid_px/ask_px atau bid_px_00/ask_px_00)")
    bp = df[names[0]].to_numpy(dtype=np.float64, na_value=np.nan)
    ap = df[names[1]].to_numpy(dtype=np.float64, na_value=np.nan)
    bs = np.nan_to_num(df[names[2]].to_numpy(dtype=np.float64, na_value=np.nan), nan=0.0)
    as_ = np.nan_to_num(df[names[3]].to_numpy(dtype=np.float64, na_value=np.nan), nan=0.0)
    return bp, ap, bs, as_


def bbo_from_book(book: pd.DataFrame, only_changes: bool = False) -> pd.DataFrame:
    """Frame BOOK (atau MBP-1/MBP-10) → frame BBO kanonik.

    Kolom: ``ts_recv, ts_event, instrument_id, symbol, bid_px, ask_px, bid_sz,
    ask_sz`` (kolom meta yang tidak ada di input dilewati). Bila
    ``only_changes=True`` hanya baris yang mengubah L1 (per instrumen) yang
    dipertahankan — baris pertama tiap instrumen selalu dipertahankan.
    """
    if "bid_px" in book.columns and "bid_px_00" not in book.columns:
        out = book[[c for c in _BBO_META if c in book.columns]
                   + ["bid_px", "ask_px", "bid_sz", "ask_sz"]].copy()
    else:
        out = pd.DataFrame({c: book[c] for c in _BBO_META if c in book.columns}, index=book.index)
        out["bid_px"] = book["bid_px_00"].astype("float64")
        out["ask_px"] = book["ask_px_00"].astype("float64")
        out["bid_sz"] = book["bid_sz_00"]
        out["ask_sz"] = book["ask_sz_00"]
    if only_changes and len(out):
        l1 = out[["bid_px", "ask_px", "bid_sz", "ask_sz"]]
        if "instrument_id" in out.columns:
            prev = l1.groupby(out["instrument_id"], sort=False).shift(1)
        else:
            prev = l1.shift(1)
        same = ((l1 == prev) | (l1.isna() & prev.isna())).all(axis=1)
        keep = ~same
        if "instrument_id" in out.columns:
            keep |= ~out["instrument_id"].duplicated()
        else:
            keep.iloc[0] = True
        out = out[keep.to_numpy()]
    return out


def mid(df: pd.DataFrame) -> pd.Series:
    """Harga tengah (bid+ask)/2; NaN bila salah satu sisi kosong."""
    bp, ap, _, _ = l1_arrays(df)
    return pd.Series((bp + ap) / 2.0, index=df.index, name="mid")


def spread(df: pd.DataFrame) -> pd.Series:
    """Spread kuotasi ask − bid (USD); NaN bila salah satu sisi kosong."""
    bp, ap, _, _ = l1_arrays(df)
    return pd.Series(ap - bp, index=df.index, name="spread")


def weighted_mid(df: pd.DataFrame) -> pd.Series:
    """Mid berbobot ukuran (micro-price naif):

    ``(bid_px * ask_sz + ask_px * bid_sz) / (bid_sz + ask_sz)``
    = ``I * ask_px + (1 − I) * bid_px`` dengan ``I = Qb / (Qb + Qa)``.
    NaN bila salah satu harga kosong atau total ukuran 0.
    """
    bp, ap, bs, as_ = l1_arrays(df)
    tot = bs + as_
    with np.errstate(invalid="ignore", divide="ignore"):
        w = (bp * as_ + ap * bs) / tot
    w = np.where((tot > 0) & np.isfinite(bp) & np.isfinite(ap), w, np.nan)
    return pd.Series(w, index=df.index, name="weighted_mid")
