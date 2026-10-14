@echo off
rem ============================================================
rem  EA SAPU JAGAD - salin seluruh paket ke D:\sapujagad
rem  Jalankan file ini dari folder paket sapujagad (hasil ekstrak zip).
rem ============================================================
set TUJUAN=D:\sapujagad
if not exist D:\ (
  echo Drive D tidak ditemukan. Ubah baris "set TUJUAN=" di file ini.
  pause
  exit /b 1
)
if not exist "%TUJUAN%" mkdir "%TUJUAN%"
xcopy "%~dp0*" "%TUJUAN%\" /E /I /Y >nul
echo.
echo Selesai. Semua file EA SAPU JAGAD ada di %TUJUAN%
echo  - EA\EA_SAPU_JAGAD.mq5        : salin ke MQL5\Experts lalu Compile (F7)
echo  - Presets\*.set               : salin ke MQL5\Presets
echo  - Files\sapu_jagad_news.csv   : salin ke Common\Files (untuk backtest berita)
echo  - Tools\sapu_jagad_forensik.py: alat uji forensik (butuh Python 3.8+)
echo.
pause
