#!/usr/bin/env bash
# Testleri koştur ve FastAPI dashboard için manifest üret.
#
# Kullanım:
#   ./scripts/run-by-tags.sh [seçenekler]
#
# Seçenekler:
#   -f <dosya>          Tag listesi dosyası (varsayılan: scripts/features.txt)
#   --retry-count <n>   Başarısız senaryo için tekrar deneme sayısı (varsayılan: 0)
#   --continue-on-fail  Bir tag başarısız olsa bile devam et
#   --dry-run           Komutları göster, çalıştırma
#   --project <yol>     Test projesinin kök dizini (varsayılan: geçerli dizin)
#   -h, --help          Bu yardım metnini göster
#
# Örnek:
#   ./scripts/run-by-tags.sh
#   ./scripts/run-by-tags.sh --retry-count 2 --continue-on-fail
#   ./scripts/run-by-tags.sh --project /ayrı-proje --retry-count 1
#   ./scripts/run-by-tags.sh --dry-run

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORTS_DIR="$(dirname "$SCRIPT_DIR")"

FILE="$SCRIPT_DIR/features.txt"
RETRY_COUNT=0
CONTINUE_ON_FAIL=0
DRY_RUN=0
PROJECT_DIR="$(pwd)"

export LC_ALL=C.UTF-8
export LANG=C.UTF-8

log()  { printf '%s\n' "$*"; }
err()  { printf 'HATA: %s\n' "$*" >&2; }

slugify() {
    printf '%s' "$1" | sed -E 's/[^A-Za-z0-9]+/-/g' | sed -E 's/^-+|-+$//g'
}

format_hms() {
    local total=$1
    printf "%02d:%02d:%02d" "$(( total / 3600 ))" "$(( (total % 3600) / 60 ))" "$(( total % 60 ))"
}

usage() {
    sed -n '3,15p' "$0" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -f)              FILE="$2";         shift 2 ;;
        --retry-count)   RETRY_COUNT="$2";  shift 2 ;;
        --continue-on-fail) CONTINUE_ON_FAIL=1; shift ;;
        --dry-run)       DRY_RUN=1;         shift ;;
        --project)       PROJECT_DIR="$2";  shift 2 ;;
        -h|--help)       usage; exit 0 ;;
        *) err "Bilinmeyen parametre: $1"; usage; exit 2 ;;
    esac
done

# ── Ön kontroller ──────────────────────────────────────────────────────────────

command -v mvn >/dev/null 2>&1 || { err "mvn bulunamadı. Maven PATH'te olmalı."; exit 2; }

if [[ ! -f "$FILE" ]]; then
    err "Tag dosyası bulunamadı: $FILE"
    exit 1
fi

ORCHESTRATOR_JAR="$REPORTS_DIR/orchestrator/target/orchestrator.jar"
if [[ ! -f "$ORCHESTRATOR_JAR" ]]; then
    log "orchestrator.jar bulunamadı. Build ediliyor..."
    if [[ $DRY_RUN -eq 0 ]]; then
        mvn -q package -pl orchestrator -am -DskipTests -f "$REPORTS_DIR/pom.xml" || {
            err "orchestrator build başarısız."
            exit 1
        }
    else
        log "[Dry-run] mvn package -pl orchestrator -am -DskipTests"
    fi
fi

# ── Test koşumu ────────────────────────────────────────────────────────────────

passed=()
failed=()
durations=()
script_start=$(date +%s)

while IFS= read -r tag || [[ -n "$tag" ]]; do
    [[ -z "$tag" || "$tag" =~ ^# ]] && continue

    slug=$(slugify "$tag")
    timestamp=$(date +%Y%m%d_%H%M%S)
    run_id="${slug}-${timestamp}"

    log ""
    log "=== Tag: $tag | Run ID: $run_id ==="

    tag_start=$(date +%s)

    if [[ $DRY_RUN -eq 1 ]]; then
        log "[Dry-run] cd $PROJECT_DIR && mvn test -Dcucumber.filter.tags=\"$tag\" -Dretry.count=$RETRY_COUNT"
        log "[Dry-run] java -jar $ORCHESTRATOR_JAR --run-id=$run_id"
        passed+=("$tag")
        durations+=("$tag:0")
        continue
    fi

    # 1. Testleri koş
    if (cd "$PROJECT_DIR" && mvn -B test \
            -Dcucumber.filter.tags="$tag" \
            -Dretry.count="$RETRY_COUNT" \
            -DALLURE_RESULTS_DIR="$PROJECT_DIR/target/allure-results"); then
        test_exit=0
    else
        test_exit=1
    fi

    # 2. Orchestrator: allure-results → manifests/*.json
    java \
        -DALLURE_RESULTS_DIR="$PROJECT_DIR/target/allure-results" \
        -jar "$ORCHESTRATOR_JAR" \
        "--run-id=$run_id" || log "UYARI: Orchestrator başarısız, manifest üretilemedi."

    tag_elapsed=$(( $(date +%s) - tag_start ))
    durations+=("$tag:$tag_elapsed")

    if [[ $test_exit -eq 0 ]]; then
        passed+=("$tag")
        log "PASS: $tag"
    else
        failed+=("$tag")
        log "FAIL: $tag"
        if [[ $CONTINUE_ON_FAIL -eq 0 ]]; then
            break
        fi
    fi
done < "$FILE"

# ── Özet ───────────────────────────────────────────────────────────────────────

total_elapsed=$(( $(date +%s) - script_start ))

log ""
log "==================================================="
log "ÖZET"
log "==================================================="
log "  PASS: ${#passed[@]}"
for t in "${passed[@]}"; do log "    ✓ $t"; done
log "  FAIL: ${#failed[@]}"
for t in "${failed[@]}"; do log "    ✗ $t"; done
log ""
log "Tag süreleri:"
for entry in "${durations[@]}"; do
    log "  ${entry%%:*} : $(format_hms "${entry#*:}")"
done
log "TOPLAM: $(format_hms "$total_elapsed")"
log "==================================================="

if [[ ${#failed[@]} -gt 0 ]]; then
    log ""
    log "Raporlar: http://localhost:8000"
    exit 1
fi

log ""
log "Raporlar: http://localhost:8000"
exit 0
