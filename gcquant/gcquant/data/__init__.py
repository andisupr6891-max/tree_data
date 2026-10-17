"""Sumber data gcquant (SPEC §3.1): Databento berpengaman biaya, pembaca DBN, data sintetis,
dan berkas lokal gratis (M1 XAUUSD, CSV harian).

Paket ``databento`` bersifat opsional: modul sintetis & berkas lokal tetap dapat dipakai
tanpanya; fungsi yang membutuhkannya mengimpor secara malas (lazy).
"""
from .databento_source import (
    DatabentoSource, LiveFeed, normalize_request, record_to_dict, request_key,
)
from .dbn_io import (
    BAR_LEN, BARS_COLUMNS, BBO_COLUMNS, BOOK_COLUMNS, DEFS_COLUMNS, MBO_COLUMNS, STATS_COLUMNS,
    TRADES_COLUMNS, canonical_schema, load_dbn, write_synthetic_mbo_dbn,
)
from .free_sources import infer_bar_len, load_daily_csv, load_m1_csv, resample_bars
from .synthetic import (
    gc_first_notice_date, gc_last_trade_date, synthetic_bars, synthetic_daily_curve,
    synthetic_mbo, synthetic_mbo_with_truth,
)

__all__ = [
    "DatabentoSource", "LiveFeed", "normalize_request", "record_to_dict", "request_key",
    "load_dbn", "write_synthetic_mbo_dbn", "canonical_schema",
    "MBO_COLUMNS", "TRADES_COLUMNS", "BBO_COLUMNS", "BOOK_COLUMNS", "STATS_COLUMNS",
    "DEFS_COLUMNS", "BARS_COLUMNS", "BAR_LEN",
    "load_m1_csv", "load_daily_csv", "resample_bars", "infer_bar_len",
    "synthetic_mbo", "synthetic_mbo_with_truth", "synthetic_bars", "synthetic_daily_curve",
    "gc_first_notice_date", "gc_last_trade_date",
]
