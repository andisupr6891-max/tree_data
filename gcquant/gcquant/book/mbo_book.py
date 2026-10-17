"""Rekonstruksi order book dari data MBO (market-by-order) Databento.

Semantik mengikuti contoh resmi Databento ("Constructing a limit order book"):

- ``T`` (trade), ``F`` (fill), ``N`` (none): tidak mengubah buku.
- ``R`` (clear): kosongkan buku instrumen tsb (per instrumen & publisher).
- ``A`` (add): tambahkan order baru di ekor antrean harganya.
- ``C`` (cancel): kurangi ukuran order sebesar ``rec.size``; hapus bila sisa 0.
- ``M`` (modify): bila ``order_id`` tidak dikenal → diperlakukan sebagai add.
  Bila harga berubah ATAU ukuran naik → order kehilangan prioritas (pindah ke
  ekor antrean di harga barunya). Bila ukuran turun → prioritas dipertahankan.
  Sisi order tidak boleh berubah (→ :class:`BookError`).
- Record ber-``side='N'`` dengan aksi A/C/M tidak sah menurut Databento dan
  diabaikan dengan aman (dihitung di ``n_ignored``).

Buku hanya konsisten setelah record yang membawa ``F_LAST`` (record terakhir
dari satu event untuk instrumen tsb). :func:`replay_mbo` karenanya hanya
mengeluarkan snapshot pada record ber-``F_LAST``.

Record ber-``F_MAYBE_BAD_BOOK`` menandai buku instrumen sebagai *basi* (stale)
sampai ada ``R`` berikutnya diikuti snapshot yang ditutup ``F_LAST``.

Struktur data: per sisi ada ``dict`` harga → level, plus daftar harga terurut
(``bisect``) yang hanya disentuh saat level dibuat/dihapus. Tiap level memegang
``dict`` order_id → ukuran yang urutan sisipnya = prioritas antrean (FIFO), dan
total ukuran yang diperbarui inkremental. Jadi setiap update O(1) amortisasi
(plus O(log L) saat level baru muncul/hilang).

Harga disimpan internal sebagai integer fixed-point (1e-9 USD, sama dengan
Databento) agar kunci dict tidak terpengaruh galat pembulatan float.
"""
from __future__ import annotations

import math
from array import array
from bisect import bisect_left, insort
from collections.abc import Mapping
from operator import attrgetter
from typing import Iterator

import numpy as np
import pandas as pd

from ..core import (
    F_LAST,
    F_MAYBE_BAD_BOOK,
    F_TOB,
    FIXED_PRICE_SCALE,
    UNDEF_PRICE,
    GcquantError,
)

__all__ = [
    "BookError",
    "OrderBook",
    "Market",
    "replay_mbo",
    "book_columns",
    "price_to_key",
    "key_to_price",
]

_UNDEF = int(UNDEF_PRICE)
_SCALE = float(FIXED_PRICE_SCALE)
# order_id semu (negatif → tak mungkin bentrok dengan uint64 Databento) untuk
# level hasil add ber-F_TOB (publisher yang hanya mengirim top-of-book).
_TOB_ID = {"B": -1, "A": -2}
_MAX_ABS_PRICE = 9.0e9  # di atas ini dianggap harga tak terdefinisi


class BookError(GcquantError):
    """Galat konsistensi order book (sisi berubah, order tak dikenal, dsb.)."""


# ---------------------------------------------------------------------------
# Konversi harga
# ---------------------------------------------------------------------------

def price_to_key(price) -> int:
    """Harga → kunci integer fixed-point (1e-9).

    ``int``/``np.integer`` dianggap SUDAH fixed-point (format mentah Databento,
    ``UNDEF_PRICE`` = tak terdefinisi). ``float`` dianggap USD; NaN/inf → tak
    terdefinisi.
    """
    if price is None:
        return _UNDEF
    if isinstance(price, (bool, np.bool_)):
        raise BookError("Harga bertipe bool tidak sah")
    if isinstance(price, (int, np.integer)):
        return int(price)
    p = float(price)
    if not math.isfinite(p) or abs(p) > _MAX_ABS_PRICE:
        return _UNDEF
    return int(round(p * _SCALE))


def key_to_price(key: int) -> float:
    """Kunci fixed-point → harga float USD (NaN bila tak terdefinisi)."""
    return float("nan") if key == _UNDEF else key / _SCALE


def _price_keys_from_array(price: np.ndarray) -> np.ndarray:
    """Versi vektor :func:`price_to_key` untuk kolom harga sebuah frame."""
    price = np.asarray(price)
    if np.issubdtype(price.dtype, np.integer):
        return price.astype(np.int64)
    p = price.astype(np.float64)
    bad = ~np.isfinite(p) | (np.abs(p) > _MAX_ABS_PRICE)
    keys = np.rint(np.where(bad, 0.0, p) * _SCALE).astype(np.int64)
    keys[bad] = _UNDEF
    return keys


