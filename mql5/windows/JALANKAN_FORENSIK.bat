@echo off
rem ============================================================
rem  EA SAPU JAGAD - uji forensik + uji ketahanan pada dataset Anda
rem  Butuh Python 3.8+ (https://www.python.org, centang "Add to PATH")
rem ============================================================
cd /d "%~dp0"
set /p DATA=Folder dataset XAUUSD (contoh D:\dataset): 
set /p GMT=Selisih jam data terhadap GMT (Exness=0, banyak broker=2): 
set /p NEWS=File kalender berita CSV (kosongkan bila tidak ada): 
set OPSI=
if not "%NEWS%"=="" set OPSI=--news "%NEWS%"
python Tools\sapu_jagad_forensik.py --data "%DATA%" --gmt-offset %GMT% %OPSI% --compare --ketahanan --out "%~dp0hasil_forensik"
echo.
echo Laporan ada di folder %~dp0hasil_forensik
pause
