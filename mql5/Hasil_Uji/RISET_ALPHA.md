# Riset Alpha XAUUSD — data asli Mei 2011 s/d Juni 2018

Tujuan riset ini: mencari sumber keuntungan (alpha) yang benar-benar ada di data emas, bukan hasil kebetulan atau mengintip data.

## Data & protokol

- **Data:** tick XAUUSD Dukascopy (repositori publik FX-Data), diringkas menjadi 2.407.951 bar M1 dengan spread asli. Spread median $0,31.
- **Periode penemuan: 2011–2014.** Semua hipotesis hanya diuji di sini.
- **Periode holdout: 2015–2018.** Hanya pengaturan yang sudah dibekukan yang diuji di sini.
- **Biaya:** setiap trade dikenai spread asli (beli di ask, jual di bid).
- **Syarat lolos penemuan untuk hipotesis klasik:** t ≥ 3.
- **Syarat lolos holdout, ditetapkan sebelum dijalankan:** total bersih > 0 **dan** t ≥ 2.
- **Total konfigurasi yang diuji: 149.** Angka ini dicatat semua, supaya peluang menemukan "pemenang" karena kebetulan bisa diperhitungkan.

## 1. Hipotesis klasik (100 konfigurasi, periode penemuan)

Tujuh keluarga yang diuji:

1. Pola jam harian (GMT dan New York)
2. Momentum harian 1–120 hari
3. Breakout Donchian H1/H4
4. Pudarkan atau ikuti gerakan besar M5
5. Drift setelah rilis data AS pukul 08:30 dan 10:00 New York
6. Breakout rentang pembukaan London dan New York
7. Efek hari dalam seminggu

**Hasil: tidak ada satu pun yang untung dengan t ≥ 3.** Semua t-stat terbesar justru negatif, karena trade jangka pendek dimakan spread.

Kandidat lemah terbaik adalah *memudarkan gerakan 5 menit pertama setelah 08:30 New York bila ≥ 1×ATR5, lalu ditahan 30 menit*: 52 trade, +$12,6 per trade, t = 2,15, untung di 4 dari 4 tahun. Kandidat ini di bawah ambang, jadi tidak dilanjutkan.

## 2. Model machine learning (49 konfigurasi, periode penemuan)

**Fitur (45–46 buah)**, semuanya dari candle M15 yang sudah tutup:

- **Bobot dan anatomi 3 candle terakhir:** badan, sumbu atas/bawah, posisi close, range/ATR, volume tick relatif, dan badan × volume.
- **Momentum** 8 horizon.
- **Rasio volatilitas**, Efficiency Ratio, dan variance ratio.
- **Z-score** terhadap EMA 20/50/200, serta posisi di channel Donchian.
- **Waktu:** jam GMT dan New York (DST), hari, dan menit sejak 08:30 New York.

**Validasi:** walk-forward. Model dilatih di 2011–2012 lalu diuji di 2013, kemudian dilatih di 2011–2013 lalu diuji di 2014.

| Tahap | Temuan |
|---|---|
| Regresi logistik & LightGBM, horizon 60/240 menit | AUC out-of-sample 0,536–0,565, artinya arah **bisa** ditebak sedikit lebih baik dari kebetulan. Tetapi semua rugi setelah spread. |
| LightGBM klasifikasi/regresi, horizon 1–24 jam, keyakinan 10/5/2% teratas | **LightGBM klasifikasi horizon 4 jam positif di kedua fold untuk ketiga tingkat keyakinan.** Pengaturan yang dibekukan: keyakinan 2% teratas. |

## 3. Holdout 2015–2018 (sekali)

| Ukuran | Hasil |
|---|---|
| Edge kotor (tanpa spread) | **+$0,39 per trade, t = 2,11, menang 60,1%**, 318 trade. Sinyalnya nyata. |
| Edge bersih (spread asli) | +$0,095 per trade, t = 0,51 |
| Bersih + slippage 0,05 | ≈ $0 |
| Per tahun (bersih) | 2015 +$55,9 · 2016 −$0,3 · 2017 −$24,7 · 2018 −$0,5 |
| **Vonis** | **TIDAK LOLOS** |

Pipeline final `sapu_jagad_alpha.py` memakai 45 fitur dan stop pengaman 6×ATR. Hasil holdout-nya: +$0,165 per trade, t = 0,68, menang 55%, 306 trade, dan juga **TIDAK LOLOS**.

Catatan: holdout ini sudah pernah dilihat sekali di run pertama, jadi angka kedua ini bukan uji out-of-sample murni.

## Kesimpulan

1. Di data emas 2011–2018 **ada sinyal arah 4 jam yang nyata tetapi kecil**, sekitar 3 basis poin per trade. Sinyal ini sebanding dengan biaya spread pada masa itu (sekitar 2,4 bp). Setelah biaya, tidak ada alpha yang lolos uji.
2. Biaya relatif emas sekarang jauh lebih kecil. Apakah sinyal serupa masih ada **dan** menutup biaya di 2023–2026 hanya bisa dijawab dengan data terbaru. Untuk itu jalankan `Tools/sapu_jagad_alpha.py` (atau `JALANKAN_ALPHA.bat`) pada data M1 dari broker Anda.
3. Model yang dikirim bersama EA (`Files/sapu_jagad_alpha.txt`) berstatus **TIDAK LOLOS**. EA hanya memantau dan tidak akan trading dengan model ini, kecuali `InpAlphaAllowUnvalidated=true`.

## Verifikasi teknis

- **Paritas model:** evaluator file model (logika yang sama dengan `AlphaPredict()` di EA) identik dengan LightGBM, dengan selisih maksimum 0.
- **Paritas fitur (uji cermin):** `AlphaFeatures()` versi MQL5, diterjemahkan baris demi baris ke Python, identik dengan pipeline pada 300 candle acak 2016. Selisih maksimumnya 5,6×10⁻⁸, dari titik awal EMA.
- **Paritas di terminal Anda:** set `InpAlphaDumpFeatures=true` di Strategy Tester, lalu jalankan:

  ```
  python sapu_jagad_alpha.py --data <data M1 yang sama> --cek-paritas sapu_jagad_alpha_fitur_ea.csv
  ```