# ---------------------------------------------------------------------------
# Akses field record generik (dict / pd.Series / namedtuple / databento MBOMsg)
# ---------------------------------------------------------------------------

def _get(rec, name, default=None):
    if isinstance(rec, (Mapping, pd.Series)):
        v = rec.get(name, default)
    else:
        v = getattr(rec, name, default)
    return default if v is None else v


def _char(x, default: str = "N") -> str:
    if x is None:
        return default
    x = getattr(x, "value", x)  # enum databento_dbn (Action.ADD → 'A')
    if isinstance(x, bytes):
        x = x.decode()
    if isinstance(x, (int, np.integer)):
        x = chr(int(x))
    if isinstance(x, float) and math.isnan(x):
        return default
    s = str(x)
    return s if s else default


def _rec_fields(rec):
    action = _char(_get(rec, "action"), "N")
    side = _char(_get(rec, "side"), "N")
    px = price_to_key(_get(rec, "price"))
    size = int(_get(rec, "size", 0))
    oid = int(_get(rec, "order_id", 0))
    flags = int(_get(rec, "flags", 0))
    return action, side, px, size, oid, flags


# ---------------------------------------------------------------------------
# Struktur level
# ---------------------------------------------------------------------------

class _Level:
    __slots__ = ("orders", "size")

    def __init__(self) -> None:
        self.orders: dict[int, int] = {}  # order_id → ukuran; urutan = prioritas
        self.size = 0


_TRACK_MAX = 512   # batas panjang daftar harga tersentuh sebelum dianggap "semua kotor"


class _Side:
    __slots__ = ("bid", "prices", "levels", "touched", "struct", "all_dirty",
                 "cache", "cache_n", "cache_id", "cache_reg")

    def __init__(self, bid: bool) -> None:
        self.bid = bid
        self.prices: list[int] = []        # naik
        self.levels: dict[int, _Level] = {}
        # Pelacakan perubahan sejak cache n-level terakhir dibuat (dipakai
        # replay agar tidak menghitung ulang seluruh n level di setiap event):
        self.touched: list[int] = []       # harga yang ukuran/jumlah order-nya berubah
        self.struct: list[int] = []        # harga level yang dibuat/dihapus
        self.all_dirty = True
        self.cache = None
        self.cache_n = -1
        self.cache_id = -1
        self.cache_reg = None

    def touch(self, px: int) -> None:
        t = self.touched
        t.append(px)
        if len(t) > _TRACK_MAX:
            t.clear()
            self.struct.clear()
            self.all_dirty = True

    def touch_all(self) -> None:
        self.touched.clear()
        self.struct.clear()
        self.all_dirty = True

    def get_or_create(self, px: int) -> _Level:
        lvl = self.levels.get(px)
        if lvl is None:
            lvl = _Level()
            self.levels[px] = lvl
            insort(self.prices, px)
            self.struct.append(px)
        return lvl

    def remove_level(self, px: int) -> None:
        del self.levels[px]
        i = bisect_left(self.prices, px)
        del self.prices[i]
        self.struct.append(px)

    def top(self, n: int | None) -> list[int]:
        """Kunci harga dari yang terbaik; ``n=None`` → semua."""
        if self.bid:
            if n is None:
                return self.prices[::-1]
            if n <= 0:
                return []
            return self.prices[:-n - 1:-1]
        if n is None:
            return list(self.prices)
        return self.prices[:max(n, 0)]

    def raw(self, n: int | None):
        ps = self.top(n)
        lvls = list(map(self.levels.__getitem__, ps))
        return ps, list(map(_size_of, lvls)), list(map(len, map(_orders_of, lvls)))

    def top_cached(self, n: int):
        """n level teratas sebagai list datar ``harga*n + ukuran*n + jumlah*n``.

        Mengembalikan ``(nilai, baru)``; ``baru`` False → list yang sama dengan
        panggilan sebelumnya. Logika inkremental (dibuktikan di uji acak):

        - Himpunan n level teratas hanya bisa berubah bila ada level yang
          dibuat/dihapus pada harga p yang sama/lebih agresif dari level ke-n
          SAAT INI (atau sisi punya < n level) → hitung ulang penuh.
        - Selain itu peringkat level teratas tetap; harga tersentuh dengan
          peringkat < n cukup ditambal ukuran & jumlah order-nya (salin-tulis).
        """
        t = self.touched
        st = self.struct
        if self.cache_n == n and not self.all_dirty:
            if not t and not st:
                return self.cache, False
            pr = self.prices
            npr = len(pr)
            full = False
            if st:
                if npr < n:
                    full = True
                elif self.bid:
                    full = max(st) >= pr[-n]
                else:
                    full = min(st) <= pr[n - 1]
            if not full:
                flat = None
                lv = self.levels
                for p in set(t):
                    lvl = lv.get(p)
                    if lvl is None:
                        continue                  # level hilang di luar n teratas
                    r = bisect_left(pr, p)
                    if self.bid:
                        r = npr - 1 - r
                    if r < n:
                        if flat is None:
                            flat = self.cache.copy()
                        flat[n + r] = lvl.size
                        flat[2 * n + r] = len(lvl.orders)
                t.clear()
                st.clear()
                if flat is None:
                    return self.cache, False
                self.cache = flat
                return flat, True
        ps, szs, cts = self.raw(n)
        k = len(ps)
        if k < n:
            pad = n - k
            flat = ps + [_UNDEF] * pad + szs + [0] * pad + cts + [0] * pad
        else:
            flat = ps + szs + cts
        self.cache = flat
        self.cache_n = n
        self.all_dirty = False
        t.clear()
        st.clear()
        return flat, True

    def clear(self) -> None:
        self.prices.clear()
        self.levels.clear()
        self.touch_all()


