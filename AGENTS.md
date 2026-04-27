# PROJECT KNOWLEDGE BASE

**Generated:** 2026-04-27
**Branch:** claude/allure-reports-integration-NYM9h
**Stack:** Java 21 (Maven) + Python 3.12 (FastAPI) + Cucumber/JUnit 5

## OVERVIEW

Multi-module test automation reporting system. Cucumber Selenium testleri → Allure/ExtentReports → FastAPI dashboard → Jira bug + DOORS DXL + email. surefirePlugin-master/ ayrı bir Cucumber+ExtentReports eklenti geliştirme projesi.

## STRUCTURE

```
java_reports/
├── pom.xml                    # Parent POM (8 Maven modules)
├── test-core/                 # Cucumber runner + Selenium step defs
├── allure-integration/        # Allure hooks (screenshot + video)
├── extent-integration/        # ExtentReports Cucumber plugin
├── report-model/              # Jackson DTO + parser/writer/bug-tracker
├── email-service/             # Simple Java Mail + Thymeleaf
├── jira-service/              # Jira REST v2 client + WireMock tests
├── doors-service/             # DOORS DXL batch wrapper
├── orchestrator/              # Pipeline stage runner (shaded JAR)
├── fastapi-server/            # Python FastAPI web sunucu (Maven değil)
├── surefirePlugin-master/     # Ayrı Cucumber+ExtentReports plugin projesi
├── contract-tests/            # FastAPI ↔ Javalin API parity testleri
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
| Allure rapor hook'ları | `allure-integration/` | `ScreenshotHook.java`, `VideoHook.java` |
| ExtentReports hook'ları | `extent-integration/` + `surefirePlugin-master/` | İki ayrı implementasyon |
| Run manifest şeması | `report-model/` | `RunManifest.java`, `AllureResultsParser.java` |
| Web dashboard | `fastapi-server/` | `server.py`, `templates/dashboard.html` |
| Jira bug açma | `jira-service/` (Java) + `fastapi-server/jira_client.py` (Python) | İki client var |
| DOORS DXL | `doors-service/` | Windows-only, batch exe |
| Email gönderme | `email-service/` | GreenMail test, Thymeleaf template |
| Pipeline orchestration | `orchestrator/` | `PipelineRunner.java` |
| CI/CD | `Jenkinsfile` | GitHub Actions da mevcut |
| Mock data | `bug-tracker.json`, `mock-email.json`, `manifests/` | Demo için |

## CONVENTIONS

- **Java package**: `com.testreports.<module>` (test-core, jira, email, doors, model, allure, javalin, orchestrator, extent)
- **Python**: FastAPI `server.py` ana entry, modüller `models.py`, `bug_tracker.py`, `jira_client.py`
- **Test**: Java → JUnit 5 + WireMock/GreenMail, Python → pytest + FastAPI TestClient
- **Config**: `.env.example` → `.env` kopyala, `application.yml` yok (env var + system property)
- **Maven**: `mvn -pl <module> test` ile tek modül test, `mvn validate` tüm projeyi
- **Git**: `main` branch her zaman temiz, feature branch'ler `claude/*` prefix'li
- **Port**: FastAPI: 8000, Javalin: 8080 (kullanımdan kalktı)

## ANTI-PATTERNS (THIS PROJECT)

- ❌ Database yok — her şey dosya tabanlı (JSON manifests, bug-tracker.json)
- ❌ Spring Boot YOK — Javalin standalone (sonra tamamen kaldırıldı, sadece FastAPI)
- ❌ `allure serve` kullanma — `allure generate` + statik hosting
- ❌ ADF formatı kullanma (Jira Cloud v3) — Server/DC için wiki renderer
- ❌ Hardcoded credential — her şey `.env` veya system property
- ❌ Pass videoları saklama — sadece fail
- ❌ `@ts-ignore`, `as any`, empty catch — review'da red sebebi

## UNIQUE STYLES

- **Raporlama hibrit**: Hem Allure hem ExtentReports aynı projede (test-core cucumber.properties iki plugin de yüklü)
- **Çift Jira client**: Java tarafı (jira-service) + Python tarafı (jira_client.py) — Python web UI'dan çağrı için
- **surefirePlugin-master**: Ayrı bir Maven projesi, parent POM'da module listesinde YOK. Kendi başına build edilir. Retry mekanizması, senaryo bağımlılık yönetimi (`@id/@dep`), ExtentReports merge tool içerir
- **Orchestrator shaded JAR**: `maven-shade-plugin` ile tüm bağımlılıkları tek JAR'da paketler

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

# Pipeline
java -jar orchestrator/target/orchestrator.jar --run-id=auto

# Python test
cd fastapi-server && python3 -m pytest tests/ -v

# surefirePlugin test
cd surefirePlugin-master && mvn test -Dcucumber.filter.tags="@Deneme"
```

## NOTES

- **Windows/WSL**: DOORS sadece Windows'ta çalışır. Sunucu WSL'de başlatılır, Windows'tan `localhost:8000` erişilir
- **ffmpeg**: Video kaydı için gerekli ama opsiyonel — yoksa graceful skip
- **Allure CLI**: `/home/ol_ta/tools/allure-2.33.0/bin/allure`
- **Maven**: `/home/ol_ta/tools/apache-maven-3.9.9/bin/mvn`
- **GitHub token**: `workflow` scope eksik → `.github/workflows/` dosyaları push edilemiyor
- **surefirePlugin features**: `@id:`, `@dep:` tag'leri ile senaryo bağımlılık yönetimi, `run-by-tag.sh` ile tag bazlı koşum, `ExtentReportMerger.java` ile rapor birleştirme
