#!/usr/bin/env python3
"""
SAPU JAGAD FORENSIK
===================
Memutar ulang (replay) logika EA SAPU JAGAD v1.20 di atas data historis XAUUSD
(mesin MOMENTUM/stop, REVERSION/limit, dan BERITA, dipilih detektor rezim) lalu
membedah hasilnya: per sesi, per jam, per mesin x rezim, sekitar rilis berita,
saat volatilitas melonjak, dan saat banyak stop terisi bersamaan (burst).
Hasilnya laporan kelemahan + rekomendasi parameter, analisis MAE (batas cut loss),
pencarian parameter (--sweep), dan uji walk-forward anti-overfitting.

Hanya butuh Python 3.8+ (tanpa pustaka tambahan).

Contoh pemakaian (Windows):
    python sapu_jagad_forensik.py --data "D:\\dataset" --gmt-offset 2 --compare
    python sapu_jagad_forensik.py --data "D:\\dataset\\XAUUSD_M1.csv" --news "D:\\news.csv" --sweep
    python sapu_jagad_forensik.py --data "D:\\dataset" --set EA_SAPU_JAGAD_XAUUSD.set --from 2025-01-01
    python sapu_jagad_forensik.py --data "D:\\dataset" --news "D:\\news.csv" --walk-forward 0.7

Format data yang dikenali otomatis:
  * Ekspor tick MT5  : <DATE> <TIME> <BID> <ASK> <LAST> <VOLUME> <FLAGS>
  * Ekspor bar MT5   : <DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE> <TICKVOL> <VOL> <SPREAD>
  * CSV umum         : kolom waktu + bid/ask, atau waktu + open/high/low/close
  * Dukascopy        : Gmt time,Ask,Bid,... (dd.mm.yyyy hh:mm:ss.fff)
  * HistData         : 20250102 010000;open;high;low;close;vol  (tanpa judul)

File berita (opsional, waktu GMT), sama dengan format EA:
    2026.10.02 12:30,USD,HIGH,Non-Farm Employment Change
Tanpa file berita, alat ini MENDETEKSI sendiri kejutan harga di menit :00/:30
sebagai perkiraan jadwal berita (lihat catatan bias di laporan).
"""

import argparse
import calendar
import csv
import glob
import json
import math
import os
import re
import sys
import time as _time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, fields, replace

# ---------------------------------------------------------------------------
# Konfigurasi (cermin dari input EA)
# ---------------------------------------------------------------------------


@dataclass
class Config:
    engine_mode: str = "adaptive"      # momentum (video 1) | reversion (video 2) | adaptive
    direction: str = "auto"            # auto | buy | sell
    one_basket_only: bool = True
    grid_levels: int = 8
    grid_step: float = 0.50
    start_distance: float = 2.00
    trail_step: float = 0.50
    trail_cooldown_ms: int = 1000
    max_positions: int = 24
    fixed_lot: float = 0.01
    tp_mode: int = 1                   # 0 USD tetap, 1 per 0.01 lot, 2 % saldo
    tp_value: float = 1.00
    commission_per_lot: float = 0.0
    use_profit_lock: bool = True
    lock_giveback_pct: float = 30.0
    recovery_after: int = 12
    recovery_tp_per_minlot: float = 0.20
    basket_sl_money: float = 0.0
    basket_sl_pct: float = 10.0
    basket_age_hours: float = 24.0
    no_add_against_trend: bool = True
    cooldown_after_loss_min: int = 60
    max_drawdown_pct: float = 30.0
    daily_profit_target: float = 0.0
    daily_loss_limit: float = 0.0
    max_spread: float = 0.50
    delete_pending_on_wide_spread: bool = True
    use_time_filter: bool = False
    start_hour: int = 1
    end_hour: int = 23
    friday_stop: bool = True
    friday_stop_hour: int = 20
    friday_close_all: bool = False
    friday_close_hour: int = 22
    london_open_gmt: int = 7
    ny_open_gmt: int = 13
    ny_close_gmt: int = 21
    trade_asia: bool = True
    trade_london: bool = True
    trade_ny: bool = True
    asia_step_mult: float = 1.0
    london_step_mult: float = 1.0
    ny_step_mult: float = 1.0
    open_guard_min: int = 10
    rollover_guard: bool = True
    rollover_start_gmt: int = 2050
    rollover_end_gmt: int = 2310
    vol_guard: bool = True
    vol_slow_period: int = 60
    vol_widen_ratio: float = 2.0
    vol_max_step_mult: float = 2.5
    vol_block_ratio: float = 4.0
    burst_max_fills: int = 5
    burst_seconds: int = 30
    burst_pause_sec: int = 300
    use_news_filter: bool = True
    news_before_min: int = 15
    news_after_min: int = 30
    news_bank_profit: bool = True
    news_ride: bool = True
    news_settle_sec: int = 20
    news_ride_window_min: int = 10
    news_impulse_atr: float = 1.5
    news_levels: int = 4
    news_step_atr: float = 0.5
    news_start_atr: float = 0.5
    news_lot_mult: float = 1.0
    news_tp_per_minlot: float = 2.0
    news_sl_per_minlot: float = 3.0
    news_max_hold_min: int = 45
    news_max_spread: float = 1.00
    trend_tf_minutes: int = 60
    trend_ema: int = 50
    regime_bars: int = 30
    er_trend: float = 0.30
    er_range: float = 0.12
    adaptive_use_h1: bool = True       # adaptif: arah momentum juga harus searah tren H1
    rev_levels: int = 6
    rev_step_atr: float = 0.3          # >0: jarak tangga reversion = max(rev_step, ATR M5 x faktor)
    rev_step: float = 0.25
    rev_start: float = 0.25
    rev_z_entry: float = 0.8
    rev_ema_period: int = 20
    rev_with_trend_only: bool = True
    rev_regime_exit: bool = True
    rev_tp_per_minlot: float = 0.50
    rev_sl_per_minlot: float = 3.0
    rev_max_hold_min: int = 240


# nama input EA -> nama field Config
SET_MAP = {
    "InpDirection": "direction", "InpOneBasketOnly": "one_basket_only",
    "InpGridLevels": "grid_levels", "InpGridStep": "grid_step", "InpStartDistance": "start_distance",
    "InpTrailStep": "trail_step", "InpTrailCooldownMs": "trail_cooldown_ms", "InpMaxPositions": "max_positions",
    "InpFixedLot": "fixed_lot", "InpTPMode": "tp_mode", "InpTPValue": "tp_value",
    "InpCommissionPerLot": "commission_per_lot", "InpUseProfitLock": "use_profit_lock",
    "InpLockGivebackPct": "lock_giveback_pct", "InpRecoveryAfter": "recovery_after",
    "InpRecoveryTPPerMinLot": "recovery_tp_per_minlot", "InpBasketSLMoney": "basket_sl_money",
    "InpBasketSLPct": "basket_sl_pct", "InpBasketAgeHours": "basket_age_hours",
    "InpNoAddAgainstTrend": "no_add_against_trend",
    "InpCooldownAfterLossMin": "cooldown_after_loss_min", "InpMaxDrawdownPct": "max_drawdown_pct",
    "InpDailyProfitTarget": "daily_profit_target", "InpDailyLossLimit": "daily_loss_limit",
    "InpMaxSpread": "max_spread", "InpDeletePendingOnWideSpread": "delete_pending_on_wide_spread",
    "InpUseTimeFilter": "use_time_filter", "InpStartHour": "start_hour", "InpEndHour": "end_hour",
    "InpFridayStop": "friday_stop", "InpFridayStopHour": "friday_stop_hour",
    "InpFridayCloseAll": "friday_close_all", "InpFridayCloseHour": "friday_close_hour",
    "InpLondonOpenGMT": "london_open_gmt", "InpNYOpenGMT": "ny_open_gmt", "InpNYCloseGMT": "ny_close_gmt",
    "InpTradeAsia": "trade_asia", "InpTradeLondon": "trade_london", "InpTradeNY": "trade_ny",
    "InpAsiaStepMult": "asia_step_mult", "InpLondonStepMult": "london_step_mult", "InpNYStepMult": "ny_step_mult",
    "InpOpenGuardMin": "open_guard_min", "InpRolloverGuard": "rollover_guard",
    "InpRolloverStartGMT": "rollover_start_gmt", "InpRolloverEndGMT": "rollover_end_gmt",
    "InpVolGuard": "vol_guard", "InpVolSlowPeriod": "vol_slow_period", "InpVolWidenRatio": "vol_widen_ratio",
    "InpVolMaxStepMult": "vol_max_step_mult", "InpVolBlockRatio": "vol_block_ratio",
    "InpBurstMaxFills": "burst_max_fills", "InpBurstSeconds": "burst_seconds", "InpBurstPauseSec": "burst_pause_sec",
    "InpUseNewsFilter": "use_news_filter", "InpNewsBeforeMin": "news_before_min", "InpNewsAfterMin": "news_after_min",
    "InpNewsBankProfit": "news_bank_profit", "InpNewsRide": "news_ride", "InpNewsSettleSec": "news_settle_sec",
    "InpNewsRideWindowMin": "news_ride_window_min", "InpNewsImpulseATR": "news_impulse_atr",
    "InpNewsLevels": "news_levels", "InpNewsStepATR": "news_step_atr", "InpNewsStartATR": "news_start_atr",
    "InpNewsLotMult": "news_lot_mult", "InpNewsTPPerMinLot": "news_tp_per_minlot",
    "InpNewsSLPerMinLot": "news_sl_per_minlot", "InpNewsMaxHoldMin": "news_max_hold_min",
    "InpNewsMaxSpread": "news_max_spread", "InpTrendEMA": "trend_ema",
    "InpEngineMode": "engine_mode", "InpRegimeBars": "regime_bars", "InpERTrend": "er_trend",
    "InpERRange": "er_range", "InpRevLevels": "rev_levels", "InpRevStep": "rev_step", "InpRevStart": "rev_start",
    "InpRevZEntry": "rev_z_entry", "InpRevEMAPeriod": "rev_ema_period", "InpRevWithTrendOnly": "rev_with_trend_only",
    "InpRevRegimeExit": "rev_regime_exit", "InpRevTPPerMinLot": "rev_tp_per_minlot",
    "InpRevSLPerMinLot": "rev_sl_per_minlot", "InpRevMaxHoldMin": "rev_max_hold_min",
    "InpAdaptiveUseH1": "adaptive_use_h1", "InpRevStepATR": "rev_step_atr",
}
DIRECTION_ENUM = {0: "buy", 1: "sell", 2: "auto"}
ENGINE_ENUM = {0: "momentum", 1: "reversion", 2: "adaptive"}
TF_MINUTES = {"PERIOD_M1": 1, "PERIOD_M5": 5, "PERIOD_M15": 15, "PERIOD_M30": 30, "PERIOD_H1": 60,
              "PERIOD_H4": 240, "PERIOD_D1": 1440}