_size_of = attrgetter("size")
_orders_of = attrgetter("orders")


def _side_code(side) -> str:
    s = _char(side, "")
    s = {"bid": "B", "ask": "A", "b": "B", "a": "A", "BID": "B", "ASK": "A"}.get(s, s)
    if s not in ("B", "A"):
        raise BookError(f"Sisi harus 'B' (bid) atau 'A' (ask), bukan {side!r}")
    return s


# ---------------------------------------------------------------------------
# OrderBook
# ---------------------------------------------------------------------------

class OrderBook:
    """Order book satu instrumen (dan satu publisher) dari record MBO.

    Parameter
    ---------
    strict:
        ``True`` (bawaan) → anomali data (cancel/modify untuk order tak
        dikenal pada cancel, cancel melebihi ukuran order, add dengan
        ``order_id`` ganda, harga cancel ≠ harga order, add tanpa harga)
        melempar :class:`BookError`. ``False`` → anomali dihitung di
        ``n_anomalies``, ditangani sebaik mungkin, dan buku ditandai basi
        (``stale``) sampai ``R`` + snapshot berikutnya.
        Perubahan sisi order SELALU melempar :class:`BookError`.

    Atribut publik: ``stale`` (bool), ``version`` (naik setiap kali buku
    berubah), ``n_anomalies``, ``n_ignored``.
    """

    def __init__(self, strict: bool = True) -> None:
        self.strict = strict
        self.orders: dict[int, tuple[str, int]] = {}  # order_id → (sisi, kunci harga)
        self._bids = _Side(True)
        self._asks = _Side(False)
        self.stale = False
        self._rebuilding = False
        self.version = 0
        self.n_anomalies = 0
        self.n_ignored = 0

    # -- penerapan record ---------------------------------------------------
    def apply(self, rec) -> bool:
        """Terapkan satu record MBO; kembalikan ``True`` bila buku berubah.

        ``rec`` boleh berupa ``databento.MBOMsg`` (harga fixed-point int),
        baris ``pd.Series``/``dict``/namedtuple dari frame MBO kanonik (harga
        float USD). Field yang dipakai: action, side, price, size, order_id, flags.
        """
        return self._apply(*_rec_fields(rec))

    def _apply(self, action: str, side: str, px: int, size: int, oid: int, flags: int) -> bool:
        if action == "A":
            changed = self._add(side, px, size, oid, flags)
        elif action == "C":
            changed = self._cancel(side, px, size, oid)
        elif action == "M":
            changed = self._modify(side, px, size, oid, flags)
        elif action == "T" or action == "F" or action == "N":
            changed = False
        elif action == "R":
            self.clear()
            self._rebuilding = True
            changed = True
        else:
            raise BookError(f"Aksi MBO tidak dikenal: {action!r}")
        if flags & F_MAYBE_BAD_BOOK:
            self.stale = True
            if action != "R":
                self._rebuilding = False
        if self._rebuilding and flags & F_LAST:
            # R + snapshot (atau R kosong) sudah ditutup F_LAST → buku segar.
            self._rebuilding = False
            self.stale = False
        if changed:
            self.version += 1
        return changed

    def _anomaly(self, msg: str) -> bool:
        if self.strict:
            raise BookError(
                msg + " (data MBO tidak konsisten; mulailah replay dari R + snapshot "
                "harian 00:00 UTC, atau pakai strict=False)")
        self.n_anomalies += 1
        self.stale = True
        return False

    def _sideobj(self, side: str) -> _Side:
        return self._bids if side == "B" else self._asks

    def _add(self, side: str, px: int, size: int, oid: int, flags: int) -> bool:
        if side == "B":
            sd = self._bids
        elif side == "A":
            sd = self._asks
        else:
            self.n_ignored += 1           # side 'N' pada add: abaikan dengan aman
            return False
        if flags & F_TOB:
            return self._tob(sd, side, px, size)
        if px == _UNDEF:
            return self._anomaly(f"Add order {oid} tanpa harga")
        if size <= 0:
            return self._anomaly(f"Add order {oid} dengan ukuran {size}")
        if oid in self.orders:
            if self.strict:
                raise BookError(f"Add untuk order_id {oid} yang sudah ada di buku")
            self._anomaly(f"Add ganda order {oid}")
            return self._modify(side, px, size, oid, flags)
        self.orders[oid] = (side, px)
        lvl = sd.get_or_create(px)
        lvl.orders[oid] = size
        lvl.size += size
        sd.touch(px)
        return True

    def _tob(self, sd: _Side, side: str, px: int, size: int) -> bool:
        # Publisher top-of-book: satu record menggantikan seluruh sisi.
        for p in sd.prices:
            for o in sd.levels[p].orders:
                self.orders.pop(o, None)
        sd.clear()
        if px != _UNDEF and size > 0:
            oid = _TOB_ID[side]
            lvl = sd.get_or_create(px)
            lvl.orders[oid] = size
            lvl.size = size
            self.orders[oid] = (side, px)
        return True

    def _remove_order(self, sd: _Side, lvl: _Level, px: int, oid: int) -> None:
        sd.touch(px)
        lvl.size -= lvl.orders.pop(oid)
        del self.orders[oid]
        if not lvl.orders:
            sd.remove_level(px)

    def _cancel(self, side: str, px: int, size: int, oid: int) -> bool:
        if side != "B" and side != "A":
            self.n_ignored += 1
            return False
        o = self.orders.get(oid)
        if o is None:
            return self._anomaly(f"Cancel untuk order tak dikenal {oid}")
        oside, opx = o
        if side != oside:
            raise BookError(f"Sisi order {oid} berubah dari {oside!r} ke {side!r} pada cancel")
        if px != opx and px != _UNDEF:
            if self.strict:
                raise BookError(
                    f"Harga cancel order {oid} ({key_to_price(px)}) ≠ harga order "
                    f"({key_to_price(opx)})")
            self._anomaly(f"Harga cancel order {oid} tidak cocok")
        sd = self._bids if oside == "B" else self._asks
        lvl = sd.levels[opx]
        cur = lvl.orders[oid]
        if size < 0:
            return self._anomaly(f"Cancel order {oid} dengan ukuran negatif {size}")
        if size > cur:
            self._anomaly(f"Cancel {size} melebihi sisa order {oid} ({cur})")
            size = cur
        if size == cur:
            self._remove_order(sd, lvl, opx, oid)
            return True
        if size == 0:
            return False
        lvl.orders[oid] = cur - size       # kunci sudah ada → posisi antrean tetap
        lvl.size -= size
        sd.touch(opx)
        return True

    def _modify(self, side: str, px: int, size: int, oid: int, flags: int) -> bool:
        if side != "B" and side != "A":
            self.n_ignored += 1
            return False
        o = self.orders.get(oid)
        if o is None:
            return self._add(side, px, size, oid, flags)   # sesuai contoh resmi
        oside, opx = o
        if side != oside:
            raise BookError(f"Sisi order {oid} berubah dari {oside!r} ke {side!r} pada modify")
        sd = self._bids if oside == "B" else self._asks
        lvl = sd.levels[opx]
        cur = lvl.orders[oid]
        if px == _UNDEF:
            return self._anomaly(f"Modify order {oid} tanpa harga")
        if size <= 0:
            # modify ke ukuran 0 = order hilang dari buku
            self._remove_order(sd, lvl, opx, oid)
            return True
        sd.touch(opx)
        sd.touch(px)
        if px != opx:
            # harga berubah → kehilangan prioritas, pindah ke ekor level baru
            lvl.size -= lvl.orders.pop(oid)
            if not lvl.orders:
                sd.remove_level(opx)
            nl = sd.get_or_create(px)
            nl.orders[oid] = size
            nl.size += size
            self.orders[oid] = (oside, px)
        elif size > cur:
            # ukuran naik → kehilangan prioritas (ke ekor antrean harga yang sama)
            del lvl.orders[oid]
            lvl.orders[oid] = size
            lvl.size += size - cur
        else:
            # ukuran turun/tetap → prioritas dipertahankan
            lvl.orders[oid] = size
            lvl.size += size - cur
        return True

    # -- manajemen ---------------------------------------------------------
    def clear(self) -> None:
        """Kosongkan buku (aksi ``R``)."""
        self.orders.clear()
        self._bids.clear()
        self._asks.clear()
        self.version += 1

    # -- kueri -------------------------------------------------------------
    def bbo(self) -> tuple[float, int, float, int]:
        """``(bid_px, bid_sz, ask_px, ask_sz)``; sisi kosong → (NaN, 0)."""
        b = self._bids.prices
        a = self._asks.prices
        if b:
            bp = b[-1]
            bid = (bp / _SCALE, self._bids.levels[bp].size)
        else:
            bid = (float("nan"), 0)
        if a:
            ap = a[0]
            ask = (ap / _SCALE, self._asks.levels[ap].size)
        else:
            ask = (float("nan"), 0)
        return bid[0], bid[1], ask[0], ask[1]

    def levels(self, side, n: int | None = 10) -> list[tuple[float, int, int]]:
        """Daftar level ``(harga, ukuran, jumlah_order)`` dari yang terbaik.

        ``side``: 'B'/'bid' atau 'A'/'ask'. ``n=None`` → semua level.
        """
        ps, szs, cts = self._sideobj(_side_code(side)).raw(n)
        return [(p / _SCALE, s, c) for p, s, c in zip(ps, szs, cts)]

    def depth(self, side, n: int | None = 10) -> int:
        """Total ukuran (kontrak) pada ``n`` level terbaik satu sisi."""
        return int(sum(self._sideobj(_side_code(side)).raw(n)[1]))

    def queue_ahead(self, order_id: int) -> int:
        """Total ukuran order lain yang berada DI DEPAN order ini pada harga yang sama."""
        order_id = int(order_id)
        o = self.orders.get(order_id)
        if o is None:
            raise BookError(f"Order {order_id} tidak ada di buku")
        side, px = o
        lvl = self._sideobj(side).levels[px]
        ahead = 0
        for oid, sz in lvl.orders.items():
            if oid == order_id:
                return ahead
            ahead += sz
        raise BookError(f"Order {order_id} hilang dari levelnya (buku korup)")

    def order(self, order_id: int) -> dict:
        """Info satu order: sisi, harga, ukuran, posisi antrean, ukuran di depan."""
        order_id = int(order_id)
        o = self.orders.get(order_id)
        if o is None:
            raise BookError(f"Order {order_id} tidak ada di buku")
        side, px = o
        lvl = self._sideobj(side).levels[px]
        pos = list(lvl.orders).index(order_id)
        return {"side": side, "price": px / _SCALE, "size": lvl.orders[order_id],
                "queue_position": pos, "size_ahead": self.queue_ahead(order_id)}

    def queue(self, side, price) -> list[tuple[int, int]]:
        """Antrean FIFO ``[(order_id, ukuran), ...]`` pada satu harga."""
        lvl = self._sideobj(_side_code(side)).levels.get(price_to_key(price))
        return [] if lvl is None else list(lvl.orders.items())

    @property
    def n_orders(self) -> int:
        return len(self.orders)

    def __len__(self) -> int:
        return len(self.orders)

    def check(self) -> None:
        """Validasi invarian internal (dipakai uji); melempar ``BookError`` bila rusak."""
        seen = 0
        for side, sd in (("B", self._bids), ("A", self._asks)):
            if sd.prices != sorted(sd.levels):
                raise BookError("Daftar harga tidak sinkron dengan level")
            for px, lvl in sd.levels.items():
                if not lvl.orders:
                    raise BookError(f"Level kosong tertinggal di {px}")
                if lvl.size != sum(lvl.orders.values()):
                    raise BookError(f"Ukuran level {px} tidak sama dengan jumlah order")
                for oid, sz in lvl.orders.items():
                    if sz <= 0 or self.orders.get(oid) != (side, px):
                        raise BookError(f"Order {oid} tidak konsisten")
                    seen += 1
        if seen != len(self.orders):
            raise BookError("Indeks order tidak sinkron dengan level")


