//+------------------------------------------------------------------+
//|                                               EA_SAPU_JAGAD.mq5  |
//|     Grid adaptif-rezim untuk XAUUSD (MetaTrader 5)               |
//|                                                                  |
//|  Gabungan dua logika dari video yang dipelajari:                 |
//|   * MESIN MOMENTUM (video 1, "Steev GTS V4.4"): tangga BUY/SELL  |
//|     STOP yang mengejar harga dan terisi saat harga berbalik.     |
//|   * MESIN REVERSION (video 2): tangga BUY/SELL LIMIT rapat yang  |
//|     menangkap pantulan harga kembali ke rata-rata.               |
//|   * MESIN BERITA: tangga stop searah impuls setelah rilis.       |
//|                                                                  |
//|  Detektor rezim (Efficiency Ratio Kaufman) memilih mesin:        |
//|   TREN  -> momentum searah gerak, RANGE -> reversion,            |
//|   NETRAL -> tidak membuka basket baru.                           |
//|                                                                  |
//|  Kecerdasan lain: perisai & penunggang berita, penjaga           |
//|  volatilitas/burst/rollover/pembukaan sesi, profil sesi,         |
//|  kunci profit, recovery, cut loss basket, larangan menambah      |
//|  melawan tren, proteksi drawdown, berita via CSV untuk backtest. |
//|                                                                  |
//|  v1.30 MESIN ALPHA: model LightGBM dari sapu_jagad_alpha.py,     |
//|  45 fitur candle M15 (bobot candle, momentum, rezim, waktu),     |
//|  trading hanya bila file model berstatus LOLOS validasi.         |
//+------------------------------------------------------------------+
#property copyright   "EA SAPU JAGAD"
#property version     "1.30"
#property description "EA SAPU JAGAD - grid adaptif-rezim XAUUSD"
#property description "Momentum (stop) + Reversion (limit) + Berita, dipilih oleh detektor rezim"
#property description "dengan kecerdasan sesi, berita, volatilitas, proteksi risiko, dan Mesin ALPHA (model ML)."

#include <Trade\Trade.mqh>

//--- enum parameter
enum ENUM_SJ_ENGINE
  {
   SJ_ENGINE_MOMENTUM  = 0, // Momentum saja (video 1)
   SJ_ENGINE_REVERSION = 1, // Reversion saja (video 2)
   SJ_ENGINE_ADAPTIVE  = 2  // Adaptif: dipilih detektor rezim
  };

enum ENUM_SJ_DIRECTION
  {
   SJ_DIR_BUY_ONLY  = 0, // Hanya BUY (seperti video 1)
   SJ_DIR_SELL_ONLY = 1, // Hanya SELL
   SJ_DIR_AUTO      = 2  // Otomatis ikut tren
  };

enum ENUM_SJ_LOT_MODE
  {
   SJ_LOT_FIXED   = 0, // Lot tetap
   SJ_LOT_BALANCE = 1  // 0.01 lot per kelipatan saldo
  };

enum ENUM_SJ_TP_MODE
  {
   SJ_TP_MONEY      = 0, // USD tetap per basket
   SJ_TP_PER_MINLOT = 1, // USD per 0.01 lot terbuka
   SJ_TP_PERCENT    = 2  // % dari saldo
  };

enum ENUM_SJ_NEWS_SOURCE
  {
   SJ_NEWS_AUTO     = 0, // Otomatis: kalender MT5 (live), file CSV (backtest)
   SJ_NEWS_CALENDAR = 1, // Hanya kalender MT5
   SJ_NEWS_CSV      = 2  // Hanya file CSV
  };

enum ENUM_SJ_NEWS_PHASE
  {
   NEWS_NONE   = 0,
   NEWS_PRE    = 1,  // menjelang rilis
   NEWS_SETTLE = 2,  // detik-detik pertama setelah rilis
   NEWS_POST   = 3   // setelah rilis, grid utama masih libur
  };

enum ENUM_SJ_REGIME
  {
   REGIME_RANGE   = 0,
   REGIME_NEUTRAL = 1,
   REGIME_TREND   = 2
  };

//--- input
input group "=== UMUM ==="
input ulong             InpMagic             = 20261014;      // Magic number (berita = +1, reversion = +2)
input string            InpComment           = "SAPU JAGAD";  // Komentar order
input ENUM_SJ_ENGINE    InpEngineMode        = SJ_ENGINE_ADAPTIVE; // Mesin trading
input ENUM_SJ_DIRECTION InpDirection         = SJ_DIR_AUTO;   // Arah mesin momentum
input bool              InpOneBasketOnly     = true;          // Hanya satu basket berjalan (momentum/reversion)

input group "=== DETEKTOR REZIM (Efficiency Ratio M1) ==="
input int               InpRegimeBars        = 30;            // Jumlah bar M1 untuk Efficiency Ratio
input double            InpERTrend           = 0.30;          // ER >= nilai ini = TREN
input double            InpERRange           = 0.12;          // ER <= nilai ini = RANGE
input bool              InpAdaptiveUseH1     = true;          // Adaptif: momentum juga harus searah tren EMA H1

input group "=== MESIN MOMENTUM: TANGGA STOP (satuan harga, 0.50 = 50 sen) ==="
input int               InpGridLevels        = 8;             // Jumlah pending stop per tangga
input double            InpGridStep          = 0.50;          // Jarak antar level
input double            InpStartDistance     = 2.00;          // Jarak level pertama dari harga
input double            InpTrailStep         = 0.50;          // Geser tangga bila harga menjauh >= nilai ini
input int               InpTrailCooldownMs   = 1000;          // Jeda minimal antar geser tangga (ms)
input int               InpMaxPositions      = 24;            // Maksimal posisi per basket momentum

input group "=== MESIN REVERSION: TANGGA LIMIT (video 2) ==="
input int               InpRevLevels         = 6;             // Jumlah pending limit per tangga
input double            InpRevStep           = 0.25;          // Jarak antar level minimal
input double            InpRevStepATR        = 0.30;          // Jarak = max(jarak minimal, ATR M5 x faktor) (0 = tetap)
input double            InpRevStart          = 0.25;          // Jarak level pertama minimal
input double            InpRevZEntry         = 0.80;          // Masuk bila |harga - EMA M5| / ATR M5 >= nilai ini
input int               InpRevEMAPeriod      = 20;            // Periode EMA M5 (rata-rata acuan)
input bool              InpRevWithTrendOnly  = true;          // Hanya beli saat turun di tren naik (dan sebaliknya)
input bool              InpRevRegimeExit     = true;          // Rezim berbalik jadi tren melawan: stop tambah & keluar impas
input double            InpRevTPPerMinLot    = 0.50;          // Target basket reversion: USD per 0.01 lot
input double            InpRevSLPerMinLot    = 3.00;          // Cut loss basket reversion: USD per 0.01 lot (0 = mati)
input int               InpRevMaxHoldMin     = 240;           // Batas waktu tahan basket reversion (menit, 0 = mati)

input group "=== JARAK ADAPTIF ATR MOMENTUM (opsional) ==="
input bool              InpUseATR            = false;         // Pakai ATR untuk jarak dasar tangga momentum
input ENUM_TIMEFRAMES   InpATRTimeframe      = PERIOD_M5;     // Timeframe ATR
input int               InpATRPeriod         = 14;            // Periode ATR
input double            InpATRStepFactor     = 0.25;          // Jarak antar level = ATR x faktor
input double            InpATRStartFactor    = 1.00;          // Jarak level pertama = ATR x faktor
input double            InpATRMinStep        = 0.30;          // Batas bawah jarak antar level
input double            InpATRMaxStep        = 2.00;          // Batas atas jarak antar level

input group "=== LOT ==="
input ENUM_SJ_LOT_MODE  InpLotMode           = SJ_LOT_FIXED;  // Mode lot
input double            InpFixedLot          = 0.01;          // Lot tetap per order
input double            InpBalancePerMinLot  = 2000.0;        // Mode saldo: 0.01 lot setiap X saldo
input double            InpMaxLot            = 0.10;          // Batas lot per order (0 = tanpa batas)

input group "=== TAKE PROFIT BASKET MOMENTUM ==="
input ENUM_SJ_TP_MODE   InpTPMode            = SJ_TP_PER_MINLOT; // Mode target profit
input double            InpTPValue           = 1.00;          // Nilai target (lihat mode)
input double            InpCommissionPerLot  = 0.0;           // Komisi pulang-pergi per 1.00 lot (akun ECN)
input bool              InpUseProfitLock     = true;          // Kunci profit: biarkan profit berlari lalu kunci
input double            InpLockGivebackPct   = 30.0;          // Tutup bila profit turun X% dari puncak
input int               InpRecoveryAfter     = 12;            // Mode recovery bila posisi >= N (0 = mati)
input double            InpRecoveryTPPerMinLot = 0.20;        // Target recovery/impas: USD per 0.01 lot terbuka

input group "=== PROTEKSI RISIKO ==="
input double            InpBasketSLMoney     = 0.0;           // Cut loss basket momentum bila rugi >= X USD (0 = mati)
input double            InpBasketSLPct       = 10.0;          // Cut loss basket bila rugi >= X% saldo (0 = mati)
input double            InpBasketAgeHours    = 24.0;          // Basket momentum > X jam: target turun ke recovery (0 = mati)
input bool              InpNoAddAgainstTrend = true;          // Jangan tambah posisi momentum saat tren berbalik melawan
input int               InpCooldownAfterLossMin = 60;         // Jeda entry setelah cut loss (menit)
input double            InpMaxDrawdownPct    = 30.0;          // Floating EA >= X% saldo: tutup semua & berhenti s/d besok (0 = mati)
input double            InpDailyProfitTarget = 0.0;           // Target profit harian USD (0 = mati)
input double            InpDailyLossLimit    = 0.0;           // Batas rugi harian USD (0 = mati)
input double            InpMinMarginLevel    = 300.0;         // Margin level minimal (%) untuk menambah posisi
input double            InpMaxSpread         = 0.50;          // Spread maksimal (satuan harga, 0 = mati)
input bool              InpDeletePendingOnWideSpread = true;  // Hapus pending saat spread melebar
input double            InpMaxSlippage       = 0.30;          // Slippage maksimal saat menutup (satuan harga)

input group "=== FILTER WAKTU (jam server) ==="
input bool              InpUseTimeFilter     = false;         // Aktifkan filter jam
input int               InpStartHour         = 1;             // Jam mulai entry
input int               InpEndHour           = 23;            // Jam berhenti entry
input bool              InpFridayStop        = true;          // Jumat: stop basket baru
input int               InpFridayStopHour    = 20;            // Jam stop basket baru hari Jumat
input bool              InpFridayCloseAll    = false;         // Jumat: tutup semua posisi
input int               InpFridayCloseHour   = 22;            // Jam tutup semua hari Jumat

input group "=== CERDAS SESI (jam GMT) ==="
input int               InpGMTOffset         = -99;           // Selisih jam server - GMT (-99 = otomatis saat live)
input int               InpTesterGMTOffset   = 0;             // Selisih jam server - GMT saat backtest
input int               InpLondonOpenGMT     = 7;             // Jam buka London (GMT)
input int               InpNYOpenGMT         = 13;            // Jam buka New York (GMT)
input int               InpNYCloseGMT        = 21;            // Jam tutup New York (GMT)
input bool              InpTradeAsia         = true;          // Buka basket baru di sesi Asia
input bool              InpTradeLondon       = true;          // Buka basket baru di sesi London
input bool              InpTradeNY           = true;          // Buka basket baru di sesi New York
input double            InpAsiaStepMult      = 1.0;           // Pengali jarak tangga sesi Asia
input double            InpLondonStepMult    = 1.0;           // Pengali jarak tangga sesi London
input double            InpNYStepMult        = 1.0;           // Pengali jarak tangga sesi New York
input int               InpOpenGuardMin      = 10;            // Anti stop-hunt: libur X menit setelah buka London/NY (0 = mati)
input bool              InpRolloverGuard     = true;          // Libur saat rollover harian (spread melebar)
input int               InpRolloverStartGMT  = 2050;          // Awal rollover (HHMM GMT)
input int               InpRolloverEndGMT    = 2310;          // Akhir rollover (HHMM GMT)

input group "=== CERDAS VOLATILITAS ==="
input bool              InpVolGuard          = true;          // Aktifkan penjaga volatilitas
input int               InpVolSlowPeriod     = 60;            // ATR M1 acuan (normal)
input double            InpVolWidenRatio     = 2.0;           // Range candle / ATR >= X: jarak tangga dilebarkan
input double            InpVolMaxStepMult    = 2.5;           // Batas pelebaran jarak tangga
input double            InpVolBlockRatio     = 4.0;           // Range candle / ATR >= X: hapus pending, stop entry
input int               InpBurstMaxFills     = 5;             // Penjaga burst: bila >= N stop terisi... (0 = mati)
input int               InpBurstSeconds      = 30;            // ...dalam X detik
input int               InpBurstPauseSec     = 300;           // ...hentikan penambahan selama X detik

