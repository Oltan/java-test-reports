@echo off
setlocal EnableDelayedExpansion

echo ========================================
echo   Test Raporlama Sistemi - Kurulum
echo ========================================
echo.

echo 1. Java kontrol ediliyor...
java -version 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [HATA] Java 21+ gerekli!
    echo Indir: https://adoptium.net/download/
    pause & exit /b 1
)
echo    Java OK
echo.

echo 2. Python kontrol ediliyor...
python --version 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [HATA] Python 3.12+ gerekli!
    echo Indir: https://www.python.org/downloads/
    pause & exit /b 1
)
echo    Python OK
echo.

echo 3. Python paketleri yukleniyor...
if exist fastapi-server\requirements.txt (
    pip install -r fastapi-server\requirements.txt
    if %ERRORLEVEL% NEQ 0 (
        echo [HATA] Paket yukleme basarisiz!
        pause & exit /b 1
    )
    echo    Paketler OK
) else (
    echo [UYARI] fastapi-server\requirements.txt bulunamadi
)
echo.

echo 4. .env dosyasi olusturuluyor...
if not exist .env (
    if exist .env.example (
        copy .env.example .env
        echo    .env olusturuldu
    ) else (
        echo [UYARI] .env.example bulunamadi, .env olusturulmuyor
    )
) else (
    echo    .env zaten mevcut
)
echo.

echo 5. Allure CLI kontrol ediliyor...
allure --version 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo    [UYARI] Allure CLI yuklu degil. Rapor goruntuleme icin gerekli.
    echo    Indir: https://github.com/allure-framework/allure2/releases
) else (
    echo    Allure OK
)
echo.

echo 6. Maven Wrapper kontrol ediliyor...
if exist mvnw.bat (
    echo    Maven Wrapper OK
) else (
    echo    [UYARI] Maven Wrapper bulunamadi. mvnw.bat olusturuluyor...
    echo @echo off > mvnw.bat
    echo echo Maven Wrapper hazir degil. Maven 3.9+ yukleyin veya mvn komutunu kullanin. >> mvnw.bat
    echo pause >> mvnw.bat
    echo    Maven Wrapper olusturuldu (lutfen Maven yukleyin)
)
echo.

echo ========================================
echo   KURULUM TAMAMLANDI!
echo ========================================
echo.
echo Baslatmak icin: start-server.bat
echo Test kosmak icin: scripts\run-by-tag.bat
echo.
pause
