# Test Otomasyon Raporlama ve Entegrasyon Sistemi

## TL;DR

> **Quick Summary**: Java Selenium Cucumber/Gherkin test projesine Allure raporlama, FastAPI+Javalin web sunucu, email bildirimi, yarı otomatik Jira bug açma, DOORS Classic test run otomasyonu ve CI/CD pipeline entegrasyonu.
>
> **Deliverables**:
> - Allure HTML raporları (screenshot + ffmpeg 15fps video, sadece fail)
> - FastAPI (Python) + Javalin (Java) web sunucu (REST API + JWT + "Create Jira Bug" butonu)
> - Thymeleaf tabanlı responsive HTML email (şirket SMTP)
> - Jira Server/DC REST v2 entegrasyonu (PAT auth, wiki-renderer)
> - DOORS Classic 9.7 batch DXL otomasyonu
> - CI/CD pipeline (Jenkins / GitHub Actions)
>
> **Estimated Effort**: Large (~20 iş günü)
> **Parallel Execution**: YES — 5-6 task/wave
> **Critical Path**: Phase 0 → WP-1 Allure → WP-4 Email + WP-2/3 Sunucu → WP-7 CI/CD → WP-8 Tasarım

---

## 1. Vizyon

Sıfırdan bir Java Selenium Cucumber/Gherkin test projesi oluşturup, entegre bir raporlama ve CI/CD pipeline'ı kurmak:

```
[CI/CD Trigger]
    → [Cucumber Test Run]
        → ffmpeg 15fps (sadece fail video)
        → Selenium screenshot
        → Allure results JSON + statik HTML
    → Web Server (FastAPI + Javalin)
        → REST API: run listesi, failure detay, screenshot/video
        → "Create Jira Bug" butonu (yarı otomatik)
    → Email (özet + link → web sunucu)
        → Mühendis tıklar → raporu inceler
            → "Create Jira Bug" butonu → Jira Bug Issue (PAT)
    → DOORS Classic Batch DXL (yeni test run, absolute number ile)
```

---

## 2. Teknik Kararlar

| Karar | Seçim | Gerekçe |
|-------|-------|---------|
| **Raporlama** | Allure Framework | ExtentReports sunset ↗ ChainTest; en iyi Cucumber adapter, video/screenshot, history, Apache 2.0 |
| **Web Sunucu** | FastAPI (Python) + Javalin (Java) | İkisi de production-ready yapılacak |
| **Email** | Simple Java Mail + Thymeleaf | Fluent API, connection pooling; WYSIWYG HTML email template |
| **Jira** | Direct REST v2 + PAT (Java HttpClient) | Jira Server/DC wiki-renderer description; OkHttp/HttpClient |
| **DOORS** | Batch DXL (`doors.exe -b`) + temp file | DOORS Classic 9.7, Windows-only |
| **CI/CD** | Jenkins veya GitHub Actions | Maven tabanlı pipeline, cron/manual trigger |
| **Auth** | JWT Stateless | Web sunucu + email link için signed token |
| **Build** | Maven multi-module | Java 17+ |
| **Test** | TDD (unit/integration/contract) | WireMock, GreenMail, Playwright, fake doors.exe |
| **Video** | ffmpeg 15fps, sadece FAIL sakla | Disk tasarrufu |
| **Jira Auth** | Personal Access Token (PAT) | Server/DC için |
| **Jira Description** | Wiki-renderer (NOT ADF!) | Server/DC REST v2 wiki format; ADF sadece Cloud v3 |
| **Allure** | `allure generate` → statik dosya | `allure serve` canlı process, email link için uygun değil |

---

## 3. Metis Review — Bulgular ve Düzeltmeler

| # | Metis Bulgusu | Aksiyon |
|---|--------------|---------|
| M1 | Jira ADF yanlış — Server/DC wiki-renderer kullanır | ❌ ADF → ✅ Wiki format |
| M2 | `allure serve` canlı process, email link için uygun değil | ❌ serve → ✅ `allure generate` + statik hosting |
| M3 | "Manuel görsel doğrulama" WP-8'de geçersiz | ✅ Playwright + snapshot test |
| M4 | Jira bug açma akışı belirsiz | ✅ Yarı otomatik: web UI "Create Jira Bug" butonu |
| M5 | Eksik Phase 0 keşif adımı | ✅ WP-0 eklendi |
| M6 | Çift sunucu scope patlaması | ✅ İkisi de tam yapılacak (kullanıcı kararı) |
| M7 | run-manifest.json şeması yok | ✅ WP-0'da tanımlanacak |
| M8 | Kabul kriterleri çalıştırılabilir değil | ✅ Tüm kriterler komut + beklenen çıktı formatında |
| M9 | CI/CD yoktu | ✅ WP-7 olarak eklendi (kullanıcı talebi) |

---

## 4. Gap Analysis & Assumptions

### Proje Mevcut Değil — Sıfırdan Oluşturulacak

| # | Durum | Aksiyon |
|---|-------|---------|
| P1 | Mevcut Cucumber projesi yok | WP-0'da referans proje oluşturulacak |
| P2 | DOORS 9.7 mevcut değil | DXL integration teorik + fake `doors.exe` ile test |
| P3 | Jira Server/DC API | Canlı API'ye bağlanacak, WireMock ile unit test |
| P4 | Çalışma ortamı | Windows (DOORS için) + WSL olabilir |
| P5 | Java 17+ varsayımı | WP-0'da doğrulanacak |

### Scope Guardrails (Kapsam Dışı)

| # | Kapsam DIŞI | Nedeni |
|---|-------------|--------|
| X1 | Full user management / RBAC | MVP: single admin JWT + signed report token |
| X2 | Database (PostgreSQL/MySQL) | File-based manifest yeterli |
| X3 | Custom Allure plugin/internals | Allure standart çıktı + branded wrapper |
| X4 | Multi-browser parallel test | Şimdilik single-browser |
| X5 | Otomatik Jira bug (onaysız) | Yarı otomatik: mühendis onayı şart |

---

## 5. Work Objectives

### Core Objective
Selenium Cucumber test sonuçlarını otomatik raporlayan, CI/CD'de çalışan, email ile bildiren, Jira ve DOORS entegrasyonlu bir pipeline kurmak.

### Concrete Deliverables
- Maven multi-module proje (Java 17+)
- Allure report (screenshot + video, history)
- FastAPI web sunucu (Python, REST API + JWT + UI)
- Javalin web sunucu (Java, aynı kontrat)
- Email service (Thymeleaf + SMTP)
- Jira client (REST v2, wiki description)
- DOORS DXL service (batch mode)
- CI/CD pipeline (Jenkinsfile / GitHub Actions workflow)
- Web UI "Create Jira Bug" triage sayfası
- run-manifest.json şeması