input group "=== CERDAS BERITA ==="
input bool              InpUseNewsFilter     = true;          // Perisai berita (grid libur sekitar rilis)
input ENUM_SJ_NEWS_SOURCE InpNewsSource      = SJ_NEWS_AUTO;  // Sumber jadwal berita
input string            InpNewsCsvFile       = "sapu_jagad_news.csv"; // File CSV di folder Common\Files (waktu GMT)
input string            InpNewsCurrencies    = "USD";         // Mata uang (pisahkan dengan koma)
input bool              InpNewsIncludeMedium = false;         // Ikutkan berita dampak sedang
input int               InpNewsBeforeMin     = 15;            // Menit sebelum rilis
input int               InpNewsAfterMin      = 30;            // Menit sesudah rilis (grid libur)
input bool              InpNewsBankProfit    = true;          // Tutup basket yang sedang profit sebelum rilis
input bool              InpNewsRide          = true;          // Tunggangi momentum setelah rilis
input int               InpNewsSettleSec     = 20;            // Tunggu lonjakan & spread awal reda (detik)
input int               InpNewsRideWindowMin = 10;            // Jendela pemasangan tangga berita (menit)
input double            InpNewsImpulseATR    = 1.5;           // Impuls minimal = ATR M1 pra-rilis x faktor
input int               InpNewsLevels        = 4;             // Jumlah level tangga berita
input double            InpNewsStepATR       = 0.5;           // Jarak level = ATR M1 pra-rilis x faktor
input double            InpNewsStartATR      = 0.5;           // Jarak level pertama = ATR M1 pra-rilis x faktor
input double            InpNewsLotMult       = 1.0;           // Pengali lot tangga berita
input double            InpNewsTPPerMinLot   = 2.0;           // Target basket berita: USD per 0.01 lot
input double            InpNewsSLPerMinLot   = 3.0;           // Cut loss basket berita: USD per 0.01 lot
input int               InpNewsMaxHoldMin    = 45;            // Batas waktu tahan basket berita (menit)
input double            InpNewsMaxSpread     = 1.00;          // Spread maksimal untuk tangga berita

input group "=== FILTER TREN H1 ==="
input ENUM_TIMEFRAMES   InpTrendTF           = PERIOD_H1;     // Timeframe tren
input int               InpTrendEMA          = 50;            // Periode EMA tren

input group "=== MESIN ALPHA (model ML dari sapu_jagad_alpha.py) ==="
input bool              InpAlphaEnable       = true;          // Aktifkan Mesin ALPHA
input string            InpAlphaModelFile    = "sapu_jagad_alpha.txt"; // File model di folder Common\Files
input bool              InpAlphaAllowUnvalidated = false;     // Izinkan trading walau model TIDAK LOLOS validasi (berisiko)
input double            InpAlphaLotMult      = 1.0;           // Pengali lot posisi alpha
input double            InpAlphaSLATR        = 6.0;           // Stop pengaman = X x ATR96 M15 (0 = mati)
input bool              InpAlphaDumpFeatures = false;         // Tulis fitur ke CSV (uji paritas EA vs Python)

input group "=== LAIN-LAIN ==="
input bool              InpShowPanel         = true;          // Tampilkan panel info
input bool              InpDeletePendingOnRemove = true;      // Hapus pending saat EA dilepas dari chart

//--- slot basket: 0/1 momentum BUY/SELL (stop), 2/3 berita BUY/SELL (stop), 4/5 reversion BUY/SELL (limit)
#define SLOT_COUNT  6
#define PANEL_LINES 17

struct SBasket
  {
   int               slot;
   int               dir;         // +1 BUY, -1 SELL
   int               positions;
   int               pendings;
   int               recentFills; // posisi yang terbuka dalam InpBurstSeconds terakhir
   double            volume;
   double            profit;      // profit + swap - komisi estimasi
   double            avgPrice;    // harga rata-rata tertimbang
   datetime          oldestTime;
  };

struct SEnv
  {
   double            bid;
   double            ask;
   double            spread;
   double            step;
   double            start;
   double            revStep;
   double            revStart;
   double            stepMult;
   double            lot;
   double            volRatio;
   double            er;          // Efficiency Ratio M1
   double            z;           // jarak harga ke EMA M5 dalam satuan ATR M5
   int               erDir;       // arah gerak bersih periode ER
   int               regime;
   int               trend;       // tren EMA H1
   int               session;     // 0 Asia, 1 London, 2 New York
   int               gmtMinute;
   int               newsPhase;
   bool              spreadBad;
   bool              volBlock;
   bool              marginLow;
   bool              inSession;
   bool              sessionAllowed;
   bool              openGuard;
   bool              rollover;
   bool              fridayStop;
   bool              fridayClose;
   bool              dailyTargetHit;
   bool              halted;
   bool              tradeAllowed;
   string            newsInfo;
  };

//--- global
CTrade                  trade;
ENUM_ORDER_TYPE_FILLING g_filling     = ORDER_FILLING_FOK;
ENUM_ORDER_TYPE_TIME    g_typeTime    = ORDER_TIME_GTC;
double                  g_tickSize    = 0.0;
ulong                   g_slippagePts = 30;
bool                    g_isTester    = false;
bool                    g_showPanel   = true;
string                  g_objPrefix   = "";
string                  g_gvPrefix    = "";
int                     g_emaHandle     = INVALID_HANDLE;
int                     g_atrHandle     = INVALID_HANDLE;
int                     g_atrSlowHandle = INVALID_HANDLE;
int                     g_atrNewsHandle = INVALID_HANDLE;
int                     g_revEmaHandle  = INVALID_HANDLE;
int                     g_atrM5Handle   = INVALID_HANDLE;

bool                    g_closing[SLOT_COUNT];
double                  g_peak[SLOT_COUNT];          // puncak profit basket (kunci profit)
datetime                g_cooldownUntil[SLOT_COUNT];
datetime                g_pauseUntil[SLOT_COUNT];    // jeda karena burst
ulong                   g_lastTrailMs[SLOT_COUNT];
ulong                   g_retryAfterMs[SLOT_COUNT];  // jeda setelah gagal pasang tangga
string                  g_status[SLOT_COUNT];
string                  g_lastCloseInfo = "-";

datetime                g_haltUntil     = 0;
datetime                g_dayStart      = 0;
double                  g_realizedToday = 0.0;
bool                    g_histDirty     = true;
ulong                   g_lastHistMs    = 0;
ulong                   g_lastPanelMs   = 0;
datetime                g_lastWarn      = 0;

//--- jadwal berita: kalender (live) dan CSV (backtest/live)
datetime                g_calTimes[];
string                  g_calNames[];
datetime                g_calRefreshed  = 0;
datetime                g_csvTimes[];
string                  g_csvNames[];
int                     g_csvPtr        = 0;

//--- status berita yang sedang dilacak
datetime                g_newsEventTime = 0;
string                  g_newsEventName = "";
double                  g_newsRefPrice  = 0.0;
double                  g_newsRefATR    = 0.0;
datetime                g_newsRideUntil = 0;
bool                    g_newsRideDone  = false;
double                  g_newsStep      = 0.0;
double                  g_newsStart     = 0.0;

//+------------------------------------------------------------------+
//| Utilitas slot                                                    |
//+------------------------------------------------------------------+
int    SlotDir(const int s)     { return (s % 2 == 0) ? 1 : -1; }
bool   SlotIsNews(const int s)  { return (s == 2 || s == 3); }
bool   SlotIsRev(const int s)   { return (s >= 4); }
ulong  SlotMagic(const int s)   { return InpMagic + (ulong)(s / 2); }
// arah tangga menjauh dari harga: stop searah posisi, limit berlawanan arah posisi
int    SlotExt(const int s)     { return SlotIsRev(s) ? -SlotDir(s) : SlotDir(s); }
string DirName(const int dir)   { return (dir > 0) ? "BUY" : "SELL"; }

string SlotName(const int s)
  {
   string prefix = "";
   if(SlotIsNews(s))
      prefix = "N-";
   if(SlotIsRev(s))
      prefix = "R-";
   return prefix + DirName(SlotDir(s));
  }

ENUM_ORDER_TYPE SlotPendingType(const int s)
  {
   if(SlotIsRev(s))
      return (SlotDir(s) > 0) ? ORDER_TYPE_BUY_LIMIT : ORDER_TYPE_SELL_LIMIT;
   return (SlotDir(s) > 0) ? ORDER_TYPE_BUY_STOP : ORDER_TYPE_SELL_STOP;
  }

string RegimeName(const int regime)
  {
   if(regime == REGIME_TREND)
      return "TREN";
   if(regime == REGIME_RANGE)
      return "RANGE";
   return "NETRAL";
  }

//+------------------------------------------------------------------+
//| Utilitas umum                                                    |
//+------------------------------------------------------------------+
bool IsOk(const uint rc)
  {
   return (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_PLACED || rc == TRADE_RETCODE_DONE_PARTIAL);
  }

double NormPrice(const double price)
  {
   double ts = (g_tickSize > 0.0) ? g_tickSize : _Point;
   return NormalizeDouble(MathRound(price / ts) * ts, _Digits);
  }

double NormalizeLot(double lot)
  {
   double vmin  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vmax  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double vstep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(vstep <= 0.0)
      vstep = 0.01;
   lot = MathFloor(lot / vstep + 1e-9) * vstep;
   if(lot < vmin)
      lot = vmin;
   if(vmax > 0.0 && lot > vmax)
      lot = vmax;
   int digits = (int)MathMax(0.0, MathCeil(-MathLog10(vstep) - 1e-9));
   return NormalizeDouble(lot, digits);
  }

double MinStopDistance()
  {
   return (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
  }

double FreezeDistance()
  {
   return (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL) * _Point;
  }

datetime DayStart(const datetime t)
  {
   MqlDateTime dt;
   TimeToStruct(t, dt);
   dt.hour = 0;
   dt.min  = 0;
   dt.sec  = 0;
   return StructToTime(dt);
  }

int HHMMToMinute(const int hhmm)
  {
   return (hhmm / 100) * 60 + (hhmm % 100);
  }

// x di dalam [a, b) dengan dukungan lewat tengah malam
bool InMinuteWindow(const int x, const int a, const int b)
  {
   if(a == b)
      return false;
   if(a < b)
      return (x >= a && x < b);
   return (x >= a || x < b);
  }

void Warn(const string msg)
  {
   // batasi pesan peringatan agar jurnal tidak banjir
   if(TimeCurrent() - g_lastWarn < 60)
      return;
   g_lastWarn = TimeCurrent();
   Print("[SAPU JAGAD] ", msg);
  }

void NextFilling()
  {
   if(g_filling == ORDER_FILLING_FOK)
      g_filling = ORDER_FILLING_IOC;
   else
      if(g_filling == ORDER_FILLING_IOC)
         g_filling = ORDER_FILLING_RETURN;
      else
         g_filling = ORDER_FILLING_FOK;
   trade.SetTypeFilling(g_filling);
  }

void InitFilling()
  {
   int mode = (int)SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   if((mode & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK)
      g_filling = ORDER_FILLING_FOK;
   else
      if((mode & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC)
         g_filling = ORDER_FILLING_IOC;
      else
         g_filling = ORDER_FILLING_RETURN;
   trade.SetTypeFilling(g_filling);
  }

int ServerGMTOffsetHours()
  {
   if(g_isTester)
      return InpTesterGMTOffset;   // TimeGMT() di tester sama dengan waktu server
   if(InpGMTOffset != -99)
      return InpGMTOffset;
   return (int)MathRound((double)(TimeTradeServer() - TimeGMT()) / 3600.0);
  }

//--- state yang tahan restart (Global Variables terminal)
void SavePeak(const int s)
  {
   GlobalVariableSet(g_gvPrefix + "PEAK" + IntegerToString(s), g_peak[s]);
  }

void ResetPeak(const int s)
  {
   if(g_peak[s] != 0.0)
     {
      g_peak[s] = 0.0;
      SavePeak(s);
     }
  }

void LoadState()
  {
   for(int s = 0; s < SLOT_COUNT; s++)
     {
      string name = g_gvPrefix + "PEAK" + IntegerToString(s);
      g_peak[s] = GlobalVariableCheck(name) ? GlobalVariableGet(name) : 0.0;
     }
   string hname = g_gvPrefix + "HALT";
   g_haltUntil = 0;
   if(GlobalVariableCheck(hname))
      g_haltUntil = (datetime)(long)GlobalVariableGet(hname);
  }

void SetHalt(const datetime until)
  {
   g_haltUntil = until;
   GlobalVariableSet(g_gvPrefix + "HALT", (double)(long)until);
  }

//+------------------------------------------------------------------+
//| Pemindaian basket                                                |
//+------------------------------------------------------------------+
bool IsOurPosition(const int s)
  {
   if(PositionGetString(POSITION_SYMBOL) != _Symbol)
      return false;
   if((ulong)PositionGetInteger(POSITION_MAGIC) != SlotMagic(s))
      return false;
   long type = PositionGetInteger(POSITION_TYPE);
   return (SlotDir(s) > 0) ? (type == POSITION_TYPE_BUY) : (type == POSITION_TYPE_SELL);
  }

bool IsOurPending(const int s)
  {
   if(OrderGetString(ORDER_SYMBOL) != _Symbol)
      return false;
   if((ulong)OrderGetInteger(ORDER_MAGIC) != SlotMagic(s))
      return false;
   return (OrderGetInteger(ORDER_TYPE) == (long)SlotPendingType(s));
  }

void ScanBasket(const int s, SBasket &b)
  {
   b.slot        = s;
   b.dir         = SlotDir(s);
   b.positions   = 0;
   b.pendings    = 0;
   b.recentFills = 0;
   b.volume      = 0.0;
   b.profit      = 0.0;
   b.avgPrice    = 0.0;
   b.oldestTime  = 0;
   double pv     = 0.0;
   datetime recentFrom = TimeCurrent() - InpBurstSeconds;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !IsOurPosition(s))
         continue;
      double vol    = PositionGetDouble(POSITION_VOLUME);
      datetime open = (datetime)PositionGetInteger(POSITION_TIME);
      b.positions++;
      b.volume += vol;
      b.profit += PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP) - vol * InpCommissionPerLot;
      pv       += PositionGetDouble(POSITION_PRICE_OPEN) * vol;
      if(open >= recentFrom)
         b.recentFills++;
      if(b.oldestTime == 0 || open < b.oldestTime)
         b.oldestTime = open;
     }
   if(b.volume > 0.0)
      b.avgPrice = pv / b.volume;

   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      ulong ticket = OrderGetTicket(i);
      if(ticket == 0 || !IsOurPending(s))
         continue;
      b.pendings++;
     }
  }

