# Laporan Forensik EA SAPU JAGAD — sapujagad

Data: 4945164 tick, 2011-05-10 09:00 s/d 2014-12-31 21:00 (waktu server). Tanpa file kalender: perisai & penunggang berita NONAKTIF di replay (anti mengintip data). 855 kejutan harga terdeteksi dari 1236291 bar M1, dipakai hanya sebagai label laporan.

## Ringkasan
| Metrik | Nilai |
|---|---|
| net | -10417.51 |
| baskets | 2410 |
| win_rate | 61.8 |
| profit_factor | 0.43 |
| max_dd | 10617.84 |
| max_dd_pct | 104.09 |
| recovery_factor | -0.98 |
| worst_mae | -1048.8 |
| avg_result | -4.32 |
| halts | 592 |
| bursts | 130 |
| news_rides | 0 |
| data_holes | 771 |

## Perbandingan: tiruan video 1 (momentum), video 2 (reversion), dan SAPU JAGAD
| Konfigurasi | Net | Basket | Win% | PF | Max DD | DD% | RF | MAE terburuk |
|---|---|---|---|---|---|---|---|---|
| sapujagad | -10417.51 | 2410 | 61.8 | 0.43 | 10617.84 | 104.09 | -0.98 | -1048.8 |
| video | -19592.55 | 364 | 99.7 | 0.3 | 30261.74 | 162.84 | -0.65 | -30257.98 |
| video2 | -6907.35 | 726 | 99.9 | 0.41 | 13291.94 | 89.69 | -0.52 | -13283.25 |

## Kestabilan per tahun
| Tahun | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|
| 2011 | 753 | -3036.52 | -4.03 | 81.9 | -1048.8 |
| 2012 | 1131 | -7013.58 | -6.2 | 77.1 | -713.19 |
| 2013 | 262 | -199.81 | -0.76 | 0.0 | -13.11 |
| 2014 | 264 | -167.6 | -0.63 | 0.0 | -10.11 |

## Per sesi (saat stop pertama terisi)
| Sesi | Basket | Net | Rata2 | Win% | MAE terburuk | Rata2 posisi |
|---|---|---|---|---|---|---|
| ASIA | 865 | -1654.17 | -1.91 | 39.2 | -954.84 | 2.8 |
| LONDON | 753 | -3290.57 | -4.37 | 66.8 | -1048.8 | 5.3 |
| NEW YORK | 792 | -5472.77 | -6.91 | 81.7 | -926.56 | 6.3 |

## Per jam (GMT)
| Jam | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|
| 1 | 339 | 141.38 | 0.42 | 28.6 | -414.03 |
| 2 | 94 | -182.68 | -1.94 | 33.0 | -174.76 |
| 3 | 109 | -970.97 | -8.91 | 39.4 | -954.84 |
| 4 | 71 | -643.1 | -9.06 | 56.3 | -713.19 |
| 5 | 89 | 13.0 | 0.15 | 55.1 | -370.55 |
| 6 | 118 | 28.09 | 0.24 | 55.1 | -69.21 |
| 7 | 126 | -376.04 | -2.98 | 54.0 | -968.64 |
| 8 | 126 | -1559.61 | -12.38 | 61.9 | -861.51 |
| 9 | 109 | 191.7 | 1.76 | 64.2 | -444.54 |
| 10 | 95 | 318.21 | 3.35 | 73.7 | -450.47 |
| 11 | 116 | -913.55 | -7.88 | 69.8 | -1048.8 |
| 12 | 181 | -951.28 | -5.26 | 75.1 | -753.0 |
| 13 | 119 | -1013.54 | -8.52 | 77.3 | -926.56 |
| 14 | 143 | -701.35 | -4.9 | 82.5 | -606.81 |
| 15 | 130 | -434.6 | -3.34 | 82.3 | -499.25 |
| 16 | 101 | -1807.51 | -17.9 | 80.2 | -765.84 |
| 17 | 109 | -671.34 | -6.16 | 83.5 | -515.15 |
| 18 | 74 | -76.53 | -1.03 | 81.1 | -436.79 |
| 19 | 88 | -751.38 | -8.54 | 83.0 | -858.49 |
| 20 | 28 | -16.52 | -0.59 | 89.3 | -454.35 |
| 23 | 45 | -39.89 | -0.89 | 31.1 | -57.92 |