### Definition of Done
- [ ] `mvn clean verify` tüm testleri geçer
- [ ] `allure generate` statik rapor oluşturur
- [ ] FastAPI `uvicorn` ile port 8000'de çalışır
- [ ] Javalin port 8080'de çalışır
- [ ] Email GreenMail testleri geçer
- [ ] Jira WireMock testleri geçer
- [ ] DOORS fake `doors.exe` testleri geçer
- [ ] CI/CD pipeline başarıyla tetiklenir
- [ ] Playwright snapshot testleri geçer

---

## 6. Verification Strategy

> **ZERO HUMAN INTERVENTION** — Tüm doğrulama ajan tarafından çalıştırılabilir.

### Test Decision
- **Infrastructure exists**: Hayır (sıfırdan kurulacak)
- **Automated tests**: TDD
- **Framework**: JUnit 5 (Java), pytest (Python), Playwright (UI), WireMock (Jira), GreenMail (email)

### QA Policy
Her task'ta agent-executed QA senaryoları:
- **Backend**: curl + JUnit assertion
- **Email**: GreenMail + MIME parsing
- **Jira**: WireMock contract verification
- **DOORS**: fake `doors.exe` + ProcessBuilder fixture
- **UI/Web**: Playwright (navigate, click, assert, screenshot)
- **Video**: ffprobe validation

---

## 7. Execution Strategy

### Parallel Execution Waves

```
Wave 0 (Phase 0 — Keşif + Scaffolding):
├── Task 0.1: Proje yapısı (Maven multi-module) [quick]
├── Task 0.2: Referans Cucumber test projesi [quick]
├── Task 0.3: Jira API keşif + PAT test [quick]
├── Task 0.4: run-manifest.json şema tasarımı [quick]
└── Task 0.5: Allure + ffmpeg kurulum doğrulama [quick]

Wave 1 (Start Immediately — Çekirdek entegrasyonlar):
├── Task 1: Allure entegrasyonu (Cucumber adapter) [deep]
├── Task 2: Screenshot + video attach (ffmpeg 15fps) [quick]
└── Task 3: run-manifest.json writer (Allure results parser) [quick]

Wave 2 (After Wave 1 — MAX PARALLEL):
├── Task 4: FastAPI web sunucu [visual-engineering]
├── Task 5: Javalin web sunucu [visual-engineering]
├── Task 6: Email service (Simple Java Mail + Thymeleaf) [quick]
├── Task 7: Jira client (REST v2 wiki + WireMock test) [deep]
└── Task 8: DOORS DXL service (fake doors.exe test) [unspecified-high]

Wave 3 (After Wave 2 — Entegrasyon + UI):
├── Task 9: Web UI "Create Jira Bug" triage sayfası [visual-engineering]
├── Task 10: Orchestrator (pipeline stage runner) [deep]
├── Task 11: Contract test (FastAPI ↔ Javalin aynı API) [quick]
├── Task 12: CI/CD pipeline (Jenkinsfile / GitHub Actions) [quick]
└── Task 13: Allure custom tasarım (brand colors, logo) [visual-engineering]

Wave FINAL (After ALL tasks — Review):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (tsc/lint/test)
├── Task F3: Real QA execution (Playwright + curl + GreenMail)
└── Task F4: Scope fidelity check (git diff vs plan)
```

### Critical Path
WP-0 → WP-1(Allure) → WP-4(FastAPI) + WP-6(Email) → WP-9(Triage UI) → WP-12(CI/CD) → F1-F4

---

## 8. TODOs

---

- [x] 0.1 **Phase 0: Maven Multi-Module Proje İskeleti**

  **What to do**:
  - Maven parent POM oluştur (Java 17+, `maven-compiler-plugin`)
  - Module yapısı:
    ```
    test-reports/
    ├── pom.xml (parent)
    ├── test-core/          → Cucumber runner, step defs, Selenium POM
    ├── allure-integration/  → Allure adapter, screenshot/video hooks
    ├── report-model/        → run-manifest.json DTO + parser
    ├── fastapi-server/      → Python FastAPI (Poetry/requirements.txt)
    ├── javalin-server/      → Java Javalin Maven module
    ├── email-service/       → Simple Java Mail + Thymeleaf
    ├── jira-service/        → Jira REST v2 client
    ├── doors-service/       → DOORS DXL wrapper
    └── orchestrator/        → Pipeline stage runner
    ```
  - `.gitignore`, `README.md`, `.env.example`
  - **Test**: `mvn -q validate` → BUILD SUCCESS

  **Must NOT do**:
  - Database dependency ekleme
  - Hardcoded credential

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`git-master`]

  **Parallelization**: Wave 0, all Task 0.x parallel
  **Blocks**: Tüm diğer task'lar
  **Blocked By**: None

  **References**:
  - `pom.xml` pattern: standard Maven multi-module with `<modules>` and `<dependencyManagement>`

  **Acceptance Criteria**:
  - [ ] `mvn -q validate` → BUILD SUCCESS
  - [ ] `ls pom.xml test-core/pom.xml allure-integration/pom.xml` → all exist
  - [ ] `.env.example` exists, no real secrets

  **QA Scenarios**:
  ```
  Scenario: Multi-module build compiles
    Tool: Bash
    Preconditions: Java 17+, Maven 3.9+
    Steps:
      1. mvn -q compile
      2. Check exit code
    Expected Result: Exit code 0
    Evidence: .sisyphus/evidence/task-0.1-build.txt

  Scenario: No secrets in version control
    Tool: Bash (grep)
    Steps:
      1. grep -r "password\|secret\|token\|api.key" --include="*.java" --include="*.yml" --include="*.properties" . | grep -v ".env.example" | grep -v "test" || true
    Expected Result: No output (no hardcoded secrets)
    Evidence: .sisyphus/evidence/task-0.1-secrets.txt
  ```

  **Commit**: YES
  - Message: `chore: initialize Maven multi-module project structure`
  - Files: `pom.xml`, module `pom.xml` files, `.gitignore`, `.env.example`

---

