# Laporan Forensik EA SAPU JAGAD — sapujagad

Data: 4686640 tick, 2015-01-01 23:00 s/d 2018-06-19 10:00 (waktu server). Tanpa file kalender: perisai & penunggang berita NONAKTIF di replay (anti mengintip data). 901 kejutan harga terdeteksi dari 1171660 bar M1, dipakai hanya sebagai label laporan.

## Ringkasan
| Metrik | Nilai |
|---|---|
| net | -10009.09 |
| baskets | 3000 |
| win_rate | 82.6 |
| profit_factor | 0.44 |
| max_dd | 10655.87 |
| max_dd_pct | 100.09 |
| recovery_factor | -0.94 |
| worst_mae | -1075.84 |
| avg_result | -3.34 |
| halts | 17 |
| bursts | 81 |
| news_rides | 0 |
| data_holes | 718 |

## Perbandingan: tiruan video 1 (momentum), video 2 (reversion), dan SAPU JAGAD
| Konfigurasi | Net | Basket | Win% | PF | Max DD | DD% | RF | MAE terburuk |
|---|---|---|---|---|---|---|---|---|
| sapujagad | -10009.09 | 3000 | 82.6 | 0.44 | 10655.87 | 100.09 | -0.94 | -1075.84 |
| video | 6187.34 | 368 | 99.7 | 3.25 | 9857.72 | 82.32 | 0.63 | -9842.85 |
| video2 | 4223.35 | 1484 | 99.9 | 2.13 | 6617.94 | 38.31 | 0.64 | -6616.95 |

## Kestabilan per tahun
| Tahun | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|
| 2015 | 811 | -1952.82 | -2.41 | 83.0 | -1075.84 |
| 2016 | 949 | -6711.76 | -7.07 | 84.1 | -824.72 |
| 2017 | 763 | -790.35 | -1.04 | 85.6 | -141.7 |
| 2018 | 477 | -554.16 | -1.16 | 74.0 | -64.69 |

## Per sesi (saat stop pertama terisi)
| Sesi | Basket | Net | Rata2 | Win% | MAE terburuk | Rata2 posisi |
|---|---|---|---|---|---|---|
| ASIA | 876 | -3800.45 | -4.34 | 78.7 | -773.35 | 3.8 |
| LONDON | 841 | -857.12 | -1.02 | 84.5 | -560.23 | 4.4 |
| NEW YORK | 1283 | -5351.52 | -4.17 | 83.9 | -1075.84 | 4.6 |

## Per jam (GMT)
| Jam | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|
| 1 | 237 | -2207.89 | -9.32 | 73.8 | -773.35 |
| 2 | 108 | -190.84 | -1.77 | 79.6 | -356.75 |
| 3 | 74 | -6.42 | -0.09 | 86.5 | -83.79 |
| 4 | 68 | 21.45 | 0.32 | 86.8 | -38.13 |
| 5 | 105 | -742.11 | -7.07 | 76.2 | -444.33 |
| 6 | 145 | -437.15 | -3.01 | 82.1 | -522.88 |
| 7 | 116 | -19.04 | -0.16 | 81.9 | -126.44 |
| 8 | 138 | -252.1 | -1.83 | 81.2 | -263.89 |
| 9 | 118 | 212.94 | 1.8 | 86.4 | -231.72 |
| 10 | 110 | -261.64 | -2.38 | 81.8 | -139.92 |
| 11 | 132 | 106.42 | 0.81 | 87.1 | -229.62 |
| 12 | 227 | -643.7 | -2.84 | 86.8 | -560.23 |
| 13 | 221 | -936.63 | -4.24 | 83.3 | -868.89 |
| 14 | 225 | -1813.67 | -8.06 | 88.4 | -979.29 |
| 15 | 202 | -126.72 | -0.63 | 86.1 | -153.45 |
| 16 | 138 | -1435.08 | -10.4 | 87.7 | -1075.84 |
| 17 | 127 | -107.48 | -0.85 | 79.5 | -248.48 |
| 18 | 159 | -143.79 | -0.9 | 79.2 | -237.83 |
| 19 | 146 | -778.89 | -5.33 | 81.5 | -824.72 |
| 20 | 65 | -9.26 | -0.14 | 81.5 | -101.25 |
| 23 | 139 | -237.49 | -1.71 | 76.3 | -188.07 |

