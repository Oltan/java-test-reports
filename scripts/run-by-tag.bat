@echo off
setlocal enabledelayedexpansion

echo ========================================
echo   Test Raporlama - Tag Runner
echo ========================================
echo.

set SCRIPT_DIR=%~dp0
set FEATURES_FILE=%SCRIPT_DIR%features.txt
set RETRY_COUNT=0
set CONTINUE_ON_FAIL=0
set DRY_RUN=0

REM Parse arguments
:parse_args
if "%~1"=="" goto :run
if "%~1"=="--retry-count" (set RETRY_COUNT=%~2 & shift & shift & goto :parse_args)
if "%~1"=="--continue-on-fail" (set CONTINUE_ON_FAIL=1 & shift & goto :parse_args)
if "%~1"=="--dry-run" (set DRY_RUN=1 & shift & goto :parse_args)
if "%~1"=="-f" (set FEATURES_FILE=%~2 & shift & shift & goto :parse_args)
if "%~1"=="-h" (goto :usage)
if "%~1"=="--help" (goto :usage)
shift & goto :parse_args

:usage
echo Usage: %0 [options]
echo   -f ^<file^>          Features file (default: features.txt)
echo   --retry-count ^<n^>  Retry count for failed tests
echo   --continue-on-fail   Continue running even if a test fails
echo   --dry-run            Show what would be run without executing
echo   -h, --help           Show this help message
exit /b 0

:run
if not exist "%FEATURES_FILE%" (
    echo ERROR: Features file not found: %FEATURES_FILE%
    exit /b 1
)

echo Using features file: %FEATURES_FILE%
echo.
echo Tags to run:
findstr /v "^#" "%FEATURES_FILE%" | findstr /v "^$"
echo.

set PASS=0
set FAIL=0
set START_TIME=%TIME%

REM Read tags from file, skip comments and empty lines
for /f "usebackq tokens=* delims=" %%t in (`type "%FEATURES_FILE%" ^| findstr /v "^#" ^| findstr /v "^$"`) do (
    echo.
    echo --- Running: %%t ---
    set TAG_START=!TIME!

    if %DRY_RUN%==1 (
        echo [DRY-RUN] mvn test -pl test-core -Dcucumber.filter.tags="%%t" -Dretry.count=!RETRY_COUNT!
        set /a PASS+=1
        echo PASS: %%t
    ) else (
        mvn -pl test-core test -Dcucumber.filter.tags="%%t" -Dretry.count=!RETRY_COUNT!
        if !ERRORLEVEL!==0 (
            set /a PASS+=1
            echo PASS: %%t
        ) else (
            set /a FAIL+=1
            echo FAIL: %%t
            if !CONTINUE_ON_FAIL!==0 (
                echo.
                echo ========================================
                echo   Stopping due to failure (use --continue-on-fail to ignore)
                echo ========================================
                exit /b 1
            )
        )
    )
)

echo.
echo ========================================
echo   SUMMARY
echo ========================================
echo Passed: !PASS!
echo Failed: !FAIL!
echo ========================================

if !FAIL! gtr 0 exit /b 1
exit /b 0
