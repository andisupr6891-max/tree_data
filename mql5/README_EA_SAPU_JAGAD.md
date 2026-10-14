# EA SAPU JAGAD v1.20 — Grid Adaptif-Rezim XAUUSD (MetaTrader 5)

EA ini dibangun dari pengamatan dua video. Logika di keduanya ditiru, lalu digabung oleh **detektor rezim pasar**. Ada juga lapisan kecerdasan untuk sesi, rilis berita, dan volatilitas.

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

## 4. Hasil uji forensik sementara (data SINTETIS)

Data asli belum tersedia di sesi pembuatan EA. Folder Download dan drive D ada di komputer Anda, bukan di container cloud. Jadi uji di bawah memakai **data sintetis** XAUUSD M1 selama 4 bulan. Fungsinya **memvalidasi mekanisme**, bukan membuktikan profit.

**Data berezim** (blok 4 jam: tren / range memantul / acak):

| Konfigurasi | Net | Win% | Profit factor | Max DD | MAE terburuk |
|---|---|---|---|---|---|
| **SAPU JAGAD v1.20** | **+778** | 89% | **1.89** | **7.6%** | −796 |
| Tiruan video 1 | −1.468 | 99% | 0.51 | 45.7% | −5.263 |
| Tiruan video 2 | −2.023 | 99% | 0.23 | 56.8% | −6.021 |

- Win rate 99% pada kedua tiruan video adalah ciri khas grid: banyak untung kecil, lalu satu basket menghapus semuanya.
- Edge SAPU JAGAD di data ini datang dari **MOMENTUM di rezim TREN** (+1.121). Mesin **REVERSION** masih sedikit negatif (−345), jadi harus dikalibrasi di data asli.
- **Walk-forward** (cari parameter di 70% data awal, uji di 30% akhir): default tetap positif di out-of-sample (+215). Satu kandidat yang terbaik di in-sample justru rugi −724 di out-of-sample. Contoh overfitting seperti ini yang harus disaring.

**Data acak + berita** (tanpa pola): SAPU JAGAD hampir impas (−125, DD 10.9%). Tiruan video 1 kehilangan −9.038 dengan DD 168% (akun jebol). Di data tanpa pola tidak ada sistem yang bisa untung; yang bisa dilakukan hanya **bertahan**.

---

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

:: 4) uji konfigurasi tertentu dari file .set EA
python sapu_jagad_forensik.py --data "D:\dataset" --set ..\Presets\EA_SAPU_JAGAD_XAUUSD.set --from 2025-01-01
```

Opsi penting:

- `--gmt-offset`: selisih jam waktu data/server broker terhadap GMT. Exness = 0; banyak broker = 2 (musim panas 3).
- `--point`: 0.01 untuk harga 2 digit, 0.001 untuk 3 digit. Hanya dipakai untuk kolom spread data bar.
- `--symbol-filter ""`: pindai semua file, bukan hanya yang namanya mengandung XAU/GOLD.

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
- Trading emas dengan grid berisiko tinggi. Hasil masa lalu, apalagi data sintetis, **tidak menjamin** hasil masa depan. Gunakan modal yang siap hilang.
