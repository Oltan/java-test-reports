# Test Raporlama ve Yönetim Sistemi v2

## TL;DR

> **Quick Summary**: Java test-core (Cucumber Selenium + Allure) korunur, diğer Java modülleri kaldırılır. FastAPI (Python) tüm pipeline yönetimini, canlı test takibini, Jira/Email/DOORS entegrasyonunu üstlenir. DuckDB ile rapor verisi yönetilir. TFS pipeline tetiklenir.
>
> **Deliverables**:
> - Temizlenmiş Java projesi (3 modül: test-core, allure-integration, report-model)
> - FastAPI pipeline orchestrator (TFS trigger + subprocess)
> - FastAPI dashboard (WebSocket canlı takip, Chart.js, sürüm/tarih raporu)
> - DuckDB migration (JSON manifest → DuckDB)
> - Python Jira client (atlassian-python-api)
> - Python email service (smtplib + Jinja2)
> - DOORS subprocess entegrasyonu (Windows)
>
> **Estimated Effort**: Large (~8-10 gün)
> **Parallel Execution**: YES — 6 wave, 3-5 task/wave
> **Critical Path**: F1 Temizlik → F2 DuckDB → F3 Pipeline → F4 Dashboard → F6 CI/CD

---

## Context

### Original Request
Selenium Cucumber test sonuçlarını otomatik raporlayan, CI/CD'de çalışan, web'den yönetilebilen, canlı test takibi yapabilen, Jira ve DOORS entegrasyonlu bir sistem. Mevcut projeyi sadeleştirip modernize etme.

### Interview Summary
**Key Discussions**:
- Java tarafı sadeleştirilecek: 8 modül → 3 modül (test-core, allure-integration, report-model)
- Kaldırılacak: jira-service, email-service, doors-service, extent-integration, orchestrator, surefirePlugin-master
- Raporlama: Allure kalsın (TFS uyumlu, unit test raporlarıyla aynı formatta)
- FastAPI: TFS pipeline tetikleme, WebSocket canlı takip, Pydantic opsiyon validasyonu
- Database: DuckDB (pip install duckdb, analitik sorgular için optimize)
- TFS (Azure DevOps Server): Mevcut pipeline'a Selenium testleri eklenecek
- Tüm bilgisayarlar Windows — DOORS direkt subprocess ile çağrılabilir

**Research Findings**:
- DuckDB: GROUP BY/aggregation'da SQLite'dan 30x hızlı, JSON import tek satır
- Azure DevOps REST API: PAT auth ile pipeline tetikleme
- FastAPI WebSocket: Canlı test durumu için ideal
- test-core'da retry ve @id/@dep core özellikleri zaten var

### Technical Decisions
| Karar | Seçim | Gerekçe |
|-------|-------|---------|
| **Raporlama** | Allure | TFS uyumlu, cucumber adapter otomatiği |
| **Backend** | FastAPI (Python) | WebSocket, Pydantic, BackgroundTasks |
| **Database** | DuckDB | OLAP optimize, JSON import, pip install |
| **Jira** | Python atlassian-python-api | PAT auth, Server/DC/Cloud |
| **Email** | Python smtplib + Jinja2 | Java bağımlılığını azalt |
| **DOORS** | subprocess doors.exe (Windows) | Tüm PC'ler Windows, agent gerekmez |
| **Pipeline** | FastAPI BackgroundTasks zinciri | Orchestrator kaldırıldı |
| **CI/CD** | Azure DevOps (TFS) REST API | Mevcut pipeline'a entegre |

### Metis Review — Database Design Gaps (Fixed)
| # | Metis Bulgusu | Aksiyon |
|---|--------------|---------|
| M1 | `scenarios` tablosu yanlış — her satır "execution result" olmalı, ayrıca `scenario_definitions` gerekli | ✅ `scenario_results` + `scenario_definitions` eklendi |
| M2 | DOORS numarası primary key olarak kullanılmamalı | ✅ Opsiyonel external mapping, `scenario_uid` internal identity |
| M3 | Cross-run scenario identity için stabil ID yok | ✅ `scenario_uid` = `feature_file:feature_line` fallback, gelecekte `@id:` tag |
| M4 | DuckDB `AUTOINCREMENT` çalışmaz | ✅ `CREATE SEQUENCE ... DEFAULT nextval(...)` |
| M5 | `bug-tracker.json` için ayrı `bug_mappings` tablosu yok | ✅ Eklendi |
| M6 | Migration idempotency garantisi yok | ✅ `migration_imports` tablosu + checksum validasyonu |
| M7 | Flaky detection için index stratejisi eksik | ✅ `idx_results_scenario_run` eklendi |

---

## Work Objectives

### Core Objective
Mevcut Java projesini sadeleştirip, FastAPI tabanlı modern bir test yönetim ve raporlama sistemi kurmak.

### Concrete Deliverables
- Temizlenmiş Maven projesi (3 modül)
- DuckDB veritabanı + JSON migration script
- FastAPI pipeline orchestrator (TFS trigger + subprocess + pipeline chain)
- FastAPI dashboard (WebSocket canlı takip, Chart.js, sürüm/tarih raporu)
- Python Jira client
- Python email service
- DOORS subprocess entegrasyonu
- TFS pipeline YAML (Selenium test step'i)
- surefirePlugin-master silinmiş

### Definition of Done
- `mvn -q validate` → BUILD SUCCESS (sadece 3 modül)
- `uvicorn server:app` → FastAPI port 8000'de çalışır
- DuckDB import: 23 mevcut manifest başarıyla import edilir
- TFS pipeline tetikleme: REST API ile çalışır
- WebSocket: canlı test durumu güncellenir
- Email: Jinja2 template ile gönderilir
- DOORS: subprocess ile doors.exe çağrılır
- surefirePlugin-master/ dizini yok

### Must Have
- Allure raporları (mevcut gibi)
- FastAPI dashboard (canlı takip, sürüm/tarih raporu)
- Çoklu test başlatma + Pydantic validasyonlu opsiyon yönetimi
- TFS pipeline tetikleme
- DuckDB migration

### Must NOT Have (Guardrails)
- ExtentReports KALDIRILACAK
- Java Jira/Email/DOORS modülleri KALDIRILACAK
- Orchestrator KALDIRILACAK
- Database (PostgreSQL/MySQL) YOK — DuckDB yeterli
- RBAC / user management YOK — sadece admin JWT
- Otomatik Jira bug YOK — yarı otomatik

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed.

### Test Decision
- **Infrastructure exists**: YES (JUnit 5, pytest, Playwright)
- **Automated tests**: Tests-after (existing infrastructure)
- **Framework**: JUnit 5 (Java), pytest (Python), Playwright (UI)

### QA Policy
Every task MUST include agent-executed QA scenarios.

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Temizlik — 5 task paralel):
├── Task 1: Java modüllerini kaldır (jira, email, doors, extent, orchestrator)
├── Task 2: surefirePlugin-master script'lerini kopyala + dizini sil
├── Task 3: POM güncelleme + build doğrulama
├── Task 4: DuckDB schema + migration script
└── Task 5: Python proje yapısı (poetry/requirements)

