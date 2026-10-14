# Laporan Forensik EA SAPU JAGAD — video2

Data: 4686640 tick, 2015-01-01 23:00 s/d 2018-06-19 10:00 (waktu server). Tanpa file kalender: perisai & penunggang berita NONAKTIF di replay (anti mengintip data). 901 kejutan harga terdeteksi dari 1171660 bar M1, dipakai hanya sebagai label laporan.

## Ringkasan
| Metrik | Nilai |
|---|---|
| net | 4223.35 |
| baskets | 1484 |
| win_rate | 99.9 |
| profit_factor | 2.13 |
| max_dd | 6617.94 |
| max_dd_pct | 38.31 |
| recovery_factor | 0.64 |
| worst_mae | -6616.95 |
| avg_result | 2.85 |
| halts | 0 |
| bursts | 0 |
| news_rides | 0 |
| data_holes | 718 |

## Kestabilan per tahun
| Tahun | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|
| 2015 | 1334 | 7009.96 | 5.25 | 100.0 | -3937.65 |
| 2016 | 137 | 847.17 | 6.18 | 100.0 | -6616.95 |
| 2017 | 12 | 111.57 | 9.3 | 100.0 | -185.85 |
| 2018 | 1 | -3745.35 | -3745.35 | 0.0 | -6349.65 |

## Per sesi (saat stop pertama terisi)
| Sesi | Basket | Net | Rata2 | Win% | MAE terburuk | Rata2 posisi |
|---|---|---|---|---|---|---|
| ASIA | 273 | 1295.59 | 4.75 | 100.0 | -1367.25 | 6.3 |
| LONDON | 454 | 2605.16 | 5.74 | 100.0 | -2608.95 | 6.2 |
| NEW YORK | 757 | 322.6 | 0.43 | 99.9 | -6616.95 | 6.8 |

## Per jam (GMT)
| Jam | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|
| 1 | 79 | 452.55 | 5.73 | 100.0 | -1367.25 |
| 2 | 27 | 79.6 | 2.95 | 100.0 | -25.22 |
| 3 | 31 | 87.61 | 2.83 | 100.0 | -27.93 |
| 4 | 17 | 105.87 | 6.23 | 100.0 | -363.75 |
| 5 | 36 | 234.5 | 6.51 | 100.0 | -637.05 |
| 6 | 38 | 116.37 | 3.06 | 100.0 | -109.06 |
| 7 | 83 | 341.08 | 4.11 | 100.0 | -185.85 |
| 8 | 64 | 280.7 | 4.39 | 100.0 | -2608.95 |
| 9 | 66 | 312.77 | 4.74 | 100.0 | -459.45 |
| 10 | 45 | 192.9 | 4.29 | 100.0 | -57.1 |
| 11 | 73 | 401.29 | 5.5 | 100.0 | -808.95 |
| 12 | 123 | 1076.42 | 8.75 | 100.0 | -2411.85 |
| 13 | 174 | 931.24 | 5.35 | 100.0 | -1453.35 |
| 14 | 200 | 927.94 | 4.64 | 100.0 | -379.05 |
| 15 | 131 | -2956.68 | -22.57 | 99.2 | -6616.95 |
| 16 | 70 | 323.82 | 4.63 | 100.0 | -684.45 |
| 17 | 64 | 318.91 | 4.98 | 100.0 | -1683.45 |
| 18 | 48 | 355.75 | 7.41 | 100.0 | -670.05 |
| 19 | 42 | 272.06 | 6.48 | 100.0 | -1045.65 |
| 20 | 28 | 149.56 | 5.34 | 100.0 | -383.85 |
| 22 | 14 | 67.36 | 4.81 | 100.0 | -43.35 |
| 23 | 31 | 151.73 | 4.89 | 100.0 | -185.85 |

## Berita vs normal
| Kelompok | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|
| utama, normal | 1484 | 4223.35 | 2.85 | 99.9 | -6616.95 |

## Per mesin & rezim pasar (bukti edge pengalih rezim)
Rezim diukur dengan Efficiency Ratio M1 saat stop/limit pertama terisi. Pengalih rezim punya edge bila MOMENTUM lebih baik di TREN dan REVERSION lebih baik di RANGE.
| Mesin | Rezim | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|---|
| REVERSION | NETRAL | 599 | 3247.78 | 5.42 | 100.0 | -6616.95 |
| REVERSION | RANGE | 682 | -86.14 | -0.13 | 99.9 | -6349.65 |
| REVERSION | TREN | 203 | 1061.71 | 5.23 | 100.0 | -1683.45 |

## Per arah / slot
| Slot | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|
| R-BUY | 743 | 4179.28 | 5.62 | 100.0 | -2608.95 |
| R-SELL | 741 | 44.07 | 0.06 | 99.9 | -6616.95 |

