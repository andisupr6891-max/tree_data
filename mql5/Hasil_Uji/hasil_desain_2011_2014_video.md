# Laporan Forensik EA SAPU JAGAD — video

Data: 4945164 tick, 2011-05-10 09:00 s/d 2014-12-31 21:00 (waktu server). Tanpa file kalender: perisai & penunggang berita NONAKTIF di replay (anti mengintip data). 855 kejutan harga terdeteksi dari 1236291 bar M1, dipakai hanya sebagai label laporan.

## Ringkasan
| Metrik | Nilai |
|---|---|
| net | -19592.55 |
| baskets | 364 |
| win_rate | 99.7 |
| profit_factor | 0.3 |
| max_dd | 30261.74 |
| max_dd_pct | 162.84 |
| recovery_factor | -0.65 |
| worst_mae | -30257.98 |
| avg_result | -53.83 |
| halts | 0 |
| bursts | 0 |
| news_rides | 0 |
| data_holes | 771 |

## Kestabilan per tahun
| Tahun | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|
| 2011 | 363 | 8579.43 | 23.63 | 100.0 | -7761.46 |
| 2014 | 1 | -28171.98 | -28171.98 | 0.0 | -30257.98 |

## Per sesi (saat stop pertama terisi)
| Sesi | Basket | Net | Rata2 | Win% | MAE terburuk | Rata2 posisi |
|---|---|---|---|---|---|---|
| ASIA | 95 | 2008.72 | 21.14 | 100.0 | -7761.46 | 13.4 |
| LONDON | 98 | 2357.46 | 24.06 | 100.0 | -2302.11 | 16.3 |
| NEW YORK | 171 | -23958.73 | -140.11 | 99.4 | -30257.98 | 16.2 |

## Per jam (GMT)
| Jam | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|
| 1 | 12 | 221.49 | 18.46 | 100.0 | -269.61 |
| 2 | 4 | 114.46 | 28.61 | 100.0 | -55.47 |
| 3 | 14 | 297.88 | 21.28 | 100.0 | -7761.46 |
| 4 | 9 | 238.62 | 26.51 | 100.0 | -894.78 |
| 5 | 12 | 253.31 | 21.11 | 100.0 | -350.83 |
| 6 | 17 | 411.68 | 24.22 | 100.0 | -1455.84 |
| 7 | 12 | 287.24 | 23.94 | 100.0 | -1530.92 |
| 8 | 19 | 469.08 | 24.69 | 100.0 | -497.33 |
| 9 | 12 | 332.01 | 27.67 | 100.0 | -439.79 |
| 10 | 14 | 381.16 | 27.23 | 100.0 | -1384.81 |
| 11 | 18 | 309.35 | 17.19 | 100.0 | -217.58 |
| 12 | 23 | 578.62 | 25.16 | 100.0 | -2302.11 |
| 13 | 40 | 887.72 | 22.19 | 100.0 | -687.47 |
| 14 | 35 | -27361.58 | -781.76 | 97.1 | -30257.98 |
| 15 | 27 | 625.46 | 23.17 | 100.0 | -956.66 |
| 16 | 18 | 505.64 | 28.09 | 100.0 | -290.08 |
| 17 | 14 | 325.14 | 23.22 | 100.0 | -385.68 |
| 18 | 13 | 507.38 | 39.03 | 100.0 | -1016.88 |
| 19 | 17 | 457.44 | 26.91 | 100.0 | -729.22 |
| 20 | 7 | 94.07 | 13.44 | 100.0 | -104.19 |
| 21 | 1 | 8.46 | 8.46 | 100.0 | -3.05 |
| 22 | 19 | 288.3 | 15.17 | 100.0 | -73.66 |
| 23 | 7 | 174.52 | 24.93 | 100.0 | -560.62 |

## Berita vs normal
| Kelompok | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|
| utama, normal | 364 | -19592.55 | -53.83 | 99.7 | -30257.98 |

## Per mesin & rezim pasar (bukti edge pengalih rezim)
Rezim diukur dengan Efficiency Ratio M1 saat stop/limit pertama terisi. Pengalih rezim punya edge bila MOMENTUM lebih baik di TREN dan REVERSION lebih baik di RANGE.
| Mesin | Rezim | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|---|
| MOMENTUM | NETRAL | 134 | 3743.62 | 27.94 | 100.0 | -2556.68 |
| MOMENTUM | RANGE | 87 | -26423.07 | -303.71 | 98.9 | -30257.98 |
| MOMENTUM | TREN | 143 | 3086.9 | 21.59 | 100.0 | -7761.46 |

## Per arah / slot
| Slot | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|
| BUY | 364 | -19592.55 | -53.83 | 99.7 | -30257.98 |

