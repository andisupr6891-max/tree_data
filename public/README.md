# 🌳 TREE DATA v3.0.0 — Sistem Trading Otomatis XAU/USD Ultra-Kuantitatif

> **Klien**: Kembang Ayu Andini  
> **Versi**: 3.0.0 (ULTIMATE EDITION)  
> **Aset**: XAU/USD (Emas) | Format Harga 3-Desimal | Broker Exness MT5

---

## 📖 Deskripsi Utama

TREE DATA v3.0.0 adalah sistem perdagangan otomatis multi-engine tingkat institusional yang dirancang khusus untuk pasangan mata uang **XAU/USD (Emas)** menggunakan filosofi **Psychological & Liquidity Capture** berbasis data CME Group. Sistem ini menggabungkan **14 model prediksi matematis** dalam sebuah mesin arbitrase terpadu bernama **"Sang Hakim"**, yang secara dinamis mengadaptasi bobot model berdasarkan kondisi pasar aktif (regime).

### Filosofi Inti
- **Sniper Scalping**: Eksekusi presisi tinggi di titik saturasi likuiditas lokal untuk meminimalkan floating drawdown
- **Institutional Tracking**: Deteksi kepanikan ritel, dinding likuiditas, jebakan pasar, dan perburuan stop-loss
- **Dynamic Regime Switching**: Pelacakan `$S_t$` menggunakan ATR(14) dan σ rolling 1000 tik
- **Self-Learning MWUM**: Pembaruan bobot eksponensial berbasis hasil perdagangan nyata

---

## ⚡ Fitur Utama

### 1. 14-Model Predictive Voting Interface

| ID | Model | Kategori | Fungsi |
|----|-------|----------|--------|
| 0 | Black-Scholes Pricing Engine | QUANT | Bias delta-neutral dari opsi |
| 1 | Implied Volatility Surface | QUANT | Skew IV dari CME options chain |
| 2 | GARCH(1,1) Volatility Forecast | STATISTICAL | Estimasi volatilitas kondisional |
| 3 | Hidden Markov Model | ML | Deteksi state tersembunyi pasar |
| 4 | Kalman Filter State Estimator | STATISTICAL | Estimasi harga sejati vs noise |
| 5 | Monte Carlo Simulation | STATISTICAL | Simulasi probabilitas jalur harga |
| 6 | Ornstein-Uhlenbeck Process | QUANT | Mean-reversion signal generator |
| 7 | Fourier Spectral Analysis | STATISTICAL | Deteksi siklus dominan via FFT |
| 8 | Deep Reinforcement Learning | ML | Policy Q-learning adaptif |
| 9 | Stochastic Calculus (Itô) | QUANT | Drift Itô berbobot volatilitas |
| 10 | Orderflow Imbalance Analysis | MARKET_MICROSTRUCTURE | Tekanan beli vs jual real-time |
| 11 | Gamma Exposure (GEX) | MARKET_MICROSTRUCTURE | Pengaruh gamma dealer |
| 12 | Regime Detection Engine | ML | Klasifikasi trending/ranging/volatile |
| 13 | Liquidity Profile Scanner | MARKET_MICROSTRUCTURE | Profil OI + akselerasi volume |

### 2. Sang Hakim Master Decision Engine
```
D_final = Σ(i=1→14) W_i,regime × V_i
```
- Threshold α = 0.80 untuk trigger eksekusi
- Split order ke 3 horizon: Scalping Sniper (α≥0.80), Intraday (α≥0.88), Long-Term (α≥0.95)

### 3. MWUM Closed-Loop Self-Learning
```
L_i = (1 - V_i × O) / 2
w_i^(t+1) = w_i^(t) × (1-η)^L_i
```
- Normalisasi Softmax setelah setiap update: Σ W_i = 1.0
- η = 0.12 (learning rate)
- Cache RAM/SQLite → async sync ke Supabase

### 4. Dynamic Risk Budgeting
- **Scalping**: 2-5% per trade
- **Intraday**: 10-15% per trade  
- **Long-Term**: 20-25% per trade
- **Total Cap**: 40% ekuitas maksimum

