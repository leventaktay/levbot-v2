@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Paketler kuruluyor...
py -m pip install pandas numpy requests --quiet
echo.
echo Tarayici baslatiliyor...
py "%~dp0pro_scanner.py"
pause
