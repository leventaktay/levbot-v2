@echo off
title Coin Scanner v3.0 - Kurulum
color 0A
echo.
echo  ==========================================
echo    COIN SCANNER v3.0 - Otomatik Kurulum
echo    OKX + Binance + BingX Destekli
echo  ==========================================
echo.

echo [1/4] Python kontrol ediliyor...

py --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYCMD=py
    goto :python_found
)

python --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYCMD=python
    goto :python_found
)

python3 --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYCMD=python3
    goto :python_found
)

echo.
echo  [HATA] Python bulunamadi!
echo  https://www.python.org/downloads/
echo  Kurulumda "Add Python to PATH" isaretleyin!
echo.
pause
exit /b

:python_found
for /f "tokens=*" %%i in ('%PYCMD% --version 2^>^&1') do echo   Bulundu: %%i
echo.

echo [2/4] Pip kontrol ediliyor...
%PYCMD% -m pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   Pip kuruluyor...
    %PYCMD% -m ensurepip --default-pip
)
echo   Pip OK
echo.

echo [3/4] Kutuphaneler kuruluyor...
echo.
%PYCMD% -m pip install PyQt5 requests urllib3 --quiet --disable-pip-version-check
if %errorlevel% neq 0 (
    echo.
    echo  [UYARI] Bazi kutuphaneler kurulamadi.
    echo  Manuel deneyin: %PYCMD% -m pip install PyQt5 requests
    echo.
    pause
)
echo   Kutuphaneler OK
echo.

echo [4/4] Coin Scanner baslatiliyor...
echo.
%PYCMD% coin_scanner.py

if %errorlevel% neq 0 (
    echo.
    echo  [HATA] Uygulama kapandi. Hata kodu: %errorlevel%
    echo.
    pause
)
