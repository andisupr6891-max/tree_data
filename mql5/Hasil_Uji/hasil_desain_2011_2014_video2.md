# Laporan Forensik EA SAPU JAGAD — video2

Data: 4945164 tick, 2011-05-10 09:00 s/d 2014-12-31 21:00 (waktu server). Tanpa file kalender: perisai & penunggang berita NONAKTIF di replay (anti mengintip data). 855 kejutan harga terdeteksi dari 1236291 bar M1, dipakai hanya sebagai label laporan.

## Ringkasan
| Metrik | Nilai |
|---|---|
| net | -6907.35 |
| baskets | 726 |
| win_rate | 99.9 |
| profit_factor | 0.41 |
| max_dd | 13291.94 |
| max_dd_pct | 89.69 |
| recovery_factor | -0.52 |
| worst_mae | -13283.25 |
| avg_result | -9.51 |
| halts | 0 |
| bursts | 0 |
| news_rides | 0 |
| data_holes | 771 |

## Kestabilan per tahun
| Tahun | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|
| 2011 | 479 | 3019.61 | 6.3 | 100.0 | -11627.55 |
| 2012 | 121 | 991.99 | 8.2 | 100.0 | -7610.85 |
| 2013 | 125 | 799.8 | 6.4 | 100.0 | -7528.95 |
| 2014 | 1 | -11718.75 | -11718.75 | 0.0 | -13283.25 |

## Per sesi (saat stop pertama terisi)
| Sesi | Basket | Net | Rata2 | Win% | MAE terburuk | Rata2 posisi |
|---|---|---|---|---|---|---|
| ASIA | 102 | 438.6 | 4.3 | 100.0 | -798.45 | 6.5 |
| LONDON | 219 | 1745.43 | 7.97 | 100.0 | -11627.55 | 8.2 |
| NEW YORK | 405 | -9091.38 | -22.45 | 99.8 | -13283.25 | 7.0 |

## Per jam (GMT)
| Jam | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|
| 1 | 17 | 82.39 | 4.85 | 100.0 | -136.95 |
| 2 | 9 | 33.57 | 3.73 | 100.0 | -37.84 |
| 3 | 9 | 41.67 | 4.63 | 100.0 | -26.39 |
| 4 | 19 | 44.6 | 2.35 | 100.0 | -33.75 |
| 5 | 17 | 52.6 | 3.09 | 100.0 | -81.96 |
| 6 | 14 | 77.36 | 5.53 | 100.0 | -86.0 |
| 7 | 25 | 204.43 | 8.18 | 100.0 | -252.75 |
| 8 | 18 | 131.54 | 7.31 | 100.0 | -84.0 |
| 9 | 23 | 111.04 | 4.83 | 100.0 | -132.15 |
| 10 | 27 | 108.92 | 4.03 | 100.0 | -1440.15 |
| 11 | 33 | 336.75 | 10.2 | 100.0 | -378.15 |
| 12 | 93 | 852.75 | 9.17 | 100.0 | -11627.55 |
| 13 | 67 | -11212.65 | -167.35 | 98.5 | -13283.25 |
| 14 | 110 | 565.02 | 5.14 | 100.0 | -7528.95 |
| 15 | 82 | 508.2 | 6.2 | 100.0 | -404.55 |
| 16 | 54 | 524.78 | 9.72 | 100.0 | -1203.45 |
| 17 | 39 | 197.63 | 5.07 | 100.0 | -7610.85 |
| 18 | 26 | 241.03 | 9.27 | 100.0 | -114.26 |
| 19 | 19 | 54.05 | 2.84 | 100.0 | -23.46 |
| 20 | 8 | 30.56 | 3.82 | 100.0 | -1715.85 |
| 21 | 3 | 11.8 | 3.93 | 100.0 | -26.46 |
| 22 | 9 | 68.43 | 7.6 | 100.0 | -798.45 |
| 23 | 5 | 26.18 | 5.24 | 100.0 | -25.09 |

## Berita vs normal
| Kelompok | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|
| utama, normal | 726 | -6907.35 | -9.51 | 99.9 | -13283.25 |

## Per mesin & rezim pasar (bukti edge pengalih rezim)
Rezim diukur dengan Efficiency Ratio M1 saat stop/limit pertama terisi. Pengalih rezim punya edge bila MOMENTUM lebih baik di TREN dan REVERSION lebih baik di RANGE.
| Mesin | Rezim | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|---|
| REVERSION | NETRAL | 292 | 1979.24 | 6.78 | 100.0 | -7610.85 |
| REVERSION | RANGE | 353 | -9653.55 | -27.35 | 99.7 | -13283.25 |
| REVERSION | TREN | 81 | 766.96 | 9.47 | 100.0 | -11627.55 |

