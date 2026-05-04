# Test Çalıştırma Rehberi

## 1. Ön Gereksinimler

```bash
# Java 21
java -version

# Maven 3.9+
export PATH="/home/ol_ta/tools/apache-maven-3.9.9/bin:$PATH"
mvn -version

# Python 3.12+ (FastAPI server için)
python3 --version

# Allure CLI (opsiyonel, rapor görüntüleme için)
export PATH="$PATH:/home/ol_ta/tools/allure-2.33.0/bin"
allure --version

# ffmpeg (opsiyonel, video kaydı için)
ffmpeg -version
```

---

## 2. Yerel Test Çalıştırma (Maven)

### 2.1 Tüm Testleri Koş

```bash
cd /home/ol_ta/projects/java_reports
mvn -pl test-core test
```

### 2.2 Tag Filtresi ile Koş

```bash
# Sadece @smoke tag'li senaryolar
mvn -pl test-core test -Dcucumber.filter.tags="@smoke"

# @smoke VE @login tag'li senaryolar
mvn -pl test-core test -Dcucumber.filter.tags="@smoke and @login"

# @smoke VEYA @regression tag'li senaryolar
mvn -pl test-core test -Dcucumber.filter.tags="@smoke or @regression"

# @wip HARİÇ tüm senaryolar
mvn -pl test-core test -Dcucumber.filter.tags="not @wip"
```

### 2.3 Retry (Tekrar Deneme) ile Koş

```bash
mvn -pl test-core test -Dcucumber.filter.tags="@flaky" -Dretry.count=2
```

### 2.4 Allure Raporu Üret

```bash
# Testleri koş
mvn -pl test-core test

# Allure raporu oluştur
allure generate --clean test-core/target/allure-results -o test-core/target/allure-report

# Statik sunucu ile görüntüle
python3 -m http.server 8080 -d test-core/target/allure-report
```

**Allure sonuç dizini:** `test-core/target/allure-results/`

---

## 3. FastAPI Üzerinden Test Çalıştırma

### 3.1 Sunucuyu Başlat

```bash
cd /home/ol_ta/projects/java_reports/fastapi-server
pip install -r requirements.txt
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
```

### 3.2 API ile Test Başlat

```bash
# Login (token al)
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'

# Response: {"token": "eyJhbGciOiJIUzI1NiIs..."}

# Test başlat
curl -X POST http://localhost:8000/api/tests/start \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
  -d '{
    "tags": "@smoke",
    "retry_count": 0,
    "browser": "chrome",
    "parallel": 1,
    "environment": "staging",
    "version": "v1.2.3",
    "visibility": "internal"
  }'
```

### 3.3 WebSocket ile Canlı İzleme

Test çalışırken WebSocket üzerinden canlı ilerleme alınabilir:

```javascript
const ws = new WebSocket("ws://localhost:8000/ws/test-status/{run_id}?token={jwt_token}");

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(`İlerleme: ${data.pct}%`);
  console.log(`Passed: ${data.passed}, Failed: ${data.failed}, Skipped: ${data.skipped}`);
  console.log(`Çalışan senaryolar: ${data.scenarios.map(s => s.name)}`);
};
```

WebSocket mesaj formatı:

```json
{
  "run_id": "test-abc123",
  "total": 10,
  "passed": 5,
  "failed": 2,
  "skipped": 1,
  "running": 2,
  "pct": 80,
  "type": "progress",
  "scenarios": [
    {"name": "Login test", "status": "passed"},
    {"name": "Dashboard test", "status": "failed"}
  ]
}
```

### 3.4 Test Çalışma Akışı

```
1. POST /api/tests/start
   → jobs tablosuna kayıt
   → worker_runs tablosuna kayıt
   → Maven subprocess başlat

2. WebSocket yayını
   → Scenario adımları parsing
   → PASSED/FAILED/SKIPPED sayaçları güncellenir
   → pct (yüzde) hesaplanır

3. Test tamamlandığında
   → allure-results/ parse edilir
   → DuckDB runs tablosuna kayıt
   → DuckDB scenario_results tablosuna kayıtlar
   → DuckDB scenario_history tablosuna aggregate kayıt
   → manifests/{run_id}.json yazılır
   → worker_runs status = completed
   → jobs status = completed (tüm worker'lar bittiyse)
```

---

## 4. Başka Projeye Taşıma

### 4.1 Hedef Proje Yapısı

```
your-project/
├── pom.xml                    # Parent POM
├── test-automation/           # Test modülü (test-core yerine)
│   ├── pom.xml
│   ├── src/
│   │   ├── test/
│   │   │   ├── java/
│   │   │   │   └── com/company/
│   │   │   │       ├── runner/CucumberTestRunner.java
│   │   │   │       ├── steps/               # Step definitions
│   │   │   │       └── hooks/               # Cucumber hooks
│   │   │   └── resources/
│   │   │       ├── features/                # .feature dosyaları
│   │   │       ├── cucumber.properties
│   │   │       ├── allure.properties
│   │   │       └── junit-platform.properties
│   │   └── main/
│   │       └── java/
│   │           └── com/company/
│   │               └── pages/               # Page Object Model
├── allure-integration/        # Bu repodan kopyala
├── report-model/              # Bu repodan kopyala
└── fastapi-server/            # Bu repodan kopyala (opsiyonel)
```