## Berita vs normal
| Kelompok | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|
| utama, normal | 3000 | -10009.09 | -3.34 | 82.6 | -1075.84 |

## Per mesin & rezim pasar (bukti edge pengalih rezim)
Rezim diukur dengan Efficiency Ratio M1 saat stop/limit pertama terisi. Pengalih rezim punya edge bila MOMENTUM lebih baik di TREN dan REVERSION lebih baik di RANGE.
| Mesin | Rezim | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|---|
| MOMENTUM | TREN | 711 | -8822.28 | -12.41 | 83.1 | -1075.84 |
| REVERSION | NETRAL | 4 | -9.93 | -2.48 | 75.0 | -13.1 |
| REVERSION | RANGE | 2285 | -1176.88 | -0.52 | 82.4 | -44.42 |

## Kejutan harga (label pasca-fakta, bukan input trading)
Kejutan = candle M1 di menit :00/:30 dengan range >= k x ATR. Bila kelompok 'tersentuh' jauh lebih buruk, siapkan file kalender berita (--news) agar perisai berita bisa diuji.
| Kelompok | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|
| tanpa kejutan | 2724 | -513.96 | -0.19 | 83.3 | -444.33 |
| tersentuh kejutan harga | 276 | -9495.13 | -34.4 | 75.7 | -1075.84 |

## Per arah / slot
| Slot | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|
| BUY | 366 | -4392.71 | -12.0 | 83.6 | -1075.84 |
| R-BUY | 800 | -740.74 | -0.93 | 81.5 | -33.81 |
| R-SELL | 1489 | -446.07 | -0.3 | 82.9 | -44.42 |
| SELL | 345 | -4429.57 | -12.84 | 82.6 | -979.29 |

## 15 basket terburuk (bahan forensik)
| Slot | Buka | Tutup | Sesi | Pos | Hasil | MAE | Burst | Vol | Berita | Alasan |
|---|---|---|---|---|---|---|---|---|---|---|
| BUY | 2015-06-19 16:10 | 2015-07-17 14:09 | NEW YORK | 24 | -1075.84 | -1075.84 | 8 | 2.58 | - | cut loss |
| SELL | 2015-08-05 14:09 | 2015-08-20 12:25 | NEW YORK | 24 | -979.29 | -979.29 | 3 | 2.14 | - | cut loss |
| SELL | 2015-09-11 13:30 | 2015-09-24 13:10 | NEW YORK | 24 | -868.89 | -868.89 | 2 | 2.15 | - | cut loss |
| BUY | 2016-02-11 19:31 | 2016-02-15 04:27 | NEW YORK | 24 | -824.72 | -824.72 | 5 | 2.34 | - | cut loss |
| SELL | 2016-04-01 14:10 | 2016-04-10 22:03 | NEW YORK | 24 | -794.33 | -794.33 | 2 | 2.01 | - | cut loss |
| BUY | 2016-03-18 01:16 | 2016-03-23 12:25 | ASIA | 24 | -773.35 | -773.35 | 7 | 4.41 | - | cut loss |
| SELL | 2016-04-14 16:03 | 2016-04-19 13:21 | NEW YORK | 24 | -664.55 | -664.55 | 3 | 1.9 | - | cut loss |
| BUY | 2016-04-21 12:23 | 2016-04-22 16:54 | LONDON | 17 | -560.23 | -560.23 | 4 | 1.96 | - | cut loss |
| SELL | 2016-04-26 06:38 | 2016-04-29 01:27 | ASIA | 14 | -522.88 | -522.88 | 4 | 2.08 | - | cut loss |
| SELL | 2016-05-30 01:28 | 2016-06-03 12:30 | ASIA | 24 | -489.38 | -489.38 | 3 | 1.55 | - | cut loss |
| BUY | 2016-06-24 05:06 | 2016-06-24 07:49 | ASIA | 24 | -444.33 | -444.33 | 5 | 0.56 | - | cut loss |
| BUY | 2016-07-11 01:50 | 2016-07-20 11:42 | ASIA | 20 | -397.76 | -397.76 | 4 | 1.67 | - | cut loss |
| SELL | 2016-07-26 02:42 | 2016-07-29 12:56 | ASIA | 12 | -356.75 | -356.75 | 3 | 4.24 | - | cut loss |
| BUY | 2016-08-26 14:36 | 2016-09-02 12:30 | NEW YORK | 17 | -349.17 | -349.17 | 7 | 0.93 | - | cut loss |
| BUY | 2016-11-22 01:16 | 2016-11-23 13:30 | ASIA | 10 | -303.22 | -303.22 | 1 | 1.75 | - | cut loss |