# ---------------------------------------------------------------------------
# Market: kumpulan buku per (instrument_id, publisher_id)
# ---------------------------------------------------------------------------

def _merge_raw(raws: list[tuple[list[int], list[int], list[int]]], bid: bool, n: int | None):
    agg: dict[int, list[int]] = {}
    for ps, szs, cts in raws:
        for p, s, c in zip(ps, szs, cts):
            a = agg.get(p)
            if a is None:
                agg[p] = [s, c]
            else:
                a[0] += s
                a[1] += c
    keys = sorted(agg, reverse=bid)
    if n is not None:
        keys = keys[:n]
    return keys, [agg[k][0] for k in keys], [agg[k][1] for k in keys]


class Market:
    """Kumpulan :class:`OrderBook` dikunci ``(instrument_id, publisher_id)``.

    Kueri per instrumen (``bbo``, ``levels``, ``depth``) mengagregasi semua
    publisher instrumen tsb (untuk GLBX.MDP3 hanya ada satu publisher).
    ``market[iid]`` → buku instrumen (bila hanya satu publisher);
    ``market[(iid, pub)]`` → buku spesifik.
    """

    def __init__(self, strict: bool = True) -> None:
        self.strict = strict
        self.books: dict[tuple[int, int], OrderBook] = {}
        self._inst: dict[int, list[OrderBook]] = {}

    def _book(self, iid: int, pub: int) -> OrderBook:
        bk = self.books.get((iid, pub))
        if bk is None:
            bk = OrderBook(strict=self.strict)
            self.books[(iid, pub)] = bk
            self._inst.setdefault(iid, []).append(bk)
        return bk

    def apply(self, rec) -> bool:
        """Terapkan satu record MBO ke buku instrumen/publisher-nya."""
        iid = int(_get(rec, "instrument_id", 0))
        pub = int(_get(rec, "publisher_id", 0))
        return self._book(iid, pub).apply(rec)

    def book(self, instrument_id: int, publisher_id: int | None = None) -> OrderBook:
        """Buku satu instrumen; ``publisher_id`` wajib bila ada >1 publisher."""
        if publisher_id is not None:
            return self.books[(int(instrument_id), int(publisher_id))]
        lst = self._inst.get(int(instrument_id))
        if not lst:
            raise KeyError(f"Instrumen {instrument_id} belum punya buku")
        if len(lst) > 1:
            raise BookError(f"Instrumen {instrument_id} punya {len(lst)} publisher; "
                            "sebutkan publisher_id")
        return lst[0]

    def _raw(self, iid: int, side: str, n: int | None):
        lst = self._inst.get(int(iid), [])
        sd = "_bids" if side == "B" else "_asks"
        if len(lst) == 1:
            return getattr(lst[0], sd).raw(n)
        return _merge_raw([getattr(b, sd).raw(n) for b in lst], side == "B", n)

    def levels(self, instrument_id: int, side, n: int | None = 10) -> list[tuple[float, int, int]]:
        """Level teragregasi lintas publisher ``(harga, ukuran, jumlah_order)``."""
        ps, szs, cts = self._raw(instrument_id, _side_code(side), n)
        return [(p / _SCALE, s, c) for p, s, c in zip(ps, szs, cts)]

    def bbo(self, instrument_id: int) -> tuple[float, int, float, int]:
        """BBO teragregasi lintas publisher ``(bid_px, bid_sz, ask_px, ask_sz)``."""
        b = self.levels(instrument_id, "B", 1)
        a = self.levels(instrument_id, "A", 1)
        bp, bs = (b[0][0], b[0][1]) if b else (float("nan"), 0)
        ap, as_ = (a[0][0], a[0][1]) if a else (float("nan"), 0)
        return bp, bs, ap, as_

    def depth(self, instrument_id: int, side, n: int | None = 10) -> int:
        return int(sum(self._raw(instrument_id, _side_code(side), n)[1]))

    def is_stale(self, instrument_id: int) -> bool:
        return any(b.stale for b in self._inst.get(int(instrument_id), []))

    def instruments(self) -> list[int]:
        return list(self._inst)

    def __getitem__(self, key) -> OrderBook:
        if isinstance(key, tuple):
            return self.books[(int(key[0]), int(key[1]))]
        return self.book(key)

    def __contains__(self, key) -> bool:
        if isinstance(key, tuple):
            return (int(key[0]), int(key[1])) in self.books
        return int(key) in self._inst

    def __iter__(self) -> Iterator[int]:
        return iter(self._inst)

    def __len__(self) -> int:
        return len(self._inst)