### 4.2 Gerekli Bağımlılıklar (pom.xml)

```xml
<properties>
    <java.version>21</java.version>
    <maven.compiler.source>21</maven.compiler.source>
    <maven.compiler.target>21</maven.compiler.target>
    <cucumber.version>7.18.0</cucumber.version>
    <selenium.version>4.21.0</selenium.version>
    <junit.version>5.10.2</junit.version>
    <allure.version>2.25.0</allure.version>
    <jackson.version>2.17.1</jackson.version>
</properties>

<dependencies>
    <!-- Cucumber -->
    <dependency>
        <groupId>io.cucumber</groupId>
        <artifactId>cucumber-java</artifactId>
        <version>${cucumber.version}</version>
    </dependency>
    <dependency>
        <groupId>io.cucumber</groupId>
        <artifactId>cucumber-junit-platform-engine</artifactId>
        <version>${cucumber.version}</version>
    </dependency>

    <!-- Selenium -->
    <dependency>
        <groupId>org.seleniumhq.selenium</groupId>
        <artifactId>selenium-java</artifactId>
        <version>${selenium.version}</version>
    </dependency>

    <!-- JUnit 5 -->
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter-engine</artifactId>
        <version>${junit.version}</version>
    </dependency>
    <dependency>
        <groupId>org.junit.platform</groupId>
        <artifactId>junit-platform-suite</artifactId>
        <version>1.10.2</version>
    </dependency>

    <!-- Allure -->
    <dependency>
        <groupId>io.qameta.allure</groupId>
        <artifactId>allure-cucumber7-jvm</artifactId>
        <version>${allure.version}</version>
    </dependency>

    <!-- Jackson (manifest JSON için) -->
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
        <version>${jackson.version}</version>
    </dependency>
</dependencies>
```

### 4.3 Cucumber Runner

```java
package com.company.runner;

import org.junit.platform.suite.api.ConfigurationParameter;
import org.junit.platform.suite.api.IncludeEngines;
import org.junit.platform.suite.api.SelectClasspathResource;
import org.junit.platform.suite.api.Suite;

@Suite
@IncludeEngines("cucumber")
@SelectClasspathResource("features")
@ConfigurationParameter(key = "cucumber.plugin", value = "io.qameta.allure.cucumber7jvm.AllureCucumber7Jvm")
@ConfigurationParameter(key = "cucumber.publish.quiet", value = "true")
public class CucumberTestRunner {
}
```

### 4.4 Cucumber Properties

**`src/test/resources/cucumber.properties`:**

```properties
cucumber.publish.quiet=true
cucumber.plugin=io.qameta.allure.cucumber7jvm.AllureCucumber7Jvm
```

**`src/test/resources/allure.properties`:**

```properties
allure.results.directory=target/allure-results
```

### 4.5 DOORS Etiketleme

Feature dosyalarında DOORS gereksinim numarasını `@DOORS-NNNNN` formatında etiketle:

```gherkin
@smoke @login @DOORS-12345
Feature: Kullanıcı girişi

  @positive
  Scenario: Başarılı giriş
    Given kullanıcı login sayfasında
    When geçerli bilgilerle giriş yapar
    Then dashboard sayfası açılır

  @negative @DOORS-12346
  Scenario: Hatalı şifre
    Given kullanıcı login sayfasında
    When hatalı şifre girer
    Then hata mesajı görüntülenir
```

**Kurallar:**
- Her senaryoya bir DOORS numarası ver (opsiyonel ama önerilir)
- Format: `@DOORS-12345` (kesinlikle rakam)
- Feature seviyesindeki tag'ler tüm senaryolara miras kalır
- Parser `@DOORS-` sonrası sadece rakamları alır

### 4.6 Allure Hook'ları (Screenshot + Video)

**`allure-integration` modülünü bağımlılık olarak ekle:**

```xml
<dependency>
    <groupId>com.testreports</groupId>
    <artifactId>allure-integration</artifactId>
    <version>1.0.0-SNAPSHOT</version>
</dependency>
```

**Veya hook sınıflarını doğrudan kopyala:**

- `ScreenshotHook.java` — Başarısız senaryoda otomatik screenshot
- `VideoHook.java` — Başarısız senaryoda otomatik video kaydı
- `WebDriverHolder.java` — Thread-local WebDriver yönetimi

**`cucumber.properties`'ye glue ekle:**

```properties
cucumber.glue=com.company.steps,com.testreports.allure
```

### 4.7 Manifest Üretimi

Test koştuktan sonra Allure sonuçlarını manifest JSON'a çevir:

```java
import com.testreports.model.AllureResultsParser;
import com.testreports.model.ManifestWriter;
import com.testreports.model.RunManifest;

import java.nio.file.Path;
import java.nio.file.Paths;

public class ManifestGenerator {
    public static void main(String[] args) {
        Path allureResultsDir = Paths.get("target/allure-results");
        Path outputDir = Paths.get("manifests");

        // Allure sonuçlarını parse et
        AllureResultsParser parser = new AllureResultsParser(allureResultsDir);
        List<ScenarioResult> scenarios = parser.parse();

        // Manifest JSON yaz
        ManifestWriter writer = new ManifestWriter(outputDir);
        RunMetadata metadata = new RunMetadata(Instant.now(), Duration.ofMinutes(5));
        writer.write(scenarios, metadata);
    }
}
```

**Veya FastAPI otomatik yapar:**

Test FastAPI üzerinden (`POST /api/tests/start`) başlatılırsa, server otomatik olarak:
1. `allure-results/` dizinini parse eder
2. `manifests/{run_id}.json` dosyasını yazar
3. DuckDB'ye kayıt atar

### 4.8 FastAPI Server Kurulumu

```bash
# Repo'yu klonla
git clone https://github.com/Oltan/java-test-reports.git
cd java-test-reports/fastapi-server

# Bağımlılıkları kur
pip install -r requirements.txt

# .env dosyası oluştur
cp .env.example .env
# JIRA_URL, JIRA_PAT, JIRA_PROJECT_KEY doldur

# Sunucuyu başlat
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
```

**Ortam değişkenleri:**

```bash
# Jira entegrasyonu
JIRA_URL=https://jira.sirket.local
JIRA_PAT=your_personal_access_token
JIRA_PROJECT_KEY=TEST
JIRA_ISSUE_TYPE=Bug

# DuckDB
REPORTS_DUCKDB_PATH=reports.duckdb

# Manifest dizini
MANIFESTS_DIR=/path/to/your/project/manifests

# JWT
JWT_SECRET=your_secret_key_here
```

---

## 5. Test Sonuçlarını Görüntüleme

### 5.1 Dashboard (http://localhost:8000)

Giriş yaptıktan sonra:
- **Dashboard:** Tüm koşuların özeti, grafikler, trendler
- **Raporlar:** Run'ları karşılaştır, merge et
- **Triage:** Başarısız senaryoları yönet, Jira issue aç
- **Admin:** Test başlat, versiyon yönetimi

### 5.2 Public Raporlar

```bash
# Public rapor listesi (auth gerekmez)
curl http://localhost:8000/public/reports

# Tek public rapor (auth gerekmez)
curl http://localhost:8000/public/reports/{share_id}
```

### 5.3 API ile Sorgulama

```bash
# Tüm run'lar
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/runs

# Belirli bir run
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/runs/{run_id}

# Başarısız senaryolar
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/runs/{run_id}/failures

# Senaryo geçmişi (DOORS bazlı)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/scenario-history

# Matrix görünümü
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/scenario-matrix

# Dashboard metrikleri
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/dashboard/metrics
```

---

## 6. Sorun Giderme

### 6.1 "No tests found" Hatası

```bash
# Runner sınıfı doğru yerde mi?
ls src/test/java/**/CucumberTestRunner.java

# Surefire include ayarı kontrol et
mvn -pl test-core test -Dtest=CucumberTestRunner
```

### 6.2 Allure Sonuçları Boş

```bash
# cucumber.properties kontrol et
cat src/test/resources/cucumber.properties

# Allure plugin aktif mi?
cucumber.plugin=io.qameta.allure.cucumber7jvm.AllureCucumber7Jvm

# Sonuç dizini kontrol et
ls target/allure-results/
```

### 6.3 Screenshot/Video Çalışmıyor

```bash
# ffmpeg kurulu mu?
ffmpeg -version

# WebDriverHolder thread-local set edilmiş mi?
# Hook sınıfları glue'da tanımlı mı?
cucumber.glue=com.company.steps,com.testreports.allure
```

### 6.4 FastAPI Test Başlatılamıyor

```bash
# Maven PATH'de mi?
which mvn

# Maven executable yetkisi
ls -la /home/ol_ta/tools/apache-maven-3.9.9/bin/mvn

# Server log kontrolü
tail -f fastapi-server/server.log
```

### 6.5 DOORS Numarası Manifest'te Görünmüyor

```bash
# Tag formatı doğru mu?
# Doğru: @DOORS-12345
# Yanlış: @DOORS-ABC, @doors-12345, @DOORS12345

# Allure result JSON'unda labels kontrolü
cat target/allure-results/*-result.json | grep -i doors
```

---

## 7. Özet Komutlar

```bash
# Hızlı başlangıç
mvn -pl test-core test -Dcucumber.filter.tags="@smoke"

# Allure raporu
allure generate --clean test-core/target/allure-results -o test-core/target/allure-report

# FastAPI başlat
cd fastapi-server && python3 -m uvicorn server:app --host 0.0.0.0 --port 8000

# Manifest üret (Java CLI)
cd report-model && mvn exec:java -Dexec.mainClass="com.testreports.model.ManifestGenerator"

# DuckDB sorgula
cd fastapi-server && duckdb reports.duckdb "SELECT * FROM scenario_history LIMIT 5"
```
