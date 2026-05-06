# PROJECT KNOWLEDGE BASE

**Generated:** 2026-04-27
**Branch:** claude/allure-reports-integration-NYM9h
**Stack:** Java 21 (Maven) + Python 3.12 (FastAPI) + Cucumber/JUnit 5

## OVERVIEW

Multi-module test automation reporting system. Cucumber Selenium testleri → Allure → FastAPI dashboard → Jira bug + DOORS DXL + email.

## STRUCTURE

```
java_reports/
├── pom.xml                    # Parent POM (3 Maven modules)
├── test-core/                 # Cucumber runner + Selenium step defs + Allure hooks

├── fastapi-server/            # Python FastAPI web sunucu (Maven değil)
├── scripts/                   # start-server.bat, start-servers.sh
├── manifests/                 # run-manifest.json dosyaları
├── .sisyphus/                 # Planlar, evidence, notepads
├── ACCESS_GUIDE.md
├── ENTEGRASYON_REHBERI.md
├── NASIL_CALISTIRILIR.md
└── start.sh                   # FastAPI başlatma
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Cucumber test koşma | `test-core/` | `CucumberTestRunner.java`, `login.feature` |
| Allure rapor hook'ları | `test-core/src/test/java/com/testreports/allure/` | `ScreenshotHook.java`, `VideoHook.java` |
| Run manifest şeması | `fastapi-server/` | `server.py` → `_write_manifest_json()` |
| Web dashboard | `fastapi-server/` | `server.py`, `templates/dashboard.html` |
| Bug tracker | `bug-tracker.json` | JSON-based bug mapping |
| Pipeline | `fastapi-server/pipeline.py` | Stage execution |
| Email gönderme | `fastapi-server/email_service.py` | Thymeleaf template |

## CONVENTIONS

- **Java package**: `com.testreports.<module>` (test-core, model, allure)
- **Python**: FastAPI `server.py` ana entry, modüller `models.py`, `bug_tracker.py`, `jira_client.py`

## ANTI-PATTERNS (THIS PROJECT)

- ❌ Database yok — her şey dosya tabanlı (JSON manifests, bug-tracker.json)
- ❌ Spring Boot YOK — FastAPI-only (sonra tamamen kaldırıldı, sadece FastAPI)
- ❌ `allure serve` kullanma — `allure generate` + statik hosting
- ❌ ADF formatı kullanma (Jira Cloud v3) — Server/DC için wiki renderer
- ❌ Hardcoded credential — her şey `.env` veya system property
- ❌ Pass videoları saklama — sadece fail
- ❌ `@ts-ignore`, `as any`, empty catch — review'da red sebebi

## UNIQUE STYLES

- **Raporlama hibrit**: Hem Allure hem ExtentReports aynı projede (test-core cucumber.properties iki plugin de yüklü) — extent kaldırıldı

## COMMANDS

```bash
# FastAPI sunucu
cd fastapi-server && python3 -m uvicorn server:app --host 0.0.0.0 --port 8000

# Maven test (tek modül)
export PATH="/home/ol_ta/tools/apache-maven-3.9.9/bin:$PATH"
mvn -pl test-core test -Dcucumber.filter.tags="@sample-fail"

# Allure rapor
export PATH="$PATH:/home/ol_ta/tools/allure-2.33.0/bin"
allure generate --clean test-core/target/allure-results -o test-core/target/allure-report

# Python test
cd fastapi-server && python3 -m pytest tests/ -v
```

## NOTES

- **ffmpeg**: Video kaydı için gerekli ama opsiyonel — yoksa graceful skip
- **Allure CLI**: `/home/ol_ta/tools/allure-2.33.0/bin/allure`
- **Maven**: `/home/ol_ta/tools/apache-maven-3.9.9/bin/mvn`