## Berita vs normal
| Kelompok | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|
| utama, normal | 2410 | -10417.51 | -4.32 | 61.8 | -1048.8 |

## Per mesin & rezim pasar (bukti edge pengalih rezim)
Rezim diukur dengan Efficiency Ratio M1 saat stop/limit pertama terisi. Pengalih rezim punya edge bila MOMENTUM lebih baik di TREN dan REVERSION lebih baik di RANGE.
| Mesin | Rezim | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|---|
| MOMENTUM | NETRAL | 1 | -0.28 | -0.28 | 0.0 | -0.28 |
| MOMENTUM | TREN | 812 | -8426.34 | -10.38 | 72.4 | -1048.8 |
| REVERSION | NETRAL | 10 | 1.49 | 0.15 | 70.0 | -9.5 |
| REVERSION | RANGE | 1587 | -1992.38 | -1.26 | 56.3 | -46.25 |

## Kejutan harga (label pasca-fakta, bukan input trading)
Kejutan = candle M1 di menit :00/:30 dengan range >= k x ATR. Bila kelompok 'tersentuh' jauh lebih buruk, siapkan file kalender berita (--news) agar perisai berita bisa diuji.
| Kelompok | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|
| tanpa kejutan | 2290 | -1336.14 | -0.58 | 62.6 | -954.84 |
| tersentuh kejutan harga | 120 | -9081.37 | -75.68 | 45.8 | -1048.8 |

## Per arah / slot
| Slot | Basket | Net | Rata2 | Win% | MAE terburuk |
|---|---|---|---|---|---|
| BUY | 364 | -761.93 | -2.09 | 72.5 | -968.64 |
| R-BUY | 710 | -922.57 | -1.3 | 56.8 | -46.25 |
| R-SELL | 887 | -1068.32 | -1.2 | 56.1 | -45.81 |
| SELL | 449 | -7664.69 | -17.07 | 72.2 | -1048.8 |

## 15 basket terburuk (bahan forensik)
| Slot | Buka | Tutup | Sesi | Pos | Hasil | MAE | Burst | Vol | Berita | Alasan |
|---|---|---|---|---|---|---|---|---|---|---|
| SELL | 2011-07-12 11:09 | 2011-07-24 22:41 | LONDON | 24 | -1048.8 | -1048.8 | 3 | 3.46 | - | cut loss |
| BUY | 2011-08-23 03:57 | 2011-08-23 16:30 | ASIA | 24 | -954.84 | -954.84 | 3 | 2.04 | - | cut loss |
| BUY | 2011-12-08 13:36 | 2011-12-12 03:34 | NEW YORK | 21 | -926.56 | -926.56 | 8 | 5.47 | - | cut loss |
| SELL | 2011-08-30 08:25 | 2011-09-02 12:32 | LONDON | 11 | -861.51 | -861.51 | 2 | 2.22 | - | cut loss |
| SELL | 2011-12-15 19:48 | 2011-12-20 13:46 | NEW YORK | 24 | -858.49 | -858.49 | 2 | 1.59 | - | cut loss |
| SELL | 2011-12-29 16:09 | 2011-12-30 10:31 | NEW YORK | 24 | -765.84 | -765.84 | 5 | 4.67 | - | cut loss |
| SELL | 2012-01-16 04:04 | 2012-01-23 05:15 | ASIA | 24 | -713.19 | -713.19 | 4 | 3.36 | - | cut loss |
| SELL | 2012-02-17 16:10 | 2012-02-27 15:23 | NEW YORK | 24 | -666.82 | -666.82 | 2 | 1.0 | - | cut loss |
| SELL | 2012-03-07 14:38 | 2012-03-09 02:50 | NEW YORK | 24 | -606.81 | -606.81 | 2 | 1.39 | - | cut loss |
| SELL | 2012-03-09 14:04 | 2012-03-09 15:35 | NEW YORK | 18 | -585.72 | -585.72 | 8 | 3.63 | - | cut loss |
| SELL | 2012-04-04 17:29 | 2012-04-08 22:01 | NEW YORK | 24 | -515.15 | -515.15 | 2 | 2.05 | - | cut loss |
| SELL | 2012-03-16 12:15 | 2012-03-19 15:26 | LONDON | 24 | -503.09 | -503.09 | 2 | 3.09 | - | cut loss |
| SELL | 2012-03-29 15:37 | 2012-04-02 15:51 | NEW YORK | 18 | -453.03 | -453.03 | 2 | 1.51 | - | cut loss |
| SELL | 2012-04-25 16:37 | 2012-04-26 14:20 | NEW YORK | 16 | -388.56 | -388.56 | 3 | 4.45 | - | cut loss |
| BUY | 2012-05-01 12:36 | 2012-05-03 12:47 | LONDON | 12 | -360.62 | -360.62 | 3 | 2.55 | - | cut loss |