void ScanAll(SBasket &b[])
  {
   for(int s = 0; s < SLOT_COUNT; s++)
      ScanBasket(s, b[s]);
  }

// ada basket momentum/reversion lain (selain slot s) yang sedang punya posisi
bool OthersBusy(const int s, const SBasket &b[])
  {
   for(int k = 0; k < SLOT_COUNT; k++)
     {
      if(k == s || SlotIsNews(k))
         continue;
      if(b[k].positions > 0)
         return true;
     }
   return false;
  }

//+------------------------------------------------------------------+
//| Eksekusi order                                                   |
//+------------------------------------------------------------------+
bool SendPendingOrder(const int s, const double lot, const double price, const string cmt)
  {
   trade.SetExpertMagicNumber(SlotMagic(s));
   ENUM_ORDER_TYPE type = SlotPendingType(s);
   for(int attempt = 0; attempt < 3; attempt++)
     {
      bool sent = false;
      if(type == ORDER_TYPE_BUY_STOP)
         sent = trade.BuyStop(lot, price, _Symbol, 0.0, 0.0, g_typeTime, 0, cmt);
      else
         if(type == ORDER_TYPE_SELL_STOP)
            sent = trade.SellStop(lot, price, _Symbol, 0.0, 0.0, g_typeTime, 0, cmt);
         else
            if(type == ORDER_TYPE_BUY_LIMIT)
               sent = trade.BuyLimit(lot, price, _Symbol, 0.0, 0.0, g_typeTime, 0, cmt);
            else
               sent = trade.SellLimit(lot, price, _Symbol, 0.0, 0.0, g_typeTime, 0, cmt);
      uint rc = trade.ResultRetcode();
      if(sent && IsOk(rc))
         return true;
      if(rc == TRADE_RETCODE_INVALID_FILL)
        {
         NextFilling();
         continue;
        }
      Warn(StringFormat("Gagal pasang %s %.2f lot @ %s: %u %s", EnumToString(type), lot,
                        DoubleToString(price, _Digits), rc, trade.ResultRetcodeDescription()));
      return false;
     }
   return false;
  }

void DeletePendings(const int s)
  {
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      ulong ticket = OrderGetTicket(i);
      if(ticket == 0 || !IsOurPending(s))
         continue;
      if(!trade.OrderDelete(ticket) || !IsOk(trade.ResultRetcode()))
         Warn(StringFormat("Gagal hapus pending #%s: %u", (string)ticket, trade.ResultRetcode()));
     }
  }

void CloseBasketNow(const int s)
  {
   // hapus pending dulu supaya tidak ada posisi baru terisi saat menutup
   DeletePendings(s);
   trade.SetExpertMagicNumber(SlotMagic(s));
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !IsOurPosition(s))
         continue;
      for(int attempt = 0; attempt < 3; attempt++)
        {
         if(trade.PositionClose(ticket, g_slippagePts) && IsOk(trade.ResultRetcode()))
            break;
         uint rc = trade.ResultRetcode();
         if(rc == TRADE_RETCODE_INVALID_FILL)
           {
            NextFilling();
            continue;
           }
         if(rc == TRADE_RETCODE_REQUOTE || rc == TRADE_RETCODE_PRICE_CHANGED || rc == TRADE_RETCODE_PRICE_OFF)
           {
            Sleep(50);
            continue;
           }
         Warn(StringFormat("Gagal tutup posisi #%s: %u %s", (string)ticket, rc, trade.ResultRetcodeDescription()));
         break;
        }
     }
  }

void StartClose(const int s, const string reason, const bool isLoss)
  {
   if(!g_closing[s])
     {
      PrintFormat("[SAPU JAGAD] Tutup basket %s: %s", SlotName(s), reason);
      g_lastCloseInfo = StringFormat("%s %s (%s)", SlotName(s), reason, TimeToString(TimeCurrent(), TIME_MINUTES));
     }
   g_closing[s] = true;
   if(isLoss && InpCooldownAfterLossMin > 0)
      g_cooldownUntil[s] = TimeCurrent() + InpCooldownAfterLossMin * 60;
   CloseBasketNow(s);
  }

void CloseAll(const string reason, const bool halt)
  {
   if(halt)
     {
      SetHalt(g_dayStart + 86400);
      PrintFormat("[SAPU JAGAD] HALT sampai %s: %s", TimeToString(g_haltUntil, TIME_DATE | TIME_MINUTES), reason);
     }
   for(int s = 0; s < SLOT_COUNT; s++)
      StartClose(s, reason, halt);
   AlphaCloseIfAny(reason);
  }

//+------------------------------------------------------------------+
//| Indikator & geometri                                             |
//+------------------------------------------------------------------+
double BufferValue(const int handle, const int shift)
  {
   if(handle == INVALID_HANDLE)
      return 0.0;
   double v[1];
   if(CopyBuffer(handle, 0, shift, 1, v) != 1)
      return 0.0;
   return v[0];
  }

// rasio range candle M1 terbaru terhadap ATR M1 normal (1.0 = normal)
double VolatilityRatio()
  {
   double atr = BufferValue(g_atrSlowHandle, 1);
   if(atr <= 0.0)
      return 1.0;
   MqlRates r[];
   if(CopyRates(_Symbol, PERIOD_M1, 0, 3, r) != 3)
      return 1.0;
   double tr0 = MathMax(r[2].high, r[1].close) - MathMin(r[2].low, r[1].close);
   double tr1 = MathMax(r[1].high, r[0].close) - MathMin(r[1].low, r[0].close);
   return MathMax(tr0, tr1) / atr;
  }

// Efficiency Ratio Kaufman pada bar M1 tertutup: |perubahan bersih| / total jalan harga
void ComputeRegime(SEnv &e)
  {
   e.er     = 0.0;
   e.erDir  = 0;
   e.regime = REGIME_NEUTRAL;
   int need = InpRegimeBars + 1;
   double cl[];
   if(CopyClose(_Symbol, PERIOD_M1, 1, need, cl) != need)
      return;
   double path = 0.0;
   for(int i = 1; i < need; i++)
      path += MathAbs(cl[i] - cl[i - 1]);
   double net = cl[need - 1] - cl[0];
   if(path <= 0.0)
      return;
   e.er    = MathAbs(net) / path;
   e.erDir = (net > 0.0) ? 1 : ((net < 0.0) ? -1 : 0);
   if(e.er >= InpERTrend)
      e.regime = REGIME_TREND;
   else
      if(e.er <= InpERRange)
         e.regime = REGIME_RANGE;
  }

void GridGeometry(double &step, double &start, const double mult)
  {
   step  = InpGridStep;
   start = InpStartDistance;
   if(InpUseATR)
     {
      double atr = BufferValue(g_atrHandle, 1);
      if(atr > 0.0)
        {
         step  = MathMin(MathMax(atr * InpATRStepFactor, InpATRMinStep), InpATRMaxStep);
         start = MathMax(atr * InpATRStartFactor, step);
        }
     }
   step  = MathMax(step * mult, g_tickSize);
   start = MathMax(start * mult, MinStopDistance() + g_tickSize);
  }

double BaseLot()
  {
   double lot = InpFixedLot;
   if(InpLotMode == SJ_LOT_BALANCE && InpBalancePerMinLot > 0.0)
      lot = 0.01 * MathFloor(AccountInfoDouble(ACCOUNT_BALANCE) / InpBalancePerMinLot);
   if(InpMaxLot > 0.0)
      lot = MathMin(lot, InpMaxLot);
   return NormalizeLot(lot);
  }

double BasketTarget(const SBasket &b, bool &recovery)
  {
   double units = b.volume / 0.01;
   recovery = (InpRecoveryAfter > 0 && b.positions >= InpRecoveryAfter) ||
              (InpBasketAgeHours > 0.0 && b.oldestTime > 0 && TimeCurrent() - b.oldestTime >= (long)(InpBasketAgeHours * 3600.0));
   if(recovery)
      return MathMax(InpRecoveryTPPerMinLot * units, 0.01);
   switch(InpTPMode)
     {
      case SJ_TP_MONEY:
         return InpTPValue;
      case SJ_TP_PERCENT:
         return AccountInfoDouble(ACCOUNT_BALANCE) * InpTPValue / 100.0;
      default:
         break;
     }
   return InpTPValue * units;
  }

int TrendDirection()
  {
   double ema = BufferValue(g_emaHandle, 1);
   if(ema <= 0.0)
      return 0;
   double closePrev = iClose(_Symbol, InpTrendTF, 1);
   if(closePrev <= 0.0)
      return 0;
   if(closePrev > ema)
      return 1;
   if(closePrev < ema)
      return -1;
   return 0;
  }

bool InServerHours(const int hour)
  {
   if(!InpUseTimeFilter || InpStartHour == InpEndHour)
      return true;
   if(InpStartHour < InpEndHour)
      return (hour >= InpStartHour && hour < InpEndHour);
   return (hour >= InpStartHour || hour < InpEndHour);
  }

int SessionOf(const int gmtHour)
  {
   if(gmtHour >= InpLondonOpenGMT && gmtHour < InpNYOpenGMT)
      return 1;
   if(gmtHour >= InpNYOpenGMT && gmtHour < InpNYCloseGMT)
      return 2;
   return 0;
  }

string SessionName(const int session)
  {
   if(session == 1)
      return "LONDON";
   if(session == 2)
      return "NEW YORK";
   return "ASIA";
  }

//+------------------------------------------------------------------+
//| Jadwal berita                                                    |
//+------------------------------------------------------------------+
bool CurrencyWanted(const string cur)
  {
   string list[];
   ushort sep = StringGetCharacter(",", 0);
   int n = StringSplit(InpNewsCurrencies, sep, list);
   for(int i = 0; i < n; i++)
     {
      string c = list[i];
      StringTrimLeft(c);
      StringTrimRight(c);
      StringToUpper(c);
      if(c != "" && c == cur)
         return true;
     }
   return false;
  }

bool UseCalendar()
  {
   if(g_isTester)
      return false;   // kalender tidak tersedia di Strategy Tester
   return (InpNewsSource == SJ_NEWS_AUTO || InpNewsSource == SJ_NEWS_CALENDAR);
  }

bool UseCsv()
  {
   if(InpNewsSource == SJ_NEWS_CSV)
      return true;
   return (InpNewsSource == SJ_NEWS_AUTO && g_isTester);
  }

// format baris CSV (waktu GMT): 2026.10.02 12:30,USD,HIGH,Non-Farm Employment Change
void LoadNewsCsv()
  {
   ArrayResize(g_csvTimes, 0);
   ArrayResize(g_csvNames, 0);
   g_csvPtr = 0;
   int h = FileOpen(InpNewsCsvFile, FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON | FILE_SHARE_READ);
   if(h == INVALID_HANDLE)
     {
      PrintFormat("[SAPU JAGAD] File berita %s tidak ditemukan di Common\\Files (err %d).", InpNewsCsvFile, GetLastError());
      return;
     }
   int offset = ServerGMTOffsetHours();
   ushort sep = StringGetCharacter(",", 0);
   while(!FileIsEnding(h))
     {
      string line = FileReadString(h);
      string f[];
      if(StringSplit(line, sep, f) < 3)
         continue;
      string ts = f[0];
      StringTrimLeft(ts);
      StringTrimRight(ts);
      StringReplace(ts, "-", ".");
      if(StringLen(ts) < 10)
         continue;
      ushort c0 = StringGetCharacter(ts, 0);
      if(c0 < '0' || c0 > '9')
         continue;   // baris judul / komentar
      datetime t = StringToTime(ts);
      if(t <= 0)
         continue;
      string cur = f[1];
      StringTrimLeft(cur);
      StringTrimRight(cur);
      StringToUpper(cur);
      if(!CurrencyWanted(cur))
         continue;
      string imp = f[2];
      StringToUpper(imp);
      bool important = (StringFind(imp, "HIGH") >= 0) || (InpNewsIncludeMedium && StringFind(imp, "MED") >= 0);
      if(!important)
         continue;
      int n = ArraySize(g_csvTimes);
      ArrayResize(g_csvTimes, n + 1);
      ArrayResize(g_csvNames, n + 1);
      g_csvTimes[n] = t + offset * 3600;
      g_csvNames[n] = cur + " " + (ArraySize(f) > 3 ? f[3] : "berita");
     }
   FileClose(h);

   // urutkan berdasarkan waktu (insertion sort, data biasanya sudah hampir urut)
   int total = ArraySize(g_csvTimes);
   for(int i = 1; i < total; i++)
     {
      datetime tt = g_csvTimes[i];
      string   nm = g_csvNames[i];
      int j = i - 1;
      while(j >= 0 && g_csvTimes[j] > tt)
        {
         g_csvTimes[j + 1] = g_csvTimes[j];
         g_csvNames[j + 1] = g_csvNames[j];
         j--;
        }
      g_csvTimes[j + 1] = tt;
      g_csvNames[j + 1] = nm;
     }
   PrintFormat("[SAPU JAGAD] %d jadwal berita dimuat dari %s", total, InpNewsCsvFile);
  }