### 5. Circuit Breaker & Fail-Safe
- Hard daily drawdown breaker: 12% ekuitas
- 3-Sigma Spread Anomaly Detector (Z-score ≥ 3)
- Fatal Cutoff via Telegram `/fatalcutoff` atau UI button
- Independent polling thread: setiap 500ms

---

## 🏗️ Arsitektur Teknologi

```
┌─────────────────────────────────────────────────────────────┐
│                    TREE DATA v3.0.0                         │
├─────────────────────────────────────────────────────────────┤
│  DATA SOURCES          PROCESSING          EXECUTION        │
│  ┌──────────┐         ┌──────────┐        ┌──────────┐     │
│  │ CME Group│──HTTP/2→│ 14 Models│→Voting→│Exness MT5│     │
│  │ (Akamai) │         │ Registry │        │ (Decimal)│     │
│  └──────────┘         └──────────┘        └──────────┘     │
│  ┌──────────┐         ┌──────────┐        ┌──────────┐     │
│  │TradingView│─HMAC──→│Sang Hakim│→Signal→│ Order    │     │
│  │ Webhook  │         │  Engine  │        │ Router   │     │
│  └──────────┘         └──────────┘        └──────────┘     │
├─────────────────────────────────────────────────────────────┤
│  INFRASTRUCTURE                                             │
│  GitHub → Vercel → Supabase → Telegram → Google Sheets     │
│  N8N Orchestration → Playwright Stealth → Tesseract OCR    │
└─────────────────────────────────────────────────────────────┘
```

### Stack Teknologi
| Layer | Teknologi |
|-------|-----------|
| Backend Engine | Python 3.11+ |
| Data Fetch | `httpx` (HTTP/2, JA3 Rotation) |
| Database | Supabase PostgreSQL (Real-Time) |
| Web API | FastAPI + HMAC-SHA256 |
| Frontend | React/Vite + Tailwind CSS → Vercel |
| Broker | Exness MT5 via `MetaTrader5` library |
| Orchestration | N8N (Event-Driven Flows) |
| Alerting | Telegram Bot API |
| Secondary Log | Google Sheets API |
| Fallback Scraping | Playwright Stealth + Tesseract OCR |

---

## 🚀 Panduan Instalasi & Deployment

### Prasyarat
```bash
Python 3.11+
Node.js 18+
MetaTrader 5 (Windows/VPS)
Akun Exness Pro/Zero
Akun Supabase (Free Tier)
Akun Vercel (Free Tier)
Telegram Bot Token
```

### 1. Clone & Install
```bash
git clone https://github.com/kembangayu/tree-data-v3.git
cd tree-data-v3
pip install -r requirements.txt
npm install && npm run build
```

### 2. Konfigurasi Environment
```bash
cp .env.example .env
# Edit .env dengan kredensial Anda:
```
```env
# Supabase
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=eyJhbGc...

# Exness MT5
MT5_LOGIN=12345678
MT5_PASSWORD=yourpassword
MT5_SERVER=Exness-MT5Real8

# Telegram
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_CHAT_ID=-100123456789

# Security
WEBHOOK_HMAC_SECRET=your-256-bit-secret-key

# Google Sheets
GOOGLE_SHEETS_ID=1BxiM...
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account"...}
```

### 3. Supabase Schema Setup
```sql
-- Jalankan di Supabase SQL Editor:

CREATE TABLE trade_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    side VARCHAR(4), horizon VARCHAR(20),
    entry_price DECIMAL(10,3), exit_price DECIMAL(10,3),
    lot_size DECIMAL(6,2), tp DECIMAL(10,3), sl DECIMAL(10,3),
    pnl DECIMAL(10,2), status VARCHAR(20),
    d_final DECIMAL(8,5), regime VARCHAR(20)
);

CREATE TABLE system_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    level VARCHAR(10), module VARCHAR(30), message TEXT,
    data JSONB
);

CREATE TABLE model_weights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    model_id INTEGER, model_name VARCHAR(50),
    weight_trending DECIMAL(10,6), weight_ranging DECIMAL(10,6),
    regime VARCHAR(20)
);

CREATE TABLE cme_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    open_interest BIGINT, volume BIGINT,
    call_put_ratio DECIMAL(6,3), implied_vol DECIMAL(6,4),
    gex BIGINT, delta DECIMAL(6,4)
);

-- Enable Real-Time untuk semua tabel
ALTER TABLE trade_records REPLICA IDENTITY FULL;
ALTER TABLE system_logs REPLICA IDENTITY FULL;
```

