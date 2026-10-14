# EA SAPU JAGAD v1.20 — Grid Adaptif-Rezim XAUUSD (MetaTrader 5)

EA ini dibangun dari pengamatan dua video. Logika di keduanya ditiru, lalu digabung oleh **detektor rezim pasar**. Ada juga lapisan kecerdasan untuk sesi, rilis berita, dan volatilitas.

> **STATUS: GAGAL uji data emas asli (Mei 2011 – Juni 2018, ±7,1 tahun).** Dengan pengaturan default, EA ini menghabiskan akun $10.000 baik di periode 2011–2014 maupun 2015–2018. Tiruan kedua video juga jebol di salah satu periode. Jangan dipakai di akun uang nyata. Rincian dan cara mengujinya dengan data Anda sendiri ada di bagian 4 dan 5.

| File | Fungsi |
|---|---|
| `Experts/EA_SAPU_JAGAD.mq5` | Kode EA (MQL5) |
| `Presets/EA_SAPU_JAGAD_XAUUSD.set` | Preset utama (adaptif + semua proteksi) |
| `Presets/EA_SAPU_JAGAD_Tiruan_Video.set` | Tiruan video 1, tanpa proteksi, hanya untuk pembanding |
| `Presets/EA_SAPU_JAGAD_Tiruan_Video2.set` | Tiruan video 2, tanpa proteksi, hanya untuk pembanding |
| `Files/sapu_jagad_news.csv` | Contoh format jadwal berita untuk backtest (ganti dengan jadwal asli) |
| `tools/sapu_jagad_forensik.py` | Alat uji forensik / replay / sweep / walk-forward untuk dataset Anda |

---

## 1. Hasil pengamatan video

### Video 1 — "Steev GTS V4.4" (momentum)

| Pengamatan | Detail |
|---|---|
| Cara yang **salah** (tanda X) | Grid statis dua arah di M5: 10 BUY STOP di atas dan 10 SELL STOP di bawah harga, jarak 0.30, lot 0.01. Di pasar bolak-balik, kedua sisi terisi lalu saling mengunci rugi. |
| Cara yang **benar** (tanda ✓) | Satu arah saja: 8 BUY STOP berjarak 0.50, level pertama sekitar 2.0 di atas harga, di M1. |
| Trailing | Saat harga turun, seluruh tangga BUY STOP **ikut turun mengejar harga** (sempat dihapus lalu dipasang ulang lebih rendah). |
| Entry | Saat harga berbalik naik, BUY STOP terisi satu per satu (4172.12 → 4172.62 → 4173.12 → …), jadi entry searah momentum. |
| Exit | Semua posisi ditutup bersama ketika total profit positif, termasuk posisi lama BUY 0.03 @ 4175.02 yang tadinya minus. |

### Video 2 — grid LIMIT rapat (mean-reversion)

| Pengamatan | Detail |
|---|---|
| Akun | XAUUSDc (akun cent), M5, lot 0.01 |
| Fase beli | Sekitar 30 **BUY LIMIT** rapat di bawah harga, jarak 0.25 (4149.274 sampai 4142.774). Posisi terisi saat harga turun (4150.161, 4149.774, 4149.524, …). |
| Exit | Saat harga memantul naik, semua posisi ditutup sekaligus dengan profit. |
| Fase jual | Sisi dibalik: sekitar 28 **SELL LIMIT** di atas harga (4150.893 sampai 4157.893) untuk memudarkan reli. |
| Risiko | Tidak terlihat stop loss. Kalau harga terus searah, semua level terisi dan tidak ada rem. |

### Bisakah digabung?

**Bisa, dan secara kuantitatif keduanya saling melengkapi.** Grid momentum (video 1) menang saat pasar **trending**. Grid reversion (video 2) menang saat pasar **ranging**, yaitu ketika harga memantul ke rata-rata. Masing-masing rugi besar di rezim lawannya. Jadi yang menentukan adalah **mengenali rezim**, bukan jumlah level atau jarak grid.

SAPU JAGAD memakai **Efficiency Ratio Kaufman** (ER) pada bar M1:

