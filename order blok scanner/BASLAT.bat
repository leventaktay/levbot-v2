@echo off
chcp 65001 >nul 2>&1
title Kripto Tarayici v10.0
color 0A

echo ══════════════════════════════════════════════
echo   KRIPTO TARAYICI v10.0 — Baslatici
echo ══════════════════════════════════════════════
echo.

REM ── Python kontrolü ──
REM Öğretici: "where" komutu Windows'ta bir programın yolunu bulur.
REM "py" = Python Launcher (genellikle Windows'ta kurulur)
REM "python" = doğrudan Python çalıştırıcısı
REM Hangisi varsa onu kullanıyoruz.
where py >nul 2>&1
if %errorlevel%==0 (
    set PYTHON=py
    goto :found_python
)

where python >nul 2>&1
if %errorlevel%==0 (
    set PYTHON=python
    goto :found_python
)

where python3 >nul 2>&1
if %errorlevel%==0 (
    set PYTHON=python3
    goto :found_python
)

echo [HATA] Python bulunamadi!
echo.
echo Python'u su adresten indirin:
echo https://www.python.org/downloads/
echo.
echo Kurulumda "Add Python to PATH" kutusunu isaretlemeyi unutmayin!
pause
exit /b 1

:found_python
echo [OK] Python bulundu: %PYTHON%

REM ── Bağımlılık kontrolü ve kurulumu ──
REM Öğretici: pip install --quiet → gereksiz çıktıyı gizler
REM --upgrade → varsa günceller, yoksa kurar
echo.
echo Bagimliliklar kontrol ediliyor...
%PYTHON% -m pip install --quiet --upgrade requests
if %errorlevel%==0 (
    echo [OK] requests kutuphanesi hazir
) else (
    echo [UYARI] requests kurulamadi, elle kurun: pip install requests
)

REM ── pip güncellemesi (isteğe bağlı, hata verirse atla) ──
%PYTHON% -m pip install --quiet --upgrade pip >nul 2>&1

echo.
echo ══════════════════════════════════════════════
echo   Tarayici baslatiliyor...
echo ══════════════════════════════════════════════
echo.

REM ── Scanner'ı başlat ──
REM Öğretici: cd /d %~dp0 → bat dosyasının bulunduğu klasöre git.
REM %~dp0 = bu bat dosyasının tam yolu (drive + path)
REM /d = farklı sürücüdeyse bile geçiş yap
cd /d %~dp0
%PYTHON% scanner_v10.py

REM ── Hata kontrolü ──
if %errorlevel% neq 0 (
    echo.
    echo [HATA] Tarayici beklenmedik sekilde kapandi!
    echo Hata kodu: %errorlevel%
    echo.
    pause
)
