@echo off
title Coin Scanner v3.0
py coin_scanner.py 2>nul || python coin_scanner.py 2>nul || python3 coin_scanner.py 2>nul
if %errorlevel% neq 0 (
    echo Hata olustu. KUR_VE_BASLAT.bat'i calistirin.
    pause
)