- [x] 0.2 **Phase 0: Referans Cucumber Test Projesi**

  **What to do**:
  - `test-core/` modülünde örnek feature file:
    ```gherkin
    @DOORS-12345 @REQ-LOGIN-001
    Feature: Kullanıcı Girişi
      Scenario: Başarılı giriş
        Given kullanıcı login sayfasında
        When geçerli kullanıcı adı "test@example.com" ve şifre girer
        Then dashboard sayfasına yönlendirilir

      @sample-fail
      Scenario: Hatalı giriş
        Given kullanıcı login sayfasında
        When geçersiz şifre girer
        Then hata mesajı görüntülenir
    ```
  - Cucumber runner (`@RunWith(Cucumber.class)`, JUnit 5)
  - WebDriver factory (Chrome/Firefox headless)
  - Step definitions (basit WebDriver çağrıları)
  - `cucumber.properties`
  - **Test**: `mvn -q -pl test-core test` → 1 scenario PASS, 1 scenario FAIL

  **Must NOT do**:
  - Gerçek bir uygulamaya bağlanma (demo/test sayfası yeterli)

  **Recommended Agent Profile**:
  - **Category**: `quick`

  **Parallelization**: Wave 0
  **Blocks**: Task 1, 2, 3
  **Blocked By**: Task 0.1

  **References**:
  - Cucumber JUnit 5: `io.cucumber:cucumber-junit-platform-engine`
  - Selenium WebDriver: `org.seleniumhq.selenium:selenium-java`

  **Acceptance Criteria**:
  - [ ] `mvn -q -pl test-core test -Dcucumber.filter.tags="@sample-fail"` → exit code ≠ 0 (test fails as expected)
  - [ ] `mvn -q -pl test-core test -Dcucumber.filter.tags="not @sample-fail"` → exit code = 0
  - [ ] `target/cucumber-reports/` dizininde JSON rapor oluşur

  **QA Scenarios**:
  ```
  Scenario: pass scenario succeeds
    Tool: Bash
    Steps:
      1. mvn -q -pl test-core test -Dcucumber.filter.tags="not @sample-fail"
    Expected Result: Exit code 0, BUILD SUCCESS
    Evidence: .sisyphus/evidence/task-0.2-pass.txt

  Scenario: fail scenario intentionally fails
    Tool: Bash
    Steps:
      1. mvn -q -pl test-core test -Dcucumber.filter.tags="@sample-fail" || echo "EXPECTED_FAIL"
    Expected Result: "EXPECTED_FAIL" in output
    Evidence: .sisyphus/evidence/task-0.2-fail.txt

  Scenario: cucumber JSON output exists
    Tool: Bash
    Steps:
      1. test -f test-core/target/cucumber-reports/*.json && echo "JSON_FOUND"
    Expected Result: "JSON_FOUND"
    Evidence: .sisyphus/evidence/task-0.2-json.txt
  ```

  **Commit**: YES
  - Message: `feat(test-core): add reference Cucumber test project with pass/fail scenarios`

---

- [x] 0.3 **Phase 0: Jira API Discovery + PAT Testi**

  **What to do**:
  - Jira Server/DC REST v2 endpoint testi
  - `GET /rest/api/2/myself` ile PAT doğrulama
  - `GET /rest/api/2/issue/createmeta` ile required fields keşfi
  - `POST /rest/api/2/issue` test (proje key, issuetype Bug)
  - Attachment API test (`POST /rest/api/2/issue/{key}/attachments`)
  - WireMock mapping'leri oluştur
  - **Test**: WireMock ile tüm endpoint mock testleri

  **Must NOT do**:
  - Canlı Jira'ya spam issue açma (testlerde WireMock kullan)

  **Recommended Agent Profile**:
  - **Category**: `quick`

  **Parallelization**: Wave 0
  **Blocks**: Task 7
  **Blocked By**: Task 0.1

  **References**:
  - Jira Server REST API v2: `https://docs.atlassian.com/software/jira/docs/api/REST/latest/`
  - Wiki-renderer format: `textile` veya `atlassian-wiki-renderer`

  **Acceptance Criteria**:
  - [ ] `mvn -q -pl jira-service test` → WireMock testleri PASS
  - [ ] PAT ile `GET /rest/api/2/myself` → 200, username doğru
  - [ ] `POST /rest/api/2/issue` WireMock → 201, issue key döner
  - [ ] Attachment upload → `X-Atlassian-Token: no-check` header var

  **QA Scenarios**:
  ```
  Scenario: WireMock verifies issue creation request
    Tool: Bash (JUnit via Maven)
    Steps:
      1. mvn -q -pl jira-service test -Dtest=JiraIssueCreationTest
    Expected Result: BUILD SUCCESS, WireMock verifies POST /rest/api/2/issue
    Evidence: .sisyphus/evidence/task-0.3-wiremock.txt

  Scenario: PAT authentication works
    Tool: Bash (curl to WireMock)
    Steps:
      1. curl -s -u "test@example.com:test-pat-token" http://localhost:9999/rest/api/2/myself
    Expected Result: HTTP 200, JSON body contains "name":"test.user"
    Evidence: .sisyphus/evidence/task-0.3-auth.json
  ```

  **Commit**: YES
  - Message: `feat(jira-service): add Jira Server/DC REST v2 client with WireMock tests`

---

- [x] 0.4 **Phase 0: run-manifest.json Şeması**

  **What to do**:
  - JSON Schema tanımı:
    ```json
    {
      "runId": "20260426-143022-a1b2c3",
      "timestamp": "2026-04-26T14:30:22Z",
      "totalScenarios": 10,
      "passed": 7,
      "failed": 2,
      "skipped": 1,
      "duration": "45.2s",
      "scenarios": [{
        "id": "login-success",
        "name": "Başarılı giriş",
        "status": "passed",
        "duration": "3.1s",
        "doorsAbsNumber": "DOORS-12345",
        "tags": ["@DOORS-12345", "@REQ-LOGIN-001"],
        "steps": [...],
        "attachments": []
      }]
    }
    ```
  - Java DTO (Jackson) + Python Pydantic model
  - Allure results → manifest dönüştürücü
  - **Test**: Schema validation her iki dilde

  **Must NOT do**:
  - Database schema — file-only

  **Recommended Agent Profile**:
  - **Category**: `quick`

  **Parallelization**: Wave 0
  **Blocks**: Task 3, 4, 5, 6, 8, 10
  **Blocked By**: Task 0.1

  **Acceptance Criteria**:
  - [ ] JSON Schema `schemas/run-manifest.schema.json` geçerli
  - [ ] Java `RunManifest.class` Jackson serialization → valid JSON
  - [ ] Python `RunManifest` Pydantic model → valid JSON
  - [ ] Sample manifest `manifests/sample-run-001.json` şemaya uygun

  **QA Scenarios**:
  ```
  Scenario: Java DTO serializes to valid manifest JSON
    Tool: Bash (JUnit)
    Steps:
      1. mvn -q -pl report-model test -Dtest=RunManifestTest#serialize
    Expected Result: BUILD SUCCESS, output JSON validates against schema
    Evidence: .sisyphus/evidence/task-0.4-java.txt

  Scenario: Python model validates against schema
    Tool: Bash (pytest)
    Steps:
      1. cd fastapi-server && pytest tests/test_schema.py -v
    Expected Result: All tests pass
    Evidence: .sisyphus/evidence/task-0.4-python.txt
  ```

  **Commit**: YES
  - Message: `feat(report-model): define run-manifest.json schema with Java DTO + Python Pydantic`

---