void RefreshCalendar()
  {
   datetime now = TimeTradeServer();
   if(g_calRefreshed > 0 && now - g_calRefreshed < 600)
      return;
   g_calRefreshed = now;
   ArrayResize(g_calTimes, 0);
   ArrayResize(g_calNames, 0);

   string list[];
   ushort sep = StringGetCharacter(",", 0);
   int nc = StringSplit(InpNewsCurrencies, sep, list);
   datetime from = now - 3 * 3600;
   datetime to   = now + 86400;
   for(int c = 0; c < nc; c++)
     {
      string cur = list[c];
      StringTrimLeft(cur);
      StringTrimRight(cur);
      StringToUpper(cur);
      if(cur == "")
         continue;
      MqlCalendarValue values[];
      if(!CalendarValueHistory(values, from, to, NULL, cur))
         continue;
      int nv = ArraySize(values);
      for(int i = 0; i < nv; i++)
        {
         MqlCalendarEvent ev;
         if(!CalendarEventById(values[i].event_id, ev))
            continue;
         bool important = (ev.importance == CALENDAR_IMPORTANCE_HIGH) ||
                          (InpNewsIncludeMedium && ev.importance == CALENDAR_IMPORTANCE_MODERATE);
         if(!important)
            continue;
         int n = ArraySize(g_calTimes);
         ArrayResize(g_calTimes, n + 1);
         ArrayResize(g_calNames, n + 1);
         g_calTimes[n] = values[i].time;
         g_calNames[n] = cur + " " + ev.name;
        }
     }
  }

int NewsTailSeconds()
  {
   return (int)MathMax(InpNewsAfterMin * 60, InpNewsSettleSec + InpNewsRideWindowMin * 60);
  }

// cari berita terdekat yang jendelanya mencakup "now"
bool FindActiveNews(const datetime now, datetime &evTime, string &evName)
  {
   int before = InpNewsBeforeMin * 60;
   int tail   = NewsTailSeconds();
   bool found = false;

   if(UseCsv())
     {
      int n = ArraySize(g_csvTimes);
      while(g_csvPtr < n && g_csvTimes[g_csvPtr] + tail < now)
         g_csvPtr++;
      if(g_csvPtr < n && g_csvTimes[g_csvPtr] - before <= now)
        {
         evTime = g_csvTimes[g_csvPtr];
         evName = g_csvNames[g_csvPtr];
         found  = true;
        }
     }
   if(UseCalendar())
     {
      RefreshCalendar();
      int n = ArraySize(g_calTimes);
      for(int i = 0; i < n; i++)
        {
         datetime t = g_calTimes[i];
         if(now < t - before || now > t + tail)
            continue;
         if(!found || t < evTime)
           {
            evTime = t;
            evName = g_calNames[i];
            found  = true;
           }
        }
     }
   return found;
  }

// tentukan fase berita & rekam harga acuan pra-rilis
int UpdateNews(const SEnv &e, string &info)
  {
   info = "";
   if(!InpUseNewsFilter)
      return NEWS_NONE;
   datetime now = TimeCurrent();
   datetime evTime = 0;
   string   evName = "";
   if(!FindActiveNews(now, evTime, evName))
      return NEWS_NONE;

   if(evTime != g_newsEventTime)
     {
      // berita baru: reset status penunggang
      g_newsEventTime = evTime;
      g_newsEventName = evName;
      g_newsRefPrice  = 0.0;
      g_newsRefATR    = 0.0;
      g_newsRideDone  = false;
      g_newsRideUntil = evTime + InpNewsSettleSec + InpNewsRideWindowMin * 60;
     }
   info = evName + " @" + TimeToString(evTime, TIME_MINUTES);

   if(now < evTime)
     {
      // harga & ATR acuan terus diperbarui sampai detik rilis
      g_newsRefPrice = (e.bid + e.ask) * 0.5;
      g_newsRefATR   = BufferValue(g_atrNewsHandle, 1);
      return NEWS_PRE;
     }
   if(now < evTime + InpNewsSettleSec)
      return NEWS_SETTLE;
   if(now <= evTime + InpNewsAfterMin * 60)
      return NEWS_POST;
   return NEWS_NONE;   // grid boleh jalan lagi, jendela penunggang mungkin masih buka
  }

string NewsPhaseName(const int phase)
  {
   if(phase == NEWS_PRE)
      return "PRA-RILIS";
   if(phase == NEWS_SETTLE)
      return "RILIS";
   if(phase == NEWS_POST)
      return "PASCA-RILIS";
   return "aman";
  }

//+------------------------------------------------------------------+
//| Statistik harian (dari riwayat deal)                             |
//+------------------------------------------------------------------+
void UpdateDaily()
  {
   datetime ds = DayStart(TimeCurrent());
   if(ds != g_dayStart)
     {
      g_dayStart  = ds;
      g_histDirty = true;
     }
   ulong nowMs = GetTickCount64();
   if(!g_histDirty && nowMs - g_lastHistMs < 10000)
      return;
   if(!HistorySelect(g_dayStart, TimeCurrent() + 60))
      return;
   g_histDirty  = false;
   g_lastHistMs = nowMs;
   double sum = 0.0;
   int n = HistoryDealsTotal();
   for(int i = 0; i < n; i++)
     {
      ulong deal = HistoryDealGetTicket(i);
      if(deal == 0)
         continue;
      if(HistoryDealGetString(deal, DEAL_SYMBOL) != _Symbol)
         continue;
      ulong magic = (ulong)HistoryDealGetInteger(deal, DEAL_MAGIC);
      if(magic < InpMagic || magic > InpMagic + 3)
         continue;
      sum += HistoryDealGetDouble(deal, DEAL_PROFIT) + HistoryDealGetDouble(deal, DEAL_SWAP) +
             HistoryDealGetDouble(deal, DEAL_COMMISSION) + HistoryDealGetDouble(deal, DEAL_FEE);
     }
   g_realizedToday = sum;
  }

//+------------------------------------------------------------------+
//| Lingkungan pasar per tick                                        |
//+------------------------------------------------------------------+
bool BuildEnv(SEnv &e)
  {
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick) || tick.bid <= 0.0 || tick.ask <= 0.0)
      return false;
   e.bid    = tick.bid;
   e.ask    = tick.ask;
   e.spread = tick.ask - tick.bid;
   e.lot    = BaseLot();
   e.trend  = TrendDirection();
   e.spreadBad = (InpMaxSpread > 0.0 && e.spread > InpMaxSpread + g_tickSize * 0.5);

   //--- sesi (GMT)
   datetime gmt = TimeCurrent() - ServerGMTOffsetHours() * 3600;
   MqlDateTime g;
   TimeToStruct(gmt, g);
   e.gmtMinute = g.hour * 60 + g.min;
   e.session   = SessionOf(g.hour);
   e.sessionAllowed = (e.session == 0 && InpTradeAsia) || (e.session == 1 && InpTradeLondon) ||
                      (e.session == 2 && InpTradeNY);
   e.openGuard = false;
   if(InpOpenGuardMin > 0)
      e.openGuard = InMinuteWindow(e.gmtMinute, InpLondonOpenGMT * 60, InpLondonOpenGMT * 60 + InpOpenGuardMin) ||
                    InMinuteWindow(e.gmtMinute, InpNYOpenGMT * 60, InpNYOpenGMT * 60 + InpOpenGuardMin);
   e.rollover = InpRolloverGuard &&
                InMinuteWindow(e.gmtMinute, HHMMToMinute(InpRolloverStartGMT), HHMMToMinute(InpRolloverEndGMT));
   double sessMult = InpAsiaStepMult;
   if(e.session == 1)
      sessMult = InpLondonStepMult;
   if(e.session == 2)
      sessMult = InpNYStepMult;

   //--- volatilitas
   e.volRatio = InpVolGuard ? VolatilityRatio() : 1.0;
   e.volBlock = InpVolGuard && e.volRatio >= InpVolBlockRatio;
   double volMult = 1.0;
   if(InpVolGuard && e.volRatio >= InpVolWidenRatio)
      volMult = MathMin(e.volRatio, InpVolMaxStepMult);
   e.stepMult = MathMax(sessMult, 0.1) * volMult;
   GridGeometry(e.step, e.start, e.stepMult);

   //--- rezim & z-score reversion
   ComputeRegime(e);
   double emaM5 = BufferValue(g_revEmaHandle, 1);
   double atrM5 = BufferValue(g_atrM5Handle, 1);
   e.z = (emaM5 > 0.0 && atrM5 > 0.0) ? ((e.bid + e.ask) * 0.5 - emaM5) / atrM5 : 0.0;
   double revBase = InpRevStep;
   if(InpRevStepATR > 0.0 && atrM5 > 0.0)
      revBase = MathMax(revBase, atrM5 * InpRevStepATR);
   e.revStep  = MathMax(revBase * e.stepMult, g_tickSize);
   e.revStart = MathMax(MathMax(InpRevStart, revBase) * e.stepMult, MinStopDistance() + g_tickSize);

   //--- berita
   string info = "";
   e.newsPhase = UpdateNews(e, info);
   e.newsInfo  = info;

   double marginUsed = AccountInfoDouble(ACCOUNT_MARGIN);
   e.marginLow = (InpMinMarginLevel > 0.0 && marginUsed > 0.0 &&
                  AccountInfoDouble(ACCOUNT_MARGIN_LEVEL) < InpMinMarginLevel);

   MqlDateTime t;
   TimeToStruct(TimeCurrent(), t);
   e.inSession      = InServerHours(t.hour);
   e.fridayStop     = InpFridayStop && t.day_of_week == 5 && t.hour >= InpFridayStopHour;
   e.fridayClose    = InpFridayCloseAll && t.day_of_week == 5 && t.hour >= InpFridayCloseHour;
   e.dailyTargetHit = (InpDailyProfitTarget > 0.0 && g_realizedToday >= InpDailyProfitTarget);
   e.halted         = (TimeCurrent() < g_haltUntil);
   e.tradeAllowed   = (TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) != 0 && MQLInfoInteger(MQL_TRADE_ALLOWED) != 0);
   return true;
  }

//+------------------------------------------------------------------+
//| Proteksi global                                                  |
//+------------------------------------------------------------------+
bool GlobalProtection(const SEnv &e, const SBasket &b[])
  {
   double floating = 0.0;
   bool anyOpen = false;
   for(int s = 0; s < SLOT_COUNT; s++)
     {
      floating += b[s].profit;
      if(b[s].positions + b[s].pendings > 0)
         anyOpen = true;
     }
   floating += AlphaFloating();
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);

   if(e.halted)
     {
      if(anyOpen)
         CloseAll("HALT aktif", false);
      for(int s = 0; s < SLOT_COUNT; s++)
         g_status[s] = "HALT s/d " + TimeToString(g_haltUntil, TIME_DATE | TIME_MINUTES);
      return true;
     }
   if(InpMaxDrawdownPct > 0.0 && floating < 0.0 && -floating >= balance * InpMaxDrawdownPct / 100.0)
     {
      CloseAll(StringFormat("drawdown %.2f >= %.1f%% saldo", floating, InpMaxDrawdownPct), true);
      return true;
     }
   if(InpDailyLossLimit > 0.0 && g_realizedToday + floating <= -InpDailyLossLimit)
     {
      CloseAll(StringFormat("batas rugi harian %.2f", g_realizedToday + floating), true);
      return true;
     }
   if(e.fridayClose && anyOpen)
     {
      CloseAll("tutup akhir pekan", false);
      return true;
     }
   return false;
  }

//+------------------------------------------------------------------+
//| Manajemen exit basket                                            |
//+------------------------------------------------------------------+
bool CheckTarget(const int s, const SBasket &b, const double target, const bool immediate, const string label)
  {
   if(immediate)
     {
      if(b.profit >= target)
        {
         StartClose(s, StringFormat("%s +%.2f", label, b.profit), false);
         return true;
        }
      return false;
     }
   // kunci profit: aktif saat target tercapai, lalu ikuti puncak profit
   if(g_peak[s] <= 0.0 && b.profit >= target)
     {
      g_peak[s] = b.profit;
      SavePeak(s);
      PrintFormat("[SAPU JAGAD] Kunci profit %s aktif di +%.2f", SlotName(s), b.profit);
     }
   if(g_peak[s] > 0.0)
     {
      if(b.profit > g_peak[s])
        {
         g_peak[s] = b.profit;
         SavePeak(s);
        }
      if(b.profit <= g_peak[s] * (1.0 - InpLockGivebackPct / 100.0))
        {
         StartClose(s, StringFormat("kunci profit +%.2f (puncak %.2f)", b.profit, g_peak[s]), false);
         return true;
        }
     }
   return false;
  }

bool RevRegimeFlipped(const int s, const SEnv &e)
  {
   return InpRevRegimeExit && e.regime == REGIME_TREND && e.erDir == -SlotDir(s);
  }

