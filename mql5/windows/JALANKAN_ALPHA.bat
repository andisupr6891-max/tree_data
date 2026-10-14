@echo off
rem ============================================================
rem  EA SAPU JAGAD - riset & ekspor model alpha dari dataset Anda
rem  Butuh Python 3.9+ dan: pip install pandas numpy lightgbm
rem ============================================================
cd /d "%~dp0"
set /p DATA=File/folder data M1 XAUUSD ekspor MT5 (contoh D:\dataset): 
set /p GMT=Selisih jam data terhadap GMT (Exness=0, banyak broker=2): 
python Tools\sapu_jagad_alpha.py --data "%DATA%" --gmt-offset %GMT% --out "%~dp0hasil_alpha"
echo.
echo Model: %~dp0hasil_alpha\sapu_jagad_alpha.txt
echo Salin file itu ke folder Common\Files terminal MT5. EA hanya trading bila status LOLOS.
pause