- [x] 0.5 **Phase 0: Allure + ffmpeg Kurulum Doğrulaması**

  **What to do**:
  - Allure CLI kurulum (`allure --version`)
  - ffmpeg kurulum (`ffmpeg -version`)
  - `allure.properties` yapılandırması
  - `allure generate` test (boş results → HTML)
  - ffmpeg screen capture test (5 saniye, 15fps)
  - `ffprobe` ile frame rate doğrulama
  - **Test**: `ffprobe test-video.mp4` → fps=15

  **Must NOT do**:
  - Gerçek test senaryosuna bağlama (Task 1-2'de yapılacak)

  **Recommended Agent Profile**:
  - **Category**: `quick`

  **Parallelization**: Wave 0
  **Blocks**: Task 1, 2
  **Blocked By**: Task 0.1

  **Acceptance Criteria**:
  - [ ] `allure --version` → sürüm yazdırır
  - [ ] `allure generate --clean target/allure-results -o target/allure-report` → HTML oluşur
  - [ ] `ffprobe test-video.mp4` → `r_frame_rate=15/1`
  - [ ] `ffprobe test-video.mp4` → `codec_type=video`

  **QA Scenarios**:
  ```
  Scenario: allure generate creates static HTML
    Tool: Bash
    Steps:
      1. mkdir -p target/allure-results && echo '{}' > target/allure-results/dummy.json
      2. allure generate --clean target/allure-results -o target/allure-report
      3. test -f target/allure-report/index.html && echo "HTML_OK"
    Expected Result: "HTML_OK"
    Evidence: .sisyphus/evidence/task-0.5-allure.txt

  Scenario: ffmpeg records at 15fps
    Tool: Bash
    Steps:
      1. ffmpeg -y -f lavfi -i testsrc=duration=3:size=640x480:rate=15 test-video.mp4
      2. ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of default=noprint_wrappers=1:nokey=1 test-video.mp4
    Expected Result: "15/1"
    Evidence: .sisyphus/evidence/task-0.5-ffmpeg.txt
  ```

  **Commit**: YES
  - Message: `chore: verify Allure CLI and ffmpeg 15fps capture`

---

- [x] 1. **Allure Cucumber Entegrasyonu**

  **What to do**:
  - `allure-cucumber7-jvm` dependency ekle
  - Cucumber runner'a Allure plugin tanımla (`plugin = {"io.qameta.allure.cucumber7jvm.AllureCucumber7Jvm"}`)
  - `allure.properties` → `allure.results.directory=target/allure-results`
  - Allure annotations (`@Feature`, `@Story`, `@Severity`) feature/scenario mapping
  - `CustomAllureListener` (TestNG/JUnit hook)
  - Allure'dan ExtentReports referanslarını temizle
  - **Test**: `mvn -q test` → `target/allure-results/*-result.json` oluşur
  - **Test**: JSON içinde scenario name, status, steps, attachments var
  - **Test**: `allure generate` → `index.html` render edilir, Playwright ile açılır

  **Must NOT do**:
  - Mevcut test senaryolarını değiştirme (sadece raporlama katmanı)
  - ExtentReports dependency bırakma

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`playwright`]

  **Parallelization**: Wave 1
  **Blocks**: Task 3, 9, 13
  **Blocked By**: Task 0.2

  **References**:
  - Allure CucumberJVM: `https://github.com/allure-framework/allure-java/tree/main/allure-cucumber7-jvm`
  - Allure annotations: `io.qameta.allure:allure-junit5`

  **Acceptance Criteria**:
  - [ ] `mvn -q test -Dcucumber.filter.tags="@sample-fail"` → `target/allure-results/` en az 1 `*-result.json` içerir
  - [ ] `*-result.json` içinde `"status": "failed"` var
  - [ ] `*-result.json` içinde `"name": "Hatalı giriş"` var
  - [ ] `allure generate --clean target/allure-results -o target/allure-report` exit 0
  - [ ] `test -f target/allure-report/index.html` → exists

  **QA Scenarios**:
  ```
  Scenario: Failed scenario produces Allure result with correct status
    Tool: Bash
    Steps:
      1. mvn -q test -Dcucumber.filter.tags="@sample-fail" || true
      2. python3 -c "import json,glob; f=glob.glob('target/allure-results/*-result.json')[0]; d=json.load(open(f)); assert d['status']=='failed'; print('STATUS_OK')"
    Expected Result: "STATUS_OK"
    Evidence: .sisyphus/evidence/task-1-status.txt

  Scenario: Allure generate produces valid HTML
    Tool: Playwright
    Preconditions: allure generate completed
    Steps:
      1. Navigate to file://target/allure-report/index.html
      2. Wait for selector: [data-testid="total-counter"]
      3. Assert page contains "failed"
    Expected Result: Dashboard renders with failure count > 0
    Evidence: .sisyphus/evidence/task-1-allure-ui.png
  ```

  **Commit**: YES
  - Message: `feat(allure): integrate Allure CucumberJVM adapter, remove ExtentReports`

---

- [x] 2. **Screenshot + Video Attach (ffmpeg 15fps)**

  **What to do**:
  - Cucumber Hooks: `@Before` → ffmpeg başlat, `@After` → ffmpeg durdur
  - Screenshot: `@After` (failed only) → `TakesScreenshot` → byte[] → Allure `@Attachment`
  - Video: `@After` → ffmpeg process kill → `.mp4` → Allure `@Attachment(type = "video/mp4")`
  - Pass senaryoda videoyu sil (disk temizliği)
  - Video için unique filename (`{scenarioName}_{timestamp}.mp4`)
  - ffmpeg komutu: `ffmpeg -f gdigrab -framerate 15 -i desktop -t 9999 output.mp4`
  - **Test**: fail senaryo → video attach edilir
  - **Test**: pass senaryo → video silinir
  - **Test**: ffprobe → 15fps, codec video

  **Must NOT do**:
  - Pass videoları saklama
  - WebDriver dışında kayıt yapma (güvenlik)

  **Recommended Agent Profile**:
  - **Category**: `quick`

  **Parallelization**: Wave 1
  **Blocks**: Task 9
  **Blocked By**: Task 0.2, 0.5

  **Acceptance Criteria**:
  - [ ] Fail senaryoda `*-result.json` `attachments` array'inde `video/mp4` var
  - [ ] Fail senaryoda `*-result.json` `attachments` array'inde `image/png` var
  - [ ] Pass senaryoda video dosyası diskte yok
  - [ ] `ffprobe failed-scenario.mp4` → `r_frame_rate=15/1`

  **QA Scenarios**:
  ```
  Scenario: Failed scenario has screenshot and video attachments
    Tool: Bash
    Steps:
      1. mvn -q test -Dcucumber.filter.tags="@sample-fail" || true
      2. python3 -c "
    import json,glob
    f=glob.glob('target/allure-results/*-result.json')[0]
    d=json.load(open(f))
    types=[a['type'] for a in d.get('attachments',[])]
    assert 'image/png' in types, 'No screenshot'
    assert 'video/mp4' in types, 'No video'
    print('ATTACH_OK')
    "
    Expected Result: "ATTACH_OK"
    Evidence: .sisyphus/evidence/task-2-attach.txt

  Scenario: Pass scenario video is deleted
    Tool: Bash
    Steps:
      1. mvn -q test -Dcucumber.filter.tags="not @sample-fail"
      2. find . -name "*.mp4" -newer pom.xml | wc -l
    Expected Result: 0 (no video files from this run remain)
    Evidence: .sisyphus/evidence/task-2-cleanup.txt
  ```

  **Commit**: YES
  - Message: `feat(allure): add screenshot + ffmpeg 15fps video attachment, delete on pass`