```
ER = |harga sekarang - harga N bar lalu| / jumlah |perubahan tiap bar|
ER >= 0.30  -> TREN   : mesin MOMENTUM, searah gerak (+ konfirmasi EMA H1)
ER <= 0.12  -> RANGE  : mesin REVERSION, bila harga cukup jauh dari EMA M5 (z-score)
di antaranya -> NETRAL : tidak membuka basket baru (pasar acak = tidak ada edge)
```

> Jujur soal "edge": tidak ada susunan grid yang otomatis profit. Di data acak, semua grid kalah oleh biaya spread. Edge hanya ada kalau (1) detektor rezim benar-benar mengenali pasar emas Anda, (2) biaya terkendali, dan (3) ekor risiko dipotong. Ketiganya harus **dibuktikan di dataset asli** dengan alat forensik dan uji walk-forward (bagian 5).
>
> **Hasil uji data asli 2011–2018: gagal.** Di data itu, pengalih rezim ini **tidak** menunjukkan edge: mesin momentum tetap rugi walaupun hanya dibuka di rezim TREN (lihat bagian 4b). Gagasan penggabungannya masuk akal di atas kertas, tetapi belum terbukti di pasar.

---

## 2. Arsitektur EA v1.20

```
                ┌──────────────────────── DETEKTOR REZIM (ER M1, z-score M5, EMA H1) ─────────────────┐
                │                                                                                      │
   TREN ────────┼──► MESIN MOMENTUM  (slot 0/1, magic)     BUY/SELL STOP mengejar harga  [video 1]     │
   RANGE ───────┼──► MESIN REVERSION (slot 4/5, magic+2)   BUY/SELL LIMIT statis         [video 2]     │
   RILIS BERITA ┼──► MESIN BERITA    (slot 2/3, magic+1)   STOP searah impuls pasca rilis              │
                └──────────────────────────────────────────────────────────────────────────────────────┘
   Lapisan proteksi: perisai berita · penjaga volatilitas & burst · rollover · anti stop-hunt buka sesi
                     · spread · margin · cut loss basket (% saldo) · penuaan basket · larangan tambah
                       melawan tren · kunci profit · drawdown global & batas harian · tutup Jumat
```

---

## 3. Kelemahan saat sesi & berita, dan kecerdasan yang ditambahkan

| Kelemahan (grid stop/limit biasa) | Kecerdasan SAPU JAGAD | Parameter |
|---|---|---|
| Lonjakan berita mengisi **seluruh tangga** dalam satu candle di harga terburuk, lalu harga berbalik (whipsaw) | **Perisai berita**: semua pending dihapus X menit sebelum sampai Y menit sesudah rilis. Basket yang sedang profit diamankan sebelum rilis. | `InpUseNewsFilter`, `InpNewsBeforeMin`, `InpNewsAfterMin`, `InpNewsBankProfit` |
| Momentum pasca berita terlewat | **Penunggang berita**: tunggu lonjakan dan spread reda, ukur impuls terhadap harga pra-rilis. Bila impuls ≥ 1,5×ATR, pasang tangga stop kecil **searah impuls** dengan TP, SL, dan batas waktu sendiri. | `InpNewsRide`, `InpNewsSettleSec`, `InpNewsImpulseATR`, `InpNewsTPPerMinLot`, `InpNewsSLPerMinLot` |
| Kalender MT5 tidak tersedia di Strategy Tester, jadi filter berita tidak bisa diuji | Jadwal berita bisa dimuat dari **file CSV** (Common\Files) | `InpNewsSource`, `InpNewsCsvFile` |
| BUY STOP dipicu harga **Ask**, sehingga lonjakan spread saat rollover bisa mengisi order palsu | **Penjaga rollover** (20:50–23:10 GMT) dan filter spread | `InpRolloverGuard`, `InpMaxSpread` |
| Pembukaan London/New York sering **stop-hunt** dua arah | **Anti stop-hunt**: tidak membuka entry X menit setelah pembukaan sesi | `InpOpenGuardMin` |
| Jarak tetap terlalu rapat saat volatilitas naik | **Penjaga volatilitas**: jarak melebar otomatis saat range candle ≥ 2×ATR. Pending dihapus dan entry berhenti saat ≥ 4×ATR. | `InpVolGuard`, `InpVolWidenRatio`, `InpVolBlockRatio` |
| Banyak stop terisi bersamaan (exposure meledak) | **Penjaga burst**: ≥ 5 terisi dalam 30 detik, penambahan dijeda | `InpBurstMaxFills`, `InpBurstSeconds` |
| Basket momentum terus menambah posisi melawan tren (ekor rugi fatal) | **Larangan menambah melawan tren**, **cut loss basket % saldo**, **penuaan basket** (>24 jam turun ke target impas) | `InpNoAddAgainstTrend`, `InpBasketSLPct`, `InpBasketAgeHours` |
| Grid limit (video 2) tanpa rem | Reversion: **cut loss per lot**, **batas waktu**, keluar impas bila rezim berubah menjadi tren melawan, hanya beli saat turun di tren naik | `InpRevSLPerMinLot`, `InpRevMaxHoldMin`, `InpRevRegimeExit`, `InpRevWithTrendOnly` |
| Karakter sesi berbeda | **Profil sesi** Asia/London/NY: aktif/nonaktif dan pengali jarak per sesi | `InpTradeAsia/London/NY`, `InpAsiaStepMult`, … |

