# Laporan Forensik EA SAPU JAGAD — video

Data: 4686640 tick, 2015-01-01 23:00 s/d 2018-06-19 10:00 (waktu server). Tanpa file kalender: perisai & penunggang berita NONAKTIF di replay (anti mengintip data). 901 kejutan harga terdeteksi dari 1171660 bar M1, dipakai hanya sebagai label laporan.

## Ringkasan
| Metrik | Nilai |
|---|---|
| net | 6187.34 |
| baskets | 368 |
| win_rate | 99.7 |
| profit_factor | 3.25 |
| max_dd | 9857.72 |
| max_dd_pct | 82.32 |
| recovery_factor | 0.63 |
| worst_mae | -9842.85 |
| avg_result | 16.81 |
| halts | 0 |
| bursts | 0 |
| news_rides | 0 |
| data_holes | 718 |

## Kestabilan per tahun
| Tahun | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|
| 2015 | 69 | 1959.89 | 28.4 | 100.0 | -679.67 |
| 2016 | 215 | 5491.2 | 25.54 | 100.0 | -9842.85 |
| 2017 | 3 | 61.59 | 20.53 | 100.0 | -9026.28 |
| 2018 | 81 | -1325.34 | -16.36 | 98.8 | -4360.71 |

## Per sesi (saat stop pertama terisi)
| Sesi | Basket | Net | Rata2 | Win% | MAE terburuk | Rata2 posisi |
|---|---|---|---|---|---|---|
| ASIA | 109 | 641.19 | 5.88 | 99.1 | -4360.71 | 16.6 |
| LONDON | 86 | 1967.86 | 22.88 | 100.0 | -1780.02 | 16.1 |
| NEW YORK | 173 | 3578.29 | 20.68 | 100.0 | -9842.85 | 15.2 |

## Per jam (GMT)
| Jam | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|
| 1 | 29 | 720.22 | 24.84 | 100.0 | -1936.03 |
| 2 | 12 | 575.95 | 48.0 | 100.0 | -206.3 |
| 3 | 16 | 398.95 | 24.93 | 100.0 | -127.33 |
| 4 | 7 | 338.06 | 48.29 | 100.0 | -879.34 |
| 5 | 15 | 338.32 | 22.55 | 100.0 | -204.62 |
| 6 | 10 | -2568.87 | -256.89 | 90.0 | -4360.71 |
| 7 | 13 | 305.83 | 23.53 | 100.0 | -1780.02 |
| 8 | 10 | 213.99 | 21.4 | 100.0 | -611.28 |
| 9 | 11 | 292.39 | 26.58 | 100.0 | -175.85 |
| 10 | 8 | 237.68 | 29.71 | 100.0 | -411.98 |
| 11 | 12 | 173.3 | 14.44 | 100.0 | -236.47 |
| 12 | 32 | 744.67 | 23.27 | 100.0 | -605.38 |
| 13 | 41 | 872.08 | 21.27 | 100.0 | -803.65 |
| 14 | 34 | 725.86 | 21.35 | 100.0 | -1125.1 |
| 15 | 26 | 511.33 | 19.67 | 100.0 | -9842.85 |
| 16 | 20 | 471.0 | 23.55 | 100.0 | -752.71 |
| 17 | 11 | 253.43 | 23.04 | 100.0 | -9026.28 |
| 18 | 16 | 261.6 | 16.35 | 100.0 | -66.58 |
| 19 | 13 | 288.73 | 22.21 | 100.0 | -417.2 |
| 20 | 12 | 194.26 | 16.19 | 100.0 | -58.89 |
| 21 | 2 | 86.06 | 43.03 | 100.0 | -136.6 |
| 22 | 9 | 269.48 | 29.94 | 100.0 | -290.55 |
| 23 | 9 | 483.02 | 53.67 | 100.0 | -891.24 |

## Berita vs normal
| Kelompok | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|
| utama, normal | 368 | 6187.34 | 16.81 | 99.7 | -9842.85 |

## Per mesin & rezim pasar (bukti edge pengalih rezim)
Rezim diukur dengan Efficiency Ratio M1 saat stop/limit pertama terisi. Pengalih rezim punya edge bila MOMENTUM lebih baik di TREN dan REVERSION lebih baik di RANGE.
| Mesin | Rezim | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|---|
| MOMENTUM | NETRAL | 137 | 528.9 | 3.86 | 99.3 | -4360.71 |
| MOMENTUM | RANGE | 86 | 2147.47 | 24.97 | 100.0 | -1001.26 |
| MOMENTUM | TREN | 145 | 3510.97 | 24.21 | 100.0 | -9842.85 |

## Per arah / slot
| Slot | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|
| BUY | 368 | 6187.34 | 16.81 | 99.7 | -9842.85 |