## 15 basket terburuk (bahan forensik)
| Slot | Buka | Tutup | Sesi | Pos | Hasil | MAE | Burst | Vol | Berita | Alasan |
|---|---|---|---|---|---|---|---|---|---|---|
| BUY | 2011-09-06 14:17 | 2014-12-31 21:59 | NEW YORK | 40 | -28171.98 | -30257.98 | 5 | 1.0 | - | akhir data |
| BUY | 2011-07-19 04:30 | 2011-07-19 05:40 | ASIA | 5 | 5.1 | -5.8 | 1 | 1.0 | - | TP |
| BUY | 2011-07-21 05:46 | 2011-07-21 07:03 | ASIA | 6 | 6.02 | -3.5 | 1 | 1.0 | - | TP |
| BUY | 2011-07-14 07:31 | 2011-07-14 08:34 | LONDON | 6 | 6.12 | -3.47 | 1 | 1.0 | - | TP |
| BUY | 2011-07-08 20:25 | 2011-07-11 05:24 | NEW YORK | 6 | 6.21 | -4.9 | 1 | 1.0 | - | TP |
| BUY | 2011-08-01 09:59 | 2011-08-01 11:13 | LONDON | 6 | 6.27 | -1.81 | 1 | 1.0 | - | TP |
| BUY | 2011-06-22 14:14 | 2011-06-22 14:34 | NEW YORK | 6 | 6.51 | -4.1 | 2 | 1.0 | - | TP |
| BUY | 2011-07-20 19:14 | 2011-07-20 19:56 | NEW YORK | 6 | 6.8 | -3.54 | 1 | 1.0 | - | TP |
| BUY | 2011-05-24 04:52 | 2011-05-24 08:29 | ASIA | 6 | 6.86 | -3.55 | 1 | 1.0 | - | TP |
| BUY | 2011-08-08 05:15 | 2011-08-08 05:28 | ASIA | 7 | 7.01 | -4.32 | 2 | 1.0 | - | TP |
| BUY | 2011-08-18 10:22 | 2011-08-18 10:31 | LONDON | 7 | 7.02 | -2.52 | 3 | 1.0 | - | TP |
| BUY | 2011-06-20 20:33 | 2011-06-21 06:21 | NEW YORK | 7 | 7.06 | -7.74 | 2 | 1.0 | - | TP |
| BUY | 2011-08-02 19:58 | 2011-08-02 21:13 | NEW YORK | 7 | 7.07 | -8.84 | 2 | 1.0 | - | TP |
| BUY | 2011-08-18 06:43 | 2011-08-18 08:10 | ASIA | 7 | 7.16 | -5.07 | 1 | 1.0 | - | TP |
| BUY | 2011-08-01 14:58 | 2011-08-01 15:14 | NEW YORK | 7 | 7.21 | -7.1 | 2 | 1.0 | - | TP |

## Analisis MAE: berapa batas cut loss basket yang optimal?
Perkiraan net bila setiap basket utama dipotong saat floating menyentuh -X (mengabaikan efek entry ulang; pakai sebagai arah, lalu konfirmasi dengan replay).
| Cut loss X (USD) | Basket terpotong | Net perkiraan | Selisih vs tanpa cut |
|---|---|---|---|
| 25 | 152 | -1164.08 | 18428.47 |
| 50 | 94 | -757.85 | 18834.7 |
| 100 | 60 | -970.8 | 18621.75 |
| 150 | 49 | -1783.39 | 17809.16 |
| 200 | 39 | -1625.43 | 17967.12 |
| 300 | 24 | -191.23 | 19401.32 |
| 500 | 16 | -426.8 | 19165.75 |
| 800 | 12 | -1808.59 | 17783.96 |
| 1200 | 9 | -2744.11 | 16848.44 |
| 2000 | 4 | 351.28 | 19943.83 |

## Temuan kelemahan & rekomendasi
- Sesi NEW YORK merugi (171 basket, net -23958.73, MAE terburuk -30257.98). Coba InpNYStepMult=1.3-1.6 atau InpTradeNY=false.
- 124 basket mengalami >= 4 stop terisi dalam 30 detik (rata-rata -192.05, MAE terburuk -30257.98). Turunkan InpBurstMaxFills.
- Analisis MAE: memotong basket di -2000 USD (lot 0.01) diperkirakan memperbaiki net +19943.83. Setel InpBasketSLMoney=2000 (atau InpBasketSLPct setara) lalu replay ulang untuk konfirmasi.
- MAE terburuk -30257.98 USD (lot 0.01). Pastikan saldo sanggup menahan >= 2x angka ini; InpMaxDrawdownPct saat ini 0%.
- Mesin MOMENTUM merugi di rezim RANGE (87 basket, net -26423.07): naikkan InpERRange agar MOMENTUM tidak dibuka saat pasar datar.

## Catatan metodologi
- Replay ini meniru logika EA, bukan pengganti Strategy Tester MT5 (eksekusi, swap, margin, dan slippage broker nyata bisa berbeda).
- Data bar diubah jadi 4 tick per bar (O-L-H-C / O-H-L-C); hasil tick asli lebih akurat.
- Anti mengintip data depan: indikator hanya memakai bar yang sudah tutup; kejutan harga yang dideteksi dari data TIDAK dipakai untuk keputusan trading (perisai berita hanya aktif dengan file kalender --news).
- Kinerja masa lalu tidak menjamin hasil masa depan.
