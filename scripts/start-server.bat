@echo off
setlocal

echo ============================================
echo   Test Raporlama Sistemi - Windows Baslatma
echo ============================================
echo.

REM FastAPI-server dizini kontrolü
if not exist "fastapi-server" (
    echo [HATA] fastapi-server dizini bulunamadi!
    echo Lutfen proje dizininde oldugunuzdan emin olun.
    pause & exit /b 1
)

REM Python kontrolü
python --version 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [HATA] Python yuklu degil veya PATH'de degil!
    echo Lutfen Python 3.12+ yukleyin.
    pause & exit /b 1
)

REM requirements.txt kontrolü
if not exist "fastapi-server\requirements.txt" (
    echo [HATA] fastapi-server\requirements.txt bulunamadi!
    pause & exit /b 1
)

echo FastAPI sunucusu baslatiliyor...
echo Port: 8000
echo Adres: http://localhost:8000
echo.
echo Kapatmak icin Ctrl+C yapin veya bu pencereyi kapatin.
echo.

REM FastAPI sunucusunu baslat
cd fastapi-server
start http://localhost:8000
python -m uvicorn server:app --host 0.0.0.0 --port 8000