## 15 basket terburuk (bahan forensik)
| Slot | Buka | Tutup | Sesi | Pos | Hasil | MAE | Burst | Vol | Berita | Alasan |
|---|---|---|---|---|---|---|---|---|---|---|
| BUY | 2018-04-19 06:35 | 2018-06-19 10:59 | ASIA | 40 | -2749.65 | -2902.45 | 3 | 1.0 | - | akhir data |
| BUY | 2016-08-02 13:40 | 2016-08-02 14:35 | NEW YORK | 5 | 5.03 | -3.63 | 1 | 1.0 | - | TP |
| BUY | 2018-01-25 03:31 | 2018-01-25 06:26 | ASIA | 5 | 5.17 | -5.37 | 1 | 1.0 | - | TP |
| BUY | 2016-08-02 12:38 | 2016-08-02 13:01 | LONDON | 5 | 5.19 | -1.57 | 1 | 1.0 | - | TP |
| BUY | 2016-06-10 11:41 | 2016-06-10 12:43 | LONDON | 5 | 5.25 | -4.44 | 1 | 1.0 | - | TP |
| BUY | 2018-01-26 03:08 | 2018-01-26 07:08 | ASIA | 5 | 5.41 | -2.42 | 1 | 1.0 | - | TP |
| BUY | 2018-01-25 17:43 | 2018-01-25 18:20 | NEW YORK | 5 | 5.86 | -1.15 | 1 | 1.0 | - | TP |
| BUY | 2016-09-06 16:16 | 2016-09-06 16:40 | NEW YORK | 6 | 6.04 | -1.77 | 1 | 1.0 | - | TP |
| BUY | 2016-06-10 13:48 | 2016-06-10 14:05 | NEW YORK | 6 | 6.1 | -2.08 | 1 | 1.0 | - | TP |
| BUY | 2016-09-06 16:59 | 2016-09-06 17:28 | NEW YORK | 6 | 6.1 | -2.6 | 2 | 1.0 | - | TP |
| BUY | 2018-01-24 12:43 | 2018-01-24 13:02 | LONDON | 6 | 6.13 | -0.55 | 2 | 1.0 | - | TP |
| BUY | 2016-06-08 10:50 | 2016-06-08 12:03 | LONDON | 6 | 6.13 | -1.94 | 1 | 1.0 | - | TP |
| BUY | 2018-04-10 08:50 | 2018-04-10 11:32 | LONDON | 6 | 6.14 | -1.99 | 2 | 1.0 | - | TP |
| BUY | 2016-06-08 12:32 | 2016-06-08 13:19 | LONDON | 6 | 6.18 | -2.93 | 2 | 1.0 | - | TP |
| BUY | 2016-07-08 19:03 | 2016-07-08 19:58 | NEW YORK | 6 | 6.2 | -5.59 | 1 | 1.0 | - | TP |

## Analisis MAE: berapa batas cut loss basket yang optimal?
Perkiraan net bila setiap basket utama dipotong saat floating menyentuh -X (mengabaikan efek entry ulang; pakai sebagai arah, lalu konfirmasi dengan replay).
| Cut loss X (USD) | Basket terpotong | Net perkiraan | Selisih vs tanpa cut |
|---|---|---|---|
| 25 | 154 | -1464.34 | -7651.68 |
| 50 | 106 | -1841.17 | -8028.51 |
| 100 | 70 | -2465.82 | -8653.16 |
| 150 | 57 | -3103.9 | -9291.24 |
| 200 | 50 | -4143.34 | -10330.68 |
| 300 | 36 | -4175.88 | -10363.22 |
| 500 | 21 | -2763.33 | -8950.67 |
| 800 | 12 | -1384.12 | -7571.46 |
| 1200 | 6 | 1453.68 | -4733.66 |
| 2000 | 4 | 760.43 | -5426.91 |

## Temuan kelemahan & rekomendasi
- 101 basket mengalami >= 4 stop terisi dalam 30 detik (rata-rata 34.79, MAE terburuk -9842.85). Burst justru menguntungkan: momentum sehat.
- MAE terburuk -9842.85 USD (lot 0.01). Pastikan saldo sanggup menahan >= 2x angka ini; InpMaxDrawdownPct saat ini 0%.

## Catatan metodologi
- Replay ini meniru logika EA, bukan pengganti Strategy Tester MT5 (eksekusi, swap, margin, dan slippage broker nyata bisa berbeda).
- Data bar diubah jadi 4 tick per bar (O-L-H-C / O-H-L-C); hasil tick asli lebih akurat.
- Anti mengintip data depan: indikator hanya memakai bar yang sudah tutup; kejutan harga yang dideteksi dari data TIDAK dipakai untuk keputusan trading (perisai berita hanya aktif dengan file kalender --news).
- Kinerja masa lalu tidak menjamin hasil masa depan.