### 4. Menjalankan Sistem
```bash
# Terminal 1: FastAPI Webhook Server
uvicorn webhook_receiver:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: Main Trading Engine
python main.py --mode live --symbol XAUUSD --magic 300000

# Terminal 3: Streamlit Dashboard (opsional lokal)
streamlit run app_dashboard.py --server.port 8501

# Atau deploy ke Vercel (frontend React):
vercel --prod
```

### 5. Konfigurasi TradingView Webhook
Di TradingView Alert Settings:
```
Webhook URL: https://your-domain.com/webhook/tradingview
Message Body:
{
  "symbol": "{{ticker}}",
  "action": "{{strategy.order.action}}",
  "price": {{close}},
  "strategy": "{{strategy.order.id}}",
  "timestamp": {{timenow}},
  "hmac_signature": "GENERATED_BY_TV_PINESCRIPT"
}
```

### 6. N8N Orchestration Setup
1. Import workflow dari `n8n/workflows/cme_fallback.json`
2. Konfigurasi credential Playwright di N8N
3. Set trigger: "Ketika harga spot menyentuh level target"
4. Output → Tesseract OCR → Parse data CME → POST ke `/webhook/cme-update`

### 7. Deploy ke Vercel
```bash
# Login Vercel
vercel login

# Set environment variables
vercel env add NEXT_PUBLIC_SUPABASE_URL
vercel env add NEXT_PUBLIC_SUPABASE_ANON_KEY

# Deploy
vercel --prod
```

---

## 📊 Contoh Kasus Operasional (Simulasi Siklus)

### Skenario: Eksekusi BUY XAU/USD

