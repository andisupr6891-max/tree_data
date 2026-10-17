import datetime as dt

import numpy as np
import pandas as pd
import pytest

from gcquant import core


def test_spesifikasi_kontrak():
    assert core.SPECS["GC"].tick_value == pytest.approx(10.0)
    assert core.SPECS["MGC"].tick_value == pytest.approx(1.0)
    assert core.SPECS["OG"].option_of == "GC"
    # bolak-balik GC: 2 x 2,50 komisi + 1 tick spread ($10) = $15
    assert core.DEFAULT_COSTS["GC"].round_turn_usd(core.SPECS["GC"]) == pytest.approx(15.0)


def test_libur_cme_2025():
    h = core.cme_holidays(2025)
    for d in ["2025-01-01", "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26",
              "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25"]:
        assert dt.date.fromisoformat(d) in h
    assert not core.is_business_day(dt.date(2025, 4, 18))     # Jumat Agung
    assert core.is_business_day(dt.date(2025, 4, 17))


def test_libur_pengamatan_akhir_pekan():
    # 4 Juli 2026 jatuh Sabtu → diamati Jumat 3 Juli
    assert dt.date(2026, 7, 3) in core.cme_holidays(2026)
    # Natal 2022 jatuh Minggu → diamati Senin 26 Desember
    assert dt.date(2022, 12, 26) in core.cme_holidays(2022)


def test_hari_kerja_dan_penambahan():
    assert core.add_business_days(dt.date(2025, 12, 24), 1) == dt.date(2025, 12, 26)
    assert core.add_business_days(dt.date(2025, 12, 26), -1) == dt.date(2025, 12, 24)
    bd = core.business_days_in_month(2025, 12)
    assert bd[-3] == dt.date(2025, 12, 29)      # hari terakhir perdagangan GCZ5


def test_simbol():
    assert core.futures_symbol("GC", 2026, 12) == "GCZ6"
    assert core.futures_symbol("GC", 2026, 12, digits=2) == "GCZ26"
    assert core.parse_futures_symbol("GCZ6", 2026) == ("GC", 2026, 12)
    assert core.parse_futures_symbol("MGCG7", 2026) == ("MGC", 2027, 2)
    assert core.parse_futures_symbol("GCZ26") == ("GC", 2026, 12)
    assert core.parse_futures_symbol("1OZM6", 2026) == ("1OZ", 2026, 6)


def test_tanggal_perdagangan_cme():
    # Minggu 17:30 CT (22:30 UTC, CDT) → trade date Senin
    assert core.cme_trade_date("2026-10-18T22:30:00Z") == dt.date(2026, 10, 19)
    # Senin 16:59 CT → masih Senin; Senin 17:01 CT → Selasa
    assert core.cme_trade_date("2026-10-19T21:59:00Z") == dt.date(2026, 10, 19)
    assert core.cme_trade_date("2026-10-19T22:01:00Z") == dt.date(2026, 10, 20)
    # Jumat setelah 17:00 CT → Senin berikutnya
    assert core.cme_trade_date("2026-10-23T22:30:00Z") == dt.date(2026, 10, 26)


def test_konversi_waktu_ns():
    n = core.to_ns("2026-01-01")
    assert n == 1767225600000000000
    assert core.ns_to_ts(n) == pd.Timestamp("2026-01-01", tz="UTC")
    arr = core.to_ns(pd.date_range("2026-01-01", periods=3, freq="1min", tz="UTC", unit="us"))
    assert arr.dtype == np.int64 and arr[1] - arr[0] == 60 * core.NS_PER_SEC
    idx = core.ns_to_ts(arr)
    assert str(idx.dtype) == "datetime64[ns, UTC]"


def test_ensure_utc_index_mengurutkan():
    df = pd.DataFrame({"x": [2, 1]}, index=pd.to_datetime(["2026-01-02", "2026-01-01"]))
    out = core.ensure_utc_index(df)
    assert out.index.tz is not None and list(out["x"]) == [1, 2]
