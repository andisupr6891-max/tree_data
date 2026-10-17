"""Inti gcquant: spesifikasi kontrak, model biaya, kalender CME, utilitas waktu.

Semua modul lain bergantung pada berkas ini. Konvensi (lihat SPEC.md):
- Waktu mentah: int64 nanodetik sejak epoch UTC (sama dengan Databento).
- DataFrame: indeks/kolom waktu bertipe datetime64[ns, UTC].
- Harga: float USD per troy ounce. Ukuran: jumlah kontrak (int).
- Sisi agresor trade: 'B' = pembeli agresif (+1), 'A' = penjual agresif (-1), 'N' = tidak diketahui (0).
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from functools import lru_cache
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

UTC = ZoneInfo("UTC")
NY = ZoneInfo("America/New_York")
CHI = ZoneInfo("America/Chicago")

NS_PER_SEC = 1_000_000_000
NS_PER_MS = 1_000_000

# Konstanta Databento (diverifikasi dari databento_dbn yang terpasang)
FIXED_PRICE_SCALE = 1_000_000_000
UNDEF_PRICE = 9_223_372_036_854_775_807
UNDEF_ORDER_SIZE = 4_294_967_295
UNDEF_STAT_QUANTITY = 9_223_372_036_854_775_807
F_LAST = 128
F_TOB = 64
F_SNAPSHOT = 32
F_MBP = 16
F_BAD_TS_RECV = 8
F_MAYBE_BAD_BOOK = 4

DATASET_CME = "GLBX.MDP3"

MONTH_CODES = {1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M",
               7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z"}
CODE_MONTHS = {v: k for k, v in MONTH_CODES.items()}


class GcquantError(Exception):
    """Galat dasar gcquant."""


class BiayaDitolak(GcquantError):
    """Permintaan data ditolak karena perkiraan biayanya melebihi batas anggaran."""


class LookAheadError(GcquantError):
    """Dilempar bila sebuah operasi akan memakai data masa depan."""


@dataclass(frozen=True)
class ContractSpec:
    root: str                 # akar simbol CME, mis. "GC"
    name: str
    exchange: str             # "COMEX"
    multiplier: float         # troy ounce per kontrak
    tick_size: float          # USD/oz
    settlement: str           # "physical" | "cash"
    option_of: str | None = None   # untuk opsi: akar futures dasarnya
    exercise: str | None = None    # "american" | "european"
    notes: str = ""

    @property
    def tick_value(self) -> float:
        """Nilai USD satu tick untuk satu kontrak."""
        return self.tick_size * self.multiplier

    def usd_per_point(self) -> float:
        """Nilai USD per perubahan harga 1,00 USD/oz untuk satu kontrak."""
        return self.multiplier


# Spesifikasi kontrak. Angka GC/MGC/OG sesuai spesifikasi CME yang lazim dipakai;
# 1OZ ditandai "periksa" karena produknya relatif baru. Cek ulang di cmegroup.com bila ragu.
SPECS: dict[str, ContractSpec] = {
    "GC": ContractSpec("GC", "COMEX Gold Futures", "COMEX", 100.0, 0.10, "physical",
                       notes="Tick 0,10 = $10/kontrak. Bulan aktif G J M Q V Z."),
    "MGC": ContractSpec("MGC", "COMEX Micro Gold Futures", "COMEX", 10.0, 0.10, "physical",
                        notes="Tick 0,10 = $1/kontrak."),
    "1OZ": ContractSpec("1OZ", "COMEX 1-Ounce Gold Futures", "COMEX", 1.0, 0.25, "cash",
                        notes="Periksa spesifikasi terbaru di cmegroup.com."),
    "OG": ContractSpec("OG", "COMEX Gold Options (on GC)", "COMEX", 100.0, 0.10, "physical",
                       option_of="GC", exercise="american",
                       notes="Opsi Amerika atas futures GC; premi tick 0,10 = $10."),
}


@dataclass(frozen=True)
class CostModel:
    """Biaya transaksi per kontrak per sisi (USD), plus model slippage & latensi.

    Angka bawaan adalah ASUMSI ritel (broker diskon + biaya bursa + NFA + routing)
    dan sengaja dibuat sedikit konservatif. Ganti dengan tagihan broker Anda.
    """
    commission_per_side: float = 2.50     # USD per kontrak per sisi, semua komponen
    slippage_ticks: float = 0.0           # tick tambahan di luar spread untuk order pasar
    latency_ms: float = 140.0             # latensi satu arah keputusan→bursa (Jakarta→Chicago ±130 ms)
    pay_spread: bool = True               # order pasar membayar setengah spread dari mid

    def round_turn_usd(self, spec: ContractSpec, spread_ticks: float = 1.0) -> float:
        """Biaya bolak-balik satu kontrak dengan spread tertentu (dalam tick)."""
        spread_cost = spread_ticks * spec.tick_value if self.pay_spread else 0.0
        slip = 2 * self.slippage_ticks * spec.tick_value
        return 2 * self.commission_per_side + spread_cost + slip


DEFAULT_COSTS: dict[str, CostModel] = {
    "GC": CostModel(commission_per_side=2.50),
    "MGC": CostModel(commission_per_side=0.85),
    "1OZ": CostModel(commission_per_side=0.40),
}


# ---------------------------------------------------------------------------
# Waktu
# ---------------------------------------------------------------------------

def to_ns(x) -> np.ndarray | int:
    """Ubah timestamp/datetime/str/array ke int64 nanodetik UTC."""
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, (pd.DatetimeIndex, pd.Series, np.ndarray, list)):
        idx = pd.DatetimeIndex(pd.to_datetime(x, utc=True))
        return idx.as_unit("ns").asi8
    ts = pd.Timestamp(x)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return int(ts.tz_convert("UTC").as_unit("ns").value)


def ns_to_ts(ns) -> pd.Timestamp | pd.DatetimeIndex:
    """Kebalikan to_ns: int64 ns → Timestamp/DatetimeIndex UTC (unit ns)."""
    if np.ndim(ns) == 0:
        return pd.Timestamp(int(ns), unit="ns", tz="UTC")
    return pd.DatetimeIndex(pd.to_datetime(np.asarray(ns, dtype="int64"), unit="ns", utc=True)).as_unit("ns")


def ensure_utc_index(df: pd.DataFrame) -> pd.DataFrame:
    """Pastikan indeks DatetimeIndex UTC beresolusi ns dan terurut naik."""
    idx = pd.DatetimeIndex(df.index)
    idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    out = df.copy()
    out.index = idx.as_unit("ns")
    if not out.index.is_monotonic_increasing:
        out = out.sort_index(kind="stable")
    return out


def cme_trade_date(ts) -> _dt.date:
    """Tanggal perdagangan CME: sesi dimulai 17:00 Chicago hari sebelumnya.

    Contoh: Senin 18:00 CT termasuk trade date Selasa.
    """
    t = pd.Timestamp(ts)
    t = t.tz_localize("UTC") if t.tzinfo is None else t
    local = t.tz_convert(CHI)
    d = local.date()
    if local.hour >= 17:
        d = d + _dt.timedelta(days=1)
    while d.weekday() >= 5:      # sesi Minggu sore → trade date Senin
        d = d + _dt.timedelta(days=1)
    return d


# ---------------------------------------------------------------------------
# Kalender hari kerja CME (perkiraan; dipakai untuk aturan kedaluwarsa)
# ---------------------------------------------------------------------------

def _nth_weekday(year: int, month: int, weekday: int, n: int) -> _dt.date:
    d = _dt.date(year, month, 1)
    d += _dt.timedelta(days=(weekday - d.weekday()) % 7)
    return d + _dt.timedelta(weeks=n - 1)


def _last_weekday(year: int, month: int, weekday: int) -> _dt.date:
    nxt = _dt.date(year + (month == 12), month % 12 + 1, 1)
    d = nxt - _dt.timedelta(days=1)
    return d - _dt.timedelta(days=(d.weekday() - weekday) % 7)


def _easter(year: int) -> _dt.date:
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return _dt.date(year, month, day)


def _observed(d: _dt.date) -> _dt.date:
    if d.weekday() == 5:
        return d - _dt.timedelta(days=1)
    if d.weekday() == 6:
        return d + _dt.timedelta(days=1)
    return d


@lru_cache(maxsize=None)
def cme_holidays(year: int) -> frozenset[_dt.date]:
    """Hari tanpa settlement CME (perkiraan aturan libur AS + Jumat Agung).

    Penutupan khusus (mis. hari berkabung nasional) tidak tercakup; tambahkan
    lewat EXTRA_HOLIDAYS bila perlu.
    """
    days = {
        _observed(_dt.date(year, 1, 1)),
        _nth_weekday(year, 1, 0, 3),      # Martin Luther King Jr.
        _nth_weekday(year, 2, 0, 3),      # Presidents Day
        _easter(year) - _dt.timedelta(days=2),   # Good Friday
        _last_weekday(year, 5, 0),        # Memorial Day
        _observed(_dt.date(year, 7, 4)),
        _nth_weekday(year, 9, 0, 1),      # Labor Day
        _nth_weekday(year, 11, 3, 4),     # Thanksgiving
        _observed(_dt.date(year, 12, 25)),
    }
    if year >= 2022:
        days.add(_observed(_dt.date(year, 6, 19)))   # Juneteenth
    days |= {d for d in EXTRA_HOLIDAYS if d.year == year}
    return frozenset(days)


EXTRA_HOLIDAYS: set[_dt.date] = {
    _dt.date(2018, 12, 5),   # hari berkabung Presiden G.H.W. Bush
    _dt.date(2025, 1, 9),    # hari berkabung Presiden Carter
}


def is_business_day(d: _dt.date) -> bool:
    return d.weekday() < 5 and d not in cme_holidays(d.year)


def business_days_in_month(year: int, month: int) -> list[_dt.date]:
    d = _dt.date(year, month, 1)
    out = []
    while d.month == month:
        if is_business_day(d):
            out.append(d)
        d += _dt.timedelta(days=1)
    return out


def add_business_days(d: _dt.date, n: int) -> _dt.date:
    step = 1 if n >= 0 else -1
    left = abs(n)
    while left:
        d += _dt.timedelta(days=step)
        if is_business_day(d):
            left -= 1
    return d


def futures_symbol(root: str, year: int, month: int, digits: int = 1) -> str:
    """Simbol mentah CME, mis. ('GC', 2026, 12) → 'GCZ6' (digits=1) atau 'GCZ26'."""
    return f"{root}{MONTH_CODES[month]}{str(year)[-digits:]}"


def parse_futures_symbol(sym: str, ref_year: int | None = None) -> tuple[str, int, int]:
    """'GCZ6' → ('GC', 2026, 12). Tahun 1 digit dipetakan ke dekade terdekat ≥ ref_year-1."""
    i = len(sym) - 1
    while i >= 0 and sym[i].isdigit():
        i -= 1
    root, code, ydig = sym[:i], sym[i], sym[i + 1:]
    month = CODE_MONTHS[code]
    if len(ydig) >= 2:
        year = 2000 + int(ydig[-2:])
    else:
        ref = ref_year or _dt.date.today().year
        base = ref - ref % 10
        year = base + int(ydig)
        if year < ref - 1:
            year += 10
    return root, year, month