# ---------------------------------------------------------------------------
# Replay frame MBO → frame BOOK
# ---------------------------------------------------------------------------

def book_columns(n_levels: int = 10) -> list[str]:
    """Nama kolom frame BOOK (konvensi nama MBP-10 Databento)."""
    cols = ["ts_recv", "ts_event", "instrument_id", "symbol"]
    for f in ("bid_px", "ask_px", "bid_sz", "ask_sz", "bid_ct", "ask_ct"):
        cols += [f"{f}_{i:02d}" for i in range(n_levels)]
    return cols


def _ts_int64(col: pd.Series) -> np.ndarray:
    if isinstance(col.dtype, pd.DatetimeTZDtype) or np.issubdtype(col.dtype, np.datetime64):
        return pd.DatetimeIndex(col).as_unit("ns").asi8.copy()
    return col.to_numpy(dtype=np.int64)


def _str_list(col: pd.Series, default: str) -> list[str]:
    vals = col.astype(object).where(col.notna(), default).tolist()
    conv = {u: _char(u, default) for u in set(vals)}
    if all(k == v for k, v in conv.items()):
        return vals
    return [conv[v] for v in vals]


def replay_mbo(mbo: pd.DataFrame, n_levels: int = 10, emit: str = "last", *,
               strict: bool = True, emit_stale: bool = False,
               market: Market | None = None) -> pd.DataFrame:
    """Replay frame MBO kanonik menjadi frame BOOK (snapshot n level).

    Parameter
    ---------
    mbo:
        Frame MBO kanonik (lihat SPEC §2) dalam URUTAN ASLI feed (jangan diurut
        ulang). Kolom wajib: ``ts_recv, instrument_id, order_id, action, side,
        price, size, flags``; opsional ``ts_event, publisher_id, symbol``.
        ``price`` float USD (NaN = tak terdefinisi); kolom harga bertipe integer
        dianggap fixed-point mentah Databento.
    n_levels:
        Jumlah level per sisi pada output.
    emit:
        ``"last"`` → satu baris setiap record ber-``F_LAST`` (buku konsisten);
        ``"tob_change"`` → hanya pada record ber-``F_LAST`` yang mengubah L1
        (harga/ukuran bid/ask terbaik) dibanding baris terakhir yang
        dikeluarkan untuk instrumen tsb; ``"every"`` → setiap record (bisa
        memuat keadaan antara yang TIDAK konsisten; hanya untuk diagnosis).
    strict:
        Diteruskan ke :class:`OrderBook` (lihat di sana).
    emit_stale:
        ``False`` (bawaan) → snapshot instrumen yang sedang basi
        (``F_MAYBE_BAD_BOOK`` / anomali) tidak dikeluarkan.
    market:
        :class:`Market` yang akan dipakai & dimutasi (berguna untuk memeriksa
        keadaan akhir atau melanjutkan replay antar potongan data).

    Kembalian
    ---------
    Frame BOOK: ``ts_recv, ts_event`` (int64 ns), ``instrument_id``, ``symbol``,
    lalu ``bid_px_00..``, ``ask_px_00..`` (float, NaN bila kosong),
    ``bid_sz_..``, ``ask_sz_..``, ``bid_ct_..``, ``ask_ct_..`` (int64, 0 bila
    kosong). Untuk instrumen dengan >1 publisher, level diagregasi lintas
    publisher. Statistik replay ada di ``out.attrs["replay"]``.
    Setiap baris hanya bergantung pada record dengan indeks ≤ record pemicunya
    (tanpa look-ahead).
    """
    if emit not in ("last", "tob_change", "every"):
        raise ValueError("emit harus 'last', 'tob_change', atau 'every'")
    n_levels = int(n_levels)
    if n_levels < 1:
        raise ValueError("n_levels minimal 1")
    required = ["ts_recv", "instrument_id", "order_id", "action", "side", "price", "size", "flags"]
    missing = [c for c in required if c not in mbo.columns]
    if missing:
        raise GcquantError(f"Frame MBO kekurangan kolom: {missing}")

    n = len(mbo)
    ts_recv = _ts_int64(mbo["ts_recv"])
    ts_event = _ts_int64(mbo["ts_event"]) if "ts_event" in mbo.columns else ts_recv
    iid_arr = mbo["instrument_id"].to_numpy(dtype=np.int64)
    symbols = (mbo["symbol"].astype(object).where(mbo["symbol"].notna(), "").to_numpy()
               if "symbol" in mbo.columns else np.full(n, "", dtype=object))

    actions = _str_list(mbo["action"], "N")
    sides = _str_list(mbo["side"], "N")
    pxs = _price_keys_from_array(mbo["price"].to_numpy()).tolist()
    sizes = mbo["size"].fillna(0).to_numpy(dtype=np.int64).tolist()
    oids = mbo["order_id"].to_numpy(dtype=np.uint64).tolist()
    flags = mbo["flags"].fillna(0).to_numpy(dtype=np.int64).tolist()
    iids = iid_arr.tolist()
    pubs = (mbo["publisher_id"].fillna(0).to_numpy(dtype=np.int64).tolist()
            if "publisher_id" in mbo.columns else [0] * n)

    mk = market if market is not None else Market(strict=strict)
    books = mk.books
    inst = mk._inst
    L = n_levels
    mode_every = emit == "every"
    mode_tob = emit == "tob_change"
    for b in books.values():          # cache level dibangun ulang pada replay ini
        for sd in (b._bids, b._asks):
            sd.touch_all()
            sd.cache_n = -1
            sd.cache_id = -1
            sd.cache_reg = None

    # Snapshot sisi bid/ask yang berbeda disimpan sekali; tiap baris output
    # hanya menyimpan indeks snapshot bid & ask-nya (hemat memori & waktu).
    caches_b: list[list[int]] = []
    caches_a: list[list[int]] = []
    ids_b = array("q")
    ids_a = array("q")
    idxs = array("q")
    last_l1: dict[int, tuple] = {}
    n_stale_skipped = 0

    for i, (a, s, p, q, o, f, iid, pub) in enumerate(
            zip(actions, sides, pxs, sizes, oids, flags, iids, pubs)):
        bk = books.get((iid, pub))
        if bk is None:
            bk = mk._book(iid, pub)
        bk._apply(a, s, p, q, o, f)
        if not (mode_every or f & F_LAST):
            continue
        grp = inst[iid]
        if len(grp) == 1:
            if bk.stale and not emit_stale:
                n_stale_skipped += 1
                continue
            sb = bk._bids
            sa = bk._asks
            cb = sb.top_cached(L)[0]
            ca = sa.top_cached(L)[0]
            if mode_tob:
                l1 = (cb[0], cb[L], ca[0], ca[L])
                if last_l1.get(iid) == l1:
                    continue
                last_l1[iid] = l1
            # daftarkan snapshot sisi hanya bila objeknya belum terdaftar
            if cb is not sb.cache_reg:
                sb.cache_id = len(caches_b)
                caches_b.append(cb)
                sb.cache_reg = cb
            if ca is not sa.cache_reg:
                sa.cache_id = len(caches_a)
                caches_a.append(ca)
                sa.cache_reg = ca
            ids_b.append(sb.cache_id)
            ids_a.append(sa.cache_id)
        else:
            if any(x.stale for x in grp) and not emit_stale:
                n_stale_skipped += 1
                continue
            flat = []
            for side_bid in (True, False):
                ps, szs, cts = _merge_raw([(x._bids if side_bid else x._asks).raw(L) for x in grp],
                                          side_bid, L)
                pad = L - len(ps)
                flat.append(ps + [_UNDEF] * pad + szs + [0] * pad + cts + [0] * pad)
            cb, ca = flat
            if mode_tob:
                l1 = (cb[0], cb[L], ca[0], ca[L])
                if last_l1.get(iid) == l1:
                    continue
                last_l1[iid] = l1
            ids_b.append(len(caches_b))
            caches_b.append(cb)
            ids_a.append(len(caches_a))
            caches_a.append(ca)
            for x in grp:                 # cache per buku tidak lagi valid untuk replay ini
                x._bids.cache_n = -1
                x._asks.cache_n = -1
        idxs.append(i)

    m = len(idxs)
    idx = np.frombuffer(idxs, dtype=np.int64) if m else np.empty(0, np.int64)
    if m:
        # baris snapshot unik → gather berurutan → transpos (3L, m) C-contiguous
        BT = np.ascontiguousarray(np.array(caches_b, dtype=np.int64)[np.frombuffer(ids_b, dtype=np.int64)].T)
        AT = np.ascontiguousarray(np.array(caches_a, dtype=np.int64)[np.frombuffer(ids_a, dtype=np.int64)].T)
    else:
        BT = np.empty((3 * L, 0), np.int64)
        AT = np.empty((3 * L, 0), np.int64)
    pxk = np.concatenate([BT[:L], AT[:L]])
    pxv = np.where(pxk == _UNDEF, np.nan, pxk / _SCALE)
    intv = np.concatenate([BT[L:2 * L], AT[L:2 * L], BT[2 * L:], AT[2 * L:]])
    cols = book_columns(L)
    meta = pd.DataFrame({
        "ts_recv": ts_recv[idx],
        "ts_event": ts_event[idx],
        "instrument_id": iid_arr[idx],
        "symbol": symbols[idx].astype(object),
    })
    out = pd.concat([meta,
                     pd.DataFrame(pxv.T, columns=cols[4:4 + 2 * L], copy=False),
                     pd.DataFrame(intv.T, columns=cols[4 + 2 * L:], copy=False)], axis=1)
    out.attrs["replay"] = {
        "n_records": n,
        "n_emitted": int(m),
        "n_stale_skipped": int(n_stale_skipped),
        "n_anomalies": int(sum(b.n_anomalies for b in mk.books.values())),
        "n_ignored": int(sum(b.n_ignored for b in mk.books.values())),
    }
    return out
