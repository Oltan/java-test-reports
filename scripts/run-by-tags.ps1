# Test Raporlama - Tag Runner (PowerShell)
#
# Kullanim:
#   .\run-by-tags.ps1 [secenekler]
#
# Secenekler:
#   -FeaturesFile <dosya>   Tag listesi dosyasi (varsayilan: scripts\features.txt)
#   -RetryCount <n>         Tekrar deneme sayisi (varsayilan: 0)
#   -ProjectPath <yol>      Test projesinin dizini (varsayilan: script'in ust dizini)
#   -ContinueOnFail         Hata olsa bile diger tag'lere devam et
#   -DryRun                 Komutlari goster, calistirma
#   -Help                   Bu yardimi goster

param(
    [string]$FeaturesFile = "",
    [int]$RetryCount = 0,
    [string]$ProjectPath = "",
    [switch]$ContinueOnFail,
    [switch]$DryRun,
    [switch]$Help
)

if ($Help) {
    Get-Content $PSCommandPath | Select-Object -Skip 1 |
        Where-Object { $_ -match '^#' } |
        ForEach-Object { $_ -replace '^# ?', '' }
    exit 0
}

# ── Varsayilan yollar ──────────────────────────────────────────────────────────

$ScriptDir  = Split-Path -Parent $PSCommandPath
$ReportsDir = Split-Path -Parent $ScriptDir

if ($FeaturesFile -eq "") {
    $FeaturesFile = Join-Path $ScriptDir "features.txt"
}
if ($ProjectPath -eq "") {
    $ProjectPath = $ReportsDir
}

$OrchestratorJar = Join-Path $ReportsDir "orchestrator\target\orchestrator.jar"

# ── Yardimci fonksiyonlar ──────────────────────────────────────────────────────

function Format-Elapsed([TimeSpan]$ts) {
    "{0:D2}:{1:D2}:{2:D2}" -f [int]$ts.TotalHours, $ts.Minutes, $ts.Seconds
}

function Invoke-Maven([string[]]$Arguments) {
    # Start-Process yerine & operatoru: argumanlari daha guvenli iletir
    # ve $LASTEXITCODE'u dogru doldurur
    & mvn @Arguments
    return $LASTEXITCODE
}

# ── On kontroller ──────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "  Test Raporlama - Tag Runner"
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $FeaturesFile)) {
    Write-Host "HATA: Tag dosyasi bulunamadi: $FeaturesFile" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $ProjectPath)) {
    Write-Host "HATA: Proje dizini bulunamadi: $ProjectPath" -ForegroundColor Red
    exit 1
}

if (-not $DryRun -and -not (Test-Path $OrchestratorJar)) {
    Write-Host "orchestrator.jar bulunamadi, build ediliyor..." -ForegroundColor Yellow
    Push-Location $ReportsDir
    & mvn -q package -pl orchestrator -am -DskipTests
    if ($LASTEXITCODE -ne 0) {
        Write-Host "HATA: Orchestrator build basarisiz." -ForegroundColor Red
        Pop-Location
        exit 1
    }
    Pop-Location
}

$tags = Get-Content $FeaturesFile |
    Where-Object { $_ -match '\S' -and $_ -notmatch '^\s*#' }

if ($tags.Count -eq 0) {
    Write-Host "HATA: $FeaturesFile icerisinde hicbir tag bulunamadi." -ForegroundColor Red
    exit 1
}

Write-Host "Proje dizini : $ProjectPath"
Write-Host "Tag dosyasi  : $FeaturesFile"
Write-Host "Retry sayisi : $RetryCount"
Write-Host ""
Write-Host "Calistirilacak tag'ler:" -ForegroundColor Yellow
$tags | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
Write-Host ""

# ── Test dongusu ───────────────────────────────────────────────────────────────

$pass       = 0
$fail       = 0
$tagResults = @()
$scriptStart = Get-Date

foreach ($tag in $tags) {
    Write-Host ""
    Write-Host "--- $tag ---" -ForegroundColor Cyan
    $tagStart = Get-Date

    $slug      = $tag -replace '[^A-Za-z0-9]', '-' -replace '-+', '-' -replace '^-|-$', ''
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $runId     = "$slug-$timestamp"

    if ($DryRun) {
        Write-Host "[Dry-run] cd $ProjectPath" -ForegroundColor DarkGray
        Write-Host "[Dry-run] mvn test -Dcucumber.filter.tags=`"$tag`" -Dretry.count=$RetryCount" -ForegroundColor DarkGray
        Write-Host "[Dry-run] java -jar $OrchestratorJar --run-id=$runId" -ForegroundColor DarkGray
        $pass++
        $tagResults += [PSCustomObject]@{ Tag = $tag; Status = "PASS"; Duration = "N/A" }
        continue
    }

    # 1. Testleri calistir
    Push-Location $ProjectPath
    Write-Host "Komutu calistiriyor: mvn test -Dcucumber.filter.tags=`"$tag`" -Dretry.count=$RetryCount" -ForegroundColor Gray
    & mvn test "-Dcucumber.filter.tags=$tag" "-Dretry.count=$RetryCount"
    $testExit = $LASTEXITCODE
    Pop-Location

    # 2. Orchestrator: allure-results -> manifests/*.json
    $allureResults = Join-Path $ProjectPath "target\allure-results"
    Write-Host "Manifest uretiliyor (run-id: $runId)..." -ForegroundColor Gray
    & java "-DALLURE_RESULTS_DIR=$allureResults" -jar $OrchestratorJar "--run-id=$runId"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "UYARI: Orchestrator basarisiz, manifest uretilemedi." -ForegroundColor Yellow
    }

    $elapsed = (Get-Date) - $tagStart
    $duration = Format-Elapsed $elapsed

    if ($testExit -eq 0) {
        $pass++
        $tagResults += [PSCustomObject]@{ Tag = $tag; Status = "PASS"; Duration = $duration }
        Write-Host "PASS: $tag ($duration)" -ForegroundColor Green
    } else {
        $fail++
        $tagResults += [PSCustomObject]@{ Tag = $tag; Status = "FAIL"; Duration = $duration }
        Write-Host "FAIL: $tag ($duration)" -ForegroundColor Red
        if (-not $ContinueOnFail) {
            Write-Host "Durduruluyor. Devam etmek icin -ContinueOnFail kullanin." -ForegroundColor Red
            break
        }
    }
}

# ── Ozet ───────────────────────────────────────────────────────────────────────

$totalDuration = Format-Elapsed ((Get-Date) - $scriptStart)

Write-Host ""
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "  OZET"
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ("PASS: " + $pass) -ForegroundColor Green
Write-Host ("FAIL: " + $fail) -ForegroundColor Red
Write-Host ""
Write-Host "Tag bazinda sonuclar:" -ForegroundColor Yellow
foreach ($r in $tagResults) {
    $color = if ($r.Status -eq "PASS") { "Green" } else { "Red" }
    Write-Host ("  " + $r.Tag + " : " + $r.Status + " (" + $r.Duration + ")") -ForegroundColor $color
}
Write-Host ""
Write-Host "Toplam sure: $totalDuration"
Write-Host "Raporlar   : http://localhost:8000"
Write-Host "=======================================" -ForegroundColor Cyan

if ($fail -gt 0) { exit 1 } else { exit 0 }