bool ManageExit(const int s, const SBasket &b, const SEnv &e)
  {
   if(g_closing[s])
      return false;
   if(b.positions == 0)
     {
      ResetPeak(s);
      return false;
     }
   double units   = b.volume / 0.01;
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   long   age     = 0;
   if(b.oldestTime > 0)
      age = (long)(TimeCurrent() - b.oldestTime);

   if(SlotIsNews(s))
     {
      if(InpNewsSLPerMinLot > 0.0 && b.profit <= -InpNewsSLPerMinLot * units)
        {
         StartClose(s, StringFormat("cut loss berita %.2f", b.profit), false);
         return true;
        }
      if(InpNewsMaxHoldMin > 0 && age >= InpNewsMaxHoldMin * 60)
        {
         StartClose(s, StringFormat("batas waktu berita %+.2f", b.profit), false);
         return true;
        }
      return CheckTarget(s, b, InpNewsTPPerMinLot * units, !InpUseProfitLock, "TP berita");
     }

   if(SlotIsRev(s))
     {
      if((InpRevSLPerMinLot > 0.0 && b.profit <= -InpRevSLPerMinLot * units) ||
         (InpBasketSLPct > 0.0 && b.profit <= -balance * InpBasketSLPct / 100.0))
        {
         StartClose(s, StringFormat("cut loss reversion %.2f", b.profit), true);
         return true;
        }
      if(InpRevMaxHoldMin > 0 && age >= InpRevMaxHoldMin * 60)
        {
         StartClose(s, StringFormat("batas waktu reversion %+.2f", b.profit), false);
         return true;
        }
      // rezim berbalik jadi tren melawan basket: cukup keluar di titik impas
      bool flipped = RevRegimeFlipped(s, e);
      double target = (flipped ? InpRecoveryTPPerMinLot : InpRevTPPerMinLot) * units;
      return CheckTarget(s, b, target, true, flipped ? "TP impas (rezim berbalik)" : "TP reversion");
     }

   if((InpBasketSLMoney > 0.0 && b.profit <= -InpBasketSLMoney) ||
      (InpBasketSLPct > 0.0 && b.profit <= -balance * InpBasketSLPct / 100.0))
     {
      StartClose(s, StringFormat("cut loss %.2f", b.profit), true);
      return true;
     }
   bool recovery = false;
   double target = BasketTarget(b, recovery);
   return CheckTarget(s, b, target, recovery || !InpUseProfitLock, recovery ? "TP recovery" : "TP basket");
  }

//+------------------------------------------------------------------+
//| Tangga pending (stop & limit)                                    |
//+------------------------------------------------------------------+
void SortLadder(ulong &tickets[], double &prices[], const int n, const bool ascending)
  {
   for(int i = 1; i < n; i++)
     {
      ulong  t = tickets[i];
      double p = prices[i];
      int j = i - 1;
      while(j >= 0 && (ascending ? prices[j] > p : prices[j] < p))
        {
         tickets[j + 1] = tickets[j];
         prices[j + 1]  = prices[j];
         j--;
        }
      tickets[j + 1] = t;
      prices[j + 1]  = p;
     }
  }

int PlaceLadder(const int s, const int count, const SEnv &e, const double step, const double start, const double lot)
  {
   int dir = SlotDir(s);
   int ext = SlotExt(s);
   double margin = 0.0;
   ENUM_ORDER_TYPE mtype = (dir > 0) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   double refPrice = (dir > 0) ? e.ask : e.bid;
   if(OrderCalcMargin(mtype, _Symbol, lot * count, refPrice, margin) &&
      margin > AccountInfoDouble(ACCOUNT_MARGIN_FREE))
     {
      g_status[s] = "margin tidak cukup";
      Warn(StringFormat("Margin tidak cukup untuk tangga %s %d x %.2f lot", SlotName(s), count, lot));
      return 0;
     }

   double anchor = refPrice + ext * start;
   string tag = "";
   if(SlotIsNews(s))
      tag = "N";
   if(SlotIsRev(s))
      tag = "R";
   tag += (dir > 0) ? "B" : "S";
   int placed = 0;
   for(int i = 0; i < count; i++)
     {
      double price = NormPrice(anchor + ext * i * step);
      string cmt = StringFormat("%s %s%d", InpComment, tag, i + 1);
      if(!SendPendingOrder(s, lot, price, cmt))
         break;
      placed++;
     }
   if(placed > 0)
      PrintFormat("[SAPU JAGAD] Tangga %s: %d x %.2f lot, mulai %s, jarak %s",
                  SlotName(s), placed, lot, DoubleToString(NormPrice(anchor), _Digits), DoubleToString(step, _Digits));
   return placed;
  }

// geser tangga mengikuti harga bila harga menjauh (stop: ikut turun/naik, limit: ikut naik/turun)
void TrailLadder(const int s, const SEnv &e, const double step, const double start, const double trailStep)
  {
   ulong nowMs = GetTickCount64();
   if(InpTrailCooldownMs > 0 && nowMs - g_lastTrailMs[s] < (ulong)InpTrailCooldownMs)
      return;

   int dir = SlotDir(s);
   int ext = SlotExt(s);
   ulong  tickets[];
   double prices[];
   int n = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      ulong ticket = OrderGetTicket(i);
      if(ticket == 0 || !IsOurPending(s))
         continue;
      ArrayResize(tickets, n + 1);
      ArrayResize(prices, n + 1);
      tickets[n] = ticket;
      prices[n]  = OrderGetDouble(ORDER_PRICE_OPEN);
      n++;
     }
   if(n == 0)
      return;

   // urutkan dari level terdekat ke harga
   SortLadder(tickets, prices, n, ext > 0);
   double ref    = (dir > 0) ? e.ask : e.bid;
   double anchor = NormPrice(ref + ext * start);
   double gap    = ext * (prices[0] - anchor);
   if(gap < trailStep - g_tickSize * 0.5)
      return;   // harga belum cukup menjauh

   double freeze = FreezeDistance();
   trade.SetExpertMagicNumber(SlotMagic(s));
   for(int i = 0; i < n; i++)
     {
      double np = NormPrice(anchor + ext * i * step);
      if(MathAbs(np - prices[i]) < g_tickSize * 0.5)
         continue;
      double distNow = ext * (prices[i] - ref);
      if(freeze > 0.0 && distNow <= freeze)
         continue;
      if(!trade.OrderModify(tickets[i], np, 0.0, 0.0, g_typeTime, 0) || !IsOk(trade.ResultRetcode()))
         Warn(StringFormat("Gagal geser pending #%s ke %s: %u", (string)tickets[i],
                           DoubleToString(np, _Digits), trade.ResultRetcode()));
     }
   g_lastTrailMs[s] = nowMs;
  }

// jumlah "slot" terpakai; di akun netting posisi digabung, jadi pakai volume
int SlotsUsed(const SBasket &b, const SEnv &e)
  {
   int byVolume = (e.lot > 0.0) ? (int)MathRound(b.volume / e.lot) : b.positions;
   return (int)MathMax(b.positions, byVolume);
  }

// pemeriksaan bersama semua mesin: 1 = boleh, 0 = bekukan, -1 = hapus pending
int CommonPermission(const int s, const SEnv &e, string &why)
  {
   why = "AKTIF";
   if(g_closing[s])             { why = "menutup basket";                 return -1; }
   if(e.halted)                 { why = "HALT";                           return -1; }
   if(e.fridayClose)            { why = "tutup akhir pekan";              return -1; }
   if(e.newsPhase != NEWS_NONE) { why = "perisai berita " + NewsPhaseName(e.newsPhase); return -1; }
   if(e.rollover)               { why = "rollover harian";                return -1; }
   if(e.volBlock)               { why = StringFormat("volatilitas ekstrem x%.1f", e.volRatio); return -1; }
   if(e.openGuard)              { why = "anti stop-hunt pembukaan sesi";  return -1; }
   if(e.marginLow)              { why = "margin level rendah";            return -1; }
   if(e.spreadBad)              { why = "spread lebar";                   return InpDeletePendingOnWideSpread ? -1 : 0; }
   return 1;
  }

// syarat bersama untuk membuka basket baru
bool NewBasketAllowed(const int s, const SBasket &b[], const SEnv &e, string &why)
  {
   if(InpOneBasketOnly && OthersBusy(s, b)) { why = "basket lain aktif";      return false; }
   if(e.dailyTargetHit)                     { why = "target harian tercapai"; return false; }
   if(!e.inSession)                         { why = "di luar jam trading";    return false; }
   if(!e.sessionAllowed)                    { why = "sesi " + SessionName(e.session) + " nonaktif"; return false; }
   if(e.fridayStop)                         { why = "Jumat: stop entry";      return false; }
   if(TimeCurrent() < g_cooldownUntil[s])   { why = "jeda setelah cut loss";  return false; }
   return true;
  }

bool MomentumDirectionAllowed(const int dir, const SEnv &e)
  {
   if(InpDirection == SJ_DIR_BUY_ONLY)
      return dir > 0;
   if(InpDirection == SJ_DIR_SELL_ONLY)
      return dir < 0;
   if(InpEngineMode == SJ_ENGINE_ADAPTIVE && !InpAdaptiveUseH1)
      return true;   // arah ditentukan Efficiency Ratio
   return e.trend == dir;
  }

int MomentumPermission(const int s, const SBasket &b[], const SEnv &e, string &why)
  {
   int perm = CommonPermission(s, e, why);
   if(perm <= 0)
      return perm;
   int dir = SlotDir(s);
   bool adaptive = (InpEngineMode == SJ_ENGINE_ADAPTIVE);
   if(TimeCurrent() < g_pauseUntil[s])
     {
      why = "jeda burst s/d " + TimeToString(g_pauseUntil[s], TIME_MINUTES | TIME_SECONDS);
      return -1;
     }
   if(SlotsUsed(b[s], e) >= InpMaxPositions)
     {
      why = "maks posisi";
      return -1;
     }
   if(b[s].positions > 0)
     {
      bool against = (e.trend == -dir) || (adaptive && e.regime == REGIME_TREND && e.erDir == -dir);
      if(InpNoAddAgainstTrend && against)
        {
         why = "tren berbalik: stop tambah posisi";
         return -1;
        }
      return 1;   // basket berjalan tetap dikelola sampai tutup (recovery)
     }
   if(InpEngineMode == SJ_ENGINE_REVERSION)
     {
      why = "mesin momentum nonaktif";
      return -1;
     }
   if(!MomentumDirectionAllowed(dir, e))
     {
      why = (InpDirection == SJ_DIR_AUTO) ? "lawan tren H1" : "arah nonaktif";
      return -1;
     }
   if(adaptive && !(e.regime == REGIME_TREND && e.erDir == dir))
     {
      why = "rezim " + RegimeName(e.regime) + ": tunggu tren " + DirName(dir);
      return -1;
     }
   if(!NewBasketAllowed(s, b, e, why))
      return -1;
   return 1;
  }

void ManageMomentumLadder(const int s, const SBasket &b[], const SEnv &e)
  {
   // penjaga burst: terlalu banyak stop terisi dalam waktu singkat = lonjakan, hentikan penambahan
   if(InpBurstMaxFills > 0 && b[s].recentFills >= InpBurstMaxFills && TimeCurrent() >= g_pauseUntil[s])
     {
      g_pauseUntil[s] = TimeCurrent() + InpBurstPauseSec;
      PrintFormat("[SAPU JAGAD] Burst %s: %d stop terisi dalam %d detik, tangga dijeda %d detik",
                  SlotName(s), b[s].recentFills, InpBurstSeconds, InpBurstPauseSec);
     }

   string why = "";
   int perm = MomentumPermission(s, b, e, why);
   g_status[s] = why;
   if(perm < 0)
     {
      if(b[s].pendings > 0)
         DeletePendings(s);
      return;
     }
   if(perm == 0)
      return;

   if(b[s].pendings == 0)
     {
      ulong nowMs = GetTickCount64();
      if(nowMs < g_retryAfterMs[s])
         return;
      int count = MathMin(InpGridLevels, InpMaxPositions - SlotsUsed(b[s], e));
      if(count > 0 && PlaceLadder(s, count, e, e.step, e.start, e.lot) == 0)
         g_retryAfterMs[s] = nowMs + 5000;   // jangan banjiri server bila gagal
      return;
     }
   TrailLadder(s, e, e.step, e.start, InpTrailStep);
  }

int ReversionPermission(const int s, const SBasket &b[], const SEnv &e, string &why)
  {
   int perm = CommonPermission(s, e, why);
   if(perm <= 0)
      return perm;
   int dir = SlotDir(s);
   if(b[s].positions > 0)
     {
      if(RevRegimeFlipped(s, e))
        {
         why = "rezim berbalik: stop tambah, keluar impas";
         return -1;
        }
      return 1;
     }
   if(InpEngineMode == SJ_ENGINE_MOMENTUM)
     {
      why = "mesin reversion nonaktif";
      return -1;
     }
   if(InpEngineMode == SJ_ENGINE_ADAPTIVE && e.regime != REGIME_RANGE)
     {
      why = "rezim " + RegimeName(e.regime) + ": tunggu RANGE";
      return -1;
     }
   int revDir = 0;
   if(e.z >= InpRevZEntry)
      revDir = -1;     // harga jauh di atas rata-rata: pasang SELL LIMIT
   if(e.z <= -InpRevZEntry)
      revDir = 1;      // harga jauh di bawah rata-rata: pasang BUY LIMIT
   if(revDir != dir)
     {
      why = StringFormat("z %+.2f belum cukup jauh", e.z);
      return -1;
     }
   if(InpRevWithTrendOnly && e.trend != dir)
     {
      why = "lawan tren H1";
      return -1;
     }
   if(!NewBasketAllowed(s, b, e, why))
      return -1;
   return 1;
  }