Wave 2 (Pipeline + Entegrasyon — 4 task):
├── Task 6: FastAPI pipeline orchestrator (BackgroundTasks zinciri)
├── Task 7: TFS REST API client
├── Task 8: Jira Python client (atlassian-python-api)
└── Task 9: Email Python service (smtplib + Jinja2)

Wave 3 (Dashboard — 4 task):
├── Task 10: WebSocket canlı test takibi
├── Task 11: Chart.js dashboard (sürüm/tarih raporu, public/private)
├── Task 12: Pydantic opsiyon validasyonu + çoklu test başlatma
└── Task 13: DOORS subprocess entegrasyonu

Wave 4 (CI/CD — 2 task):
├── Task 14: TFS pipeline YAML (Selenium test step'i)
└── Task 15: Entegrasyon testleri + uçtan uca doğrulama

Wave FINAL (After ALL tasks — Review):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real QA execution (unspecified-high)
└── Task F4: Scope fidelity check (deep)
```

### Critical Path
Wave 1 (T1-T5) → Wave 2 (T6) → Wave 3 (T10) → Wave 4 (T15) → F1-F4

---

## TODOs

- [x] 1. **Java Modüllerini Kaldır**

  **What to do**:
  - Parent `pom.xml` module listesinden kaldırılacak modüller: `jira-service`, `email-service`, `doors-service`, `extent-integration`, `orchestrator`
  - Bu modüllerin dizinlerini `git rm -rf` ile sil
  - Kalan modülleri doğrula: `test-core`, `allure-integration`, `report-model`
  - `test-core/pom.xml`'den `extent-integration` bağımlılığını kaldır
  - `test-core/cucumber.properties`'ten ExtentReports plugin referansını kaldır
  - `test-core/src/test/java/com/testreports/runner/CucumberTestRunner.java` ve `RetryTestRunner.java`'dan `com.testreports.extent` import'larını kaldır
  - `allure-integration/` bağımlılıklarını kontrol et (sadece Allure)
  - `.gitignore` güncelle

  **Must NOT do**:
  - test-core, allure-integration, report-model kaynak koduna (Java business logic) dokunma
  - POM, cucumber.properties, extent referanslı import satırları değişiklikleri İZİNLİ (yapılandırma)
  - Allure Cucumber adapter'ını kaldırma

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`git-master`]
  - **Reason**: File deletion + POM editing

  **Parallelization**:
  - **Can Run In Parallel**: YES (Wave 1, with T2, T3, T4, T5)
  - **Blocks**: T6 (pipeline)
  - **Blocked By**: None

  **References**:
  - parent `pom.xml` — module list
  - `test-core/pom.xml` — extent-integration dependency
  - `test-core/src/test/resources/cucumber.properties` — plugin list

  **Acceptance Criteria**:
  - [ ] `mvn -q validate` → BUILD SUCCESS (3 modules)
  - [ ] `mvn -q -pl test-core test` → PASS
  - [ ] Dizinler silinmiş: jira-service, email-service, doors-service, extent-integration, orchestrator

  **QA Scenarios**:
  ```
  Scenario: Build verification after module removal
    Tool: Bash
    Steps:
      1. export PATH="/home/ol_ta/tools/apache-maven-3.9.9/bin:$PATH"
      2. mvn -q validate
      3. ls pom.xml && grep module pom.xml | wc -l
    Expected Result: BUILD SUCCESS, exactly 3 modules listed
    Evidence: .sisyphus/evidence/task-1-build.txt

  Scenario: Test execution
    Tool: Bash
    Steps:
      1. mvn -q -pl test-core test
    Expected Result: Tests pass without ExtentReports errors
    Evidence: .sisyphus/evidence/task-1-test.txt
  ```

  **Commit**: YES
  - Message: `chore: remove legacy Java modules (jira, email, doors, extent, orchestrator)`
  - Files: `pom.xml`, `test-core/pom.xml`, `test-core/cucumber.properties`, deleted dirs

- [x] 2. **surefirePlugin-master Temizliği**

  **What to do**:
  - Kopyala: `surefirePlugin-master/run-by-tags.ps1` → `scripts/run-by-tags.ps1`
  - Kopyala: `surefirePlugin-master/run-by-tag.sh` → `scripts/run-by-tag.sh`
  - Script'lerdeki path'leri güncelle (`surefirePlugin-master/` → `test-core/`)
  - `surefirePlugin-master/` dizinini `git rm -rf` ile sil
  - Core retry ve @id/@dep zaten test-core'da var — doğrula
  - `scripts/` dizininde eski referans kontrolü

  **Must NOT do**:
  - Core retry/dependency logic'e dokunma (test-core'da zaten var)
  - Eski ExtentCucumberPlugin'i kopyalama

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`git-master`]
  - **Reason**: File copy + delete

  **Parallelization**:
  - **Can Run In Parallel**: YES (Wave 1, with T1, T3, T4, T5)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `surefirePlugin-master/run-by-tags.ps1` — source
  - `surefirePlugin-master/run-by-tag.sh` — source
  - `scripts/` — target
  - `test-core/src/test/java/com/testreports/runner/RetryTestRunner.java` — verify exists
  - `test-core/src/test/java/com/testreports/runner/DependencyResolver.java` — verify exists

  **Acceptance Criteria**:
  - [ ] `scripts/run-by-tags.ps1` ve `scripts/run-by-tag.sh` mevcut
  - [ ] surefirePlugin-master/ dizini silinmiş
  - [ ] `test -d surefirePlugin-master/` → yok
  - [ ] `mvn -q -pl test-core test -Dcucumber.filter.tags="@retry"` → PASS

  **QA Scenarios**:
  ```
  Scenario: Directory deletion
    Tool: Bash
    Steps:
      1. test -d surefirePlugin-master/ && echo "FAIL" || echo "PASS"
    Expected Result: PASS (directory gone)
    Evidence: .sisyphus/evidence/task-2-deleted.txt

  Scenario: Script verification
    Tool: Bash
    Steps:
      1. head -5 scripts/run-by-tags.ps1
      2. head -5 scripts/run-by-tag.sh
    Expected Result: Contains "test-core", not "surefirePlugin-master"
    Evidence: .sisyphus/evidence/task-2-scripts.txt
  ```

  **Commit**: YES
  - Message: `chore: remove surefirePlugin-master, migrate scripts to scripts/`
  - Files: `scripts/run-by-tags.ps1`, `scripts/run-by-tag.sh`, deleted `surefirePlugin-master/`

- [x] 3. **POM ve Build Doğrulama**

  **What to do**:
  - Parent `pom.xml` temizliğini tamamla
  - `test-core/pom.xml` bağımlılıklarını sadeleştir:
    - `extent-integration` bağımlılığını kaldır
    - Sadece `allure-integration`, `report-model` kalsın
  - `allure-integration/pom.xml` kontrolü
  - `report-model/pom.xml` kontrolü
  - `mvn clean verify` ile full build + test

  **Must NOT do**:
  - Allure bağımlılıklarını kırma

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - **Reason**: POM editing + build validation

  **Parallelization**:
  - **Can Run In Parallel**: YES (Wave 1, with T1, T2, T4, T5)
  - **Blocks**: T6 (pipeline)
  - **Blocked By**: T1 (modüller kaldırıldıktan sonra)

  **References**:
  - parent `pom.xml`
  - `test-core/pom.xml`
  - `allure-integration/pom.xml`
  - `report-model/pom.xml`

  **Acceptance Criteria**:
  - [ ] `mvn -q clean verify` → BUILD SUCCESS
  - [ ] All tests pass
  - [ ] POM'da sadece 3 module

  **QA Scenarios**:
  ```
  Scenario: Full build verification
    Tool: Bash
    Steps:
      1. export PATH="/home/ol_ta/tools/apache-maven-3.9.9/bin:$PATH"
      2. mvn -q clean verify
    Expected Result: BUILD SUCCESS, all tests pass
    Evidence: .sisyphus/evidence/task-3-verify.txt
  ```

  **Commit**: YES
  - Message: `build: simplify POM to 3 modules (test-core, allure, report-model)`
  - Files: `pom.xml`, `test-core/pom.xml`

- [x] 4. **DuckDB Schema + Migration Script**

  **What to do**:
  - `pip install duckdb` (requirements.txt ekle)
  - DuckDB schema tasarla (Metis onaylı):
    ```sql
    -- Run metadata (her test koşumu)
    CREATE TABLE runs (
      id TEXT PRIMARY KEY,
      version TEXT,
      environment TEXT,
      started_at TIMESTAMP,
      finished_at TIMESTAMP,
      total_scenarios INTEGER,
      passed INTEGER,
      failed INTEGER,
      skipped INTEGER,
      visibility TEXT DEFAULT 'internal',
      source_manifest_file TEXT,
      source_manifest_hash TEXT,
      imported_at TIMESTAMP DEFAULT current_timestamp
    );

    -- Stabil senaryo kimliği (cross-run identity)
    CREATE TABLE scenario_definitions (
      scenario_uid TEXT PRIMARY KEY,
      identity_source TEXT NOT NULL,       -- 'feature_line' | 'doors_number' | 'explicit_tag'
      identity_key TEXT NOT NULL,          -- 'features/login.feature:42' | 'DOORS-12345'
      current_name TEXT,
      current_feature_file TEXT,
      current_feature_line INTEGER,
      doors_number TEXT,                   -- opsiyonel, Jira dedup için
      first_seen_run_id TEXT,
      last_seen_run_id TEXT,
      first_seen_at TIMESTAMP,
      last_seen_at TIMESTAMP,
      active BOOLEAN DEFAULT true
    );

    -- Her run'daki senaryo sonucu
    CREATE SEQUENCE scenario_result_id_seq START 1;
    CREATE TABLE scenario_results (
      id BIGINT PRIMARY KEY DEFAULT nextval('scenario_result_id_seq'),
      run_id TEXT NOT NULL REFERENCES runs(id),
      scenario_uid TEXT REFERENCES scenario_definitions(scenario_uid),
      name_at_run TEXT NOT NULL,
      status TEXT NOT NULL CHECK (status IN ('PASSED', 'FAILED', 'SKIPPED', 'BROKEN', 'UNKNOWN')),
      duration_seconds DOUBLE,
      error_message TEXT,
      feature_file_at_run TEXT,
      feature_line_at_run INTEGER,
      doors_number_at_run TEXT,
      jira_key_at_run TEXT,
      screenshot_path TEXT,
      video_path TEXT,
      retry_attempt INTEGER DEFAULT 1,
      source_manifest_file TEXT,
      source_manifest_hash TEXT,
      imported_at TIMESTAMP DEFAULT current_timestamp
    );

    -- DOORS → Jira bug eşleme (bug-tracker.json migrasyonu)
    CREATE TABLE bug_mappings (
      doors_number TEXT PRIMARY KEY,
      jira_key TEXT NOT NULL,
      jira_status TEXT,
      source TEXT DEFAULT 'bug-tracker.json',
      first_seen_at TIMESTAMP DEFAULT current_timestamp,
      updated_at TIMESTAMP DEFAULT current_timestamp
    );

    -- Migration audit trail (idempotent import)
    CREATE TABLE migration_imports (
      id TEXT PRIMARY KEY,
      source_file TEXT NOT NULL,
      source_hash TEXT NOT NULL,
      status TEXT NOT NULL,
      started_at TIMESTAMP,
      finished_at TIMESTAMP,
      rows_imported INTEGER,
      error_message TEXT
    );

    -- Pipeline stage durumu
    CREATE TABLE pipeline_status (
      run_id TEXT REFERENCES runs(id),
      stage TEXT NOT NULL,
      status TEXT NOT NULL,
      started_at TIMESTAMP,
      finished_at TIMESTAMP,
      error_message TEXT,
      PRIMARY KEY (run_id, stage)
    );

    -- İndeksler (flaky detection + dashboard performansı)
    CREATE INDEX idx_runs_started_at ON runs(started_at);
    CREATE INDEX idx_runs_version ON runs(version);
    CREATE INDEX idx_runs_version_started_at ON runs(version, started_at);
    CREATE INDEX idx_results_run_id ON scenario_results(run_id);
    CREATE INDEX idx_results_scenario_uid ON scenario_results(scenario_uid);
    CREATE INDEX idx_results_status ON scenario_results(status);
    CREATE INDEX idx_results_doors_number ON scenario_results(doors_number_at_run);
    CREATE INDEX idx_results_scenario_run ON scenario_results(scenario_uid, run_id);
    CREATE INDEX idx_bug_mappings_jira_key ON bug_mappings(jira_key);
    ```
  - Migration script: `fastapi-server/migrate_json_to_duckdb.py`
  - Migration stratejisi (adım adım):
    1. `bug-tracker.json` → `bug_mappings` tablosuna import
    2. Her `manifests/*.json` için: checksum hesapla → `runs` insert → her senaryo için `scenario_uid` hesapla → `scenario_definitions` upsert → `scenario_results` insert
    3. `scenario_uid` hesaplama (öncelik sırası):
       - `feature_file:feature_line` (örn: `features/login.feature:42`)
       - DOORS numarası varsa ek kimlik olarak
       - Gelecekte `@id:` tag'i kullanılabilir
    4. Aynı `run_id` + aynı checksum → skip (idempotent)
    5. Aynı `run_id` + farklı checksum → abort + hata bildir
    6. Her import `migration_imports` tablosuna kaydet
  - `run-aliases.json` → `runs` tablosunda version/alias olarak sakla

  **Must NOT do**:
  - Eski JSON'ları silme (archive olarak kalsın)
  - Allure sonuçlarına dokunma

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []
  - **Reason**: Database design + migration script

  **Parallelization**:
  - **Can Run In Parallel**: YES (Wave 1, with T1, T2, T3, T5)
  - **Blocks**: T10 (dashboard), T11 (dashboard queries)
  - **Blocked By**: None

  **References**:
  - `fastapi-server/models.py` — existing RunManifest Pydantic model
  - `manifests/*.json` — source data
  - `fastapi-server/bug_tracker.py` — existing bug tracker logic
  - DuckDB docs: `https://duckdb.org/docs/api/python/overview`

  **Acceptance Criteria**:
  - [ ] DuckDB schema oluşturuldu (6 tablo: runs, scenario_definitions, scenario_results, bug_mappings, migration_imports, pipeline_status)
  - [ ] 23 mevcut manifest import edildi
  - [ ] `SELECT COUNT(*) FROM runs` → 23
  - [ ] `SELECT COUNT(*) FROM scenario_results` → manifest'lerdeki toplam senaryo sayısı
  - [ ] `SELECT COUNT(*) FROM bug_mappings` → `bug-tracker.json`'daki entry sayısı
  - [ ] Import idempotent: 2. kez çalıştırınca row sayıları DEĞİŞMEZ
  - [ ] Aynı run_id + farklı checksum → hata verir
  - [ ] DOORS numarası olmayan senaryolar da import edilir

  **QA Scenarios**:
  ```
  Scenario: DuckDB schema creation
    Tool: Bash
    Steps:
      1. cd fastapi-server && python3 -c "
         import duckdb
         conn = duckdb.connect('reports.duckdb')
         tables = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' ORDER BY name\").fetchall()
         print(tables)"
    Expected Result: ['bug_mappings', 'migration_imports', 'pipeline_status', 'runs', 'scenario_definitions', 'scenario_results'] listed
    Evidence: .sisyphus/evidence/task-4-schema.txt

  Scenario: JSON migration + idempotency
    Tool: Bash
    Steps:
      1. cd fastapi-server && python3 migrate_json_to_duckdb.py
      2. python3 -c "
         import duckdb; conn = duckdb.connect('reports.duckdb')
         r = conn.execute('SELECT COUNT(*) FROM runs').fetchone()
         s = conn.execute('SELECT COUNT(*) FROM scenario_results').fetchone()
         b = conn.execute('SELECT COUNT(*) FROM bug_mappings').fetchone()
         print(f'runs={r[0]} scenarios={s[0]} bugs={b[0]}')"
      3. cd fastapi-server && python3 migrate_json_to_duckdb.py  # 2. kez
      4. python3 -c "..." # Aynı sorgu
    Expected Result: 1. ve 2. çalıştırmada AYNI sayılar (idempotent)
    Evidence: .sisyphus/evidence/task-4-migration.txt
  ```

  **Commit**: YES
  - Message: `feat: DuckDB schema + JSON migration script`
  - Files: `fastapi-server/requirements.txt`, `fastapi-server/db.py`, `fastapi-server/migrate_json_to_duckdb.py`

- [x] 5. **Python Proje Yapısı (FastAPI)**

  **What to do**:
  - `fastapi-server/requirements.txt` güncelle:
    ```
    fastapi==0.115.*
    uvicorn[standard]==0.34.*
    duckdb==1.2.*
    atlassian-python-api==3.41.*
    jinja2==3.1.*
    pydantic==2.*
    httpx==0.28.*
    websockets==13.*
    python-dotenv==1.*
    ```
  - `pip install -r requirements.txt`
  - FastAPI proje yapısı:
    ```
    fastapi-server/
    ├── server.py          # Ana FastAPI app (mevcut, güncellenecek)
    ├── db.py              # DuckDB bağlantı + sorgular
    ├── pipeline.py        # Pipeline orchestrator
    ├── tfs_client.py      # Azure DevOps REST client
    ├── jira_client.py     # atlassian-python-api wrapper
    ├── email_service.py   # smtplib + Jinja2
    ├── doors_service.py   # subprocess doors.exe
    ├── models.py          # Pydantic modeller (mevcut, güncellenecek)
    ├── templates/         # Jinja2 email + dashboard HTML
    ├── static/            # CSS, JS (chart.js)
    └── tests/             # pytest testleri
    ```
  - Mevcut `server.py`'yi yeni yapıya hazırla

  **Must NOT do**:
  - Mevcut çalışan endpoint'leri kırma
  - `templates/dashboard.html` silme

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - **Reason**: Project scaffolding

  **Parallelization**:
  - **Can Run In Parallel**: YES (Wave 1, with T1, T2, T3, T4)
  - **Blocks**: T6-T13
  - **Blocked By**: None

  **References**:
  - `fastapi-server/server.py` — mevcut app
  - `fastapi-server/models.py` — mevcut Pydantic modeller
  - `fastapi-server/requirements.txt` — mevcut bağımlılıklar

  **Acceptance Criteria**:
  - [ ] `pip install -r requirements.txt` → success
  - [ ] `python -c "import fastapi, duckdb, atlassian, jinja2"` → no errors

  **QA Scenarios**:
  ```
  Scenario: Dependency installation
    Tool: Bash
    Steps:
      1. cd fastapi-server && pip install -r requirements.txt
    Expected Result: All packages installed successfully
    Evidence: .sisyphus/evidence/task-5-pip.txt

  Scenario: Import verification
    Tool: Bash
    Steps:
      1. cd fastapi-server && python3 -c "
         import fastapi
         import duckdb
         import jinja2
         import pydantic
         print('ALL IMPORTS OK')"
    Expected Result: ALL IMPORTS OK
    Evidence: .sisyphus/evidence/task-5-import.txt
  ```

  **Commit**: YES
  - Message: `build: update FastAPI project structure and dependencies`
  - Files: `fastapi-server/requirements.txt`

- [x] 6. **FastAPI Pipeline Orchestrator**

  **What to do**:
  - `fastapi-server/pipeline.py` oluştur
  - Pipeline stage chain:
    1. `ManifestWriteStage` → `run-manifest.json` yaz
    2. `AllureGenerateStage` → `subprocess.run(["allure", "generate"])`
    3. `JiraCreateStage` → Jira bug aç (non-critical)
    4. `DoorsUpdateStage` → `subprocess.run(["doors.exe", ...])` (non-critical)
    5. `EmailSendStage` → Jinja2 template ile email
  - `BackgroundTasks` ile tüm stage'leri zincirleme çalıştır
  - Stage durumlarını DuckDB'de `pipeline_status` tablosunda takip et
  - `critical` vs `non-critical` stage ayrımı
  - `/api/pipeline/run` endpoint'i
  - `/api/pipeline/status/{run_id}` endpoint'i

  **Must NOT do**:
  - Stage'leri blocking yapma (async/background kullan)
  - Hardcoded paths

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []
  - **Reason**: Complex async orchestration

  **Parallelization**:
  - **Can Run In Parallel**: NO (Wave 2)
  - **Blocks**: T10 (dashboard), T15 (integration test)
  - **Blocked By**: T1, T4, T5

  **References**:
  - `orchestrator/src/main/java/com/testreports/orchestrator/PipelineRunner.java` — existing logic (silindikten sonra `git show HEAD~1:orchestrator/...` ile eriş)
  - `orchestrator/src/main/java/com/testreports/orchestrator/PipelineConfig.java` — config pattern (git show ile)
  - FastAPI docs: BackgroundTasks

  **Acceptance Criteria**:
  - [ ] `/api/pipeline/run` → pipeline başlar, job_id döner
  - [ ] `/api/pipeline/status/{job_id}` → stage durumları döner
  - [ ] DuckDB'de `pipeline_status` tablosu güncellenir
  - [ ] Non-critical stage hatası pipeline'ı durdurmaz

  **QA Scenarios**:
  ```
  Scenario: Pipeline run trigger
    Tool: Bash (curl)
    Steps:
      1. curl -X POST http://localhost:8000/api/pipeline/run -H "Authorization: Bearer $TOKEN" -d '{"run_id":"test-001"}' -H "Content-Type: application/json"
    Expected Result: 200, {"status": "started", "job_id": "..."}
    Evidence: .sisyphus/evidence/task-6-pipeline-run.txt

  Scenario: Pipeline status check
    Tool: Bash (curl)
    Steps:
      1. curl http://localhost:8000/api/pipeline/status/test-001 -H "Authorization: Bearer $TOKEN"
    Expected Result: 200, {"job_id":"...", "stages": [...]}
    Evidence: .sisyphus/evidence/task-6-pipeline-status.txt
  ```

  **Commit**: YES
  - Message: `feat: FastAPI pipeline orchestrator`
  - Files: `fastapi-server/pipeline.py`, `fastapi-server/server.py`, `fastapi-server/db.py`

- [x] 7. **TFS REST API Client**

  **What to do**:
  - `fastapi-server/tfs_client.py` oluştur
  - Azure DevOps REST API wrapper:
    ```python
    class TFSClient:
        def trigger_pipeline(self, pipeline_id, variables): ...
        def get_run_status(self, pipeline_id, run_id): ...
        def get_run_logs(self, pipeline_id, run_id): ...
    ```
  - PAT auth: Base64 encode + Basic Auth header
  - Pipeline trigger payload: `variables` ve `templateParameters`
  - Environment variables: `AZURE_ORG_URL`, `AZURE_PROJECT`, `AZURE_PAT`
  - Webhook callback: TFS pipeline tamamlanınca FastAPI'ye bildirim
  - `/api/tfs/trigger` endpoint'i
  - `/api/tfs/webhook` endpoint'i (TFS'den callback al)

  **Must NOT do**:
  - PAT'ı hardcode etme (`.env` kullan)
  - Pipeline ID'yi hardcode etme

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []
  - **Reason**: External API integration

  **Parallelization**:
  - **Can Run In Parallel**: YES (Wave 2, with T8, T9)
  - **Blocks**: T15 (integration test)
  - **Blocked By**: T1, T5

  **References**:
  - Azure DevOps REST API docs: pipelines/runs
  - Mevcut `Jenkinsfile` → pipeline yapısı
  - `.env.example` (root) — ortam değişkenleri

  **Acceptance Criteria**:
  - [ ] TFS pipeline tetiklenebiliyor
  - [ ] Pipeline değişkenleri gönderilebiliyor (tags, retry-count)
  - [ ] Pipeline durumu sorgulanabiliyor
  - [ ] Webhook callback işleniyor

  **QA Scenarios**:
  ```
  Scenario: TFS pipeline trigger
    Tool: Bash (curl)
    Steps:
      1. curl -X POST http://localhost:8000/api/tfs/trigger -H "Authorization: Bearer $TOKEN" -d '{"pipeline_id":1,"variables":{"CUCUMBER_TAGS":"@smoke"}}' -H "Content-Type: application/json"
    Expected Result: 200, {"run_id": "...", "status": "queued"}
    Evidence: .sisyphus/evidence/task-7-tfs-trigger.txt
  ```

  **Commit**: YES
  - Message: `feat: Azure DevOps REST API client`
  - Files: `fastapi-server/tfs_client.py`, `fastapi-server/server.py`

- [x] 8. **Jira Python Client**

  **What to do**:
  - Mevcut `fastapi-server/jira_client.py`'yi `atlassian-python-api` ile güçlendir
  - Özellikler:
    - Create issue (bug) with wiki-renderer description
    - Create issue with attachment (screenshot)
    - Search issues by DOORS number (custom field)
    - Get issue status
    - Add comment to existing issue
  - PAT auth (Basic Auth base64)
  - Dry-run mode (`--jira.dry-run=true`)
  - Retry with backoff (3 attempts)
  - Environment variables: `JIRA_URL`, `JIRA_PAT`, `JIRA_PROJECT_KEY`
  - `/api/jira/create-bug` endpoint'i

  **Must NOT do**:
  - Java Jira client'ı kopyalama (Java kaldırıldı)
  - ADF formatı kullanma (wiki-renderer kullan)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []
  - **Reason**: External API + auth

  **Parallelization**:
  - **Can Run In Parallel**: YES (Wave 2, with T7, T9)
  - **Blocks**: T15 (integration test)
  - **Blocked By**: T1, T5

  **References**:
  - `fastapi-server/jira_client.py` — mevcut lightweight client
  - `jira-service/src/main/java/com/testreports/jira/JiraClient.java` — feature reference (git show ile, sadece oku)
  - `.env.example` (root) — Jira env vars

  **Acceptance Criteria**:
  - [ ] `create_issue()` → Jira'da bug oluşur
  - [ ] `search_by_doors_number()` → mevcut bug'ları bulur
  - [ ] Screenshot attachment çalışır
  - [ ] Dry-run mode çalışır

  **QA Scenarios**:
  ```
  Scenario: Jira bug creation
    Tool: Bash (curl)
    Steps:
      1. curl -X POST http://localhost:8000/api/jira/create-bug -H "Authorization: Bearer $TOKEN" -d '{"summary":"Test bug","doors_number":"DOORS-12345"}' -H "Content-Type: application/json"
    Expected Result: 200, {"key": "PROJ-123", "status": "Open"}
    Evidence: .sisyphus/evidence/task-8-jira-create.txt
  ```

  **Commit**: YES
  - Message: `feat: Python Jira client with atlassian-python-api`
  - Files: `fastapi-server/jira_client.py`

- [x] 9. **Email Python Service**

  **What to do**:
  - `fastapi-server/email_service.py` oluştur
  - Jinja2 HTML template: `templates/emails/test_report.html`
    - Özet: pass/fail/skip sayıları, süre, tarih
    - Link: FastAPI dashboard'a direkt link
    - Responsive tasarım (mevcut Thymeleaf template'inden ilham al)
  - `smtplib` ile gönderim:
    ```python
    def send_email(to, subject, template_name, context):
        template = env.get_template(template_name)
        html = template.render(**context)
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
    ```
  - Environment variables: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`
  - `/api/email/send` endpoint'i (pipeline içinden çağrılacak)

  **Must NOT do**:
  - Java Thymeleaf template'ini birebir kopyalama (Jinja2 farklı)
  - Email'i blocking yapma

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - **Reason**: Template + SMTP

  **Parallelization**:
  - **Can Run In Parallel**: YES (Wave 2, with T7, T8)
  - **Blocks**: T15 (integration test)
  - **Blocked By**: T1, T5

  **References**:
  - `email-service/src/main/resources/templates/` — existing Thymeleaf templates (design reference)
  - Jinja2 docs: template inheritance
  - `.env.example` (root)

  **Acceptance Criteria**:
  - [ ] Jinja2 template render ediliyor
  - [ ] Email gönderiliyor (smtplib)
  - [ ] Dashboard linki doğru

  **QA Scenarios**:
  ```
  Scenario: Email send
    Tool: Bash (curl)
    Steps:
      1. curl -X POST http://localhost:8000/api/email/send -H "Authorization: Bearer $TOKEN" -d '{"to":"test@example.com","run_id":"test-001"}' -H "Content-Type: application/json"
    Expected Result: 200, {"sent": true}
    Evidence: .sisyphus/evidence/task-9-email.txt
  ```

  **Commit**: YES
  - Message: `feat: Python email service with Jinja2 + smtplib`
  - Files: `fastapi-server/email_service.py`, `fastapi-server/templates/emails/test_report.html`

- [x] 10. **WebSocket Canlı Test Takibi**

  **What to do**:
  - `fastapi-server/websocket_handler.py` oluştur
  - WebSocket endpoint: `/ws/test-status/{run_id}`
  - Maven test çıktısını parse et (subprocess stdout streaming):
    ```python
    async def stream_test_output(run_id):
        proc = await asyncio.create_subprocess_exec(
            "mvn", "-pl", "test-core", "test", ...
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        async for line in proc.stdout:
            # Parse: "Scenario: Login test — PASSED"
            status = parse_cucumber_line(line.decode())
            await broadcast(run_id, status)
    ```
  - Dashboard'da canlı güncelleme:
    - ✅ Login test — PASSED (2.3s)
    - 🔄 Search test — RUNNING (5.1s)
    - ❌ Checkout test — FAILED (timeout)
    - Progress bar: %67 tamamlandı
  - DuckDB'de `live_status` tablosu (test bitince `scenarios` tablosuna taşınır)

  **Must NOT do**:
  - WebSocket'i blocking yapma
  - Polling kullanma (push-based olsun)

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: []
  - **Reason**: Real-time UI + streaming

  **Parallelization**:
  - **Can Run In Parallel**: NO (Wave 3, after Wave 2)
  - **Blocks**: T15 (integration test)
  - **Blocked By**: T6 (pipeline)

  **References**:
  - FastAPI WebSocket docs
  - `test-core/src/test/java/com/testreports/runner/CucumberTestRunner.java` — test output format
  - DuckDB docs: INSERT

  **Acceptance Criteria**:
  - [ ] WebSocket bağlantısı kuruluyor
  - [ ] Test durumu anlık güncelleniyor
  - [ ] Dashboard'da canlı progress bar
  - [ ] Test bitince `scenarios` tablosuna yazılıyor

  **QA Scenarios**:
  ```
  Scenario: WebSocket live tracking
    Tool: Bash (websocat or python websocket)
    Steps:
     1. python3 -c "
        import asyncio, websockets
        async def test():
            async with websockets.connect('ws://localhost:8000/ws/test-status/test-001') as ws:
                for i in range(3):
                    msg = await ws.recv()
                    print(msg)
        asyncio.run(test())"
    Expected Result: Real-time scenario status messages received
    Evidence: .sisyphus/evidence/task-10-websocket.txt
  ```

  **Commit**: YES
  - Message: `feat: WebSocket live test tracking`
  - Files: `fastapi-server/websocket_handler.py`, `fastapi-server/server.py`

- [x] 11. **Chart.js Dashboard + Sürüm/Tarih Raporu**

  **What to do**:
  - `fastapi-server/templates/dashboard.html` overhaul:
    - Chart.js pie chart: pass/fail/skip dağılımı
    - Chart.js bar chart: sürüm bazlı test sonuçları
    - Metric cards: success rate, total runs, avg duration, flaky count
    - Dark theme (opsiyonel toggle)
  - Sürüm dropdown: `SELECT DISTINCT version FROM runs ORDER BY version DESC`
  - Tarih picker: Flatpickr ile saat hassasiyetinde aralık seçimi
  - "Rapor Oluştur" butonu: seçili sürüm/tarih aralığını filtrele
  - Public/Private ayrımı:
    - `/dashboard` → JWT required (admin)
    - `/reports/{run_id}` → Public, token gerekmez
    - `visibility` tag'i ile filtre (DuckDB: `WHERE visibility = 'public'`)
  - DuckDB sorguları:
    ```sql
    -- Sürüm bazlı aggregation
    SELECT version, COUNT(*) as runs, SUM(passed) as total_passed
    FROM runs WHERE version = ? GROUP BY version;

    -- Tarih aralığı (saat hassasiyetinde)
    SELECT * FROM runs WHERE started_at BETWEEN ? AND ?;

    -- Flaky test tespiti (cross-run identity ile)
    SELECT
      sr.scenario_uid,
      sd.current_name,
      COUNT(*) AS executions,
      SUM(CASE WHEN sr.status = 'PASSED' THEN 1 ELSE 0 END) AS passed_count,
      SUM(CASE WHEN sr.status = 'FAILED' THEN 1 ELSE 0 END) AS failed_count
    FROM scenario_results sr
    JOIN runs r ON sr.run_id = r.id
    LEFT JOIN scenario_definitions sd ON sr.scenario_uid = sd.scenario_uid
    WHERE r.started_at >= current_timestamp - INTERVAL '30 days'
    GROUP BY sr.scenario_uid, sd.current_name
    HAVING passed_count > 0 AND failed_count > 0
    ORDER BY (CAST(failed_count AS FLOAT) / executions) DESC;
    ```

  **Must NOT do**:
  - Chart.js CDN kullanma (local bundle yap)
  - Hardcoded veri

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: []
  - **Reason**: UI/UX + Chart.js + DuckDB queries

  **Parallelization**:
  - **Can Run In Parallel**: NO (Wave 3)
  - **Blocks**: T15 (integration test)
  - **Blocked By**: T4 (DuckDB), T10 (WebSocket)

  **References**:
  - `fastapi-server/templates/dashboard.html` — existing dashboard
  - `fastapi-server/static/chart.min.js` — existing Chart.js
  - DuckDB docs: date functions, aggregation

  **Acceptance Criteria**:
  - [ ] Pie chart: pass/fail/skip
  - [ ] Bar chart: sürüm bazlı
  - [ ] Tarih picker: Flatpickr, saat hassasiyeti
  - [ ] Sürüm dropdown: tüm sürümler listelenir
  - [ ] `/reports/{run_id}` → public erişim
  - [ ] `/dashboard` → JWT gerekli

  **QA Scenarios**:
  ```
  Scenario: Dashboard rendering
    Tool: Playwright
    Steps:
      1. Navigate to http://localhost:8000/dashboard
      2. Wait for pie chart to render (canvas element visible)
      3. Select version from dropdown
      4. Click date picker, select range
      5. Click "Rapor Oluştur"
    Expected Result: Charts render, filters work, report generated
    Evidence: .sisyphus/evidence/task-11-dashboard.png

  Scenario: Public report access
    Tool: Playwright
    Steps:
      1. Navigate to http://localhost:8000/reports/test-001
    Expected Result: Report visible without login
    Evidence: .sisyphus/evidence/task-11-public.png
  ```

  **Commit**: YES
  - Message: `feat: Chart.js dashboard with version/date filtering and public/private`
  - Files: `fastapi-server/templates/dashboard.html`, `fastapi-server/static/`, `fastapi-server/server.py`

- [x] 12. **Opsiyon Validasyonu + Çoklu Test Başlatma**

  **What to do**:
  - Pydantic model: `TestRunOptions`
    ```python
    class TestRunOptions(BaseModel):
        tags: str = Field(default="@smoke", pattern=r"^@[\w,]+$")
        retry_count: int = Field(default=0, ge=0, le=10)
        browser: str = Field(default="chrome", pattern=r"^(chrome|firefox|edge)$")
        parallel: int = Field(default=1, ge=1, le=5)
        environment: str = Field(default="staging", pattern=r"^(staging|prod|dev)$")
        notify_email: Optional[str] = None
        version: Optional[str] = None
        visibility: str = Field(default="internal", pattern=r"^(internal|public)$")
    ```
  - `/api/tests/start` endpoint'i:
    - Pydantic validasyon → yanlış input'u engelle
    - `BackgroundTasks` ile paralel test başlatma
    - Birden fazla `run_id` döndür
  - `/api/tests/running` → şu anda çalışan testleri listele
  - `/api/tests/{run_id}/cancel` → testi iptal et (subprocess kill)
  - Kubernetes olmadan da çalışabilmeli (salt Python threading)

  **Must NOT do**:
  - Validasyonsuz test başlatma (Pydantic zorunlu)
  - Thread pool overflow (max parallel limit)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []
  - **Reason**: Pydantic validation + concurrent execution

  **Parallelization**:
  - **Can Run In Parallel**: YES (Wave 3, with T13)
  - **Blocks**: T15 (integration test)
  - **Blocked By**: T6 (pipeline)

  **References**:
  - `test-core/src/test/java/com/testreports/runner/CucumberTestRunner.java` — accepted parameters
  - FastAPI BackgroundTasks docs
  - Pydantic docs: Field validators

  **Acceptance Criteria**:
  - [ ] Geçersiz tag → 400 error
  - [ ] Geçersiz retry_count (>10) → 400 error
  - [ ] 3 paralel test → 3 run_id döner
  - [ ] `/api/tests/running` → çalışan testleri listeler
  - [ ] `/api/tests/{run_id}/cancel` → test durur

  **QA Scenarios**:
  ```
  Scenario: Invalid options rejected
    Tool: Bash (curl)
    Steps:
      1. curl -X POST http://localhost:8000/api/tests/start -d '{"tags":"invalid_tag","retry_count":99}' -H "Content-Type: application/json"
    Expected Result: 422 Validation Error (tags must start with @, retry_count > 10)
    Evidence: .sisyphus/evidence/task-12-validation.txt

  Scenario: Parallel test launch
    Tool: Bash (curl)
    Steps:
      1. curl -X POST http://localhost:8000/api/tests/start -d '{"parallel":3,"tags":"@smoke"}' -H "Content-Type: application/json"
    Expected Result: 200, {"runs": ["id1","id2","id3"]}
    Evidence: .sisyphus/evidence/task-12-parallel.txt
  ```

  **Commit**: YES
  - Message: `feat: Pydantic test options validation + multi-test launch`
  - Files: `fastapi-server/models.py`, `fastapi-server/server.py`

- [x] 13. **DOORS Subprocess Entegrasyonu**

  **What to do**:
  - `fastapi-server/doors_service.py` oluştur
  - Basit subprocess wrapper (Windows):
    ```python
    import subprocess, tempfile
    def run_doors_dxl(script_content: str, doors_path: str = r"C:\Program Files\IBM\DOORS\9.7\bin\doors.exe"):
        with tempfile.NamedTemporaryFile(suffix=".dxl", delete=False) as f:
            f.write(script_content.encode())
        result = subprocess.run([doors_path, "-b", f.name], capture_output=True, text=True)
        return result.returncode, result.stdout, result.stderr
    ```
  - `/api/doors/run` endpoint'i
  - Pipeline'da non-critical stage olarak çağrılır
  - DOORS yoksa graceful skip (opsiyonel)
  - DuckDB'de `doors_number` → Jira bug mapping

  **Must NOT do**:
  - DOORS'u zorunlu yapma (opsiyonel)
  - Linux'ta çalışmasını bekleme

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - **Reason**: Simple subprocess wrapper

  **Parallelization**:
  - **Can Run In Parallel**: YES (Wave 3, with T12)
  - **Blocks**: T15 (integration test)
  - **Blocked By**: T1, T5

  **References**:
  - `doors-service/src/main/java/` — existing logic reference
  - `fastapi-server/bug_tracker.py` — DOORS-Jira mapping

  **Acceptance Criteria**:
  - [ ] `doors.exe` varsa çalışır
  - [ ] `doors.exe` yoksa graceful skip
  - [ ] DOORS numarası DuckDB'ye yazılır

  **QA Scenarios**:
  ```
  Scenario: DOORS subprocess call
    Tool: Bash (curl)
    Steps:
      1. curl -X POST http://localhost:8000/api/doors/run -d '{"script":"// DXL test"}' -H "Content-Type: application/json"
    Expected Result: 200 (or 200 with "doors not available" if not on Windows)
    Evidence: .sisyphus/evidence/task-13-doors.txt
  ```

  **Commit**: YES
  - Message: `feat: DOORS subprocess integration`
  - Files: `fastapi-server/doors_service.py`

---

- [x] 14. **TFS Pipeline YAML**

  **What to do**:
  - `pipeline-selenium.yml` oluştur (Azure DevOps pipeline)
  - Pipeline structure:
    ```yaml
    trigger: none  # Manuel tetikleme (FastAPI'den)
    pool: windows-latest  # Selenium için Windows agent
    
    parameters:
      - name: CUCUMBER_TAGS
        type: string
        default: "@smoke"
      - name: RETRY_COUNT
        type: number
        default: 0
    
    steps:
      - task: Maven@4
        inputs:
          mavenPOMFile: 'pom.xml'
          goals: 'test'
          options: '-pl test-core -Dcucumber.filter.tags=$(CUCUMBER_TAGS)'
      - script: |
          allure generate --clean test-core/target/allure-results -o test-core/target/allure-report
        displayName: 'Generate Allure Report'
      - task: PublishBuildArtifacts@1
        inputs:
          PathtoPublish: 'test-core/target/allure-report'
          ArtifactName: 'allure-report'
    ```
  - FastAPI'den tetikleme: `variables` ile CUCUMBER_TAGS ve RETRY_COUNT gönder
  - Allure report → build artifacts olarak publish

  **Must NOT do**:
  - Pipeline'da hardcoded path
  - GitHub Actions syntax kullanma (Azure DevOps syntax)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - **Reason**: YAML pipeline definition

  **Parallelization**:
  - **Can Run In Parallel**: NO (Wave 4)
  - **Blocks**: T15 (integration test)
  - **Blocked By**: T3 (build verified)

  **References**:
  - Mevcut `Jenkinsfile` — pipeline structure reference
  - Azure DevOps pipeline YAML schema

  **Acceptance Criteria**:
  - [ ] `pipeline-selenium.yml` valid YAML
  - [ ] Maven test step'i doğru
  - [ ] Allure generate step'i doğru
  - [ ] Artifacts publish step'i doğru

  **QA Scenarios**:
  ```
  Scenario: Pipeline YAML validation
    Tool: Bash
    Steps:
      1. python3 -c "import yaml; yaml.safe_load(open('pipeline-selenium.yml'))"
    Expected Result: Valid YAML, no parse errors
    Evidence: .sisyphus/evidence/task-14-yaml.txt
  ```

  **Commit**: YES
  - Message: `ci: Azure DevOps pipeline YAML for Selenium tests`
  - Files: `pipeline-selenium.yml`

- [x] 15. **Entegrasyon Testleri + Uçtan Uca Doğrulama**

  **What to do**:
  - pytest test suite:
    - `test_pipeline.py`: Pipeline orchestrator testleri
    - `test_tfs_client.py`: TFS API mock testleri
    - `test_jira_client.py`: Jira API mock testleri
    - `test_email_service.py`: Email template + SMTP mock testleri
    - `test_websocket.py`: WebSocket bağlantı testleri
    - `test_dashboard.py`: FastAPI TestClient ile dashboard endpoint testleri
  - FastAPI TestClient ile uçtan uca:
    - Pipeline trigger → status check
    - Test start (geçerli/geçersiz opsiyonlar)
    - Dashboard render
    - Public report access
  - `fastapi-server/tests/conftest.py`: Test fixtures (DuckDB in-memory, mock clients)

  **Must NOT do**:
  - Gerçek TFS/Jira/SMTP'ye bağlanma (mock kullan)
  - Eski Java test'lerini kopyalama

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []
  - **Reason**: Comprehensive test suite

  **Parallelization**:
  - **Can Run In Parallel**: NO (Wave 4, after all features)
  - **Blocks**: F1-F4 (final verification)
  - **Blocked By**: T6-T13

  **References**:
  - `fastapi-server/tests/` — existing test directory
  - pytest docs: fixtures, async tests
  - FastAPI TestClient docs

  **Acceptance Criteria**:
  - [ ] `cd fastapi-server && python -m pytest tests/ -v` → ALL PASS
  - [ ] ≥80% code coverage on new code

  **QA Scenarios**:
  ```
  Scenario: Full pytest suite
    Tool: Bash
    Steps:
      1. cd fastapi-server && python -m pytest tests/ -v --tb=short
    Expected Result: All tests pass, 0 failures
    Evidence: .sisyphus/evidence/task-15-pytest.txt
  ```

  **Commit**: YES
  - Message: `test: integration tests for pipeline, TFS, Jira, email, WebSocket`
  - Files: `fastapi-server/tests/`

---

## Final Verification Wave

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [ ] F1. **Plan Compliance Audit** — `oracle`

  Read the plan end-to-end. For each "Must Have": verify implementation exists.
  - Java: 3 modules only (`mvn validate` output)
  - surefirePlugin-master/ deleted (`test -d surefirePlugin-master` → fail)
  - DuckDB schema + data migrated
  - FastAPI pipeline orchestrator working
  - WebSocket live tracking working
  - Chart.js dashboard rendering
  - TFS pipeline YAML valid
  - For each "Must NOT Have": search codebase — no ExtentReports, no Java Jira, no orchestrator
  - Check evidence files exist in `.sisyphus/evidence/`

  Output: `Must Have [8/8] | Must NOT Have [5/5] | Tasks [15/15] | VERDICT`

- [ ] F2. **Code Quality Review** — `unspecified-high`

  Run `export PATH="/home/ol_ta/tools/apache-maven-3.9.9/bin:$PATH" && mvn -q clean verify && cd fastapi-server && python -m pytest tests/ -v`.
  Review all changed files for:
  - Dead Java imports (removed modules)
  - Stale references (surefirePlugin-master, extent)
  - Hardcoded credentials
  - AI slop: excessive comments, generic variable names
  - Python: PEP8, type hints, async/await correctness

  Output: `Java Build [PASS/FAIL] | Python Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high` (+ `playwright` skill)

  Execute EVERY QA scenario from EVERY task — follow exact steps, capture evidence.
  Test cross-feature integration:
  - Pipeline trigger → WebSocket live update → Dashboard show result
  - Multi-test launch → all tests tracked independently
  - Invalid options → 422 error
  - Public report → accessible without auth
  Save evidence to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`

  For each task: read "What to do", read actual diff (git log/diff).
  Verify 1:1 — everything in spec was built, nothing beyond spec.
  Check "Must NOT do" compliance for every task.
  Detect cross-task contamination.
  Verify no ExtentReports, no Java orchestrator, no surefirePlugin-master references.
  Output: `Tasks [15/15 compliant] | Must NOT [15/15 compliant] | Contamination [CLEAN/N issues] | VERDICT`

---

## Commit Strategy

- Wave 1: `chore: remove legacy Java modules, merge surefirePlugin-master`
- Wave 2: `feat: FastAPI pipeline orchestrator, TFS client, Jira, Email`
- Wave 3: `feat: FastAPI dashboard — live tracking, Chart.js, multi-test`
- Wave 4: `feat: TFS pipeline YAML, integration tests`

## Success Criteria

### Verification Commands
```bash
export PATH="/home/ol_ta/tools/apache-maven-3.9.9/bin:$PATH"
mvn -q validate  # Expected: BUILD SUCCESS (3 modules only)
mvn -q -pl test-core test  # Expected: Tests pass
cd fastapi-server && python -m pytest tests/ -v  # Expected: Tests pass
```

### Final Checklist
- [ ] Java modülleri: sadece test-core, allure-integration, report-model
- [ ] surefirePlugin-master/ dizini silinmiş
- [ ] DuckDB import başarılı
- [ ] FastAPI WebSocket canlı takip çalışıyor
- [ ] TFS pipeline tetiklenebiliyor
- [ ] Email Jinja2 template ile gönderiliyor
- [ ] DOORS subprocess çağrılabiliyor