## 15 basket terburuk (bahan forensik)
| Slot | Buka | Tutup | Sesi | Pos | Hasil | MAE | Burst | Vol | Berita | Alasan |
|---|---|---|---|---|---|---|---|---|---|---|
| R-SELL | 2017-01-03 15:36 | 2018-06-19 10:59 | NEW YORK | 30 | -3745.35 | -6349.65 | 5 | 1.0 | - | akhir data |
| R-SELL | 2015-06-08 14:10 | 2015-06-08 14:15 | NEW YORK | 1 | 0.5 | -0.32 | 1 | 1.0 | - | TP |
| R-SELL | 2015-06-22 18:37 | 2015-06-22 18:39 | NEW YORK | 1 | 0.5 | -0.31 | 1 | 1.0 | - | TP |
| R-BUY | 2015-06-30 12:56 | 2015-06-30 13:00 | LONDON | 1 | 0.5 | -0.49 | 1 | 1.0 | - | TP |
| R-BUY | 2015-07-09 03:25 | 2015-07-09 03:41 | ASIA | 1 | 0.5 | -0.41 | 1 | 1.0 | - | TP |
| R-BUY | 2015-07-15 07:00 | 2015-07-15 07:07 | LONDON | 1 | 0.5 | -0.44 | 1 | 1.0 | - | TP |
| R-SELL | 2015-08-31 09:52 | 2015-08-31 10:03 | LONDON | 1 | 0.5 | -0.29 | 1 | 1.0 | - | TP |
| R-SELL | 2015-09-07 03:05 | 2015-09-07 04:06 | ASIA | 1 | 0.5 | -0.45 | 1 | 1.0 | - | TP |
| R-BUY | 2016-12-13 03:35 | 2016-12-13 03:39 | ASIA | 1 | 0.5 | -0.41 | 1 | 1.0 | - | TP |
| R-BUY | 2016-12-14 13:19 | 2016-12-14 13:25 | NEW YORK | 1 | 0.5 | -0.5 | 1 | 1.0 | - | TP |
| R-SELL | 2015-06-23 03:15 | 2015-06-23 03:52 | ASIA | 1 | 0.5 | -0.34 | 1 | 1.0 | - | TP |
| R-SELL | 2015-06-25 18:26 | 2015-06-25 20:51 | NEW YORK | 1 | 0.5 | -0.54 | 1 | 1.0 | - | TP |
| R-BUY | 2015-06-23 02:52 | 2015-06-23 03:04 | ASIA | 1 | 0.51 | -0.41 | 1 | 1.0 | - | TP |
| R-SELL | 2015-08-24 01:51 | 2015-08-24 01:52 | ASIA | 1 | 0.51 | -0.63 | 1 | 1.0 | - | TP |
| R-SELL | 2015-08-24 14:15 | 2015-08-24 14:16 | NEW YORK | 1 | 0.51 | -0.42 | 1 | 1.0 | - | TP |

## Analisis MAE: berapa batas cut loss basket yang optimal?
Perkiraan net bila setiap basket utama dipotong saat floating menyentuh -X (mengabaikan efek entry ulang; pakai sebagai arah, lalu konfirmasi dengan replay).
| Cut loss X (USD) | Basket terpotong | Net perkiraan | Selisih vs tanpa cut |
|---|---|---|---|
| 25 | 0 | 0 | 0 |
| 50 | 0 | 0 | 0 |
| 100 | 0 | 0 | 0 |
| 150 | 0 | 0 | 0 |
| 200 | 0 | 0 | 0 |
| 300 | 0 | 0 | 0 |
| 500 | 0 | 0 | 0 |
| 800 | 0 | 0 | 0 |
| 1200 | 0 | 0 | 0 |
| 2000 | 0 | 0 | 0 |

## Temuan kelemahan & rekomendasi
- 316 basket mengalami >= 4 stop terisi dalam 30 detik (rata-rata 3.03, MAE terburuk -6616.95). Burst justru menguntungkan: momentum sehat.
- MAE terburuk -6616.95 USD (lot 0.01). Pastikan saldo sanggup menahan >= 2x angka ini; InpMaxDrawdownPct saat ini 0%.
- Mesin REVERSION merugi di rezim RANGE (682 basket, net -86.14): turunkan InpERRange / naikkan InpRevZEntry agar REVERSION hanya di pasar benar-benar datar.

## Catatan metodologi
- Replay ini meniru logika EA, bukan pengganti Strategy Tester MT5 (eksekusi, swap, margin, dan slippage broker nyata bisa berbeda).
- Data bar diubah jadi 4 tick per bar (O-L-H-C / O-H-L-C); hasil tick asli lebih akurat.
- Anti mengintip data depan: indikator hanya memakai bar yang sudah tutup; kejutan harga yang dideteksi dari data TIDAK dipakai untuk keputusan trading (perisai berita hanya aktif dengan file kalender --news).
- Kinerja masa lalu tidak menjamin hasil masa depan.