void ManageReversionLadder(const int s, const SBasket &b[], const SEnv &e)
  {
   string why = "";
   int perm = ReversionPermission(s, b, e, why);
   g_status[s] = why;
   if(perm < 0)
     {
      if(b[s].pendings > 0)
         DeletePendings(s);
      return;
     }
   if(perm == 0 || b[s].positions > 0)
      return;   // tangga limit statis selama basket berjalan (seperti video 2)

   if(b[s].pendings == 0)
     {
      ulong nowMs = GetTickCount64();
      if(nowMs < g_retryAfterMs[s])
         return;
      if(PlaceLadder(s, InpRevLevels, e, e.revStep, e.revStart, e.lot) == 0)
         g_retryAfterMs[s] = nowMs + 5000;
      return;
     }
   TrailLadder(s, e, e.revStep, e.revStart, e.revStep);
  }

//+------------------------------------------------------------------+
//| Kecerdasan berita                                                |
//+------------------------------------------------------------------+
// menjelang rilis: amankan basket momentum/reversion yang sedang profit
void NewsPreActions(const SEnv &e, const SBasket &b[])
  {
   if(!InpNewsBankProfit || e.newsPhase != NEWS_PRE)
      return;
   for(int s = 0; s < SLOT_COUNT; s++)
     {
      if(SlotIsNews(s))
         continue;
      if(b[s].positions > 0 && b[s].profit > 0.0 && !g_closing[s])
         StartClose(s, StringFormat("amankan profit sebelum berita +%.2f", b[s].profit), false);
     }
  }

// pasca rilis: pasang tangga searah impuls bila pergerakan cukup kuat
void NewsRide(const SEnv &e, const SBasket &b[])
  {
   if(!InpUseNewsFilter || !InpNewsRide || g_newsEventTime == 0 || g_newsRideDone)
      return;
   datetime now = TimeCurrent();
   if(now < g_newsEventTime + InpNewsSettleSec)
      return;
   if(now > g_newsRideUntil)
     {
      g_newsRideDone = true;
      return;
     }
   if(g_newsRefPrice <= 0.0 || g_newsRefATR <= 0.0)
     {
      g_newsRideDone = true;   // EA tidak melihat harga sebelum rilis
      return;
     }
   if(e.halted || e.marginLow || e.spread > InpNewsMaxSpread)
      return;

   double impulse = (e.bid + e.ask) * 0.5 - g_newsRefPrice;
   if(MathAbs(impulse) < InpNewsImpulseATR * g_newsRefATR)
      return;
   int dir = (impulse > 0.0) ? 1 : -1;
   int s = (dir > 0) ? 2 : 3;
   if(g_closing[s] || b[s].positions + b[s].pendings > 0)
      return;

   g_newsStep  = MathMax(g_newsRefATR * InpNewsStepATR, g_tickSize);
   g_newsStart = MathMax(g_newsRefATR * InpNewsStartATR, MinStopDistance() + g_tickSize);
   double lot  = NormalizeLot(e.lot * InpNewsLotMult);
   g_newsRideDone = true;   // satu tangga per berita
   PrintFormat("[SAPU JAGAD] Penunggang berita %s: impuls %+.2f (ATR %.2f) setelah %s",
               DirName(dir), impulse, g_newsRefATR, g_newsEventName);
   PlaceLadder(s, InpNewsLevels, e, g_newsStep, g_newsStart, lot);
  }

void ManageNewsLadder(const int s, const SBasket &b, const SEnv &e)
  {
   if(b.pendings == 0)
     {
      g_status[s] = (b.positions > 0) ? "posisi berita dikelola" : "siaga";
      return;
     }
   if(g_closing[s] || e.halted || TimeCurrent() > g_newsRideUntil)
     {
      DeletePendings(s);   // jendela habis: pending yang belum terisi dibuang
      g_status[s] = "jendela berita selesai";
      return;
     }
   if(e.spread > InpNewsMaxSpread)
     {
      g_status[s] = "tangga berita beku (spread)";
      return;
     }
   g_status[s] = "tangga berita aktif";
   TrailLadder(s, e, g_newsStep, g_newsStart, InpTrailStep);
  }

//+------------------------------------------------------------------+
//| Mesin ALPHA: model ML (LightGBM) hasil sapu_jagad_alpha.py       |
//| Fitur dihitung dari candle M15 yang sudah tutup, IDENTIK dengan  |
//| compute_features() di Python. Model dibaca dari file teks.       |
//+------------------------------------------------------------------+
#define ALPHA_NFEAT 45
#define ALPHA_BARS  2000
string ALPHA_FEATURES = "body_0,uwick_0,lwick_0,clv_0,rngatr_0,vol_0,wbody_0,body_1,uwick_1,lwick_1,clv_1,rngatr_1,vol_1,wbody_1,body_2,uwick_2,lwick_2,clv_2,rngatr_2,vol_2,wbody_2,ret_1,ret_2,ret_4,ret_8,ret_16,ret_32,ret_96,ret_480,volratio,er_16,er_96,vr_4,z_ema_20,z_ema_50,z_ema_200,don_32,don_96,don_480,gmt_sin,gmt_cos,ny_sin,ny_cos,dow,min_since_830";

bool     g_aLoaded    = false;
bool     g_aValidated = false;
int      g_aHorizon   = 240;
double   g_aCut       = 1.0;
string   g_aSummary   = "";
string   g_aStatus    = "-";
datetime g_aLastBar   = 0;
double   g_aLastProb  = 0.5;
int      g_aTreeRoot[];
int      g_aNodeStart[];
int      g_aLeafStart[];
int      g_aNodeFeat[];
double   g_aNodeThr[];
int      g_aNodeLeft[];
int      g_aNodeRight[];
int      g_aNodeDefLeft[];
int      g_aNodeMiss[];
double   g_aLeaf[];

ulong AlphaMagic() { return InpMagic + 3; }

double SafeDiv(const double a, const double d)
  {
   if(d > 0.0)
      return a / d;
   return 0.0;
  }

// rata-rata a[end-p+1 .. end]
double SmaEnd(const double &a[], const int end, const int p)
  {
   if(end - p + 1 < 0)
      return 0.0;
   double sum = 0.0;
   for(int i = end - p + 1; i <= end; i++)
      sum += a[i];
   return sum / p;
  }

// varians sampel (ddof = 1) dari a[end-p+1 .. end]
double SampleVarEnd(const double &a[], const int end, const int p)
  {
   if(end - p + 1 < 0 || p < 2)
      return 0.0;
   double m = SmaEnd(a, end, p);
   double ss = 0.0;
   for(int i = end - p + 1; i <= end; i++)
      ss += (a[i] - m) * (a[i] - m);
   return ss / (p - 1);
  }

// jam musim panas AS: Minggu ke-2 Maret 07:00 UTC s/d Minggu pertama November 06:00 UTC
bool UsDstActive(const datetime utc)
  {
   MqlDateTime t;
   TimeToStruct(utc, t);
   MqlDateTime s;
   s.year = t.year;
   s.mon  = 3;
   s.day  = 1;
   s.hour = 0;
   s.min  = 0;
   s.sec  = 0;
   datetime mar1 = StructToTime(s);
   MqlDateTime w;
   TimeToStruct(mar1, w);
   int firstSun = 1 + (7 - w.day_of_week) % 7;
   datetime dstStart = mar1 + (firstSun - 1 + 7) * 86400 + 7 * 3600;
   s.mon = 11;
   datetime nov1 = StructToTime(s);
   TimeToStruct(nov1, w);
   firstSun = 1 + (7 - w.day_of_week) % 7;
   datetime dstEnd = nov1 + (firstSun - 1) * 86400 + 6 * 3600;
   return (utc >= dstStart && utc < dstEnd);
  }

bool AlphaLoadModel()
  {
   g_aLoaded = false;
   int h = FileOpen(InpAlphaModelFile, FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON | FILE_SHARE_READ);
   if(h == INVALID_HANDLE)
     {
      g_aStatus = "file model tidak ditemukan";
      PrintFormat("[SAPU JAGAD] Alpha: file %s tidak ada di Common\\Files (err %d).", InpAlphaModelFile, GetLastError());
      return false;
     }
   string head = FileReadString(h);
   if(StringFind(head, "SAPUJAGAD_ALPHA") != 0)
     {
      FileClose(h);
      g_aStatus = "format file model salah";
      return false;
     }
   int nTrees = 0;
   string feats = "";
   while(!FileIsEnding(h))
     {
      string line = FileReadString(h);
      int eq = StringFind(line, "=");
      if(eq <= 0)
         continue;
      string key = StringSubstr(line, 0, eq);
      string val = StringSubstr(line, eq + 1);
      if(key == "validated")
         g_aValidated = (StringToInteger(val) == 1);
      else
         if(key == "horizon_min")
            g_aHorizon = (int)StringToInteger(val);
         else
            if(key == "cut")
               g_aCut = StringToDouble(val);
            else
               if(key == "features")
                  feats = val;
               else
                  if(key == "summary")
                     g_aSummary = val;
                  else
                     if(key == "trees")
                       {
                        nTrees = (int)StringToInteger(val);
                        break;
                       }
     }
   if(feats != ALPHA_FEATURES || nTrees <= 0 || g_aHorizon <= 0)
     {
      FileClose(h);
      g_aStatus = "model tidak cocok dengan versi EA";
      Print("[SAPU JAGAD] Alpha: daftar fitur/format model tidak cocok dengan EA ini.");
      return false;
     }
   ArrayResize(g_aTreeRoot, nTrees);
   ArrayResize(g_aNodeStart, nTrees);
   ArrayResize(g_aLeafStart, nTrees);
   ArrayResize(g_aNodeFeat, 0);
   ArrayResize(g_aNodeThr, 0);
   ArrayResize(g_aNodeLeft, 0);
   ArrayResize(g_aNodeRight, 0);
   ArrayResize(g_aNodeDefLeft, 0);
   ArrayResize(g_aNodeMiss, 0);
   ArrayResize(g_aLeaf, 0);
   ushort sp = StringGetCharacter(" ", 0);
   int nodeTotal = 0;
   int leafTotal = 0;
   bool ok = true;
   for(int t = 0; t < nTrees && ok; t++)
     {
      string p[];
      if(StringSplit(FileReadString(h), sp, p) != 4 || p[0] != "TREE")
        {
         ok = false;
         break;
        }
      int nn = (int)StringToInteger(p[1]);
      int nl = (int)StringToInteger(p[2]);
      g_aTreeRoot[t]  = (int)StringToInteger(p[3]);
      g_aNodeStart[t] = nodeTotal;
      g_aLeafStart[t] = leafTotal;
      ArrayResize(g_aNodeFeat, nodeTotal + nn);
      ArrayResize(g_aNodeThr, nodeTotal + nn);
      ArrayResize(g_aNodeLeft, nodeTotal + nn);
      ArrayResize(g_aNodeRight, nodeTotal + nn);
      ArrayResize(g_aNodeDefLeft, nodeTotal + nn);
      ArrayResize(g_aNodeMiss, nodeTotal + nn);
      for(int k = 0; k < nn; k++)
        {
         string q[];
         if(StringSplit(FileReadString(h), sp, q) != 7 || q[0] != "N")
           {
            ok = false;
            break;
           }
         int n = nodeTotal + k;
         g_aNodeFeat[n]    = (int)StringToInteger(q[1]);
         g_aNodeThr[n]     = StringToDouble(q[2]);
         g_aNodeLeft[n]    = (int)StringToInteger(q[3]);
         g_aNodeRight[n]   = (int)StringToInteger(q[4]);
         g_aNodeDefLeft[n] = (int)StringToInteger(q[5]);
         g_aNodeMiss[n]    = (int)StringToInteger(q[6]);
         if(g_aNodeFeat[n] < 0 || g_aNodeFeat[n] >= ALPHA_NFEAT)
            ok = false;
        }
      ArrayResize(g_aLeaf, leafTotal + nl);
      for(int k = 0; k < nl && ok; k++)
        {
         string q[];
         if(StringSplit(FileReadString(h), sp, q) != 2 || q[0] != "L")
           {
            ok = false;
            break;
           }
         g_aLeaf[leafTotal + k] = StringToDouble(q[1]);
        }
      nodeTotal += nn;
      leafTotal += nl;
     }
   FileClose(h);
   if(!ok)
     {
      g_aStatus = "file model rusak";
      Print("[SAPU JAGAD] Alpha: file model rusak/terpotong.");
      return false;
     }
   g_aLoaded = true;
   g_aStatus = g_aValidated ? "model LOLOS validasi" : "model TIDAK LOLOS validasi";
   PrintFormat("[SAPU JAGAD] Alpha: %d pohon, horizon %d mnt, ambang %.4f, %s | %s",
               nTrees, g_aHorizon, g_aCut, g_aStatus, g_aSummary);
   return true;
  }