PRESETS = {
    # tiruan sedekat mungkin dengan perilaku Steev GTS V4.4 di video
    "video": dict(engine_mode="momentum", direction="buy", use_profit_lock=False, recovery_after=0, max_drawdown_pct=0.0,
                  basket_sl_pct=0.0, basket_age_hours=0.0, no_add_against_trend=False,
                  max_positions=40, max_spread=0.0, friday_stop=False, open_guard_min=0, rollover_guard=False,
                  vol_guard=False, burst_max_fills=0, use_news_filter=False),
    # tiruan grid BUY/SELL LIMIT rapat di video kedua (zs.x_hanss)
    "video2": dict(engine_mode="reversion", rev_levels=30, rev_step=0.25, rev_step_atr=0.0, rev_start=0.25,
                   rev_z_entry=0.0,
                   rev_with_trend_only=False, rev_regime_exit=False, rev_sl_per_minlot=0.0, rev_max_hold_min=0,
                   basket_sl_pct=0.0, max_drawdown_pct=0.0, max_spread=0.0, friday_stop=False, open_guard_min=0,
                   rollover_guard=False, vol_guard=False, burst_max_fills=0, use_news_filter=False,
                   one_basket_only=True),
    "sapujagad": {},
}


def coerce(value, typ):
    if typ is bool:
        return str(value).strip().lower() in ("1", "true", "yes", "ya")
    if typ is int:
        return int(float(value))
    if typ is float:
        return float(value)
    return str(value)


def load_set_file(path, cfg):
    raw = open(path, "rb").read()
    text = None
    for enc in ("utf-16", "utf-8-sig", "cp1252"):
        try:
            text = raw.decode(enc)
            if "=" in text:
                break
        except UnicodeDecodeError:
            continue
    types = {f.name: f.type for f in fields(Config)}
    pytypes = {"bool": bool, "int": int, "float": float, "str": str}
    changes = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith(";") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        val = val.split("||")[0].strip()
        key = key.strip()
        if key == "InpTrendTF":
            enum_minutes = {1: 1, 5: 5, 15: 15, 30: 30, 16385: 60, 16388: 240, 16408: 1440}
            changes["trend_tf_minutes"] = enum_minutes.get(int(val), 60) if val.isdigit() else TF_MINUTES.get(val, 60)
            continue
        name = SET_MAP.get(key)
        if not name:
            continue
        if name == "direction":
            changes[name] = DIRECTION_ENUM.get(int(float(val)), "auto")
            continue
        if name == "engine_mode":
            changes[name] = ENGINE_ENUM.get(int(float(val)), "adaptive")
            continue
        t = types[name]
        t = pytypes.get(t, t) if isinstance(t, str) else t
        changes[name] = coerce(val, t)
    return replace(cfg, **changes)


def write_set_file(path, cfg):
    inv = {v: k for k, v in SET_MAP.items()}
    lines = ["; EA SAPU JAGAD - hasil sapu_jagad_forensik.py"]
    for f in fields(Config):
        v = getattr(cfg, f.name)
        if f.name == "direction":
            v = {"buy": 0, "sell": 1, "auto": 2}[v]
        elif f.name == "engine_mode":
            v = {"momentum": 0, "reversion": 1, "adaptive": 2}[v]
        elif f.name == "trend_tf_minutes":
            lines.append("InpTrendTF=%d" % {1: 1, 5: 5, 15: 15, 30: 30, 60: 16385, 240: 16388}.get(v, 16385))
            continue
        if isinstance(v, bool):
            v = "true" if v else "false"
        key = inv.get(f.name)
        if key:
            lines.append("%s=%s" % (key, v))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Pembaca data
# ---------------------------------------------------------------------------

_DT_PATTERNS = [
    (re.compile(r"^(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})[ T]+(\d{1,2}):(\d{2})(?::(\d{2})(?:[.,](\d+))?)?"), "ymd"),
    (re.compile(r"^(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})[ T]+(\d{1,2}):(\d{2})(?::(\d{2})(?:[.,](\d+))?)?"), "dmy"),
    (re.compile(r"^(\d{4})(\d{2})(\d{2})[ T]?(\d{2})(\d{2})(\d{2})(\d{0,3})"), "compact"),
]
_DAY_CACHE = {}


def parse_dt(text):
    """Teks waktu -> detik epoch (float), zona waktu dianggap apa adanya."""
    s = text.strip().strip('"')
    if s.isdigit() and len(s) in (10, 13):
        v = int(s)
        return v / 1000.0 if len(s) == 13 else float(v)
    for rx, kind in _DT_PATTERNS:
        m = rx.match(s)
        if not m:
            continue
        g = m.groups()
        if kind == "dmy":
            d, mo, y = int(g[0]), int(g[1]), int(g[2])
        else:
            y, mo, d = int(g[0]), int(g[1]), int(g[2])
        key = (y, mo, d)
        day = _DAY_CACHE.get(key)
        if day is None:
            day = calendar.timegm((y, mo, d, 0, 0, 0))
            _DAY_CACHE[key] = day
        sec = int(g[3]) * 3600 + int(g[4]) * 60 + (int(g[5]) if g[5] else 0)
        frac = g[6]
        return day + sec + (float("0." + frac) if frac else 0.0)
    return None


def _sniff_delim(line):
    for d in ("\t", ";", ",", "|"):
        if d in line:
            return d
    return None


def _norm(name):
    return re.sub(r"[^a-z]", "", name.lower())


class FileInfo:
    def __init__(self, path):
        self.path = path
        self.kind = None          # "tick" | "bar"
        self.delim = ","
        self.header = False
        self.cols = {}
        self.first_ts = None
        self.ok = False
        self.reason = ""


def inspect_file(path):
    info = FileInfo(path)
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
            head = [fh.readline() for _ in range(5)]
    except OSError as exc:
        info.reason = str(exc)
        return info
    head = [h.strip("\r\n") for h in head if h.strip()]
    if not head:
        info.reason = "file kosong"
        return info
    delim = _sniff_delim(head[0]) or ","
    info.delim = delim
    first = head[0].split(delim)
    has_header = any(re.search(r"[a-zA-Z]{3,}", c) and not re.match(r"^\d", c.strip()) for c in first)
    info.header = has_header
    cols = {}
    if has_header:
        names = [_norm(c) for c in first]
        for i, n in enumerate(names):
            if n in ("date", "tanggal"):
                cols["date"] = i
            elif n in ("time", "jam", "waktu") and "date" in cols:
                cols["time"] = i
            elif n in ("time", "datetime", "timestamp", "gmttime", "localtime", "dt", "waktu"):
                cols["datetime"] = i
            elif n in ("bid", "bidprice"):
                cols["bid"] = i
            elif n in ("ask", "askprice"):
                cols["ask"] = i
            elif n in ("open", "o"):
                cols["open"] = i
            elif n in ("high", "h"):
                cols["high"] = i
            elif n in ("low", "l"):
                cols["low"] = i
            elif n in ("close", "c"):
                cols["close"] = i
            elif n == "spread":
                cols["spread"] = i
            elif n in ("last", "price") and "bid" not in cols:
                cols["last"] = i
        if "date" in cols and "time" not in cols and "datetime" not in cols:
            # kolom "date" berisi tanggal+jam
            cols["datetime"] = cols.pop("date")
        sample = head[1].split(delim) if len(head) > 1 else None
    else:
        sample = first
        n = len(first)
        if re.match(r"^\d{8}[ T]?\d{6}", first[0]):     # HistData
            cols["datetime"] = 0
            if n >= 5:
                cols.update(open=1, high=2, low=3, close=4)
            else:
                cols.update(bid=1, ask=2)
        elif (n >= 4 and re.match(r"^\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}$", first[0].strip())
              and parse_dt(first[0] + " " + first[1]) is not None):
            cols.update(date=0, time=1)
            if n >= 6:
                cols.update(open=2, high=3, low=4, close=5)
                if n >= 9:
                    cols["spread"] = 8
            else:
                cols.update(bid=2, ask=3)
        elif parse_dt(first[0]) is not None:
            cols["datetime"] = 0
            if n >= 5:
                cols.update(open=1, high=2, low=3, close=4)
            else:
                cols.update(bid=1, ask=2)
    if sample is None:
        info.reason = "tidak ada baris data"
        return info
    if "bid" in cols or "ask" in cols or "last" in cols:
        info.kind = "tick"
    elif all(k in cols for k in ("open", "high", "low", "close")):
        info.kind = "bar"
    else:
        info.reason = "kolom harga tidak dikenali"
        return info
    if "datetime" not in cols and not ("date" in cols and "time" in cols):
        info.reason = "kolom waktu tidak dikenali"
        return info
    info.cols = cols
    info.first_ts = _row_ts(sample, cols)
    if info.first_ts is None:
        info.reason = "format waktu tidak dikenali"
        return info
    info.ok = True
    return info