---

- [ ] 3. **run-manifest.json Writer**

  **What to do**:
  - `AllureResultsParser`: `target/allure-results/*-result.json` → Java DTO
  - `ManifestWriter`: DTO → `manifests/{runId}.json`
  - Run ID generation: `yyyyMMdd-HHmmss-{shortHash}`
  - Allure history ID mapping
  - Scenario ↔ DOORS Absolute Number mapping (tag `@DOORS-XXXXX`)
  - **Test**: 2 senaryo (1 pass + 1 fail) → manifest doğru
  - **Test**: manifest JSON Schema validation

  **Must NOT do**:
  - Database yazma

  **Recommended Agent Profile**:
  - **Category**: `quick`

  **Parallelization**: Wave 1
  **Blocks**: Task 4, 5, 6, 10
  **Blocked By**: Task 0.4, 1

  **Acceptance Criteria**:
  - [ ] `manifests/sample-run-001.json` — `totalScenarios >= 2`
  - [ ] `failed >= 1`
  - [ ] `scenarios[].doorsAbsNumber` DOORS tag'inden parse edilmiş

  **QA Scenarios**:
  ```
  Scenario: Manifest correctly reflects test results
    Tool: Bash
    Steps:
      1. cat manifests/sample-run-001.json | python3 -c "
    import json,sys
    d=json.load(sys.stdin)
    assert d['totalScenarios'] == d['passed'] + d['failed'] + d['skipped']
    print('MANIFEST_OK')
    "
    Expected Result: "MANIFEST_OK"
    Evidence: .sisyphus/evidence/task-3-manifest.txt
  ```

  **Commit**: YES
  - Message: `feat(report-model): add Allure-to-manifest parser and JSON writer`

---

- [ ] 4. **FastAPI Web Sunucu (Python)**

  **What to do**:
  - Poetry projesi: `fastapi`, `uvicorn`, `pyjwt`, `pydantic`
  - Statik dosya servisi: `manifests/` → `/reports/`
  - REST API:
    - `GET /api/v1/runs` → tüm manifest'ler
    - `GET /api/v1/runs/{runId}` → tek manifest
    - `GET /api/v1/runs/{runId}/failures` → sadece fail'ler
    - `GET /api/v1/runs/{runId}/screenshot/{name}` → görsel
    - `GET /api/v1/runs/{runId}/video/{name}` → video
  - JWT auth: `/api/v1/auth/login` → token, tüm `/api/v1/*` endpoint'ler `Authorization: Bearer`
  - CORS yapılandırması
  - **Test**: pytest ile tüm endpoint'ler
  - **Test**: HTTP 401 (no token)
  - **Test**: HTTP 200 (valid token)

  **Must NOT do**:
  - Database (dosya tabanlı manifest okur)
  - Full user management (tek admin JWT)

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`

  **Parallelization**: Wave 2 (Task 5 ile paralel)
  **Blocks**: Task 9, 11
  **Blocked By**: Task 0.4, 3

  **Acceptance Criteria**:
  - [ ] `pytest fastapi-server/tests -v` → all pass
  - [ ] `curl -i http://localhost:8000/api/v1/runs` → 401 Unauthorized
  - [ ] `curl -H "Authorization: Bearer $(python3 fastapi-server/scripts/get_token.py)" http://localhost:8000/api/v1/runs` → 200
  - [ ] Response body JSON Schema valid (Task 0.4 şeması)

  **QA Scenarios**:
  ```
  Scenario: Unauthorized access returns 401
    Tool: Bash (curl)
    Steps:
      1. curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/runs
    Expected Result: "401"
    Evidence: .sisyphus/evidence/task-4-unauth.txt

  Scenario: Authenticated request returns run list
    Tool: Bash (curl)
    Preconditions: uvicorn running on port 8000
    Steps:
      1. TOKEN=$(python3 fastapi-server/scripts/get_token.py)
      2. curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/runs | python3 -c "import json,sys; d=json.load(sys.stdin); assert isinstance(d,list); print('API_OK')"
    Expected Result: "API_OK"
    Evidence: .sisyphus/evidence/task-4-auth.txt
  ```

  **Commit**: YES
  - Message: `feat(fastapi): implement REST API + JWT auth + static report hosting`

---

- [ ] 5. **Javalin Web Sunucu (Java)**

  **What to do**:
  - Maven module: `javalin-server` (Javalin + Undertow/Jetty)
  - Task 4 ile aynı REST API kontratı
  - JWT filter (stateless)
  - Statik dosya servisi
  - CORS
  - **Test**: JUnit 5 + OkHttp client
  - **Test**: Contract test — FastAPI response yapısıyla birebir aynı

  **Must NOT do**:
  - Farklı API tasarımı (kontrat Task 4 ile aynı)

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`

  **Parallelization**: Wave 2 (Task 4 ile paralel)
  **Blocks**: Task 11
  **Blocked By**: Task 0.4, 3

  **Acceptance Criteria**:
  - [ ] `mvn -q -pl javalin-server test` → all pass
  - [ ] `curl -i http://localhost:8080/api/v1/runs` → 401
  - [ ] Javalin response JSON yapısı FastAPI ile aynı (contract test)

  **QA Scenarios**:
  ```
  Scenario: Javalin returns same JSON structure as FastAPI
    Tool: Bash (diff)
    Preconditions: both servers running
    Steps:
      1. FASTAPI_JSON=$(curl -s -H "Authorization: Bearer $T" http://localhost:8000/api/v1/runs | python3 -c "import json,sys; [print(k) for k in json.load(sys.stdin)[0].keys()]" | sort)
      2. JAVALIN_JSON=$(curl -s -H "Authorization: Bearer $T" http://localhost:8080/api/v1/runs | python3 -c "import json,sys; [print(k) for k in json.load(sys.stdin)[0].keys()]" | sort)
      3. diff <(echo "$FASTAPI_JSON") <(echo "$JAVALIN_JSON")
    Expected Result: No diff output (identical keys)
    Evidence: .sisyphus/evidence/task-5-contract.txt
  ```

  **Commit**: YES
  - Message: `feat(javalin): implement REST API with contract parity to FastAPI`

---