// peluang harga naik dalam horizon model (0..1)
double AlphaPredict(const double &f[])
  {
   int nTrees = ArraySize(g_aTreeRoot);
   double raw = 0.0;
   for(int t = 0; t < nTrees; t++)
     {
      int base = g_aNodeStart[t];
      int k = g_aTreeRoot[t];
      int guard = 0;
      while(k >= 0 && guard < 4096)
        {
         int n = base + k;
         double v = f[g_aNodeFeat[n]];
         bool valid = MathIsValidNumber(v);
         bool goLeft = false;
         if(g_aNodeMiss[n] == 2 && !valid)
            goLeft = (g_aNodeDefLeft[n] == 1);
         else
            if(g_aNodeMiss[n] == 1 && (!valid || v == 0.0))
               goLeft = (g_aNodeDefLeft[n] == 1);
            else
              {
               if(!valid)
                  v = 0.0;
               goLeft = (v <= g_aNodeThr[n]);
              }
         k = goLeft ? g_aNodeLeft[n] : g_aNodeRight[n];
         guard++;
        }
      if(k < 0)
         raw += g_aLeaf[g_aLeafStart[t] - k - 1];
     }
   return 1.0 / (1.0 + MathExp(-raw));
  }

// fitur candle M15 tertutup terakhir (urutan = ALPHA_FEATURES)
bool AlphaFeatures(double &f[], datetime &decUtc, double &atrOut)
  {
   MqlRates r[];
   int n = CopyRates(_Symbol, PERIOD_M15, 1, ALPHA_BARS, r);
   if(n < 600)
      return false;
   double o[], hh[], ll[], c[], tv[], tr[], d1[], d4[];
   ArrayResize(o, n);
   ArrayResize(hh, n);
   ArrayResize(ll, n);
   ArrayResize(c, n);
   ArrayResize(tv, n);
   ArrayResize(tr, n);
   ArrayResize(d1, n);
   ArrayResize(d4, n);
   for(int i = 0; i < n; i++)
     {
      o[i]  = r[i].open;
      hh[i] = r[i].high;
      ll[i] = r[i].low;
      c[i]  = r[i].close;
      tv[i] = (double)r[i].tick_volume;
      if(i == 0)
         tr[i] = hh[i] - ll[i];
      else
         tr[i] = MathMax(hh[i] - ll[i], MathMax(MathAbs(hh[i] - c[i - 1]), MathAbs(ll[i] - c[i - 1])));
      d1[i] = (i >= 1) ? c[i] - c[i - 1] : 0.0;
      d4[i] = (i >= 4) ? c[i] - c[i - 4] : 0.0;
     }
   int N = n - 1;
   double atr96 = SmaEnd(tr, N, 96);
   atrOut = atr96;
   ArrayResize(f, ALPHA_NFEAT);
   ArrayInitialize(f, 0.0);
   int idx = 0;
   //--- anatomi / bobot 3 candle terakhir
   for(int k = 0; k < 3; k++)
     {
      int j = N - k;
      double rng  = hh[j] - ll[j];
      double body = SafeDiv(c[j] - o[j], rng);
      double vol  = SafeDiv(tv[j], SmaEnd(tv, j, 96));
      f[idx++] = body;
      f[idx++] = SafeDiv(hh[j] - MathMax(o[j], c[j]), rng);
      f[idx++] = SafeDiv(MathMin(o[j], c[j]) - ll[j], rng);
      f[idx++] = SafeDiv((c[j] - ll[j]) - (hh[j] - c[j]), rng);
      f[idx++] = SafeDiv(rng, SmaEnd(tr, j, 96));
      f[idx++] = vol;
      f[idx++] = body * vol;
     }
   //--- momentum multi-horizon
   int lags[8] = {1, 2, 4, 8, 16, 32, 96, 480};
   for(int k = 0; k < 8; k++)
      f[idx++] = SafeDiv(c[N] - c[N - lags[k]], atr96);
   //--- volatilitas & rezim
   f[idx++] = SafeDiv(SmaEnd(tr, N, 14), atr96);
   int ers[2] = {16, 96};
   for(int k = 0; k < 2; k++)
     {
      double path = 0.0;
      for(int i = N - ers[k] + 1; i <= N; i++)
         path += MathAbs(c[i] - c[i - 1]);
      f[idx++] = SafeDiv(MathAbs(c[N] - c[N - ers[k]]), path);
     }
   f[idx++] = SafeDiv(SampleVarEnd(d4, N, 96), 4.0 * SampleVarEnd(d1, N, 96));
   //--- jarak ke EMA (dalam ATR)
   int spans[3] = {20, 50, 200};
   for(int k = 0; k < 3; k++)
     {
      double a = 2.0 / (spans[k] + 1.0);
      double ema = c[0];
      for(int i = 1; i <= N; i++)
         ema = a * c[i] + (1.0 - a) * ema;
      f[idx++] = SafeDiv(c[N] - ema, atr96);
     }
   //--- posisi di channel Donchian
   int dons[3] = {32, 96, 480};
   for(int k = 0; k < 3; k++)
     {
      double hi = hh[N];
      double lo = ll[N];
      for(int i = N - dons[k] + 1; i <= N; i++)
        {
         hi = MathMax(hi, hh[i]);
         lo = MathMin(lo, ll[i]);
        }
      f[idx++] = SafeDiv(c[N] - lo, hi - lo);
     }
   //--- waktu keputusan (akhir candle) dalam GMT & New York
   decUtc = r[N].time + 900 - ServerGMTOffsetHours() * 3600;
   double gm = (double)((long)decUtc % 86400) / 3600.0;
   datetime nyT = decUtc + (UsDstActive(decUtc) ? -4 : -5) * 3600;
   double nyh = (double)((long)nyT % 86400) / 3600.0;
   MqlDateTime nyS;
   TimeToStruct(nyT, nyS);
   int dowPy = (nyS.day_of_week + 6) % 7;          // Senin = 0 seperti pandas
   f[idx++] = MathSin(2.0 * M_PI * gm / 24.0);
   f[idx++] = MathCos(2.0 * M_PI * gm / 24.0);
   f[idx++] = MathSin(2.0 * M_PI * nyh / 24.0);
   f[idx++] = MathCos(2.0 * M_PI * nyh / 24.0);
   f[idx++] = (double)dowPy;
   int since = (int)(((long)nyT % 86400) / 60) - 510;
   f[idx++] = (since >= 0 && since <= 180 && dowPy < 5) ? (double)since : -1.0;
   for(int i = 0; i < ALPHA_NFEAT; i++)
      if(!MathIsValidNumber(f[i]))
         f[i] = 0.0;
   return (idx == ALPHA_NFEAT);
  }

void AlphaDump(const double &f[], const datetime decUtc)
  {
   int h = FileOpen("sapu_jagad_alpha_fitur_ea.csv", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON | FILE_SHARE_READ);
   if(h == INVALID_HANDLE)
      return;
   if(FileSize(h) == 0)
      FileWriteString(h, "dec_time," + ALPHA_FEATURES + "\n");
   FileSeek(h, 0, SEEK_END);
   string line = TimeToString(decUtc, TIME_DATE | TIME_SECONDS);
   for(int i = 0; i < ArraySize(f); i++)
      line += "," + DoubleToString(f[i], 10);
   FileWriteString(h, line + "\n");
   FileClose(h);
  }

bool AlphaFindPosition(ulong &ticket, int &dir, datetime &opened, double &profit)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol || (ulong)PositionGetInteger(POSITION_MAGIC) != AlphaMagic())
         continue;
      ticket = t;
      dir    = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
      opened = (datetime)PositionGetInteger(POSITION_TIME);
      profit = PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP) -
               PositionGetDouble(POSITION_VOLUME) * InpCommissionPerLot;
      return true;
     }
   return false;
  }

double AlphaFloating()
  {
   ulong ticket = 0;
   int dir = 0;
   datetime opened = 0;
   double profit = 0.0;
   if(AlphaFindPosition(ticket, dir, opened, profit))
      return profit;
   return 0.0;
  }

void AlphaClose(const ulong ticket, const string reason)
  {
   trade.SetExpertMagicNumber(AlphaMagic());
   for(int attempt = 0; attempt < 3; attempt++)
     {
      if(trade.PositionClose(ticket, g_slippagePts) && IsOk(trade.ResultRetcode()))
        {
         PrintFormat("[SAPU JAGAD] Alpha tutup: %s", reason);
         g_lastCloseInfo = StringFormat("ALPHA %s (%s)", reason, TimeToString(TimeCurrent(), TIME_MINUTES));
         return;
        }
      if(trade.ResultRetcode() == TRADE_RETCODE_INVALID_FILL)
         NextFilling();
      else
         Sleep(50);
     }
   Warn(StringFormat("Alpha gagal menutup posisi #%s: %u", (string)ticket, trade.ResultRetcode()));
  }

void AlphaCloseIfAny(const string reason)
  {
   ulong ticket = 0;
   int dir = 0;
   datetime opened = 0;
   double profit = 0.0;
   if(AlphaFindPosition(ticket, dir, opened, profit))
      AlphaClose(ticket, reason);
  }

void ManageAlpha(const SEnv &e)
  {
   if(!InpAlphaEnable)
     {
      g_aStatus = "nonaktif";
      return;
     }
   ulong ticket = 0;
   int dir = 0;
   datetime opened = 0;
   double profit = 0.0;
   bool hasPos = AlphaFindPosition(ticket, dir, opened, profit);
   if(hasPos)
     {
      if(e.halted || e.fridayClose)
        {
         AlphaClose(ticket, "proteksi global");
         return;
        }
      if(TimeCurrent() >= opened + g_aHorizon * 60)
        {
         AlphaClose(ticket, StringFormat("horizon %d mnt selesai %+.2f", g_aHorizon, profit));
         return;
        }
     }
   if(!g_aLoaded)
      return;

   datetime bar = iTime(_Symbol, PERIOD_M15, 0);
   if(bar == 0 || bar == g_aLastBar)
      return;
   g_aLastBar = bar;

   double f[];
   datetime decUtc = 0;
   double atr = 0.0;
   if(!AlphaFeatures(f, decUtc, atr))
     {
      g_aStatus = "riwayat M15 belum cukup";
      return;
     }
   if(InpAlphaDumpFeatures)
      AlphaDump(f, decUtc);
   g_aLastProb = AlphaPredict(f);
   double score = g_aLastProb - 0.5;

   if(!g_aValidated && !InpAlphaAllowUnvalidated)
     {
      g_aStatus = "model TIDAK LOLOS validasi: hanya memantau";
      return;
     }
   if(hasPos)
     {
      g_aStatus = StringFormat("posisi %s berjalan", DirName(dir));
      return;
     }
   if(MathAbs(score) < g_aCut)
     {
      g_aStatus = "menunggu sinyal kuat";
      return;
     }
   if(e.halted || e.fridayClose || e.marginLow || e.spreadBad)
     {
      g_aStatus = "sinyal ada, entry diblok proteksi";
      return;
     }

   int d = (score > 0.0) ? 1 : -1;
   double lot = NormalizeLot(e.lot * InpAlphaLotMult);
   double price = (d > 0) ? e.ask : e.bid;
   double sl = 0.0;
   if(InpAlphaSLATR > 0.0 && atr > 0.0)
     {
      double dist = MathMax(InpAlphaSLATR * atr, MinStopDistance() + g_tickSize);
      sl = NormPrice(price - d * dist);
     }
   trade.SetExpertMagicNumber(AlphaMagic());
   bool ok = false;
   for(int attempt = 0; attempt < 3 && !ok; attempt++)
     {
      bool sent = (d > 0) ? trade.Buy(lot, _Symbol, 0.0, sl, 0.0, InpComment + " ALPHA")
                          : trade.Sell(lot, _Symbol, 0.0, sl, 0.0, InpComment + " ALPHA");
      ok = sent && IsOk(trade.ResultRetcode());
      if(!ok)
        {
         if(trade.ResultRetcode() == TRADE_RETCODE_INVALID_FILL)
            NextFilling();
         else
            break;
        }
     }
   if(ok)
     {
      g_aStatus = StringFormat("masuk %s p=%.3f", DirName(d), g_aLastProb);
      PrintFormat("[SAPU JAGAD] Alpha %s %.2f lot, p=%.3f (skor %+.3f >= %.3f), SL %s, keluar %d mnt",
                  DirName(d), lot, g_aLastProb, score, g_aCut, DoubleToString(sl, _Digits), g_aHorizon);
     }
   else
      Warn(StringFormat("Alpha gagal masuk %s: %u %s", DirName(d), trade.ResultRetcode(), trade.ResultRetcodeDescription()));
  }

//+------------------------------------------------------------------+
//| Panel informasi                                                  |
//+------------------------------------------------------------------+
void PanelLine(const int idx, const string text, const color clr)
  {
   string name = g_objPrefix + "L" + IntegerToString(idx);
   if(ObjectFind(0, name) < 0)
     {
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_XDISTANCE, 16);
      ObjectSetInteger(0, name, OBJPROP_YDISTANCE, 30 + idx * 16);
      ObjectSetString(0, name, OBJPROP_FONT, "Consolas");
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 9);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
     }
   ObjectSetString(0, name, OBJPROP_TEXT, text);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
  }

void PanelBackground(const int lines)
  {
   string name = g_objPrefix + "BG";
   if(ObjectFind(0, name) < 0)
     {
      ObjectCreate(0, name, OBJ_RECTANGLE_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_XDISTANCE, 8);
      ObjectSetInteger(0, name, OBJPROP_YDISTANCE, 24);
      ObjectSetInteger(0, name, OBJPROP_XSIZE, 500);
      ObjectSetInteger(0, name, OBJPROP_BGCOLOR, C'12,14,18');
      ObjectSetInteger(0, name, OBJPROP_BORDER_TYPE, BORDER_FLAT);
      ObjectSetInteger(0, name, OBJPROP_COLOR, clrGoldenrod);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
     }
   ObjectSetInteger(0, name, OBJPROP_YSIZE, lines * 16 + 12);
  }