def _row_ts(row, cols):
    try:
        if "datetime" in cols:
            return parse_dt(row[cols["datetime"]])
        return parse_dt(row[cols["date"]].strip() + " " + row[cols["time"]].strip())
    except (IndexError, ValueError):
        return None


def _f(row, idx):
    try:
        v = row[idx].strip()
        return float(v) if v else None
    except (IndexError, ValueError):
        return None


def iter_file_ticks(info, point, default_spread):
    """Hasilkan (t, bid, ask). Data bar diubah menjadi 4 tick sintetis per bar."""
    c = info.cols
    with open(info.path, "r", encoding="utf-8-sig", errors="replace", newline="") as fh:
        reader = csv.reader(fh, delimiter=info.delim)
        if info.header:
            next(reader, None)
        if info.kind == "tick":
            bid = ask = None
            ib, ia, il = c.get("bid"), c.get("ask"), c.get("last")
            for row in reader:
                t = _row_ts(row, c)
                if t is None:
                    continue
                if ib is not None:
                    v = _f(row, ib)
                    if v:
                        bid = v
                if ia is not None:
                    v = _f(row, ia)
                    if v:
                        ask = v
                if il is not None and ib is None:
                    v = _f(row, il)
                    if v:
                        bid = v
                        ask = v + default_spread
                if bid is None:
                    continue
                if ask is None or ask < bid:
                    ask = bid + default_spread
                yield t, bid, ask
        else:
            io_, ih, il_, ic, isp = c["open"], c["high"], c["low"], c["close"], c.get("spread")
            for row in reader:
                t = _row_ts(row, c)
                if t is None:
                    continue
                o, h, l, cl = _f(row, io_), _f(row, ih), _f(row, il_), _f(row, ic)
                if None in (o, h, l, cl):
                    continue
                sp = default_spread
                if isp is not None:
                    v = _f(row, isp)
                    if v:
                        sp = v * point
                path = (o, l, h, cl) if cl >= o else (o, h, l, cl)
                for k, p in enumerate(path):
                    yield t + (0, 15, 30, 59)[k], p, p + sp


def discover_files(data_paths, symbol_filter):
    files = []
    for dp in data_paths:
        if os.path.isdir(dp):
            for ext in ("*.csv", "*.txt", "*.CSV", "*.TXT"):
                files.extend(glob.glob(os.path.join(dp, "**", ext), recursive=True))
        else:
            files.extend(glob.glob(dp))
    files = sorted(set(files))
    if symbol_filter:
        rx = re.compile(symbol_filter, re.I)
        files = [f for f in files if rx.search(os.path.basename(f))]
    return files


class TickSource:
    def __init__(self, infos, point, default_spread, t_from=None, t_to=None):
        self.infos = sorted(infos, key=lambda i: i.first_ts)
        self.point = point
        self.default_spread = default_spread
        self.t_from = t_from
        self.t_to = t_to

    def __iter__(self):
        last_t = -1.0
        for info in self.infos:
            for t, bid, ask in iter_file_ticks(info, self.point, self.default_spread):
                if t < last_t:
                    continue            # duplikat/tumpang tindih antar file
                if self.t_from and t < self.t_from:
                    continue
                if self.t_to and t >= self.t_to:
                    return
                last_t = t
                yield t, bid, ask


# ---------------------------------------------------------------------------
# Berita
# ---------------------------------------------------------------------------

def load_news_csv(path, currencies, include_medium, gmt_offset_h):
    events = []
    wanted = {c.strip().upper() for c in currencies.split(",") if c.strip()}
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        for line in fh:
            parts = [p.strip() for p in line.strip().split(",")]
            if len(parts) < 3:
                continue
            t = parse_dt(parts[0])
            if t is None:
                continue
            cur, imp = parts[1].upper(), parts[2].upper()
            if cur not in wanted:
                continue
            if not ("HIGH" in imp or (include_medium and "MED" in imp)):
                continue
            events.append((t + gmt_offset_h * 3600, cur + " " + (parts[3] if len(parts) > 3 else "berita")))
    events.sort()
    return events


