@echo off
echo ============================================
echo   Test Raporlama Sistemi - Windows Baslatma
echo ============================================
echo.
echo WSL uzerinde FastAPI sunucusu baslatiliyor...
echo.

wsl -d Ubuntu -e bash -c "cd /mnt/c/Users/ol_ta/desktop/java_reports/fastapi-server && python3 -m uvicorn server:app --host 0.0.0.0 --port 8000"

echo.
echo Sunucu durdu. Kapatmak icin Ctrl+C yapin.
pause