string BasketLine(const SBasket &b)
  {
   double target = 0.0;
   bool recovery = false;
   if(SlotIsNews(b.slot))
      target = InpNewsTPPerMinLot * b.volume / 0.01;
   else
      if(SlotIsRev(b.slot))
         target = InpRevTPPerMinLot * b.volume / 0.01;
      else
         target = BasketTarget(b, recovery);
   string s = StringFormat("%-6s %2d pos %5.2f lot  P/L %+8.2f  target %6.2f%s  pend %d",
                           SlotName(b.slot), b.positions, b.volume, b.profit, target,
                           recovery ? "R" : " ", b.pendings);
   if(b.positions > 0)
      s += "  avg " + DoubleToString(b.avgPrice, _Digits);
   return s;
  }

string StatusLine(const int s)
  {
   string txt = "       status: " + g_status[s];
   if(g_peak[s] > 0.0)
      txt += StringFormat("  | kunci puncak %.2f", g_peak[s]);
   return txt;
  }

// pilih slot yang paling relevan untuk ditampilkan dari sepasang slot
int ActiveOf(const SBasket &b[], const int a, const int c)
  {
   return (b[c].positions + b[c].pendings > b[a].positions + b[a].pendings) ? c : a;
  }

void UpdatePanel(const SEnv &e, const SBasket &b[])
  {
   if(!g_showPanel)
      return;
   ulong nowMs = GetTickCount64();
   if(nowMs - g_lastPanelMs < 300)
      return;
   g_lastPanelMs = nowMs;

   string engine = "ADAPTIF";
   if(InpEngineMode == SJ_ENGINE_MOMENTUM)
      engine = "MOMENTUM";
   if(InpEngineMode == SJ_ENGINE_REVERSION)
      engine = "REVERSION";
   string trend = (e.trend > 0) ? "NAIK" : ((e.trend < 0) ? "TURUN" : "netral");
   string news = "filter mati";
   if(InpUseNewsFilter)
     {
      news = NewsPhaseName(e.newsPhase);
      if(e.newsInfo != "")
         news += " - " + e.newsInfo;
      if(g_newsEventTime > 0 && !g_newsRideDone && TimeCurrent() <= g_newsRideUntil)
         news += " | penunggang siaga";
     }
   double balance  = AccountInfoDouble(ACCOUNT_BALANCE);
   double floating = 0.0;
   for(int s = 0; s < SLOT_COUNT; s++)
      floating += b[s].profit;
   double ddPct = (balance > 0.0 && floating < 0.0) ? -floating / balance * 100.0 : 0.0;
   string cur   = AccountInfoString(ACCOUNT_CURRENCY);
   string flags = "";
   if(e.rollover)
      flags += " ROLLOVER";
   if(e.openGuard)
      flags += " BUKA-SESI";
   if(e.volBlock)
      flags += " VOL-EKSTREM";
   string erDir = (e.erDir > 0) ? "naik" : ((e.erDir < 0) ? "turun" : "-");

   PanelBackground(PANEL_LINES);   // latar dibuat dulu agar label tergambar di atasnya
   int i = 0;
   PanelLine(i++, "EA SAPU JAGAD v1.30   " + _Symbol + (e.tradeAllowed ? "" : "   [AutoTrading OFF]"),
             e.tradeAllowed ? clrGold : clrTomato);
   PanelLine(i++, StringFormat("Mesin %s | Rezim %s (ER %.2f %s) | z %+.2f | Tren H1 %s", engine,
                               RegimeName(e.regime), e.er, erDir, e.z, trend), clrSilver);
   PanelLine(i++, StringFormat("Sesi %s %02d:%02d GMT | spread %s / %s | volatilitas x%.2f%s", SessionName(e.session),
                               e.gmtMinute / 60, e.gmtMinute % 60, DoubleToString(e.spread, _Digits),
                               DoubleToString(InpMaxSpread, 2), e.volRatio, flags),
             (flags != "" || e.spreadBad) ? clrOrange : clrSilver);
   PanelLine(i++, StringFormat("Momentum jarak %s mulai %s | Reversion jarak %s mulai %s | lot %.2f",
                               DoubleToString(e.step, 2), DoubleToString(e.start, 2),
                               DoubleToString(e.revStep, 2), DoubleToString(e.revStart, 2), e.lot), clrSilver);
   PanelLine(i++, BasketLine(b[0]), b[0].profit >= 0.0 ? clrLimeGreen : clrTomato);
   PanelLine(i++, StatusLine(0), clrDarkGray);
   PanelLine(i++, BasketLine(b[1]), b[1].profit >= 0.0 ? clrLimeGreen : clrTomato);
   PanelLine(i++, StatusLine(1), clrDarkGray);
   PanelLine(i++, BasketLine(b[4]), b[4].profit >= 0.0 ? clrLimeGreen : clrTomato);
   PanelLine(i++, StatusLine(4), clrDarkGray);
   PanelLine(i++, BasketLine(b[5]), b[5].profit >= 0.0 ? clrLimeGreen : clrTomato);
   PanelLine(i++, StatusLine(5), clrDarkGray);
   PanelLine(i++, "Berita: " + news, (e.newsPhase != NEWS_NONE) ? clrOrange : clrSilver);
   int ns = ActiveOf(b, 2, 3);
   PanelLine(i++, BasketLine(b[ns]) + "  | " + g_status[ns], b[ns].profit >= 0.0 ? clrLimeGreen : clrTomato);
   PanelLine(i++, StringFormat("Hari ini %+.2f %s | floating %+.2f | DD %.1f%%/%.0f%% | margin %.0f%%",
                               g_realizedToday, cur, floating, ddPct, InpMaxDrawdownPct,
                               AccountInfoDouble(ACCOUNT_MARGIN_LEVEL)),
             (g_realizedToday + floating) >= 0.0 ? clrLimeGreen : clrTomato);
   PanelLine(i++, StringFormat("Alpha: %s | p naik %.3f | skor %+.3f / ambang %.3f | H %d mnt%s", g_aStatus,
                               g_aLastProb, g_aLastProb - 0.5, g_aCut, g_aHorizon,
                               (g_aLoaded && !g_aValidated) ? " | TIDAK LOLOS" : ""),
             (g_aLoaded && g_aValidated) ? clrAqua : clrDarkGray);
   PanelLine(i++, "Tutup terakhir: " + g_lastCloseInfo, clrDarkGray);
   ChartRedraw(0);
  }

//+------------------------------------------------------------------+
//| Event handler                                                    |
//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpGridLevels < 1 || InpGridStep <= 0.0 || InpStartDistance < 0.0 || InpTrailStep <= 0.0 ||
      InpMaxPositions < 1 || InpFixedLot <= 0.0 || InpLockGivebackPct <= 0.0 || InpLockGivebackPct >= 100.0 ||
      InpStartHour < 0 || InpStartHour > 23 || InpEndHour < 0 || InpEndHour > 23 ||
      InpNewsLevels < 1 || InpVolSlowPeriod < 2 || InpVolWidenRatio <= 0.0 || InpVolBlockRatio <= 0.0 ||
      InpRegimeBars < 5 || InpERRange >= InpERTrend || InpRevLevels < 1 || InpRevStep <= 0.0 ||
      InpRevEMAPeriod < 2)
     {
      Print("[SAPU JAGAD] Parameter tidak valid, periksa kembali input EA.");
      return INIT_PARAMETERS_INCORRECT;
     }

   g_isTester  = (MQLInfoInteger(MQL_TESTER) != 0);
   g_showPanel = InpShowPanel && (!g_isTester || MQLInfoInteger(MQL_VISUAL_MODE) != 0);
   g_tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(g_tickSize <= 0.0)
      g_tickSize = _Point;
   g_slippagePts = (ulong)MathMax(1.0, MathRound(InpMaxSlippage / _Point));

   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(g_slippagePts);
   trade.SetMarginMode();
   trade.LogLevel(LOG_LEVEL_NO);   // log error ditangani sendiri (dibatasi) agar jurnal tidak banjir
   InitFilling();

   int expMode = (int)SymbolInfoInteger(_Symbol, SYMBOL_EXPIRATION_MODE);
   g_typeTime  = ((expMode & SYMBOL_EXPIRATION_GTC) == SYMBOL_EXPIRATION_GTC) ? ORDER_TIME_GTC : ORDER_TIME_DAY;

   g_objPrefix = "SJ_" + IntegerToString((long)InpMagic) + "_";
   g_gvPrefix  = "SJ_" + IntegerToString((long)InpMagic) + "_" + _Symbol + "_";
   for(int s = 0; s < SLOT_COUNT; s++)
     {
      g_closing[s]       = false;
      g_cooldownUntil[s] = 0;
      g_pauseUntil[s]    = 0;
      g_lastTrailMs[s]   = 0;
      g_retryAfterMs[s]  = 0;
      g_status[s]        = "-";
     }
   LoadState();

   g_emaHandle     = iMA(_Symbol, InpTrendTF, InpTrendEMA, 0, MODE_EMA, PRICE_CLOSE);
   g_atrSlowHandle = iATR(_Symbol, PERIOD_M1, InpVolSlowPeriod);
   g_atrNewsHandle = iATR(_Symbol, PERIOD_M1, 14);
   g_revEmaHandle  = iMA(_Symbol, PERIOD_M5, InpRevEMAPeriod, 0, MODE_EMA, PRICE_CLOSE);
   g_atrM5Handle   = iATR(_Symbol, PERIOD_M5, 14);
   if(g_emaHandle == INVALID_HANDLE || g_atrSlowHandle == INVALID_HANDLE || g_atrNewsHandle == INVALID_HANDLE ||
      g_revEmaHandle == INVALID_HANDLE || g_atrM5Handle == INVALID_HANDLE)
     {
      Print("[SAPU JAGAD] Gagal membuat indikator.");
      return INIT_FAILED;
     }
   if(InpUseATR)
     {
      g_atrHandle = iATR(_Symbol, InpATRTimeframe, InpATRPeriod);
      if(g_atrHandle == INVALID_HANDLE)
        {
         Print("[SAPU JAGAD] Gagal membuat indikator ATR.");
         return INIT_FAILED;
        }
     }

   if(InpUseNewsFilter && UseCsv())
      LoadNewsCsv();
   if(InpAlphaEnable)
      AlphaLoadModel();
   g_aLastBar = iTime(_Symbol, PERIOD_M15, 0);   // jangan entry dari candle yang sudah lama tutup

   if(AccountInfoInteger(ACCOUNT_MARGIN_MODE) != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
      Print("[SAPU JAGAD] Peringatan: akun bukan HEDGING. Posisi akan digabung (netting); gunakan satu arah saja.");

   PrintFormat("[SAPU JAGAD] Siap di %s | digit %d | tick %s | stops level %s | filling %s | GMT%+d",
               _Symbol, _Digits, DoubleToString(g_tickSize, _Digits), DoubleToString(MinStopDistance(), _Digits),
               EnumToString(g_filling), ServerGMTOffsetHours());
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   if(InpDeletePendingOnRemove && (reason == REASON_REMOVE || reason == REASON_CHARTCLOSE))
     {
      // cegah pending "yatim" terisi tanpa ada EA yang mengelola
      for(int s = 0; s < SLOT_COUNT; s++)
         DeletePendings(s);
     }
   ObjectsDeleteAll(0, g_objPrefix);
   int handles[6];
   handles[0] = g_emaHandle;
   handles[1] = g_atrHandle;
   handles[2] = g_atrSlowHandle;
   handles[3] = g_atrNewsHandle;
   handles[4] = g_revEmaHandle;
   handles[5] = g_atrM5Handle;
   for(int i = 0; i < 6; i++)
      if(handles[i] != INVALID_HANDLE)
         IndicatorRelease(handles[i]);
   ChartRedraw(0);
  }

void OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &request, const MqlTradeResult &result)
  {
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
      g_histDirty = true;
  }

void OnTick()
  {
   UpdateDaily();
   SEnv env;
   if(!BuildEnv(env))
      return;

   SBasket b[SLOT_COUNT];
   ScanAll(b);

   //--- 1. lanjutkan penutupan basket yang belum tuntas
   bool anyClosing = false;
   for(int s = 0; s < SLOT_COUNT; s++)
      if(g_closing[s])
        {
         CloseBasketNow(s);
         anyClosing = true;
        }
   if(anyClosing)
     {
      ScanAll(b);
      for(int s = 0; s < SLOT_COUNT; s++)
         if(g_closing[s] && b[s].positions == 0 && b[s].pendings == 0)
           {
            g_closing[s] = false;
            ResetPeak(s);
           }
     }

   if(!env.tradeAllowed)
     {
      UpdatePanel(env, b);
      return;
     }

   //--- 2. proteksi global, 3. exit per basket, 4. kecerdasan berita & tangga
   if(!GlobalProtection(env, b))
     {
      bool closed = false;
      for(int s = 0; s < SLOT_COUNT; s++)
         if(ManageExit(s, b[s], env))
            closed = true;
      if(!closed)
        {
         NewsPreActions(env, b);
         ManageMomentumLadder(0, b, env);
         ManageMomentumLadder(1, b, env);
         ManageReversionLadder(4, b, env);
         ManageReversionLadder(5, b, env);
         ManageNewsLadder(2, b[2], env);
         ManageNewsLadder(3, b[3], env);
         NewsRide(env, b);
        }
     }
   ManageAlpha(env);

   env.halted = (TimeCurrent() < g_haltUntil);
   UpdatePanel(env, b);
  }
//+------------------------------------------------------------------+