---

## 4. Hasil uji: data sintetis, lalu data emas asli 7,1 tahun

### 4a. Uji awal di data sintetis (4 bulan) — dan biasnya

Uji pertama hanya memakai data **sintetis** buatan sendiri selama 4 bulan. Hasilnya tampak bagus (+$778, PF 1.89, DD 7,6%), tetapi ada tiga bias yang membuatnya **tidak bisa dipercaya**:

1. Default (jumlah level reversion, jarak ATR, konfirmasi H1) dipilih setelah melihat hasil di data sintetis yang sama. Itu pemilihan in-sample.
2. Data berezim itu dirancang sendiri, dengan rezim yang memang mudah dikenali oleh detektor ER.
3. Mode tanpa kalender sempat memakai lonjakan harga yang dideteksi dari data itu sendiri untuk perisai berita. Itu sama dengan mengintip masa depan. **Sudah diperbaiki**: lonjakan hasil deteksi kini hanya dipakai sebagai label laporan.

### 4b. Uji data emas asli 2011–2018 (tanpa mengintip data depan)

**Sumber data:** tick XAUUSD Dukascopy dari repositori publik FX-Data, sekitar 230 juta tick, diringkas menjadi bar M1 dengan spread asli rata-rata per menit. Semua waktu dalam GMT.

**Cacat data yang ditangani:** jam 00:00–01:00 GMT hilang setiap hari. Celah ini dikenali, dan order yang terlewati diisi di harga ordernya. Perlakuan ini berlaku sama untuk semua konfigurasi.

**Protokol anti-bias:**
- Indikator hanya memakai bar yang sudah tutup.
- Tidak ada lonjakan hasil deteksi yang dipakai untuk keputusan trading.
- Data dibagi menjadi **desain 2011–2014** (boleh dibedah) dan **holdout 2015–2018** (disentuh sekali, untuk evaluasi akhir).
- Tiap periode dimulai dengan saldo $10.000, lot 0.01.

| Konfigurasi | 2011–2014 (desain) | 2015–2018 (holdout) |
|---|---|---|
| **SAPU JAGAD v1.20 default** | **−$10.418, DD 104% (akun habis)** | **−$10.009, DD 100% (akun habis)** |
| Tiruan video 1 (momentum, tanpa SL) | −$19.593, DD 163% (jebol di 2014) | +$6.187, DD 82% (floating terburuk −$9.843) |
| Tiruan video 2 (limit, tanpa SL) | −$6.907, DD 90% (jebol di 2014) | +$4.223, DD 38% (floating terburuk −$6.617) |