- [ ] 6. **Email Service (Simple Java Mail + Thymeleaf)**

  **What to do**:
  - Maven module: `email-service`
  - Simple Java Mail (SMTP + connection pooling)
  - Thymeleaf template engine
  - HTML template: `email-summary.html`
    - Run ID, tarih, geçen/kalan/atlama sayıları
    - Başarı oranı progress bar
    - Web sunucu linki (signed JWT ile)
  - Plain-text fallback (`text/plain` part)
  - Şirket logosu CID inline embedding
  - SMTP retry (exponential backoff, 3 deneme)
  - **Test**: GreenMail ile integration test
  - **Test**: MIME multipart/alternative yapısı doğru

  **Must NOT do**:
  - SMTP credential hardcode
  - Spam-like content

  **Recommended Agent Profile**:
  - **Category**: `quick`

  **Parallelization**: Wave 2
  **Blocks**: Task 10
  **Blocked By**: Task 0.4, 3

  **Acceptance Criteria**:
  - [ ] `mvn -q -pl email-service test` → GreenMail 1 mesaj alır
  - [ ] Email subject: run ID + fail count içerir
  - [ ] MIME: `multipart/alternative` → `text/html` + `text/plain`
  - [ ] HTML body: web sunucu linki `/reports/{runId}` içerir
  - [ ] No raw SMTP password in body

  **QA Scenarios**:
  ```
  Scenario: GreenMail receives formatted email
    Tool: Bash (JUnit)
    Steps:
      1. mvn -q -pl email-service test -Dtest=EmailServiceTest#sendReport
    Expected Result: BUILD SUCCESS, GreenMail inbox size = 1
    Evidence: .sisyphus/evidence/task-6-email.txt

  Scenario: Email contains correct MIME structure
    Tool: Bash (JUnit)
    Steps:
      1. mvn -q -pl email-service test -Dtest=EmailMimeTest#verifyMultipart
    Expected Result: text/html + text/plain parts both present
    Evidence: .sisyphus/evidence/task-6-mime.txt
  ```

  **Commit**: YES
  - Message: `feat(email): add Thymeleaf HTML email service with GreenMail tests`

---

- [ ] 7. **Jira Client (REST v2 Wiki + WireMock)**

  **What to do**:
  - Maven module: `jira-service`
  - OkHttp/HttpClient REST client
  - PAT Basic Auth header
  - Wiki-renderer description builder (NOT ADF!)
    ```
    h2. Test Failure: {scenarioName}
    *Run ID*: {runId}
    *Scenario*: {scenarioName}
    *Step Failed*: {stepName}
    *Error*: {errorMessage}
    *Report Link*: [{runId}]
    *Screenshot*: !{screenshotUrl}!
    ```
  - Attachment upload (`multipart/form-data`, `X-Atlassian-Token: no-check`)
  - Duplicate detection (runId + scenarioId hash → var olan issue key dön)
  - Retry + exponential backoff
  - Dry-run mode (`jira.dry-run=true` → log only)
  - **Test**: WireMock ile tüm endpoint'ler
  - **Test**: Custom field mapping

  **Must NOT do**:
  - ADF format (Cloud v3 only)
  - Canlı Jira'ya test sırasında issue açma

  **Recommended Agent Profile**:
  - **Category**: `deep`

  **Parallelization**: Wave 2
  **Blocks**: Task 9, 10
  **Blocked By**: Task 0.3

  **Acceptance Criteria**:
  - [ ] `mvn -q -pl jira-service test` → WireMock verifies `POST /rest/api/2/issue`
  - [ ] Request body: `project.key`, `issuetype.name=Bug`, `summary`, `description` (wiki format)
  - [ ] Duplicate request → `409 Conflict` → existing key döner
  - [ ] Attachment upload: `X-Atlassian-Token: no-check` header mevcut
  - [ ] Dry-run mode: hiçbir gerçek HTTP çağrısı yapılmaz

  **QA Scenarios**:
  ```
  Scenario: Jira issue creation request matches expected wiki format
    Tool: Bash (JUnit/WireMock)
    Steps:
      1. mvn -q -pl jira-service test -Dtest=JiraIssueCreationTest#verifyWikiFormat
    Expected Result: WireMock verifies description contains "h2. Test Failure:"
    Evidence: .sisyphus/evidence/task-7-wiki.txt

  Scenario: Duplicate detection prevents second issue
    Tool: Bash (JUnit/WireMock)
    Steps:
      1. mvn -q -pl jira-service test -Dtest=JiraDuplicateTest#preventDuplicate
    Expected Result: BUILD SUCCESS, second call returns existing key
    Evidence: .sisyphus/evidence/task-7-dedup.txt
  ```

  **Commit**: YES
  - Message: `feat(jira): implement REST v2 wiki client with WireMock + dry-run mode`

---