## Per arah / slot
| Slot | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|
| R-BUY | 380 | -9313.41 | -24.51 | 99.7 | -13283.25 |
| R-SELL | 346 | 2406.06 | 6.95 | 100.0 | -11627.55 |

## 15 basket terburuk (bahan forensik)
| Slot | Buka | Tutup | Sesi | Pos | Hasil | MAE | Burst | Vol | Berita | Alasan |
|---|---|---|---|---|---|---|---|---|---|---|
| R-BUY | 2013-04-10 13:37 | 2014-12-31 21:59 | NEW YORK | 30 | -11718.75 | -13283.25 | 9 | 1.0 | - | akhir data |
| R-BUY | 2011-05-10 12:30 | 2011-05-10 12:31 | LONDON | 1 | 0.5 | -0.52 | 1 | 1.0 | - | TP |
| R-BUY | 2011-05-24 12:16 | 2011-05-24 12:19 | LONDON | 1 | 0.5 | -0.47 | 1 | 1.0 | - | TP |
| R-SELL | 2011-06-15 08:25 | 2011-06-15 08:33 | LONDON | 1 | 0.5 | -0.36 | 1 | 1.0 | - | TP |
| R-BUY | 2012-05-30 14:12 | 2012-05-30 14:12 | NEW YORK | 1 | 0.51 | -0.34 | 1 | 1.0 | - | TP |
| R-SELL | 2011-05-26 19:01 | 2011-05-26 19:05 | NEW YORK | 1 | 0.51 | -0.54 | 1 | 1.0 | - | TP |
| R-SELL | 2011-06-13 14:48 | 2011-06-13 14:52 | NEW YORK | 1 | 0.51 | -0.43 | 1 | 1.0 | - | TP |
| R-SELL | 2011-07-06 21:12 | 2011-07-06 22:37 | ASIA | 1 | 0.51 | -0.47 | 1 | 1.0 | - | TP |
| R-BUY | 2012-05-16 05:40 | 2012-05-16 05:44 | ASIA | 1 | 0.51 | -0.5 | 1 | 1.0 | - | TP |
| R-SELL | 2011-06-16 07:44 | 2011-06-16 07:59 | LONDON | 1 | 0.51 | -0.36 | 1 | 1.0 | - | TP |
| R-BUY | 2013-04-04 14:41 | 2013-04-04 14:41 | NEW YORK | 1 | 0.52 | -0.46 | 1 | 1.0 | - | TP |
| R-BUY | 2011-05-25 18:36 | 2011-05-25 19:04 | NEW YORK | 1 | 0.52 | -0.58 | 1 | 1.0 | - | TP |
| R-SELL | 2011-05-25 19:06 | 2011-05-25 19:23 | NEW YORK | 1 | 0.52 | -0.54 | 1 | 1.0 | - | TP |
| R-SELL | 2011-06-10 10:06 | 2011-06-10 10:18 | LONDON | 1 | 0.52 | -0.51 | 1 | 1.0 | - | TP |
| R-BUY | 2011-06-13 05:23 | 2011-06-13 05:38 | ASIA | 1 | 0.52 | -0.45 | 1 | 1.0 | - | TP |

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
- Sesi NEW YORK merugi (405 basket, net -9091.38, MAE terburuk -13283.25). Coba InpNYStepMult=1.3-1.6 atau InpTradeNY=false.
- 224 basket mengalami >= 4 stop terisi dalam 30 detik (rata-rata -37.86, MAE terburuk -13283.25). Turunkan InpBurstMaxFills.
- MAE terburuk -13283.25 USD (lot 0.01). Pastikan saldo sanggup menahan >= 2x angka ini; InpMaxDrawdownPct saat ini 0%.
- Mesin REVERSION merugi di rezim RANGE (353 basket, net -9653.55): turunkan InpERRange / naikkan InpRevZEntry agar REVERSION hanya di pasar benar-benar datar.

## Catatan metodologi
- Replay ini meniru logika EA, bukan pengganti Strategy Tester MT5 (eksekusi, swap, margin, dan slippage broker nyata bisa berbeda).
- Data bar diubah jadi 4 tick per bar (O-L-H-C / O-H-L-C); hasil tick asli lebih akurat.
- Anti mengintip data depan: indikator hanya memakai bar yang sudah tutup; kejutan harga yang dideteksi dari data TIDAK dipakai untuk keputusan trading (perisai berita hanya aktif dengan file kalender --news).
- Kinerja masa lalu tidak menjamin hasil masa depan.