**Temuan forensik (data asli):**
- Basket di kondisi **normal hampir impas**: 2015–2018 ada 2.724 basket dengan net −$514.
- Hampir seluruh kerugian datang dari basket yang **tersentuh lonjakan harga**: 276 basket, −$9.495.
- Mesin MOMENTUM adalah penyumbang rugi terbesar (2015–2018: −$8.822; 65 kali cut loss senilai −$13.128).
- Mesin REVERSION juga negatif: banyak TP kecil, dikalahkan cut loss.
- **Bukan masalah biaya**: dengan spread hampir nol pun, default tetap menghabiskan akun di 2011–2014 (PF 0,62).
- Percobaan perbaikan di data desain tidak menolong, sehingga **tidak dimasukkan ke EA**. Yang dicoba: perisai jam rilis AS tanpa kalender, keluar darurat saat lonjakan, cut loss basket 2%, reversion dimatikan, dan jarak berbasis ATR.
- Dilema grid terlihat jelas. Tanpa cut loss, grid untung bertahun-tahun lalu jebol (tiruan video). Dengan cut loss, grid berdarah pelan-pelan (SAPU JAGAD).

**Batas berlakunya kesimpulan:** data 2011–2018 berasal dari era harga emas $1.050–1.900 dengan spread Dukascopy sekitar $0.36. Kondisi emas 2023–2026 berbeda: harga lebih tinggi, pergerakan per menit lebih besar, dan spread relatif lebih kecil. Kesimpulan "tidak ada edge" kuat untuk 2011–2018, tetapi untuk kondisi terkini **harus diuji dengan data terbaru Anda** memakai protokol yang sama (bagian 5).

## 5. Uji forensik dengan dataset Anda (drive D)

Hanya butuh Python 3.8+ tanpa pustaka tambahan. Jalankan di komputer yang punya drive D:

```bat
cd C:\path\ke\repo\mql5\tools

:: 1) replay + bandingkan dengan tiruan kedua video (semua file XAU/GOLD di D:\dataset dipindai)
python sapu_jagad_forensik.py --data "D:\dataset" --gmt-offset 2 --compare

:: 2) pakai jadwal berita asli (waktu GMT) agar analisis berita jujur
python sapu_jagad_forensik.py --data "D:\dataset" --news "D:\news.csv" --gmt-offset 2 --compare

:: 3) uji anti-overfitting: cari parameter di 70% data awal, uji di 30% sisanya
python sapu_jagad_forensik.py --data "D:\dataset" --news "D:\news.csv" --gmt-offset 2 --walk-forward 0.7

:: 4) uji ketahanan: biaya 2x, slippage, variasi parameter +/-30%, per tahun, Monte Carlo
python sapu_jagad_forensik.py --data "D:\dataset" --gmt-offset 2 --ketahanan

:: 5) uji konfigurasi tertentu dari file .set EA
python sapu_jagad_forensik.py --data "D:\dataset" --set ..\Presets\EA_SAPU_JAGAD_XAUUSD.set --from 2025-01-01
```

Opsi penting:

- `--gmt-offset`: selisih jam waktu data/server broker terhadap GMT. Exness = 0; banyak broker = 2 (musim panas 3).
- `--point`: 0.01 untuk harga 2 digit, 0.001 untuk 3 digit. Hanya dipakai untuk kolom spread data bar.
- `--symbol-filter ""`: pindai semua file, bukan hanya yang namanya mengandung XAU/GOLD.
- Celah data di tengah sesi (lebih dari 10 menit, bukan jeda harian/akhir pekan) dikenali otomatis dan tidak dihitung sebagai lonjakan pasar.

**Aturan anti mengintip data:**
- Tanpa `--news`, perisai berita tidak aktif di replay.
- Pakai `--walk-forward` atau pisahkan sendiri data desain dan holdout.
- Jangan mengubah parameter setelah melihat hasil holdout.

Format data yang dikenali otomatis: ekspor tick/bar MT5, CSV umum (waktu + bid/ask atau OHLC), Dukascopy, dan HistData.

Hasil di folder `hasil_forensik/`:

- `laporan_forensik_*.md`: ringkasan, per sesi, per jam GMT, **per mesin × rezim**, berita vs normal, 15 basket terburuk, **analisis MAE** (batas cut loss optimal), temuan kelemahan + rekomendasi parameter, dan walk-forward.
- `basket_*.csv`: setiap basket dengan waktu buka/tutup, sesi, rezim, ER, MAE/MFE, burst, rasio volatilitas, dan alasan tutup.
- `ekuitas_*.csv`: kurva ekuitas per jam.
- `EA_SAPU_JAGAD_terbaik.set`: parameter terbaik (bila `--sweep`), siap dimuat di MT5.

Alur kalibrasi yang disarankan:

1. Jalankan replay dengan `--compare` dan baca bagian "Temuan kelemahan".
2. Terapkan rekomendasinya ke file `.set`, lalu replay ulang untuk konfirmasi.
3. Jalankan `--walk-forward 0.7`. Hanya pakai parameter yang **tetap positif di kolom OOS**.
4. Backtest di Strategy Tester MT5 dengan "Every tick based on real ticks" dan file berita CSV.
5. Jalankan di akun demo minimal 2–4 minggu, lalu live dengan lot kecil (akun cent cocok untuk ini).

---

## 6. Instalasi & backtest di MT5

1. Salin `Experts/EA_SAPU_JAGAD.mq5` ke `MQL5\Experts\`. Buka di MetaEditor, lalu tekan **Compile (F7)**.
2. Salin `Presets/*.set` ke `MQL5\Presets\`.
3. Untuk backtest berita, salin `Files/sapu_jagad_news.csv` (isi dengan jadwal asli, **waktu GMT**) ke folder **Common\Files** terminal (`File > Open Data Folder`, naik ke `..\..\Common\Files`).
4. Pasang EA di chart XAUUSD (timeframe bebas; logika berjalan per tick), aktifkan **Algo Trading**, lalu muat preset.
5. Akun **hedging** disarankan. Di akun netting, posisi digabung dan EA memberi peringatan.

Atur zona waktu sesuai broker: `InpGMTOffset` (-99 = otomatis saat live) dan `InpTesterGMTOffset` (wajib diisi saat backtest).

---

## 7. Parameter terpenting

| Kelompok | Parameter | Default | Keterangan |
|---|---|---|---|
| Mesin | `InpEngineMode` | Adaptif | Momentum saja / Reversion saja / Adaptif |
| Rezim | `InpERTrend` / `InpERRange` | 0.30 / 0.12 | Ambang TREN / RANGE |
| Momentum | `InpGridLevels`, `InpGridStep`, `InpStartDistance` | 8, 0.50, 2.00 | Sesuai video 1 |
| Reversion | `InpRevLevels`, `InpRevStep`, `InpRevStepATR` | 6, 0.25, 0.3 | Video 2 memakai 30 level, dikecilkan demi keamanan |
| Reversion | `InpRevZEntry` | 0.8 | Jarak minimal harga ke EMA M5 dalam satuan ATR M5 |
| Target | `InpTPValue`, `InpRevTPPerMinLot` | 1.00, 0.50 | USD per 0.01 lot terbuka |
| Risiko | `InpBasketSLPct`, `InpMaxDrawdownPct` | 10%, 30% | Cut loss basket dan rem global |
| Berita | `InpNewsBeforeMin`, `InpNewsAfterMin` | 15, 30 | Jendela perisai berita |

Semua jarak ditulis dalam **satuan harga** (0.50 = 50 sen), sehingga aman untuk broker 2 maupun 3 digit.

---

## 8. Batasan & peringatan

- **EA belum dikompilasi di lingkungan pembuatannya** karena MetaEditor tidak tersedia di container cloud. Kode sudah diperiksa statis (kurung, fungsi, jumlah argumen). Bila MetaEditor menampilkan error atau warning saat Compile, kirimkan pesannya untuk diperbaiki.
- Alat forensik meniru logika EA, tetapi **bukan pengganti** Strategy Tester. Slippage, swap, margin, dan eksekusi broker nyata bisa berbeda.
- **Uji data asli 2011–2018 gagal** (bagian 4b). EA ini belum layak untuk uang nyata. Ujilah dulu di data terbaru Anda, lalu di akun demo.
- Trading emas dengan grid berisiko tinggi. Hasil masa lalu **tidak menjamin** hasil masa depan. Gunakan modal yang siap hilang.