- [ ] 8. **DOORS DXL Service (Batch + Fake Test)**

  **What to do**:
  - Maven module: `doors-service`
  - Java wrapper: `ProcessBuilder` → `doors.exe -b script.dxl -paramFile temp.json -W`
  - DXL script template:
    - Temp dosyadan JSON oku
    - Absolute Number ile DOORS objesi bul (`find(obj, attr="Absolute Number", value)`)
    - Test Run objesi oluştur/güncelle (custom module schema)
    - Pass/Fail durumunu attribute'a yaz
    - Zaman damgası ekle
    - `cout` ile sonuç yaz
  - Fail-safe: `doors.exe` bulunamazsa → warning log, pipeline devam
  - Timeout: 120s
  - Windows OS check
  - Dry-run mode (`doors.dry-run=true`)
  - **Test**: Fake `doors.exe` script (argümanları log'lar)
  - **Test**: Timeout path
  - **Test**: Object not found path

  **Must NOT do**:
  - Gerçek DOORS lisansı gerektiren test (fake.exe yeterli)
  - Pipeline'ı DOORS yoksa çökertme

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`

  **Parallelization**: Wave 2
  **Blocks**: Task 10
  **Blocked By**: Task 0.4

  **Acceptance Criteria**:
  - [ ] `mvn -q -pl doors-service test` → fake `doors.exe` doğru argümanları alır
  - [ ] Temp JSON: `{"absNumber": "DOORS-12345", "status": "failed", "runId": "..."}`
  - [ ] Timeout → controlled failure
  - [ ] OS check: non-Windows → warning, no crash
  - [ ] Dry-run: `doors.exe` çağrılmaz, sadece log

  **QA Scenarios**:
  ```
  Scenario: Fake doors.exe receives correct batch arguments
    Tool: Bash (JUnit)
    Steps:
      1. mvn -q -pl doors-service test -Dtest=DoorsBatchTest#verifyArguments
    Expected Result: fake.exe logs "-b", "-paramFile", temp JSON path found
    Evidence: .sisyphus/evidence/task-8-args.txt

  Scenario: Missing doors.exe doesn't crash pipeline
    Tool: Bash (JUnit)
    Steps:
      1. mv fake-doors.exe fake-doors.exe.bak
      2. mvn -q -pl doors-service test -Dtest=DoorsFailSafeTest || true
      3. mv fake-doors.exe.bak fake-doors.exe
    Expected Result: Test passes (warning logged, no exception)
    Evidence: .sisyphus/evidence/task-8-failsafe.txt
  ```

  **Commit**: YES
  - Message: `feat(doors): add batch DXL wrapper with fake.exe test + dry-run mode`

---

- [ ] 9. **Web UI — "Create Jira Bug" Triage Sayfası**

  **What to do**:
  - FastAPI/Javalin'de HTML template endpoint: `GET /reports/{runId}/triage`
  - Her fail senaryo için kart:
    - Scenario name, adımlar, hata mesajı, screenshot, video player
    - "Create Jira Bug" butonu → `POST /api/v1/runs/{runId}/scenarios/{scenarioId}/jira`
  - Jira bug preview (özet, açıklama wiki preview)
  - Mühendis onaylarsa → Jira API çağrısı → issue key göster
  - Web sunucu log'u: kim, ne zaman, hangi issue
  - **Test**: Playwright — butona tıkla, Jira mock response'u gör
  - **Test**: Snapshot test (baseline karşılaştırma)

  **Must NOT do**:
  - Onaysız Jira issue açma
  - Karmaşık workflow (sadece Bug tipi)

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: [`playwright`]

  **Parallelization**: Wave 3
  **Blocks**: None (final UI deliverable)
  **Blocked By**: Task 4, 5, 7

  **Acceptance Criteria**:
  - [ ] Playwright: navigate → `[data-testid="run-summary"]` görünür
  - [ ] Playwright: `[data-testid="create-jira-button"]` tıklanabilir
  - [ ] `POST /api/v1/runs/{runId}/scenarios/{scenarioId}/jira` → 201, `{"jiraKey": "PROJ-123"}`
  - [ ] Response: Jira issue key sayfada görünür

  **QA Scenarios**:
  ```
  Scenario: Create Jira Bug button triggers API call
    Tool: Playwright
    Preconditions: FastAPI running, WireMock Jira active
    Steps:
      1. page.goto('http://localhost:8000/reports/sample-run-001/triage')
      2. page.click('[data-testid="create-jira-button"]')
      3. page.waitForSelector('[data-testid="jira-key-display"]')
      4. assert page.textContent('[data-testid="jira-key-display"]') includes 'PROJ-'
    Expected Result: Jira issue key displayed after button click
    Evidence: .sisyphus/evidence/task-9-jira-ui.png

  Scenario: Triage page renders failure cards
    Tool: Playwright
    Steps:
      1. page.goto('http://localhost:8000/reports/sample-run-001/triage')
      2. assert page.locator('[data-testid="failure-card"]').count() > 0
    Expected Result: At least 1 failure card visible
    Evidence: .sisyphus/evidence/task-9-triage.png
  ```

  **Commit**: YES
  - Message: `feat(web): add Create Jira Bug triage page with Playwright tests`

---

- [ ] 10. **Orchestrator — Pipeline Stage Runner**

  **What to do**:
  - Maven module: `orchestrator`
  - Pipeline aşamaları (sıralı, her biri bağımsız fail):
    1. `TestRunner` → Cucumber çalıştır
    2. `AllureGenerator` → `allure generate`
    3. `ManifestWriter` → `manifests/{runId}.json`
    4. `WebDeployer` → manifest + report → web sunucu dizini
    5. `EmailSender` → özet email
    6. `JiraCreator` → (isteğe bağlı, triage UI'dan) → `POST /api/v1/runs/{runId}/scenarios/{scenarioId}/jira`
    7. `DoorsUpdater` → batch DXL
  - Her stage try-catch → non-critical fail → log + continue
  - Run manifest üretimi (pipeline başında)
  - CLI: `java -jar orchestrator.jar --run-id=auto`
  - **Test**: Mock stage'ler ile sıralı execution
  - **Test**: Non-critical fail → pipeline devam eder
  - **Test**: Critical fail → exit code ≠ 0

  **Must NOT do**:
  - Bir stage fail edince tüm pipeline'ı durdurma (non-critical'lar için)

  **Recommended Agent Profile**:
  - **Category**: `deep`

  **Parallelization**: Wave 3
  **Blocks**: Task 12
  **Blocked By**: Task 3, 6, 7, 8

  **Acceptance Criteria**:
  - [ ] `mvn -q -pl orchestrator test` → mock pipeline tüm stage'leri sırayla çalıştırır
  - [ ] Non-critical fail (DOORS) → pipeline exit 0, warning log
  - [ ] Critical fail (Allure) → pipeline exit ≠ 0
  - [ ] Run manifest `manifests/{runId}.json` oluşur
  - [ ] Her stage başlangıç/bitiş log'u

  **QA Scenarios**:
  ```
  Scenario: Pipeline runs all stages in order
    Tool: Bash (JUnit)
    Steps:
      1. mvn -q -pl orchestrator test -Dtest=PipelineTest#runAllStages
    Expected Result: BUILD SUCCESS, stage logs show sequential order
    Evidence: .sisyphus/evidence/task-10-pipeline.txt

  Scenario: DOORS failure doesn't stop pipeline
    Tool: Bash (JUnit)
    Steps:
      1. mvn -q -pl orchestrator test -Dtest=PipelineTest#nonCriticalFailure
    Expected Result: BUILD SUCCESS, DOORS stage logs warning, pipeline continues
    Evidence: .sisyphus/evidence/task-10-resilience.txt
  ```

  **Commit**: YES
  - Message: `feat(orchestrator): implement pipeline stage runner with resilience`

---

- [ ] 11. **Contract Test — FastAPI ↔ Javalin API Parity**

  **What to do**:
  - OpenAPI/Swagger spec (her iki sunucu için ortak)
  - Contract test: aynı test senaryoları her iki sunucuda çalışır
  - Response body yapısal eşitlik kontrolü
  - HTTP status code eşitliği
  - **Test**: pytest parametrize — aynı test, iki farklı base URL

  **Must NOT do**:
  - Manuel karşılaştırma

  **Recommended Agent Profile**:
  - **Category**: `quick`

  **Parallelization**: Wave 3
  **Blocks**: None
  **Blocked By**: Task 4, 5

  **Acceptance Criteria**:
  - [ ] `pytest contract-tests/ -v --base-url-fastapi=http://localhost:8000 --base-url-javalin=http://localhost:8080` → all pass
  - [ ] Tüm endpoint'ler her iki sunucuda 200 döner
  - [ ] Response JSON key set identical

  **QA Scenarios**:
  ```
  Scenario: Both servers return identical run list structure
    Tool: Bash (pytest)
    Steps:
      1. pytest contract-tests/test_api_parity.py::test_runs_endpoint -v
    Expected Result: 1 passed
    Evidence: .sisyphus/evidence/task-11-contract.txt
  ```

  **Commit**: YES
  - Message: `test(contract): add FastAPI ↔ Javalin API parity contract tests`

---

- [ ] 12. **CI/CD Pipeline (Jenkins / GitHub Actions)**

  **What to do**:
  - Pipeline dosyası: `Jenkinsfile` veya `.github/workflows/test-report.yml`
  - Trigger: cron (günlük), manual, SCM poll
  - Stages:
    1. Checkout + Java/Python setup
    2. `mvn clean test` (Cucumber testleri)
    3. `allure generate`
    4. Web sunucuya deploy (manifest + report)
    5. Email notification
    6. Artifact archiving (Allure report + manifest)
  - Environment variables: SMTP, Jira PAT, DOORS path (Jenkins credentials / GitHub Secrets)
  - Failure handling: her stage sonucu görünür
  - Allure report Jenkins plugin veya GitHub Pages deploy
  - **Test**: Pipeline syntax validation
  - **Test**: Dry-run ile stage order doğrulama

  **Must NOT do**:
  - Credential'ları pipeline dosyasına hardcode

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`git-master`]

  **Parallelization**: Wave 3
  **Blocks**: None
  **Blocked By**: Task 10

  **Acceptance Criteria**:
  - [ ] `Jenkinsfile` parse valid (Jenkins Syntax Check)
  - [ ] Pipeline stages tanımlı: Checkout, Test, Report, Deploy, Notify
  - [ ] Tüm secret'lar `${CREDENTIAL_ID}` formatında
  - [ ] `allure report` archiving step mevcut

  **QA Scenarios**:
  ```
  Scenario: Jenkinsfile passes syntax validation
    Tool: Bash (curl)
    Steps:
      1. curl -s -X POST -H "Content-Type: application/xml" --data-binary @Jenkinsfile "https://jenkins.example.com/pipeline-model-converter/validate"
    Expected Result: JSON contains "result": "success" (or local lint check passes)
    Evidence: .sisyphus/evidence/task-12-jenkins.txt

  Scenario: Environment variables reference Jenkins credentials
    Tool: Bash (grep)
    Steps:
      1. grep -c 'credentials(' Jenkinsfile
    Expected Result: > 0 (credentials used)
    Evidence: .sisyphus/evidence/task-12-secrets.txt
  ```

  **Commit**: YES
  - Message: `ci: add Jenkinsfile / GitHub Actions pipeline for test-report automation`