## Analisis MAE: berapa batas cut loss basket yang optimal?
Perkiraan net bila setiap basket utama dipotong saat floating menyentuh -X (mengabaikan efek entry ulang; pakai sebagai arah, lalu konfirmasi dengan replay).
| Cut loss X (USD) | Basket terpotong | Net perkiraan | Selisih vs tanpa cut |
|---|---|---|---|
| 25 | 282 | -4564.81 | 3861.81 |
| 50 | 153 | -4075.27 | 4351.35 |
| 100 | 84 | -4771.89 | 3654.73 |
| 150 | 62 | -5707.0 | 2719.62 |
| 200 | 46 | -5472.72 | 2953.9 |
| 300 | 33 | -7816.55 | 610.07 |
| 500 | 14 | -6455.92 | 1970.7 |
| 800 | 6 | -8601.14 | -174.52 |
| 1200 | 0 | -8426.62 | 0.0 |
| 2000 | 0 | -8426.62 | 0.0 |

## Temuan kelemahan & rekomendasi
- Sesi LONDON merugi (753 basket, net -3290.57, MAE terburuk -1048.80). Coba InpLondonStepMult=1.3-1.6 atau InpTradeLondon=false.
- Sesi NEW YORK merugi (792 basket, net -5472.77, MAE terburuk -926.56). Coba InpNYStepMult=1.3-1.6 atau InpTradeNY=false.
- Sesi ASIA merugi (865 basket, net -1654.17, MAE terburuk -954.84). Coba InpAsiaStepMult=1.3-1.6 atau InpTradeAsia=false.
- Basket yang dibuka saat volatilitas tinggi (>= x2.0) rata-rata -11.27 (lebih buruk dari umum -4.32). Turunkan InpVolBlockRatio atau naikkan InpVolMaxStepMult.
- 348 basket mengalami >= 4 stop terisi dalam 30 detik (rata-rata -9.66, MAE terburuk -926.56). Turunkan InpBurstMaxFills.
- Analisis MAE: memotong basket di -50 USD (lot 0.01) diperkirakan memperbaiki net +4351.35. Setel InpBasketSLMoney=50 (atau InpBasketSLPct setara) lalu replay ulang untuk konfirmasi.
- MAE terburuk -1048.80 USD (lot 0.01). Pastikan saldo sanggup menahan >= 2x angka ini; InpMaxDrawdownPct saat ini 30%.
- Mesin MOMENTUM merugi di rezim TREN (812 basket, net -8426.34): naikkan InpERRange agar MOMENTUM tidak dibuka saat pasar datar.
- Mesin REVERSION merugi di rezim RANGE (1587 basket, net -1992.38): turunkan InpERRange / naikkan InpRevZEntry agar REVERSION hanya di pasar benar-benar datar.

## Catatan metodologi
- Replay ini meniru logika EA, bukan pengganti Strategy Tester MT5 (eksekusi, swap, margin, dan slippage broker nyata bisa berbeda).
- Data bar diubah jadi 4 tick per bar (O-L-H-C / O-H-L-C); hasil tick asli lebih akurat.
- Anti mengintip data depan: indikator hanya memakai bar yang sudah tutup; kejutan harga yang dideteksi dari data TIDAK dipakai untuk keputusan trading (perisai berita hanya aktif dengan file kalender --news).
- Kinerja masa lalu tidak menjamin hasil masa depan.
