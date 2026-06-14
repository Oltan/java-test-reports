# PROJECT KNOWLEDGE BASE

**Updated:** 2026-06-14
**Branch:** claude/dreamy-heisenberg-li4yol
**Stack:** Java 21 (Maven) + Python 3.11 (FastAPI) + Cucumber/JUnit 5

## OVERVIEW

Multi-module test automation reporting system. Cucumber Selenium testleri → Allure → FastAPI dashboard → Jira bug + DOORS DXL + email.

## STRUCTURE

```
java-test-reports/
├── pom.xml                    # Parent POM
├── test-core/                 # Cucumber runner + Selenium step defs + Allure hooks
├── fastapi-server/            # Python FastAPI web sunucu (Maven değil)
│   ├── server.py              # Ana entry point (~2541 satır)
│   ├── models.py              # Pydantic modeller
│   ├── pipeline.py            # Stage execution
│   ├── jira_client.py         # Jira integration
│   ├── email_service.py       # SMTP email
│   ├── bug_tracker.py         # JSON-based bug mapping
│   ├── services/              # allure_parser.py, manifests.py, auth.py
│   ├── templates/             # Jinja2 HTML templates
│   ├── static/                # CSS, JS
│   └── tests/                 # pytest suite (119 passed)
├── scripts/                   # start-server.bat, start-servers.sh
├── docs/                      # Kullanıcı dokümantasyonu
└── docs/arsiv/                # Arşiv dokümanlar
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Cucumber test koşma | `test-core/` | `CucumberTestRunner.java`, feature files |
| Allure rapor hook'ları | `test-core/src/test/java/com/testreports/allure/` | `ScreenshotHook.java`, `VideoHook.java` |
| Web dashboard | `fastapi-server/server.py` | Tüm routes burada |
| Run manifest şeması | `fastapi-server/server.py` | `_write_manifest_json()` |
| Pydantic modeller | `fastapi-server/models.py` | `RunManifest`, `ScenarioResult`, `StepResult` |
| Pipeline | `fastapi-server/pipeline.py` | Stage execution |
| Email | `fastapi-server/email_service.py` | SMTP + Jinja2 template |
| Allure parsing | `fastapi-server/services/allure_parser.py` | JSON→DuckDB |
| Auth | `fastapi-server/services/auth.py` | JWT verify_token |
| Python tests | `fastapi-server/tests/` | conftest.py, fixtures/ |
| Java dep resolver | `test-core/.../runner/DependencyResolver.java` | Topo-sort, @id:/@dep: tags |
| Java retry runner | `test-core/.../runner/RetryTestRunner.java` | DependencyResolver'a delege ediyor |

## CONVENTIONS

- **Java package**: `com.testreports.<module>` (test-core, allure, runner)
- **Python**: FastAPI `server.py` ana entry, modüller `models.py`, `bug_tracker.py`, `jira_client.py`
- **Test fixtures**: `fastapi-server/tests/fixtures/*.json` — git'e commit'li, hermetic
- **Config**: `.env` dosyası (`.env.example` template) — commit'lenmez

## ANTI-PATTERNS (THIS PROJECT)

- ❌ Database yok — her şey dosya tabanlı (JSON manifests, bug-tracker.json) + DuckDB
- ❌ Spring Boot YOK — sadece FastAPI
- ❌ `allure serve` kullanma — `allure generate` + statik hosting
- ❌ ADF formatı kullanma (Jira Cloud v3) — Server/DC için wiki renderer
- ❌ Hardcoded credential — her şey `.env` veya system property
- ❌ Pass videoları saklama — sadece fail
- ❌ Hardcoded absolute path — system property veya env var kullan

## COMMANDS

```bash
# FastAPI sunucu
cd fastapi-server && python3 -m uvicorn server:app --host 0.0.0.0 --port 8000

# Maven test
mvn test -Dcucumber.filter.tags="@smoke"

# Maven test — izole çıktı dizini (per-run için)
mvn test -Dallure.results.directory=target/allure-results-run001 \
         -Dcucumber.filter.tags="@sample-fail"

# Allure rapor
allure generate --clean test-core/target/allure-results -o test-core/target/allure-report

# Python test (fastapi-server/ dizininden)
python3 -m pytest tests/ -v
# Beklenti: 119 passed

# Java unit testleri
mvn test -Dtest=DependencyResolverTest
```

## NOTES

- **ffmpeg**: Video kaydı için gerekli ama opsiyonel — yoksa graceful skip
- **Allure CLI**: PATH'te olmalı (örn. `allure-2.33.0/bin`)
- **Maven**: PATH'te olmalı (örn. `apache-maven-3.9.9/bin`)
- **browser system property**: `-Dbrowser=chrome|firefox|edge` (default: chrome)
- **video display**: `-Dvideo.display=:99` (default: env DISPLAY, sonra `:0.0`)
