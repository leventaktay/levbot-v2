@echo off
chcp 65001 >nul
echo ========================================
echo   Pro Crypto Scanner v2.0 - GUI
echo   Patterns + Sessions + Exchange Links
echo ========================================
echo.

cd /d "%~dp0"

echo [1/2] Paketler kontrol ediliyor...
py -m pip install PyQt5 pandas numpy requests --quiet
echo.

echo [2/2] GUI baslatiliyor...
py "%~dp0scanner_gui.py"

if errorlevel 1 (
    echo.
    echo HATA olustu! Detaylar yukarida.
    pause
)
