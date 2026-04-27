param(
    [string]$File = "features.txt",
    [switch]$DryRun,
    [switch]$ContinueOnFail,
    [switch]$SingleFile,
    [int]$RetryCount = 0
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding = [System.Text.Encoding]::UTF8

function Log($msg)
{
    Write-Host $msg
}
function Err($msg)
{
    Write-Error $msg
}
function Warn($msg)
{
    Write-Warning $msg
}

function Require-Cmd($cmd)
{
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue))
    {
        Err "'$cmd' not found on PATH"
        exit 2
    }
}

function Slugify($text)
{
    $slug = $text -replace '[^A-Za-z0-9]+', '-'
    $slug = $slug -replace '^-+', '' -replace '-+$', ''
    return $slug
}

Require-Cmd mvn

# Start overall script timer
$scriptTimer = [System.Diagnostics.Stopwatch]::StartNew()
# Hashtable to keep per-tag durations
$tagTimes = @{ }

$passed = @()
$failed = @()

Get-Content -Raw -Encoding UTF8 $File -ErrorAction Stop |
        ForEach-Object { $_ -split "`n" } |
        ForEach-Object {
            $tag = $_.Trim()
            if (-not $tag -or $tag.StartsWith("#"))
            {
                return
            }

            $slug = Slugify $tag
            $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"

            if ($SingleFile)
            {
                $report = "target/extent-report/${slug}-$timestamp.html"
            }
            else
            {
                $report = "target/extent-report/${slug}/index.html"
            }

            Log "=== Running tag: $tag (slug: $slug) ==========="
            Log "-> extent.reporter.spark.out = $report"

            $mvnArgs = @(
                "-Dextent.reporter.spark.start=true"
                "-Dextent.reporter.spark.out=$report"
                "-Dcucumber.filter.tags=$tag"
                "-Dretry.count=$RetryCount"
                "-Dfile.encoding = UTF-8"
            #      "-Dreport.include.tags=true"
            #      "-Dreport.include.failed.category=false"
                "test"
            )

            # Start per-tag timer
            $tagTimer = [System.Diagnostics.Stopwatch]::StartNew()

            if ($DryRun)
            {
                Log "[Dry run] mvn -q $( $mvnArgs -join ' ' )"
                $passed += $tag
                $tagTimer.Stop()
                $tagTimes[$tag] = $tagTimer.Elapsed
            }
            else
            {
                & mvn -q @mvnArgs
                $rc = $LASTEXITCODE
                $tagTimer.Stop()
                $tagTimes[$tag] = $tagTimer.Elapsed

                if ($rc -eq 0)
                {
                    $passed += $tag
                }
                else
                {
                    $failed += $tag
                    if (-not $ContinueOnFail)
                    {
                        $scriptTimer.Stop()
                        Write-Host "`n==================================================="
                        Write-Host "[RetryRunner] Final Summary (interrupted):"
                        Write-Host "  PASSED: $( $passed.Count )"
                        $passed | ForEach-Object { Write-Host "    - $_" }
                        Write-Host "  FAILED: $( $failed.Count )"
                        $failed | ForEach-Object { Write-Host "    - $_" }
                        Write-Host "==================================================="
                        Write-Host "Per-tag durations:"
                        $tagTimes.GetEnumerator() | Sort-Object Name | ForEach-Object { Write-Host "  $( $_.Key ) : $( $_.Value )" }
                        Write-Host "TOTAL TIME: $( $scriptTimer.Elapsed )"
                        exit 1
                    }
                }
            }
        }

Write-Host "`n==================================================="
Write-Host "[RetryRunner] Final Summary:"
Write-Host "  PASSED: $( $passed.Count )"
$passed | ForEach-Object { Write-Host "    - $_" }
Write-Host "  FAILED: $( $failed.Count )"
$failed | ForEach-Object { Write-Host "    - $_" }
Write-Host "==================================================="

if ($tagTimes.Count -gt 0)
{
    Write-Host "Per-tag durations:"
    # Sort by tag name for deterministic output; change to Sort-Object Value to sort by duration
    $tagTimes.GetEnumerator() | Sort-Object Name | ForEach-Object { Write-Host "  $( $_.Key ) : $( $_.Value )" }
}

Write-Host "TOTAL TIME: $( $scriptTimer.Elapsed )"

if ($failed.Count -gt 0)
{
    exit 1
}
else
{
    exit 0
}
