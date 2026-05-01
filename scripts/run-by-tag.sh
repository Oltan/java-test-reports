#!/usr/bin/env bash
set -u

FILE="features.txt"
DRY_RUN=0
CONTINUE_ON_FAIL=0
SINGLE_FILE=0
RETRY_COUNT=0  # passed only to CucumberRetryRunnerTest

export LC_ALL=C.UTF-8
export LANG=C.UTF-8

usage() {
  cat <<EOF
Usage: $0 [-f <file>] [--dry-run] [--continue-on-fail] [--single-file] [--retry-count <n>]
EOF
}

log()  { printf '%b\n' "$*"; }
err()  { printf 'ERROR: %b\n' "$*" >&2; }
warn() { printf 'WARN: %b\n' "$*" >&2; }

require_cmd() { command -v "$1" >/dev/null 2>&1 || { err "'$1' not found"; exit 2; }; }

slugify() {
  echo "$1" | sed -E 's/[^A-Za-z0-9]+/-/g' | sed -E 's/^-+|-+$//g'
}

# Format seconds as HH:MM:SS
format_hms() {
  local total=$1
  local h=$(( total / 3600 ))
  local m=$(( (total % 3600) / 60 ))
  local s=$(( total % 60 ))
  printf "%02d:%02d:%02d" "$h" "$m" "$s"
}

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    -f) FILE="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --continue-on-fail) CONTINUE_ON_FAIL=1; shift ;;
    --single-file) SINGLE_FILE=1; shift ;;
    --retry-count) RETRY_COUNT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) err "Unknown arg: $1"; usage; exit 2 ;;
  esac
done

require_cmd mvn
require_cmd date

# Start overall timer
script_start=$(date +%s)

passed=()
failed=()
tag_durations=()  # entries like "tag:secs"

# Process tags
while IFS= read -r tag || [[ -n "$tag" ]]; do
  [[ -z "$tag" || "$tag" =~ ^# ]] && continue

  slug=$(slugify "$tag")
  timestamp=$(date +%Y%m%d_%H%M%S)

  if [[ $SINGLE_FILE -eq 1 ]]; then
    report="target/extent-report/${slug}-${timestamp}.html"
  else
    report="target/extent-report/${slug}/index.html"
  fi

  log "=== Running tag: $tag (slug: $slug) ==="
  log "-> extent.reporter.spark.out = $report"

  mvn_args=(-q
    -Dextent.reporter.spark.start=true
    -Dextent.reporter.spark.out="$report"
    -Dcucumber.filter.tags="$tag"
    -Dretry.count="$RETRY_COUNT"
#    -Dreport.include.tags=true
#    -Dreport.include.failed.category=false
    test
  )

  tag_start=$(date +%s)

    if [[ $DRY_RUN -eq 1 ]]; then
      log "[Dry run] mvn ${mvn_args[*]}"
      passed+=("$tag")
      tag_elapsed=$(( $(date +%s) - tag_start ))
      tag_durations+=("$tag:$tag_elapsed")
    else
      if mvn "${mvn_args[@]}"; then
        passed+=("$tag")
        tag_elapsed=$(( $(date +%s) - tag_start ))
        tag_durations+=("$tag:$tag_elapsed")
      else
        failed+=("$tag")
        tag_elapsed=$(( $(date +%s) - tag_start ))
        tag_durations+=("$tag:$tag_elapsed")
        if [[ $CONTINUE_ON_FAIL -eq 0 ]]; then
          break
        fi
      fi
    fi
  done < "$FILE"

  # Compute total time
  script_end=$(date +%s)
  total_elapsed=$((script_end - script_start))

  # Final summary
  echo
  echo "==================================================="
  echo "[RetryRunner] Final Summary:"
  echo "  PASSED: ${#passed[@]}"
  for t in "${passed[@]}"; do echo "    - $t"; done
  echo "  FAILED: ${#failed[@]}"
  for t in "${failed[@]}"; do echo "    - $t"; done
  echo "==================================================="

  if [[ ${#tag_durations[@]} -gt 0 ]]; then
    echo "Per-tag durations:"
    for entry in "${tag_durations[@]}"; do
      tag_name="${entry%%:*}"
      secs="${entry#*:}"
      echo "  $tag_name : $(format_hms "$secs")"
    done
  fi

  echo "TOTAL TIME: $(format_hms "$total_elapsed")"

  if [[ ${#failed[@]} -gt 0 ]]; then
    exit 1
  else
    exit 0
  fi