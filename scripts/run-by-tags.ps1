# Test Raporlama - Tag Runner (PowerShell)
# Usage: .\run-by-tags.ps1 [-FeaturesFile <file>] [-RetryCount <n>] [-ContinueOnFail] [-DryRun]

param(
    [string]$FeaturesFile = "features.txt",
    [int]$RetryCount = 0,
    [switch]$ContinueOnFail,
    [switch]$DryRun,
    [switch]$Help
)

if ($Help) {
    Write-Host @"
Usage: .\run-by-tags.ps1 [options]
  -FeaturesFile <file>  Features file (default: features.txt)
  -RetryCount <n>       Retry count for failed tests (default: 0)
  -ContinueOnFail       Continue running even if a test fails
  -DryRun               Show what would be run without executing
  -Help                 Show this help message

Example:
  .\run-by-tags.ps1 -RetryCount 2 -ContinueOnFail
"@
    exit 0
}

Write-Host "========================================"
Write-Host "  Test Raporlama - Tag Runner"
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $FeaturesFile)) {
    Write-Host "ERROR: Features file not found: $FeaturesFile" -ForegroundColor Red
    exit 1
}

Write-Host "Using features file: $FeaturesFile" -ForegroundColor Gray

# Read tags from file, skip comments and empty lines
$tags = Get-Content $FeaturesFile | Where-Object {
    $_ -match '\S' -and -not $_ -match '^\s*#'
}

Write-Host ""
Write-Host "Tags to run:" -ForegroundColor Yellow
$tags | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
Write-Host ""

$pass = 0
$fail = 0
$tagResults = @()

$scriptStart = Get-Date

foreach ($tag in $tags) {
    Write-Host ""
    Write-Host "--- Running: $tag ---" -ForegroundColor Cyan

    $tagStart = Get-Date

    if ($DryRun) {
        Write-Host "[DRY-RUN] mvn test -pl test-core -Dcucumber.filter.tags=`"$tag`" -Dretry.count=$RetryCount" -ForegroundColor DarkGray
        $pass++
        $tagResults += @{ Tag = $tag; Status = "PASS"; Duration = "N/A" }
        Write-Host "PASS: $tag" -ForegroundColor Green
    } else {
        $mvnArgs = @("test", "-pl", "test-core", "-Dcucumber.filter.tags=$tag", "-Dretry.count=$RetryCount")
        Write-Host "Running: mvn $($mvnArgs -join ' ')" -ForegroundColor Gray

        $process = Start-Process -FilePath "mvn" -ArgumentList $mvnArgs -NoNewWindow -Wait -PassThru
        $exitCode = $process.ExitCode

        $tagEnd = Get-Date
        $duration = "{0:mm:ss}" -f ($tagEnd - $tagStart)

        if ($exitCode -eq 0) {
            $pass++
            $tagResults += @{ Tag = $tag; Status = "PASS"; Duration = $duration }
            Write-Host "PASS: $tag" -ForegroundColor Green
        } else {
            $fail++
            $tagResults += @{ Tag = $tag; Status = "FAIL"; Duration = $duration }
            Write-Host "FAIL: $tag" -ForegroundColor Red

            if (-not $ContinueOnFail) {
                Write-Host ""
                Write-Host "========================================" -ForegroundColor Red
                Write-Host "  Stopping due to failure" -ForegroundColor Red
                Write-Host "  (use -ContinueOnFail to ignore)" -ForegroundColor Gray
                Write-Host "========================================" -ForegroundColor Red
                break
            }
        }
    }
}

$scriptEnd = Get-Date
$totalDuration = "{0:mm:ss}" -f ($scriptEnd - $scriptStart)

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  SUMMARY"
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Passed: $pass" -ForegroundColor Green
Write-Host "Failed: $fail" -ForegroundColor Red
Write-Host "Total Duration: $totalDuration" -ForegroundColor Gray
Write-Host ""

if ($tagResults.Count -gt 0) {
    Write-Host "Per-tag results:" -ForegroundColor Yellow
    foreach ($result in $tagResults) {
        $color = if ($result.Status -eq "PASS") { "Green" } else { "Red" }
        Write-Host "  $($result.Tag) : $($result.Status) ($($result.Duration))" -ForegroundColor $color
    }
}

Write-Host "========================================" -ForegroundColor Cyan

if ($fail -gt 0) {
    exit 1
} else {
    exit 0
}