def infer_news(source, gmt_offset_h, k=5.0):
    """Perkiraan jadwal berita: candle M1 di menit :00/:30 (GMT) dengan range >= k x ATR60."""
    bars = []
    cur = None
    for t, bid, _ask in source:
        m = int(t // 60) * 60
        if cur is None or m != cur[0]:
            if cur is not None:
                bars.append(cur)
            cur = [m, bid, bid, bid, bid]
        else:
            if bid > cur[2]:
                cur[2] = bid
            if bid < cur[3]:
                cur[3] = bid
            cur[4] = bid
    if cur is not None:
        bars.append(cur)
    events = []
    trs = deque(maxlen=60)
    prev_close = None
    for b in bars:
        tr = b[2] - b[3] if prev_close is None else max(b[2], prev_close) - min(b[3], prev_close)
        if len(trs) == 60:
            atr = sum(trs) / 60.0
            gmt = b[0] - gmt_offset_h * 3600
            minute = int(gmt % 3600 // 60)
            weekday = int((gmt // 86400 + 3) % 7)
            if atr > 0 and tr >= k * atr and minute in (0, 30) and weekday < 5:
                if not events or b[0] - events[-1][0] > 3600:
                    events.append((b[0], "kejutan terdeteksi x%.1f" % (tr / atr)))
        trs.append(tr)
        prev_close = b[4]
    return events, len(bars)


# ---------------------------------------------------------------------------
# Mesin replay (cermin logika EA)
# ---------------------------------------------------------------------------

NEWS_NONE, NEWS_PRE, NEWS_SETTLE, NEWS_POST = 0, 1, 2, 3
SESSION_NAMES = ("ASIA", "LONDON", "NEW YORK")
# slot: 0/1 momentum (stop), 2/3 berita (stop), 4/5 reversion (limit)
SLOT_NAMES = ("BUY", "SELL", "N-BUY", "N-SELL", "R-BUY", "R-SELL")
SLOT_ENGINE = ("MOMENTUM", "MOMENTUM", "BERITA", "BERITA", "REVERSION", "REVERSION")
REGIME_RANGE, REGIME_NEUTRAL, REGIME_TREND = 0, 1, 2
REGIME_NAMES = ("RANGE", "NETRAL", "TREN")
SLOT_COUNT = 6


class Basket:
    __slots__ = ("slot", "dir", "kind", "ext", "pos", "pend", "pend_lot", "peak", "cooldown_until",
                 "pause_until", "last_trail", "rec")

    def __init__(self, slot):
        self.slot = slot
        self.dir = 1 if slot % 2 == 0 else -1
        self.kind = "limit" if slot >= 4 else "stop"
        # arah tangga menjauh dari harga: stop searah posisi, limit berlawanan
        self.ext = self.dir if self.kind == "stop" else -self.dir
        self.pos = []          # [harga, lot, waktu]
        self.pend = []         # harga pending
        self.pend_lot = 0.0
        self.peak = 0.0
        self.cooldown_until = 0.0
        self.pause_until = 0.0
        self.last_trail = -1e18
        self.rec = None        # catatan forensik basket berjalan


class Engine:
    def __init__(self, cfg, news, gmt_offset_h, contract=100.0, balance=10000.0, tick_size=0.01):
        self.cfg = cfg
        self.news = news
        self.news_ptr = 0
        self.off = gmt_offset_h * 3600
        self.contract = contract
        self.balance = balance
        self.start_balance = balance
        self.tick = tick_size
        self.b = [Basket(s) for s in range(SLOT_COUNT)]
        self.records = []
        self.realized_day = 0.0
        self.day_key = None
        self.halt_until = 0.0
        # bar M1 (volatilitas & rezim)
        self.m1 = None             # [start, open, high, low, close]
        self.m1_prev_close = None
        self.tr_hist = deque(maxlen=max(cfg.vol_slow_period, 14))
        self.atr_slow = 0.0
        self.atr14 = 0.0
        self.last_tr = 0.0
        self.m1_closes = deque(maxlen=cfg.regime_bars + 1)
        self.er = 0.0
        self.er_dir = 0
        # bar M5 (z-score reversion)
        self.m5 = None
        self.m5_prev_close = None
        self.m5_tr = deque(maxlen=14)
        self.atr_m5 = 0.0
        self.ema_m5 = None
        # tren TF tinggi
        self.htf_start = None
        self.htf_close = None
        self.ema = None
        self.ema_prev_bar = None
        self.close_prev_bar = None
        # berita
        self.ev_time = 0.0
        self.ev_name = ""
        self.ref_price = 0.0
        self.ref_atr = 0.0
        self.ride_until = 0.0
        self.ride_done = False
        self.news_step = 0.0
        self.news_start = 0.0
        self.ride_log = []
        # ekuitas
        self.peak_equity = balance
        self.max_dd = 0.0
        self.max_dd_pct = 0.0
        self.equity_curve = []
        self.last_curve_t = 0.0
        self.counters = defaultdict(int)

    # ---------------- indikator ----------------
    def _bars(self, t, bid):
        cfg = self.cfg
        m = t - t % 60
        if self.m1 is None or m != self.m1[0]:
            if self.m1 is not None:
                o, h, l, c = self.m1[1:]
                pc = self.m1_prev_close
                tr = h - l if pc is None else max(h, pc) - min(l, pc)
                self.tr_hist.append(tr)
                self.last_tr = tr
                n = len(self.tr_hist)
                ps = cfg.vol_slow_period
                if n >= ps:
                    self.atr_slow = sum(list(self.tr_hist)[-ps:]) / ps
                if n >= 14:
                    self.atr14 = sum(list(self.tr_hist)[-14:]) / 14.0
                self.m1_prev_close = c
                # Efficiency Ratio (Kaufman): |perubahan bersih| / total jalan
                self.m1_closes.append(c)
                if len(self.m1_closes) == self.m1_closes.maxlen:
                    cl = list(self.m1_closes)
                    path = sum(abs(cl[i] - cl[i - 1]) for i in range(1, len(cl)))
                    net = cl[-1] - cl[0]
                    self.er = abs(net) / path if path > 0 else 0.0
                    self.er_dir = 1 if net > 0 else (-1 if net < 0 else 0)
            self.m1 = [m, bid, bid, bid, bid]
        else:
            if bid > self.m1[2]:
                self.m1[2] = bid
            if bid < self.m1[3]:
                self.m1[3] = bid
            self.m1[4] = bid
        m5 = t - t % 300
        if self.m5 is None or m5 != self.m5[0]:
            if self.m5 is not None:
                o, h, l, c = self.m5[1:]
                pc = self.m5_prev_close
                self.m5_tr.append(h - l if pc is None else max(h, pc) - min(l, pc))
                if len(self.m5_tr) == 14:
                    self.atr_m5 = sum(self.m5_tr) / 14.0
                a = 2.0 / (cfg.rev_ema_period + 1.0)
                self.ema_m5 = c if self.ema_m5 is None else a * c + (1 - a) * self.ema_m5
                self.m5_prev_close = c
            self.m5 = [m5, bid, bid, bid, bid]
        else:
            if bid > self.m5[2]:
                self.m5[2] = bid
            if bid < self.m5[3]:
                self.m5[3] = bid
            self.m5[4] = bid
        tfs = cfg.trend_tf_minutes * 60
        hs = t - t % tfs
        if self.htf_start is None or hs != self.htf_start:
            if self.htf_close is not None:
                a = 2.0 / (cfg.trend_ema + 1.0)
                self.ema = self.htf_close if self.ema is None else a * self.htf_close + (1 - a) * self.ema
                self.ema_prev_bar = self.ema
                self.close_prev_bar = self.htf_close
            self.htf_start = hs
        self.htf_close = bid

    def _vol_ratio(self):
        if self.atr_slow <= 0 or self.m1 is None:
            return 1.0
        pc = self.m1_prev_close
        h, l = self.m1[2], self.m1[3]
        tr0 = h - l if pc is None else max(h, pc) - min(l, pc)
        return max(tr0, self.last_tr) / self.atr_slow

    def _trend(self):
        if self.ema_prev_bar is None or self.close_prev_bar is None:
            return 0
        if self.close_prev_bar > self.ema_prev_bar:
            return 1
        if self.close_prev_bar < self.ema_prev_bar:
            return -1
        return 0

    def _regime(self):
        if len(self.m1_closes) < self.m1_closes.maxlen:
            return REGIME_NEUTRAL
        if self.er >= self.cfg.er_trend:
            return REGIME_TREND
        if self.er <= self.cfg.er_range:
            return REGIME_RANGE
        return REGIME_NEUTRAL

    def _zscore(self, mid):
        if self.ema_m5 is None or self.atr_m5 <= 0:
            return 0.0
        return (mid - self.ema_m5) / self.atr_m5

    # ---------------- utilitas basket ----------------
    def _profit(self, bk, bid, ask):
        c = self.contract
        comm = self.cfg.commission_per_lot
        if bk.dir > 0:
            return sum((bid - p) * lot * c - lot * comm for p, lot, _ in bk.pos)
        return sum((p - ask) * lot * c - lot * comm for p, lot, _ in bk.pos)

    def _volume(self, bk):
        return sum(lot for _, lot, _ in bk.pos)

    def _close(self, bk, t, bid, ask, reason, is_loss=False):
        cfg = self.cfg
        pnl = self._profit(bk, bid, ask) if bk.pos else 0.0
        if bk.pos:
            self.balance += pnl
            self.realized_day += pnl
            r = bk.rec
            if r is not None:
                r["close_t"] = t
                r["result"] = pnl
                r["reason"] = reason
                r["positions"] = len(bk.pos)
                r["volume"] = self._volume(bk)
                self.records.append(r)
        bk.pos = []
        bk.pend = []
        bk.peak = 0.0
        bk.rec = None
        if is_loss and cfg.cooldown_after_loss_min > 0:
            bk.cooldown_until = t + cfg.cooldown_after_loss_min * 60

    def _close_all(self, t, bid, ask, reason, halt):
        if halt:
            self.halt_until = (t - t % 86400) + 86400
            self.counters["halt"] += 1
        for bk in self.b:
            if bk.pos or bk.pend:
                self._close(bk, t, bid, ask, reason, is_loss=halt)

    def _fills(self, bk, t, bid, ask, env_vol, session, news_phase, regime):
        if not bk.pend:
            return
        keep = []
        is_stop = bk.kind == "stop"
        for p in bk.pend:
            if bk.dir > 0:
                hit = ask >= p if is_stop else ask <= p
            else:
                hit = bid <= p if is_stop else bid >= p
            if not hit:
                keep.append(p)
                continue
            # stop menjadi market order (bisa slip); limit terisi di harganya
            px = (ask if bk.dir > 0 else bid) if is_stop else p
            if not bk.pos:
                bk.rec = {"slot": SLOT_NAMES[bk.slot], "engine": SLOT_ENGINE[bk.slot], "open_t": t,
                          "session": SESSION_NAMES[session], "vol_ratio": round(env_vol, 2),
                          "news": news_phase != NEWS_NONE or bk.slot in (2, 3),
                          "er": round(self.er, 2), "regime": REGIME_NAMES[regime],
                          "mae": 0.0, "mfe": 0.0, "max_burst": 0, "fills": 0, "slip": 0.0}
            bk.pos.append([px, bk.pend_lot, t])
            bk.rec["fills"] += 1
            bk.rec["slip"] += abs(px - p)
        bk.pend = keep

    # ---------------- berita ----------------
    def _news(self, t, bid, ask):
        cfg = self.cfg
        if not cfg.use_news_filter or not self.news:
            return NEWS_NONE, ""
        before = cfg.news_before_min * 60
        tail = max(cfg.news_after_min * 60, cfg.news_settle_sec + cfg.news_ride_window_min * 60)
        n = len(self.news)
        while self.news_ptr < n and self.news[self.news_ptr][0] + tail < t:
            self.news_ptr += 1
        if self.news_ptr >= n or self.news[self.news_ptr][0] - before > t:
            return NEWS_NONE, ""
        ev_t, ev_name = self.news[self.news_ptr]
        if ev_t != self.ev_time:
            self.ev_time, self.ev_name = ev_t, ev_name
            self.ref_price = 0.0
            self.ref_atr = 0.0
            self.ride_done = False
            self.ride_until = ev_t + cfg.news_settle_sec + cfg.news_ride_window_min * 60
        if t < ev_t:
            self.ref_price = (bid + ask) * 0.5
            self.ref_atr = self.atr14
            return NEWS_PRE, ev_name
        if t < ev_t + cfg.news_settle_sec:
            return NEWS_SETTLE, ev_name
        if t <= ev_t + cfg.news_after_min * 60:
            return NEWS_POST, ev_name
        return NEWS_NONE, ev_name

    # ---------------- tangga ----------------
    def _place(self, bk, count, bid, ask, step, start, lot):
        ref = ask if bk.dir > 0 else bid
        anchor = ref + bk.ext * start
        tk = self.tick
        bk.pend = [round((anchor + i * step * bk.ext) / tk) * tk for i in range(count)]
        bk.pend_lot = lot
        self.counters["ladders"] += 1

    def _trail(self, bk, t, bid, ask, step, start, trail_step):
        cfg = self.cfg
        if not bk.pend:
            return
        if (t - bk.last_trail) * 1000.0 < cfg.trail_cooldown_ms:
            return
        tk = self.tick
        ref = ask if bk.dir > 0 else bid
        anchor = round((ref + bk.ext * start) / tk) * tk
        nearest = min(bk.pend, key=lambda p: bk.ext * p)
        if bk.ext * (nearest - anchor) < trail_step - tk * 0.5:
            return   # harga belum cukup menjauh dari tangga
        bk.pend = [round((anchor + i * step * bk.ext) / tk) * tk for i in range(len(bk.pend))]
        bk.last_trail = t
        self.counters["trails"] += 1

    def _others_busy(self, slot):
        return any(self.b[s].pos for s in (0, 1, 4, 5) if s != slot)

    # ---------------- satu tick ----------------
    def on_tick(self, t, bid, ask):
        cfg = self.cfg
        self._bars(t, bid)
        spread = ask - bid
        mid = (bid + ask) * 0.5

        day = int(t // 86400)
        if day != self.day_key:
            self.day_key = day
            self.realized_day = 0.0

        gmt = t - self.off
        gmt_min = int(gmt % 86400 // 60)
        gmt_hour = gmt_min // 60
        if cfg.london_open_gmt <= gmt_hour < cfg.ny_open_gmt:
            session = 1
        elif cfg.ny_open_gmt <= gmt_hour < cfg.ny_close_gmt:
            session = 2
        else:
            session = 0

        vol = self._vol_ratio() if cfg.vol_guard else 1.0
        regime = self._regime()
        news_phase, news_name = self._news(t, bid, ask)

        # 1. pending terisi oleh pergerakan harga
        for bk in self.b:
            self._fills(bk, t, bid, ask, vol, session, news_phase, regime)

        # catatan MAE/MFE & burst
        floating = 0.0
        for bk in self.b:
            if bk.pos:
                p = self._profit(bk, bid, ask)
                floating += p
                r = bk.rec
                if p < r["mae"]:
                    r["mae"] = p
                if p > r["mfe"]:
                    r["mfe"] = p
                recent = sum(1 for x in bk.pos if x[2] >= t - cfg.burst_seconds)
                if recent > r["max_burst"]:
                    r["max_burst"] = recent

        equity = self.balance + floating
        if equity > self.peak_equity:
            self.peak_equity = equity
        dd = self.peak_equity - equity
        if dd > self.max_dd:
            self.max_dd = dd
            self.max_dd_pct = dd / self.peak_equity * 100.0 if self.peak_equity > 0 else 0.0
        if t - self.last_curve_t >= 3600:
            self.equity_curve.append((t, round(equity, 2)))
            self.last_curve_t = t

        # 2. proteksi global
        any_open = any(bk.pos or bk.pend for bk in self.b)
        weekday = int((t // 86400 + 3) % 7)
        hour = int(t % 86400 // 3600)
        friday_close = cfg.friday_close_all and weekday == 4 and hour >= cfg.friday_close_hour
        if t < self.halt_until:
            if any_open:
                self._close_all(t, bid, ask, "HALT", False)
            return
        if cfg.max_drawdown_pct > 0 and floating < 0 and -floating >= self.balance * cfg.max_drawdown_pct / 100.0:
            self._close_all(t, bid, ask, "drawdown maksimal", True)
            return
        if cfg.daily_loss_limit > 0 and self.realized_day + floating <= -cfg.daily_loss_limit:
            self._close_all(t, bid, ask, "batas rugi harian", True)
            return
        if friday_close and any_open:
            self._close_all(t, bid, ask, "tutup akhir pekan", False)
            return

        # 3. exit per basket
        closed = False
        sl_pct_money = self.balance * cfg.basket_sl_pct / 100.0 if cfg.basket_sl_pct > 0 else 0.0
        for bk in self.b:
            if not bk.pos:
                bk.peak = 0.0
                continue
            p = self._profit(bk, bid, ask)
            units = self._volume(bk) / 0.01
            age = t - bk.pos[0][2]
            if bk.slot in (2, 3):
                if cfg.news_sl_per_minlot > 0 and p <= -cfg.news_sl_per_minlot * units:
                    self._close(bk, t, bid, ask, "cut loss berita")
                    closed = True
                    continue
                if cfg.news_max_hold_min > 0 and age >= cfg.news_max_hold_min * 60:
                    self._close(bk, t, bid, ask, "batas waktu berita")
                    closed = True
                    continue
                target, immediate = cfg.news_tp_per_minlot * units, not cfg.use_profit_lock
            elif bk.slot in (4, 5):
                if ((cfg.rev_sl_per_minlot > 0 and p <= -cfg.rev_sl_per_minlot * units) or
                        (sl_pct_money > 0 and p <= -sl_pct_money)):
                    self._close(bk, t, bid, ask, "cut loss reversion", is_loss=True)
                    closed = True
                    continue
                if cfg.rev_max_hold_min > 0 and age >= cfg.rev_max_hold_min * 60:
                    self._close(bk, t, bid, ask, "batas waktu reversion")
                    closed = True
                    continue
                # rezim berbalik jadi tren melawan basket: keluar di titik impas
                flipped = cfg.rev_regime_exit and regime == REGIME_TREND and self.er_dir == -bk.dir
                target = (cfg.recovery_tp_per_minlot if flipped else cfg.rev_tp_per_minlot) * units
                immediate = True
            else:
                if ((cfg.basket_sl_money > 0 and p <= -cfg.basket_sl_money) or
                        (sl_pct_money > 0 and p <= -sl_pct_money)):
                    self._close(bk, t, bid, ask, "cut loss", is_loss=True)
                    closed = True
                    continue
                recovery = ((cfg.recovery_after > 0 and len(bk.pos) >= cfg.recovery_after) or
                            (cfg.basket_age_hours > 0 and age >= cfg.basket_age_hours * 3600))
                if recovery:
                    target = max(cfg.recovery_tp_per_minlot * units, 0.01)
                elif cfg.tp_mode == 0:
                    target = cfg.tp_value
                elif cfg.tp_mode == 2:
                    target = self.balance * cfg.tp_value / 100.0
                else:
                    target = cfg.tp_value * units
                immediate = recovery or not cfg.use_profit_lock
            if immediate:
                if p >= target:
                    self._close(bk, t, bid, ask, "TP")
                    closed = True
                continue
            if bk.peak <= 0 and p >= target:
                bk.peak = p
            if bk.peak > 0:
                if p > bk.peak:
                    bk.peak = p
                if p <= bk.peak * (1.0 - cfg.lock_giveback_pct / 100.0):
                    self._close(bk, t, bid, ask, "kunci profit")
                    closed = True
        if closed:
            return

        # 4a. amankan profit sebelum berita
        if cfg.news_bank_profit and news_phase == NEWS_PRE:
            for bk in (self.b[0], self.b[1], self.b[4], self.b[5]):
                if bk.pos and self._profit(bk, bid, ask) > 0:
                    self._close(bk, t, bid, ask, "amankan sebelum berita")
                    self.counters["bank_news"] += 1

        # kondisi bersama
        sess_mult = (cfg.asia_step_mult, cfg.london_step_mult, cfg.ny_step_mult)[session]
        vol_mult = min(vol, cfg.vol_max_step_mult) if (cfg.vol_guard and vol >= cfg.vol_widen_ratio) else 1.0
        mult = max(sess_mult, 0.1) * vol_mult
        trend = self._trend() if (cfg.direction == "auto" or cfg.no_add_against_trend or cfg.rev_with_trend_only) else 0
        open_guard = cfg.open_guard_min > 0 and (
            cfg.london_open_gmt * 60 <= gmt_min < cfg.london_open_gmt * 60 + cfg.open_guard_min or
            cfg.ny_open_gmt * 60 <= gmt_min < cfg.ny_open_gmt * 60 + cfg.open_guard_min)
        ra = cfg.rollover_start_gmt // 100 * 60 + cfg.rollover_start_gmt % 100
        rb = cfg.rollover_end_gmt // 100 * 60 + cfg.rollover_end_gmt % 100
        rollover = cfg.rollover_guard and ra != rb and ((ra <= gmt_min < rb) if ra < rb else (gmt_min >= ra or gmt_min < rb))
        spread_bad = cfg.max_spread > 0 and spread > cfg.max_spread + self.tick * 0.5
        vol_block = cfg.vol_guard and vol >= cfg.vol_block_ratio
        in_hours = True
        if cfg.use_time_filter and cfg.start_hour != cfg.end_hour:
            in_hours = (cfg.start_hour <= hour < cfg.end_hour) if cfg.start_hour < cfg.end_hour else \
                (hour >= cfg.start_hour or hour < cfg.end_hour)
        session_ok = (cfg.trade_asia, cfg.trade_london, cfg.trade_ny)[session]
        friday_stop = cfg.friday_stop and weekday == 4 and hour >= cfg.friday_stop_hour
        daily_hit = cfg.daily_profit_target > 0 and self.realized_day >= cfg.daily_profit_target
        global_block = friday_close or news_phase != NEWS_NONE or rollover or vol_block or open_guard
        entry_block = daily_hit or not in_hours or not session_ok or friday_stop

        # 4b. tangga MOMENTUM (stop order, video 1)
        momentum_on = cfg.engine_mode != "reversion"
        adaptive = cfg.engine_mode == "adaptive"
        step = max(cfg.grid_step * mult, self.tick)
        start = max(cfg.start_distance * mult, self.tick)
        lot = cfg.fixed_lot
        for s in (0, 1):
            bk = self.b[s]
            if cfg.burst_max_fills > 0 and t >= bk.pause_until:
                recent = sum(1 for x in bk.pos if x[2] >= t - cfg.burst_seconds)
                if recent >= cfg.burst_max_fills:
                    bk.pause_until = t + cfg.burst_pause_sec
                    self.counters["burst"] += 1
            perm = 1
            if global_block or t < bk.pause_until:
                perm = -1
            elif spread_bad:
                perm = -1 if cfg.delete_pending_on_wide_spread else 0
            elif len(bk.pos) >= cfg.max_positions:
                perm = -1
            elif bk.pos and cfg.no_add_against_trend and (
                    trend == -bk.dir or (adaptive and regime == REGIME_TREND and self.er_dir == -bk.dir)):
                perm = -1
            elif not bk.pos:
                if cfg.direction == "buy":
                    dir_ok = bk.dir > 0
                elif cfg.direction == "sell":
                    dir_ok = bk.dir < 0
                elif adaptive and not cfg.adaptive_use_h1:
                    dir_ok = True               # arah ditentukan Efficiency Ratio saja
                else:
                    dir_ok = trend == bk.dir
                # adaptif: momentum hanya saat rezim TREN dan searah gerak yang sedang terjadi
                regime_ok = not adaptive or (regime == REGIME_TREND and self.er_dir == bk.dir)
                if (not momentum_on or not dir_ok or not regime_ok or (cfg.one_basket_only and self._others_busy(s))
                        or entry_block or t < bk.cooldown_until):
                    perm = -1
            if perm < 0:
                bk.pend = []
                continue
            if perm == 0:
                continue
            if not bk.pend:
                count = min(cfg.grid_levels, cfg.max_positions - len(bk.pos))
                if count > 0:
                    self._place(bk, count, bid, ask, step, start, lot)
            else:
                self._trail(bk, t, bid, ask, step, start, cfg.trail_step)

        # 4c. tangga REVERSION (limit order, video 2)
        rev_on = cfg.engine_mode != "momentum"
        z = self._zscore(mid)
        rev_dir = -1 if z >= cfg.rev_z_entry else (1 if z <= -cfg.rev_z_entry else 0)
        rbase = cfg.rev_step
        if cfg.rev_step_atr > 0 and self.atr_m5 > 0:
            rbase = max(rbase, self.atr_m5 * cfg.rev_step_atr)
        rstep = max(rbase * mult, self.tick)
        rstart = max(max(cfg.rev_start, rbase) * mult, self.tick)
        for s in (4, 5):
            bk = self.b[s]
            flipped = cfg.rev_regime_exit and regime == REGIME_TREND and self.er_dir == -bk.dir
            perm = 1
            if global_block:
                perm = -1
            elif spread_bad:
                perm = -1 if cfg.delete_pending_on_wide_spread else 0
            elif bk.pos and flipped:
                perm = -1                       # rezim berbalik: stop tambah posisi
            elif not bk.pos:
                regime_ok = cfg.engine_mode == "reversion" or regime == REGIME_RANGE
                trend_ok = not cfg.rev_with_trend_only or trend == bk.dir
                if (not rev_on or not regime_ok or rev_dir != bk.dir or not trend_ok
                        or (cfg.one_basket_only and self._others_busy(s)) or entry_block or t < bk.cooldown_until):
                    perm = -1
            if perm < 0:
                bk.pend = []
                continue
            if perm == 0 or bk.pos:
                continue                        # tangga limit statis selama basket berjalan
            if not bk.pend:
                self._place(bk, cfg.rev_levels, bid, ask, rstep, rstart, cfg.fixed_lot)
            else:
                self._trail(bk, t, bid, ask, rstep, rstart, rstep)

        # 4d. tangga berita
        for s in (2, 3):
            bk = self.b[s]
            if not bk.pend:
                continue
            if t > self.ride_until:
                bk.pend = []
            elif spread <= cfg.news_max_spread:
                self._trail(bk, t, bid, ask, self.news_step, self.news_start, cfg.trail_step)

        # 4e. penunggang berita
        if (cfg.use_news_filter and cfg.news_ride and self.ev_time and not self.ride_done
                and t >= self.ev_time + cfg.news_settle_sec):
            if t > self.ride_until or self.ref_price <= 0 or self.ref_atr <= 0:
                self.ride_done = True
            elif spread <= cfg.news_max_spread:
                impulse = mid - self.ref_price
                if abs(impulse) >= cfg.news_impulse_atr * self.ref_atr:
                    d = 1 if impulse > 0 else -1
                    bk = self.b[2 if d > 0 else 3]
                    if not bk.pos and not bk.pend:
                        self.news_step = max(self.ref_atr * cfg.news_step_atr, self.tick)
                        self.news_start = max(self.ref_atr * cfg.news_start_atr, self.tick)
                        self.ride_done = True   # satu tangga per berita
                        self._place(bk, cfg.news_levels, bid, ask, self.news_step, self.news_start,
                                    cfg.fixed_lot * cfg.news_lot_mult)
                        self.ride_log.append((self.ev_time, self.ev_name, d, round(impulse, 2)))

    def finish(self, t, bid, ask):
        for bk in self.b:
            if bk.pos:
                self._close(bk, t, bid, ask, "akhir data")


def run_sim(cfg, ticks, news, gmt_offset_h, contract, balance, tick_size):
    eng = Engine(cfg, news, gmt_offset_h, contract, balance, tick_size)
    last = None
    n = 0
    for t, bid, ask in ticks:
        eng.on_tick(t, bid, ask)
        last = (t, bid, ask)
        n += 1
    if last:
        eng.finish(*last)
    eng.n_ticks = n
    return eng


# ---------------------------------------------------------------------------
# Analisis & laporan
# ---------------------------------------------------------------------------

def ts_str(t):
    return _time.strftime("%Y-%m-%d %H:%M", _time.gmtime(t))


def summarize(eng):
    recs = eng.records
    wins = [r["result"] for r in recs if r["result"] > 0]
    losses = [r["result"] for r in recs if r["result"] <= 0]
    gross_win, gross_loss = sum(wins), -sum(losses)
    net = eng.balance - eng.start_balance
    return {
        "net": round(net, 2),
        "baskets": len(recs),
        "win_rate": round(len(wins) / len(recs) * 100, 1) if recs else 0.0,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0),
        "max_dd": round(eng.max_dd, 2),
        "max_dd_pct": round(eng.max_dd_pct, 2),
        "recovery_factor": round(net / eng.max_dd, 2) if eng.max_dd > 0 else 0.0,
        "worst_mae": round(min((r["mae"] for r in recs), default=0.0), 2),
        "avg_result": round(net / len(recs), 2) if recs else 0.0,
        "halts": eng.counters["halt"],
        "bursts": eng.counters["burst"],
        "news_rides": len(eng.ride_log),
    }


def group_stats(recs, keyfn):
    g = defaultdict(list)
    for r in recs:
        g[keyfn(r)].append(r)
    out = {}
    for k, rs in g.items():
        res = [r["result"] for r in rs]
        out[k] = {
            "n": len(rs), "net": round(sum(res), 2), "avg": round(sum(res) / len(rs), 2),
            "win": round(sum(1 for x in res if x > 0) / len(rs) * 100, 1),
            "worst_mae": round(min(r["mae"] for r in rs), 2),
            "avg_pos": round(sum(r["positions"] for r in rs) / len(rs), 1),
        }
    return out


def table(rows, headers):
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def mae_whatif(recs):
    main = [r for r in recs if r["engine"] == "MOMENTUM"]
    base = sum(r["result"] for r in main)
    rows = []
    for x in (25, 50, 100, 150, 200, 300, 500, 800, 1200, 2000):
        cut = [r for r in main if r["mae"] <= -x]
        net = sum(-x if r["mae"] <= -x else r["result"] for r in main)
        rows.append([x, len(cut), round(net, 2), round(net - base, 2)])
    return rows


def findings(eng, cfg, s):
    recs = eng.records
    tips = []
    if not recs:
        return ["Tidak ada basket yang terbentuk - periksa format data / zona waktu / filter."]
    by_sess = group_stats(recs, lambda r: r["session"])
    for name, st in by_sess.items():
        if st["n"] >= 10 and st["net"] < 0:
            key = {"ASIA": "InpTradeAsia", "LONDON": "InpTradeLondon", "NEW YORK": "InpTradeNY"}[name]
            mult = {"ASIA": "InpAsiaStepMult", "LONDON": "InpLondonStepMult", "NEW YORK": "InpNYStepMult"}[name]
            tips.append("Sesi %s merugi (%d basket, net %.2f, MAE terburuk %.2f). Coba %s=1.3-1.6 atau %s=false."
                        % (name, st["n"], st["net"], st["worst_mae"], mult, key))
    news_r = [r for r in recs if r["news"] and not r["slot"].startswith("N-")]
    calm_r = [r for r in recs if not r["news"]]
    if news_r:
        avg_n = sum(r["result"] for r in news_r) / len(news_r)
        avg_c = sum(r["result"] for r in calm_r) / len(calm_r) if calm_r else 0.0
        if avg_n < avg_c:
            tips.append("Basket utama yang tersentuh jendela berita rata-rata %.2f vs normal %.2f. "
                        "Perlebar InpNewsBeforeMin/InpNewsAfterMin atau aktifkan InpNewsBankProfit." % (avg_n, avg_c))
    hi = [r for r in recs if r["vol_ratio"] >= cfg.vol_widen_ratio and not r["slot"].startswith("N-")]
    if len(hi) >= 5:
        avg_hi = sum(r["result"] for r in hi) / len(hi)
        if avg_hi < s["avg_result"]:
            tips.append("Basket yang dibuka saat volatilitas tinggi (>= x%.1f) rata-rata %.2f (lebih buruk dari umum %.2f). "
                        "Turunkan InpVolBlockRatio atau naikkan InpVolMaxStepMult." % (cfg.vol_widen_ratio, avg_hi, s["avg_result"]))
    burst = [r for r in recs if r["max_burst"] >= 4]
    if len(burst) >= 5:
        avg_b = sum(r["result"] for r in burst) / len(burst)
        tips.append("%d basket mengalami >= 4 stop terisi dalam %d detik (rata-rata %.2f, MAE terburuk %.2f). %s"
                    % (len(burst), cfg.burst_seconds, avg_b, min(r["mae"] for r in burst),
                       "Turunkan InpBurstMaxFills." if avg_b < 0 else "Burst justru menguntungkan: momentum sehat."))
    best = max(mae_whatif(recs), key=lambda r: r[2]) if recs else None
    if best and best[3] > 0:
        tips.append("Analisis MAE: memotong basket di -%d USD (lot %.2f) diperkirakan memperbaiki net %+.2f. "
                    "Setel InpBasketSLMoney=%d (atau InpBasketSLPct setara) lalu replay ulang untuk konfirmasi."
                    % (best[0], cfg.fixed_lot, best[3], best[0]))
    deep = sorted(recs, key=lambda r: r["mae"])[:max(1, len(recs) // 50)]
    if deep:
        worst = deep[0]["mae"]
        tips.append("MAE terburuk %.2f USD (lot %.2f). Pastikan saldo sanggup menahan >= 2x angka ini; "
                    "InpMaxDrawdownPct saat ini %.0f%%." % (worst, cfg.fixed_lot, cfg.max_drawdown_pct))
    ge = group_stats(recs, lambda r: (r["engine"], r["regime"]))
    for (engine, regime), st in sorted(ge.items()):
        if st["n"] >= 10 and st["net"] < 0 and engine in ("MOMENTUM", "REVERSION"):
            hint = ("naikkan InpERRange agar MOMENTUM tidak dibuka saat pasar datar" if engine == "MOMENTUM"
                    else "turunkan InpERRange / naikkan InpRevZEntry agar REVERSION hanya di pasar benar-benar datar")
            tips.append("Mesin %s merugi di rezim %s (%d basket, net %.2f): %s." % (engine, regime, st["n"], st["net"], hint))
    rides = [r for r in recs if r["slot"].startswith("N-")]
    if rides:
        net_r = sum(r["result"] for r in rides)
        wr = sum(1 for r in rides if r["result"] > 0) / len(rides) * 100
        tips.append("Penunggang berita: %d basket, net %.2f, win %.0f%%. %s"
                    % (len(rides), net_r, wr,
                       "Pertahankan." if net_r > 0 else "Naikkan InpNewsImpulseATR (mis. 2.0-2.5) atau matikan InpNewsRide."))
    by_slot = group_stats([r for r in recs if not r["slot"].startswith("N-")], lambda r: r["slot"])
    if "BUY" in by_slot and "SELL" in by_slot:
        b, sl = by_slot["BUY"], by_slot["SELL"]
        if b["net"] * sl["net"] < 0:
            bad = "SELL" if sl["net"] < 0 else "BUY"
            tips.append("Arah %s merugi pada data ini. Pertimbangkan InpDirection=%s atau perpanjang InpTrendEMA."
                        % (bad, "BUY ONLY (0)" if bad == "SELL" else "SELL ONLY (1)"))
    return tips


def write_report(out_dir, label, eng, cfg, s, news_info, compare_rows=None, sweep_rows=None, wf_rows=None):
    recs = eng.records
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "basket_%s.csv" % label), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["slot", "buka", "tutup", "sesi", "posisi", "lot", "hasil", "mae", "mfe", "burst_maks",
                    "rasio_vol", "berita", "alasan_tutup", "slip_total"])
        for r in recs:
            w.writerow([r["slot"], ts_str(r["open_t"]), ts_str(r["close_t"]), r["session"], r["positions"],
                        round(r["volume"], 2), round(r["result"], 2), round(r["mae"], 2), round(r["mfe"], 2),
                        r["max_burst"], r["vol_ratio"], int(r["news"]), r["reason"], round(r["slip"], 2)])
    with open(os.path.join(out_dir, "ekuitas_%s.csv" % label), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["waktu", "ekuitas"])
        for t, e in eng.equity_curve:
            w.writerow([ts_str(t), e])

    L = ["# Laporan Forensik EA SAPU JAGAD — %s" % label, ""]
    L.append("Data: %d tick, %s s/d %s (waktu server). %s" % (
        eng.n_ticks, ts_str(eng.equity_curve[0][0]) if eng.equity_curve else "-",
        ts_str(eng.equity_curve[-1][0]) if eng.equity_curve else "-", news_info))
    L.append("")
    L.append("## Ringkasan")
    L.append(table([[k, v] for k, v in s.items()], ["Metrik", "Nilai"]))
    if compare_rows:
        L.append("")
        L.append("## Perbandingan: tiruan video 1 (momentum), video 2 (reversion), dan SAPU JAGAD")
        L.append(table(compare_rows, ["Konfigurasi", "Net", "Basket", "Win%", "PF", "Max DD", "DD%", "RF", "MAE terburuk"]))
    L.append("")
    L.append("## Per sesi (saat stop pertama terisi)")
    gs = group_stats(recs, lambda r: r["session"])
    L.append(table([[k, v["n"], v["net"], v["avg"], v["win"], v["worst_mae"], v["avg_pos"]] for k, v in sorted(gs.items())],
                   ["Sesi", "Basket", "Net", "Rata2", "Win%", "MAE terburuk", "Rata2 posisi"]))
    L.append("")
    L.append("## Per jam (GMT)")
    off = eng.off
    gh = group_stats(recs, lambda r: int((r["open_t"] - off) % 86400 // 3600))
    L.append(table([[k, v["n"], v["net"], v["avg"], v["win"], v["worst_mae"]] for k, v in sorted(gh.items())],
                   ["Jam", "Basket", "Net", "Rata2", "Win%", "MAE terburuk"]))
    L.append("")
    L.append("## Berita vs normal")
    gn = group_stats(recs, lambda r: ("tangga berita" if r["slot"].startswith("N-") else
                                      ("utama, sekitar berita" if r["news"] else "utama, normal")))
    L.append(table([[k, v["n"], v["net"], v["avg"], v["win"], v["worst_mae"]] for k, v in sorted(gn.items())],
                   ["Kelompok", "Basket", "Net", "Rata2", "Win%", "MAE terburuk"]))
    L.append("")
    L.append("## Per mesin & rezim pasar (bukti edge pengalih rezim)")
    L.append("Rezim diukur dengan Efficiency Ratio M1 saat stop/limit pertama terisi. Pengalih rezim punya edge "
             "bila MOMENTUM lebih baik di TREN dan REVERSION lebih baik di RANGE.")
    ge = group_stats(recs, lambda r: (r["engine"], r["regime"]))
    L.append(table([[k[0], k[1], v["n"], v["net"], v["avg"], v["win"], v["worst_mae"]] for k, v in sorted(ge.items())],
                   ["Mesin", "Rezim", "Basket", "Net", "Rata2", "Win%", "MAE terburuk"]))
    L.append("")
    L.append("## Per arah / slot")
    gsl = group_stats(recs, lambda r: r["slot"])
    L.append(table([[k, v["n"], v["net"], v["avg"], v["win"], v["worst_mae"]] for k, v in sorted(gsl.items())],
                   ["Slot", "Basket", "Net", "Rata2", "Win%", "MAE terburuk"]))
    L.append("")
    L.append("## 15 basket terburuk (bahan forensik)")
    worst = sorted(recs, key=lambda r: r["result"])[:15]
    L.append(table([[r["slot"], ts_str(r["open_t"]), ts_str(r["close_t"]), r["session"], r["positions"],
                     round(r["result"], 2), round(r["mae"], 2), r["max_burst"], r["vol_ratio"],
                     "ya" if r["news"] else "-", r["reason"]] for r in worst],
                   ["Slot", "Buka", "Tutup", "Sesi", "Pos", "Hasil", "MAE", "Burst", "Vol", "Berita", "Alasan"]))
    L.append("")
    L.append("## Analisis MAE: berapa batas cut loss basket yang optimal?")
    L.append("Perkiraan net bila setiap basket utama dipotong saat floating menyentuh -X "
             "(mengabaikan efek entry ulang; pakai sebagai arah, lalu konfirmasi dengan replay).")
    mae_rows = mae_whatif(recs)
    L.append(table(mae_rows, ["Cut loss X (USD)", "Basket terpotong", "Net perkiraan", "Selisih vs tanpa cut"]))
    L.append("")
    L.append("## Temuan kelemahan & rekomendasi")
    for tip in findings(eng, cfg, s):
        L.append("- " + tip)
    if sweep_rows:
        L.append("")
        L.append("## Pencarian parameter (urut recovery factor)")
        L.append(table(sweep_rows, ["Mesin", "Step", "Start", "Level", "TP/0.01", "Net", "Max DD", "RF", "Basket", "Win%"]))
    if wf_rows:
        L.append("")
        L.append("## Walk-forward (anti overfitting)")
        L.append("Parameter dicari HANYA di data awal (in-sample), lalu diuji di data akhir yang belum pernah dilihat "
                 "(out-of-sample). Edge yang asli harus tetap positif di kolom OOS.")
        L.append(table(wf_rows, ["Konfigurasi", "IS net", "IS DD", "IS RF", "OOS net", "OOS DD", "OOS RF", "OOS basket"]))
    L.append("")
    L.append("## Catatan metodologi")
    L.append("- Replay ini meniru logika EA, bukan pengganti Strategy Tester MT5 (eksekusi, swap, margin, "
             "dan slippage broker nyata bisa berbeda).")
    L.append("- Data bar diubah jadi 4 tick per bar (O-L-H-C / O-H-L-C); hasil tick asli lebih akurat.")
    L.append("- Bila jadwal berita dideteksi dari kejutan harga, hanya berita yang *menggerakkan* harga yang "
             "tercatat. Ini bias ke berita besar; gunakan file kalender untuk hasil yang jujur.")
    L.append("- Kinerja masa lalu tidak menjamin hasil masa depan.")
    path = os.path.join(out_dir, "laporan_forensik_%s.md" % label)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    return path


def compare_row(label, s):
    return [label, s["net"], s["baskets"], s["win_rate"], s["profit_factor"], s["max_dd"], s["max_dd_pct"],
            s["recovery_factor"], s["worst_mae"]]


# --- pencarian parameter (multiproses) -------------------------------------
_G = {}


def _sweep_init(ticks, news, args_tuple):
    _G["ticks"], _G["news"], _G["args"] = ticks, news, args_tuple


def _sweep_one(cfg):
    gmt, contract, balance, tick = _G["args"]
    eng = run_sim(cfg, _G["ticks"], _G["news"], gmt, contract, balance, tick)
    return cfg, summarize(eng)


def run_sweep(base, ticks, news, args, workers):
    grid = []
    for engine in ("momentum", "adaptive"):
        for step in (0.3, 0.5, 0.8):
            for start in (1.0, 2.0, 3.0):
                for levels in (5, 8):
                    for tp in (0.7, 1.2):
                        grid.append(replace(base, engine_mode=engine, grid_step=step, start_distance=start,
                                            grid_levels=levels, tp_value=tp))
    argt = (args.gmt_offset, args.contract, args.balance, args.tick_size)
    print("Sweep %d kombinasi dengan %d proses..." % (len(grid), workers))
    results = []
    if workers > 1:
        import multiprocessing as mp
        with mp.Pool(workers, initializer=_sweep_init, initargs=(ticks, news, argt)) as pool:
            for i, res in enumerate(pool.imap_unordered(_sweep_one, grid), 1):
                results.append(res)
                if i % 10 == 0 or i == len(grid):
                    print("  sweep %d/%d" % (i, len(grid)), flush=True)
    else:
        _sweep_init(ticks, news, argt)
        for i, cfg in enumerate(grid, 1):
            results.append(_sweep_one(cfg))
            if i % 10 == 0 or i == len(grid):
                print("  sweep %d/%d" % (i, len(grid)), flush=True)
    min_baskets = max(10, int(sum(r[1]["baskets"] for r in results) / len(results) * 0.3))
    ok = [r for r in results if r[1]["baskets"] >= min_baskets and r[1]["net"] > 0]
    ok.sort(key=lambda r: (r[1]["recovery_factor"], r[1]["net"]), reverse=True)
    return ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_date(s):
    return parse_dt(s + (" 00:00" if len(s) <= 10 else "")) if s else None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Forensik & replay EA SAPU JAGAD pada data XAUUSD")
    ap.add_argument("--data", nargs="+", required=True, help="file atau folder data (boleh lebih dari satu)")
    ap.add_argument("--symbol-filter", default=r"xau|gold", help="regex nama file (kosongkan '' untuk semua)")
    ap.add_argument("--news", help="file CSV jadwal berita (waktu GMT)")
    ap.add_argument("--news-currencies", default="USD")
    ap.add_argument("--news-medium", action="store_true")
    ap.add_argument("--infer-k", type=float, default=5.0, help="ambang deteksi kejutan (x ATR60) bila tanpa file berita")
    ap.add_argument("--gmt-offset", type=float, default=0, help="selisih jam waktu data/server terhadap GMT")
    ap.add_argument("--point", type=float, default=0.01, help="nilai 1 point (2 digit: 0.01, 3 digit: 0.001)")
    ap.add_argument("--tick-size", type=float, default=0.01)
    ap.add_argument("--spread", type=float, default=0.20, help="spread bawaan bila data tidak punya spread")
    ap.add_argument("--contract", type=float, default=100.0, help="ukuran kontrak (oz per 1.00 lot)")
    ap.add_argument("--balance", type=float, default=10000.0)
    ap.add_argument("--from", dest="date_from")
    ap.add_argument("--to", dest="date_to")
    ap.add_argument("--set", help="file .set EA untuk konfigurasi")
    ap.add_argument("--preset", choices=sorted(PRESETS), default="sapujagad")
    ap.add_argument("--compare", action="store_true", help="bandingkan dengan tiruan video asli")
    ap.add_argument("--sweep", action="store_true", help="cari parameter terbaik (butuh RAM untuk data)")
    ap.add_argument("--walk-forward", type=float, metavar="FRAKSI",
                    help="mis. 0.7: cari parameter di 70%% data awal, uji di 30%% sisanya")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--out", default="hasil_forensik")
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)

    files = discover_files(args.data, args.symbol_filter)
    infos = []
    print("Memeriksa %d file..." % len(files))
    for f in files:
        info = inspect_file(f)
        if info.ok:
            infos.append(info)
            print("  OK  %-5s %s (mulai %s)" % (info.kind, f, ts_str(info.first_ts)))
        else:
            print("  --  dilewati %s: %s" % (f, info.reason))
    if not infos:
        print("Tidak ada file data yang bisa dibaca.")
        return 2

    src = TickSource(infos, args.point, args.spread, parse_date(args.date_from), parse_date(args.date_to))
    cache = None
    if args.sweep or args.walk_forward:
        print("Memuat data ke memori untuk sweep / walk-forward...")
        cache = list(src)
        source = cache
    else:
        source = src

    if args.news:
        news = load_news_csv(args.news, args.news_currencies, args.news_medium, args.gmt_offset)
        news_info = "Berita: %d jadwal dari %s." % (len(news), os.path.basename(args.news))
    else:
        news, nbars = infer_news(source, args.gmt_offset, args.infer_k)
        news_info = "Berita: %d kejutan terdeteksi dari %d bar M1 (tanpa file kalender)." % (len(news), nbars)
    print(news_info)

    cfg = replace(Config(), **PRESETS[args.preset])
    if args.set:
        cfg = load_set_file(args.set, cfg)
    label = os.path.splitext(os.path.basename(args.set))[0] if args.set else args.preset

    t0 = _time.time()
    eng = run_sim(cfg, source, news, args.gmt_offset, args.contract, args.balance, args.tick_size)
    s = summarize(eng)
    print("Replay %s selesai dalam %.1f detik: net %.2f, DD %.2f (%.1f%%), %d basket"
          % (label, _time.time() - t0, s["net"], s["max_dd"], s["max_dd_pct"], s["baskets"]))

    compare_rows = None
    if args.compare:
        rows = [compare_row(label, s)]
        others = [p for p in ("video", "video2", "sapujagad") if p != label]
        for p in others:
            e2 = run_sim(replace(Config(), **PRESETS[p]), source, news, args.gmt_offset, args.contract,
                         args.balance, args.tick_size)
            s2 = summarize(e2)
            rows.append(compare_row(p, s2))
            write_report(args.out, p, e2, replace(Config(), **PRESETS[p]), s2, news_info)
            print("Replay %s: net %.2f, DD %.2f (%.1f%%)" % (p, s2["net"], s2["max_dd"], s2["max_dd_pct"]))
        compare_rows = rows

    sweep_rows = None
    if args.sweep:
        ranked = run_sweep(cfg, cache, news, args, args.workers)
        sweep_rows = [[c.engine_mode, c.grid_step, c.start_distance, c.grid_levels, c.tp_value, r["net"], r["max_dd"],
                       r["recovery_factor"], r["baskets"], r["win_rate"]] for c, r in ranked[:10]]
        if ranked:
            best = ranked[0][0]
            write_set_file(os.path.join(args.out, "EA_SAPU_JAGAD_terbaik.set"), best)
            print("Parameter terbaik disimpan ke %s" % os.path.join(args.out, "EA_SAPU_JAGAD_terbaik.set"))

    wf_rows = None
    if args.walk_forward:
        import bisect
        times = [x[0] for x in cache]
        split_t = times[0] + (times[-1] - times[0]) * args.walk_forward
        i = bisect.bisect_left(times, split_t)
        is_ticks, oos_ticks = cache[:i], cache[i:]
        print("Walk-forward: in-sample s/d %s, out-of-sample %d tick" % (ts_str(split_t), len(oos_ticks)))
        ranked = run_sweep(cfg, is_ticks, news, args, args.workers)
        argt = (args.gmt_offset, args.contract, args.balance, args.tick_size)
        candidates = [("default " + label, cfg, None)] + [
            ("#%d %s step%.2g start%.2g lvl%d tp%.2g" % (k + 1, c.engine_mode, c.grid_step, c.start_distance,
                                                         c.grid_levels, c.tp_value), c, r)
            for k, (c, r) in enumerate(ranked[:5])]
        wf_rows = []
        for name, c, r_is in candidates:
            if r_is is None:
                r_is = summarize(run_sim(c, is_ticks, news, *argt))
            r_oos = summarize(run_sim(c, oos_ticks, news, *argt))
            wf_rows.append([name, r_is["net"], r_is["max_dd"], r_is["recovery_factor"], r_oos["net"],
                            r_oos["max_dd"], r_oos["recovery_factor"], r_oos["baskets"]])
            print("  %-40s IS %9.2f | OOS %9.2f" % (name, r_is["net"], r_oos["net"]))

    path = write_report(args.out, label, eng, cfg, s, news_info, compare_rows, sweep_rows, wf_rows)
    with open(os.path.join(args.out, "ringkasan_%s.json" % label), "w", encoding="utf-8") as fh:
        json.dump({"config": asdict(cfg), "summary": s, "news_rides": eng.ride_log[:200]}, fh, indent=2, default=str)
    print("Laporan: %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