## Analisis MAE: berapa batas cut loss basket yang optimal?
Perkiraan net bila setiap basket utama dipotong saat floating menyentuh -X (mengabaikan efek entry ulang; pakai sebagai arah, lalu konfirmasi dengan replay).
| Cut loss X (USD) | Basket terpotong | Net perkiraan | Selisih vs tanpa cut |
|---|---|---|---|
| 25 | 243 | -4083.18 | 4739.1 |
| 50 | 135 | -4135.51 | 4686.77 |
| 100 | 67 | -4155.71 | 4666.57 |
| 150 | 42 | -4628.35 | 4193.93 |
| 200 | 33 | -5360.39 | 3461.89 |
| 300 | 18 | -4923.93 | 3898.35 |
| 500 | 9 | -6258.2 | 2564.08 |
| 800 | 4 | -8273.54 | 548.74 |
| 1200 | 0 | -8822.28 | 0.0 |
| 2000 | 0 | -8822.28 | 0.0 |

## Temuan kelemahan & rekomendasi
- Sesi ASIA merugi (876 basket, net -3800.45, MAE terburuk -773.35). Coba InpAsiaStepMult=1.3-1.6 atau InpTradeAsia=false.
- Sesi LONDON merugi (841 basket, net -857.12, MAE terburuk -560.23). Coba InpLondonStepMult=1.3-1.6 atau InpTradeLondon=false.
- Sesi NEW YORK merugi (1283 basket, net -5351.52, MAE terburuk -1075.84). Coba InpNYStepMult=1.3-1.6 atau InpTradeNY=false.
- Basket yang dibuka saat volatilitas tinggi (>= x2.0) rata-rata -6.87 (lebih buruk dari umum -3.34). Turunkan InpVolBlockRatio atau naikkan InpVolMaxStepMult.
- 271 basket mengalami >= 4 stop terisi dalam 30 detik (rata-rata -16.84, MAE terburuk -1075.84). Turunkan InpBurstMaxFills.
- Analisis MAE: memotong basket di -25 USD (lot 0.01) diperkirakan memperbaiki net +4739.10. Setel InpBasketSLMoney=25 (atau InpBasketSLPct setara) lalu replay ulang untuk konfirmasi.
- MAE terburuk -1075.84 USD (lot 0.01). Pastikan saldo sanggup menahan >= 2x angka ini; InpMaxDrawdownPct saat ini 30%.
- Mesin MOMENTUM merugi di rezim TREN (711 basket, net -8822.28): naikkan InpERRange agar MOMENTUM tidak dibuka saat pasar datar.
- Mesin REVERSION merugi di rezim RANGE (2285 basket, net -1176.88): turunkan InpERRange / naikkan InpRevZEntry agar REVERSION hanya di pasar benar-benar datar.

## Catatan metodologi
- Replay ini meniru logika EA, bukan pengganti Strategy Tester MT5 (eksekusi, swap, margin, dan slippage broker nyata bisa berbeda).
- Data bar diubah jadi 4 tick per bar (O-L-H-C / O-H-L-C); hasil tick asli lebih akurat.
- Anti mengintip data depan: indikator hanya memakai bar yang sudah tutup; kejutan harga yang dideteksi dari data TIDAK dipakai untuk keputusan trading (perisai berita hanya aktif dengan file kalender --news).
- Kinerja masa lalu tidak menjamin hasil masa depan.