```
T+00:00 │ TICK INGESTION
        │ Bid: 3318.542 | Ask: 3318.754 | Spread: 0.212
        │ Session: LONDON OVERLAP | Volume: 847
        │
T+00:00 │ ATR CALCULATION (14-period)
        │ ATR_current: 0.847 | ATR_mean: 0.521
        │ γ × mean = 1.5 × 0.521 = 0.782
        │ ATR > 0.782 → REGIME = REGIME_TRENDING
        │
T+00:01 │ CME DATA (dari RAM cache, age: 4:23)
        │ OI: 587,234 | CPR: 1.182 | IV: 16.43%
        │ GEX: -2,340,000 | Delta: +0.0821
        │
T+00:02 │ 14-MODEL VOTING [TRENDING WEIGHTS AKTIF]
        │ BS    W=7.24% V=+0.731 → +0.05293
        │ IV    W=6.53% V=+0.624 → +0.04075
        │ GARCH W=7.21% V=+0.812 → +0.05858
        │ HMM   W=8.02% V=+0.594 → +0.04764
        │ KF    W=6.81% V=+0.445 → +0.03030
        │ MC    W=6.01% V=+0.678 → +0.04075
        │ OU    W=5.51% V=-0.234 → -0.01289
        │ FFT   W=6.22% V=+0.521 → +0.03241
        │ DRL   W=9.02% V=+0.889 → +0.08020
        │ SDE   W=7.01% V=+0.712 → +0.04991
        │ OFA   W=8.51% V=+0.934 → +0.07949
        │ GEX   W=7.51% V=+0.756 → +0.05676
        │ RDE   W=8.02% V=+0.821 → +0.06584
        │ LPS   W=8.67% V=+0.645 → +0.05592
        │ ─────────────────────────────────
        │ D_final = +0.67859... → +0.679
        │
T+00:02 │ SANG HAKIM VERDICT
        │ |D_final| = 0.679 → WAIT (< α=0.80)
        │
T+02:15 │ [3 menit kemudian - setelah news release]
        │ D_final = +0.8934 ≥ α=0.80 → TRIGGERED!
        │ Horizon: INTRADAY (0.88 ≤ D < 0.95)
        │ Side: BUY
        │
T+02:15 │ RISK CHECK
        │ Daily DD: 2.3% / 12% ✓
        │ Spread Z-score: +0.82 < 3σ ✓
        │ Total Allocated: 18% / 40% ✓
        │ ENTRY ALLOWED ✓
        │
T+02:15 │ POSITION SIZING
        │ Risk%: 12% × 0.8934 = 10.72%
        │ Risk$: $50,000 × 10.72% = $5,360
        │ Lot: 5360 / (150 × 10) = 3.57 lots
        │
T+02:15 │ ORDER EXECUTION → Exness MT5
        │ BUY 3.57 XAUUSD @ 3318.754 (Ask)
        │ TP: 3321.754 (+3.000 pts = 2.0× SL)
        │ SL: 3317.254 (-1.500 pts)
        │ Magic: 300000 | Slippage: 3pts
        │ decimal.Decimal precision: ✓
        │
T+02:15 │ NOTIFICATIONS
        │ → Telegram: "🎯 BUY 3.57 XAUUSD @ 3318.754"
        │ → Supabase: INSERT trade_records async
        │ → Google Sheets: N8N log entry
        │
T+45:30 │ TP HIT
        │ Bid: 3321.812 ≥ TP 3321.754
        │ Exit @ 3321.754 | P&L: +$1,071.39
        │
T+45:30 │ MWUM UPDATE
        │ Outcome O = +1 (WIN)
        │ L_i = (1 - V_i × 1) / 2 untuk semua model
        │ Bobot model dengan V rendah dipenalti
        │ Normalisasi: Σ W_i,TRENDING = 1.000 ✓
        │ Cache lokal → async sync Supabase
```

---

## 🔐 Keamanan & Compliance

- **HMAC-SHA256**: Semua webhook TradingView diverifikasi kriptografi
- **JA3 Fingerprint Rotation**: Bypass deteksi bot Akamai WAF CME Group
- **Exponential Backoff**: Retry otomatis untuk error broker 10004/10014
- **Rate Limiter**: Token Bucket/Sliding Window untuk absorb burst signal
- **3-Decimal Precision**: `decimal.Decimal` untuk eliminasi floating-point drift

---

## 📁 Struktur Repository

```
tree-data-v3/
├── config.py                          # Global constants & parameters
├── main.py                            # Entry point
├── webhook_receiver.py                # FastAPI HMAC webhook server
├── app_dashboard.py                   # Streamlit/Dash retro UI
├── requirements.txt
├── .env.example
├── connectors/
│   └── meta_trader_gateway.py         # Exness MT5 API layer
├── engine/
│   ├── sang_hakim.py                  # Master decision arbiter
│   ├── data_learning_engine.py        # MWUM self-learning loop
│   └── risk/
│       └── fail_safe_engine.py        # Circuit breaker + 3σ detector
├── models/
│   ├── black_scholes.py
│   ├── implied_volatility.py
│   ├── garch.py
│   ├── hmm.py
│   ├── kalman_filter.py
│   ├── monte_carlo.py
│   ├── ornstein_uhlenbeck.py
│   ├── fourier_transform.py
│   ├── deep_rl.py
│   ├── stochastic_calculus.py
│   ├── orderflow_analysis.py
│   ├── gamma_exposure.py
│   ├── regime_detection.py
│   └── liquidity_profile.py
├── n8n/
│   └── workflows/
│       └── cme_fallback.json
├── frontend/
│   └── src/                           # React/Vite dashboard
└── README.md
```

---

*TREE DATA v3.0.0 © 2025 Kembang Ayu Andini — Sistem Trading XAU/USD Institusional*