---

- [ ] 13. **Allure Custom Tasarım + Email Branding**

  **What to do**:
  - `allure-custom-logo.svg` + `allure-custom.css` → Allure report override
  - Şirket renk paleti: CSS variables
  - Allure report index.html wrapper (minimal, marka renkleri)
  - Email template final: responsive, Gmail/Outlook uyumlu (inline CSS)
  - Logo CID embedding
  - **Test**: Playwright — Allure report sayfası yüklenir
  - **Test**: Playwright snapshot — logo görünür, renkler doğru
  - **Test**: Email Litmus/Email on Acid veya Playwright screenshot (Gmail web)

  **Must NOT do**:
  - Allure internal JS/CSS modify (sadece official override mekanizması)
  - Manuel "güzel görünüyor" onayı

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: [`playwright`]

  **Parallelization**: Wave 3
  **Blocks**: None
  **Blocked By**: Task 1, 6

  **Acceptance Criteria**:
  - [ ] Playwright: `target/allure-report/index.html` → `[data-testid="total-counter"]` görünür
  - [ ] Playwright: CSS `--brand-primary` değişkeni uygulanmış
  - [ ] Playwright: custom logo `img[src*="logo"]` yüklenir
  - [ ] Email: Playwright screenshot → baseline diff < threshold

  **QA Scenarios**:
  ```
  Scenario: Allure report shows custom branding
    Tool: Playwright
    Steps:
      1. page.goto('file://target/allure-report/index.html')
      2. page.waitForSelector('img[src*="logo"]')
      3. screenshot = page.screenshot()
    Expected Result: Logo visible in screenshot
    Evidence: .sisyphus/evidence/task-13-branding.png

  Scenario: Email renders correctly in Gmail-like viewport
    Tool: Playwright (viewport: 600x800, Gmail user-agent)
    Steps:
      1. page.setContent(emailHtml)
      2. page.waitForSelector('table[role="presentation"]')
      3. assert page.locator('img[src*="cid:logo"]').count() > 0
    Expected Result: Table layout intact, inline logo visible
    Evidence: .sisyphus/evidence/task-13-email.png
  ```

  **Commit**: YES
  - Message: `style(allure,email): add custom brand colors + logo with Playwright visual tests`

---

## 9. Final Verification Wave

> 4 review agents in PARALLEL. ALL must APPROVE. Present results, get explicit user OK.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Her "Must Have" için implementasyon kontrolü; her "Must NOT Have" için codebase taraması. Evidence dosyaları `.sisyphus/evidence/` altında mevcut mu?
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  `mvn clean verify` + `pytest` + linter. `as any`/`@ts-ignore`, empty catch, console.log, commented-out code, unused imports kontrolü.
  Output: `Build [PASS/FAIL] | Tests [N pass/N fail] | VERDICT`

- [ ] F3. **Real QA Execution** — `unspecified-high` (+ `playwright`)
  Temiz state'ten başla. Tüm task'lardaki QA senaryolarını çalıştır. Cross-task integration test. Edge cases: empty state, invalid input, rapid actions.
  Output: `Scenarios [N/N pass] | Integration [N/N] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  Her task için "What to do" vs actual diff karşılaştırması. 1:1 mapping. "Must NOT do" compliance. Cross-task contamination tespiti.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | VERDICT`

---

## 10. Commit Strategy

Tüm commit'ler Conventional Commits formatında: `type(scope): mesaj`. Her task sonunda 1 commit. Pre-commit: `mvn -q test -pl <module>` (sadece ilgili modül).

---

## 11. Success Criteria

### Verification Commands
```bash
# Full build
mvn clean verify && pytest fastapi-server/tests -v

# Allure report
allure generate --clean target/allure-results -o target/allure-report
test -f target/allure-report/index.html

# Web servers
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/runs | python3 -m json.tool
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/v1/runs | python3 -m json.tool

# Email (GreenMail test)
mvn -q -pl email-service test

# Jira (WireMock test)
mvn -q -pl jira-service test

# Video validation
ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of default=noprint_wrappers=1:nokey=1 failed-scenario.mp4
# Expected: 15/1

# CI/CD
jenkinsfile-validator Jenkinsfile  # or: act -W .github/workflows/test-report.yml
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All tests pass (`mvn clean verify` + `pytest`)
- [ ] All QA scenarios produce evidence in `.sisyphus/evidence/`
- [ ] CI/CD pipeline runs successfully
- [ ] No hardcoded credentials in repo
- [ ] Zero manual/human verification steps
