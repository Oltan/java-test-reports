# Entegrasyon Rehberi

Bu rehber, başka bir Java, Cucumber ve Selenium projesinin bu raporlama sistemine bağlanması için yazıldı. Amaç basit: testler Allure sonucu üretsin, sonuçlar `run-manifest.json` dosyalarına çevrilsin, FastAPI dashboard bu manifestleri okusun, başarısız senaryolar DOORS etiketi ve Jira triage akışıyla takip edilsin.

Mevcut depo kökü:

```text
/home/ol_ta/projects/java_reports
```

Ana parçalar:

```text
test-core             Cucumber runner, Selenium step sınıfları
allure-integration   Screenshot, video, failure location hook sınıfları
report-model         Allure sonuç parser sınıfları, manifest modeli, manifest writer
fastapi-server       Dashboard, API, triage, Jira ve DOORS köprüleri
manifests            FastAPI tarafından okunan run manifest dosyaları
bug-tracker.json     DOORS numarası ve Jira issue eşleştirmesi
```

## 1. Quick Start

En kısa entegrasyon yolu:

1. Hedef projede Maven test modülüne Cucumber, Selenium, JUnit Platform ve Allure bağımlılıklarını ekleyin.
2. `allure-integration` modülünü bağımlılık olarak bağlayın veya içindeki hook sınıflarını hedef projeye kopyalayın.
3. `src/test/resources` altına `cucumber.properties`, `allure.properties` ve gerekiyorsa `junit-platform.properties` ekleyin.
4. Feature dosyalarında DOORS ilişkisini `@DOORS-NNNNN` etiketiyle yazın.
5. Testleri çalıştırıp `target/allure-results` üretin.
6. `report-model` içindeki parser ve writer ile manifest dosyasını `manifests/` dizinine yazın.
7. FastAPI sunucusuna `MANIFESTS_DIR` verip dashboardu açın.
8. Jira için önce dry run modunu kullanın, sonra gerçek Jira ortam değişkenlerini verin.

Mevcut depoda hızlı yerel koşu:

```bash
cd /home/ol_ta/projects/java_reports
export PATH="/home/ol_ta/tools/apache-maven-3.9.9/bin:$PATH"
export PATH="$PATH:/home/ol_ta/tools/allure-2.33.0/bin"
mvn -pl test-core test -Dcucumber.filter.tags="@sample-fail"
allure generate --clean test-core/target/allure-results -o test-core/target/allure-report
```

FastAPI dashboard:

```bash
cd /home/ol_ta/projects/java_reports/fastapi-server
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
```

Tarayıcı:

```text
http://localhost:8000
```

## 2. Maven config

### 2.1 Parent veya tek modül POM sürümleri

Hedef proje tek modüllüyse bu değerleri ana `pom.xml` içine koyun. Çok modüllü yapıda parent POM içinde tutun.

```xml
<properties>
    <java.version>21</java.version>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <maven.compiler.source>21</maven.compiler.source>
    <maven.compiler.target>21</maven.compiler.target>
    <cucumber.version>7.18.0</cucumber.version>
    <selenium.version>4.21.0</selenium.version>
    <junit.version>5.10.2</junit.version>
    <allure.version>2.25.0</allure.version>
    <jackson.version>2.17.1</jackson.version>
    <slf4j.version>2.0.13</slf4j.version>
</properties>
```

Java 17 kullanan ekipler `maven.compiler.source` ve `maven.compiler.target` değerlerini `17` yapabilir.

### 2.2 test-core benzeri modül bağımlılıkları

Mevcut örnek dosya:

```text
test-core/pom.xml
```

Hedef test modülü için temel bağımlılıklar:

```xml
<dependencies>
    <dependency>
        <groupId>io.cucumber</groupId>
        <artifactId>cucumber-java</artifactId>
    </dependency>
    <dependency>
        <groupId>io.cucumber</groupId>
        <artifactId>cucumber-junit-platform-engine</artifactId>
    </dependency>
    <dependency>
        <groupId>io.cucumber</groupId>
        <artifactId>cucumber-core</artifactId>
        <version>${cucumber.version}</version>
    </dependency>
    <dependency>
        <groupId>org.seleniumhq.selenium</groupId>
        <artifactId>selenium-java</artifactId>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter-api</artifactId>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter-engine</artifactId>
    </dependency>
    <dependency>
        <groupId>org.junit.platform</groupId>
        <artifactId>junit-platform-launcher</artifactId>
    </dependency>
    <dependency>
        <groupId>org.junit.platform</groupId>
        <artifactId>junit-platform-suite</artifactId>
    </dependency>
    <dependency>
        <groupId>io.qameta.allure</groupId>
        <artifactId>allure-cucumber7-jvm</artifactId>
        <exclusions>
            <exclusion>
                <groupId>io.cucumber</groupId>
                <artifactId>gherkin</artifactId>
            </exclusion>
        </exclusions>
    </dependency>
    <dependency>
        <groupId>com.testreports</groupId>
        <artifactId>allure-integration</artifactId>
        <version>1.0.0-SNAPSHOT</version>
    </dependency>
</dependencies>
```

Manifest üretmek için hedef projeye `report-model` modülünü de ekleyin:

```xml
<dependency>
    <groupId>com.testreports</groupId>
    <artifactId>report-model</artifactId>
    <version>1.0.0-SNAPSHOT</version>
</dependency>
```

### 2.3 Surefire ayarı

Mevcut parent POM içindeki Surefire ayarı `*TestRunner.java` ve `*Test.java` sınıflarını çalıştırır. Test modülünde sadece Cucumber runner çalıştırmak isterseniz:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <configuration>
                <includes>
                    <include>**/CucumberTestRunner.java</include>
                </includes>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Kontrol komutları:

```bash
cd /home/ol_ta/projects/java_reports
export PATH="/home/ol_ta/tools/apache-maven-3.9.9/bin:$PATH"
mvn validate
mvn -pl test-core test
```

## 3. Cucumber ve Allure setup

### 3.1 Cucumber runner

Mevcut runner:

```text
test-core/src/test/java/com/testreports/runner/CucumberTestRunner.java
```

Örnek:

```java
package com.company.project.runner;

import org.junit.platform.suite.api.ConfigurationParameter;
import org.junit.platform.suite.api.IncludeEngines;
import org.junit.platform.suite.api.SelectClasspathResource;
import org.junit.platform.suite.api.Suite;

import static io.cucumber.junit.platform.engine.Constants.GLUE_PROPERTY_NAME;
import static io.cucumber.junit.platform.engine.Constants.PLUGIN_PROPERTY_NAME;

@Suite
@IncludeEngines("cucumber")
@SelectClasspathResource("features")
@ConfigurationParameter(key = PLUGIN_PROPERTY_NAME, value = "io.qameta.allure.cucumber7jvm.AllureCucumber7Jvm,json:target/cucumber-report.json,pretty")
@ConfigurationParameter(key = GLUE_PROPERTY_NAME, value = "com.testreports.allure,com.company.project.steps")
public class CucumberTestRunner {
}
```

`com.testreports.allure` glue değeri, screenshot, video ve failure location hook sınıflarını Cucumber'a tanıtır. Hook sınıflarını kendi paketinize kopyalarsanız bu paketi değiştirin.

### 3.2 cucumber.properties

Mevcut dosya:

```text
test-core/src/test/resources/cucumber.properties
```

İçerik:

```properties
cucumber.publish.quiet=true
cucumber.plugin=io.qameta.allure.cucumber7jvm.AllureCucumber7Jvm,\
  com.testreports.allure.FailureLocationCapture,\
  json:target/cucumber-report.json,\
  pretty
cucumber.glue=com.testreports.allure,com.testreports.steps
```

Hedef projede step paketini değiştirin:

```properties
cucumber.glue=com.testreports.allure,com.company.project.steps
```

Tag filtresiyle koşu:

```bash
mvn test -Dcucumber.filter.tags="@smoke"
```

Mevcut depodaki örnek:

```bash
mvn -pl test-core test -Dcucumber.filter.tags="@sample-fail"
```

### 3.3 allure.properties

Mevcut dosya:

```text
test-core/src/test/resources/allure.properties
```

İçerik:

```properties
allure.results.directory=target/allure-results
```

Çok modüllü projede bu yol modülün `target` dizinine göre oluşur. Bu depoda sonuç dizini şudur:

```text
test-core/target/allure-results
```

Allure raporu üretme:

```bash
allure generate --clean test-core/target/allure-results -o test-core/target/allure-report
```

Tek modüllü hedef proje:

```bash
allure generate --clean target/allure-results -o target/allure-report
```

### 3.4 junit-platform.properties

Bu depoda ayrı `junit-platform.properties` dosyası yok, çünkü runner sınıfı `@ConfigurationParameter` ile gerekli ayarları veriyor. Hedef proje properties dosyasıyla yönetmek isterse şu dosyayı oluşturabilir:

```text
src/test/resources/junit-platform.properties
```

Örnek:

```properties
cucumber.glue=com.testreports.allure,com.company.project.steps
cucumber.plugin=io.qameta.allure.cucumber7jvm.AllureCucumber7Jvm,json:target/cucumber-report.json,pretty
cucumber.publish.quiet=true
```

Runner ve properties dosyasında aynı ayarları iki kez vermeyin. Birini ana kaynak seçin.

### 3.5 Screenshot, video ve WebDriverHolder

Hook sınıfları:

```text
allure-integration/src/main/java/com/testreports/allure/ScreenshotHook.java
allure-integration/src/main/java/com/testreports/allure/VideoHook.java
allure-integration/src/main/java/com/testreports/allure/WebDriverHolder.java
allure-integration/src/main/java/com/testreports/allure/FailureLocationCapture.java
```

Driver oluşturduktan sonra holder'a yazın:

```java
WebDriver driver = WebDriverFactory.createDriver();
com.testreports.allure.WebDriverHolder.setDriver(driver);
```

Test sonunda temizleyin:

```java
driver.quit();
com.testreports.allure.WebDriverHolder.removeDriver();
```

Screenshot sadece başarısız senaryoda eklenir. Video hook başarılı senaryoların videosunu siler, başarısız senaryonun videosunu Allure ekine koyar. `ffmpeg` yoksa test akışı durmaz, video kaydı atlanır.

## 4. DOORS tagging

Allure parser DOORS numarasını Cucumber tag listesinden okur. Beklenen biçim:

```text
@DOORS-NNNNN
```

Mevcut örnek:

```text
test-core/src/test/resources/features/login.feature
```

```gherkin
@DOORS-12345
@REQ-LOGIN-001
Feature: Login Feature

  @sample-fail
  Scenario: Hatalı giriş
    Given user is on the login page
    When user enters valid credentials
    Then user should see element that doesn't exist
```

Parser kuralı:

```java
private static final Pattern DOORS_TAG_PATTERN = Pattern.compile("@DOORS-(\\d+)", Pattern.CASE_INSENSITIVE);
```

Bu yüzden `@DOORS-12345` manifest içinde şu alana çevrilir:

```json
"doorsAbsNumber": "12345"
```

Triage ekranı ve bug tracker aynı değeri kullanır. Takım içinde tek biçim seçin, örnek olarak her senaryoya bir DOORS etiketi verin. Feature düzeyindeki etiketler Allure tarafından senaryolara taşınır.

## 5. FastAPI ingestion ve manifest dizini

FastAPI manifest dosyalarını JSON olarak okur. Varsayılan yol `server.py` içinde şu şekilde hesaplanır:

```python
MANIFESTS_DIR = Path(os.getenv("MANIFESTS_DIR", str(Path(__file__).parent.parent / "manifests")))
```

Mevcut depo varsayılan dizini:

```text
/home/ol_ta/projects/java_reports/manifests
```

Başka bir proje manifestlerini okutmak için:

```bash
export MANIFESTS_DIR="/path/to/your/project/manifests"
cd /home/ol_ta/projects/java_reports/fastapi-server
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
```

Python bağımlılıkları:

```bash
cd /home/ol_ta/projects/java_reports
python3 -m pip install --upgrade pip
pip install -r fastapi-server/requirements.txt
```

API kontrolü:

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

curl http://localhost:8000/api/v1/runs \
  -H "Authorization: Bearer TOKEN_DEGERI"
```

Üretim benzeri kullanımda `ADMIN_USERNAME`, `ADMIN_PASSWORD` ve `JWT_SECRET` değerlerini ortam değişkeni veya `.env` ile verin. Gerçek şifre veya token dosyaya yazmayın.

### 5.1 Manifest üretme

`report-model` şu iki sınıfı sağlar:

```text
report-model/src/main/java/com/testreports/model/AllureResultsParser.java
report-model/src/main/java/com/testreports/model/ManifestWriter.java
```

Hedef projede test sonrası çalışan küçük bir sınıf veya Maven exec adımı ile Allure sonuçlarını manifeste çevirin:

```java
package com.company.project.reporting;

import com.testreports.model.AllureResultsParser;
import com.testreports.model.ManifestWriter;
import com.testreports.model.ScenarioResult;

import java.nio.file.Path;
import java.time.Instant;
import java.util.List;

public class WriteRunManifest {
    public static void main(String[] args) throws Exception {
        Path allureResults = Path.of(args.length > 0 ? args[0] : "target/allure-results");
        Path manifests = Path.of(args.length > 1 ? args[1] : "manifests");
        List<ScenarioResult> scenarios = new AllureResultsParser(allureResults).parse();
        String runId = new ManifestWriter(manifests).write(
                scenarios,
                new ManifestWriter.RunMetadata(Instant.now(), null)
        );
        System.out.println("Manifest written: " + runId);
    }
}
```

Çok modüllü mevcut depo için sonuç ve manifest yolları:

```bash
java -cp "target/classes:target/dependency/*" com.company.project.reporting.WriteRunManifest \
  test-core/target/allure-results \
  manifests
```

Tek modüllü hedef proje için:

```bash
java -cp "target/classes:target/dependency/*" com.company.project.reporting.WriteRunManifest \
  target/allure-results \
  manifests
```

Manifest alanları FastAPI modeliyle uyumlu olmalıdır:

```json
{
  "runId": "20260503-120000-a1b2c3",
  "timestamp": "2026-05-03T12:00:00Z",
  "totalScenarios": 1,
  "passed": 0,
  "failed": 1,
  "skipped": 0,
  "duration": "PT12S",
  "scenarios": [
    {
      "id": "scenario-001",
      "name": "Hatalı giriş",
      "status": "failed",
      "duration": "PT12S",
      "doorsAbsNumber": "12345",
      "tags": ["@DOORS-12345", "@sample-fail"],
      "steps": [],
      "attachments": []
    }
  ]
}
```

## 6. Jira mapping ve triage workflow

Jira tarafı FastAPI içinden `fastapi-server/jira_client.py` ile çalışır. Desteklenen ortam değişkenleri:

```text
JIRA_URL=https://jira.example.local
JIRA_PAT=PERSONAL_ACCESS_TOKEN_DEGERI
JIRA_PROJECT_KEY=TEST
JIRA_ISSUE_TYPE=Bug
JIRA_RETRY_COUNT=3
```

Alternatif adlar da okunur:

```text
JIRA_BASE_URL
JIRA_PROJECT
```

Dry run için gerçek Jira bilgisi gerekmez:

```bash
export DRY_RUN=true
export JIRA_DRY_RUN=true
cd /home/ol_ta/projects/java_reports/fastapi-server
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
```

Dry run hata simülasyonu:

```bash
export JIRA_DRY_RUN_RESULT=failure
```

Bug eşleştirme dosyası:

```text
bug-tracker.json
```

Başlangıç içeriği:

```json
{"version": "1.0", "mappings": {}}
```

Kayıt örneği:

```json
{
  "12345": {
    "jiraKey": "DRY-1a2b3c4d",
    "status": "OPEN",
    "firstSeen": "2026-05-03T12:00:00+00:00",
    "lastSeen": "2026-05-03T12:00:00+00:00",
    "scenarioName": "Hatalı giriş",
    "runIds": ["20260503-120000-a1b2c3"],
    "resolution": null
  }
}
```

Triage akışı:

1. Test koşusu manifest üretir.
2. FastAPI run listesini ve başarısız senaryoları gösterir.
3. Triage sayfası `doorsAbsNumber` alanına bakar.
4. Aynı DOORS numarası için daha önce Jira açıldıysa mevcut eşleşme gösterilir.
5. Yeni bug gerekiyorsa Jira oluşturulur veya dry run modunda `DRY-...` anahtarı üretilir.
6. Eşleşme `bug-tracker.json` içinde saklanır.

İlgili endpointler:

```text
GET  /api/v1/runs
GET  /api/v1/runs/{run_id}/bug-status
GET  /api/v1/bugs
GET  /api/v1/bugs/{doors_number}
POST /api/v1/bugs/{doors_number}/create
POST /api/v1/runs/{run_id}/scenarios/{scenario_id}/jira
POST /api/triage/{run_id}/scenarios/{scenario_id}/jira
POST /api/triage/{run_id}/scenarios/{scenario_id}/link-jira
```

Triage sayfası formatı:

```text
http://localhost:8000/reports/{runId}/triage
```

## 7. DOORS çalıştırma

Bu rehberdeki zorunlu entegrasyon noktası Cucumber tag biçimidir. DOORS batch güncellemesi için FastAPI pipeline komut alır:

```text
PIPELINE_DOORS_COMMAND
```

Örnek:

```bash
export PIPELINE_DOORS_COMMAND="python3 fastapi-server/doors_service.py manifests/latest.json"
```

IBM DOORS aracı Windows ajan gerektirebilir. Linux ajanlarda gerçek DOORS yoksa komutu dry run veya skip edecek şekilde ayarlayın. Kurumsal DOORS alan adları projeye göre değiştiği için DXL tarafını kendi alan adlarınızla eşleştirin.

## 8. CI usage

### 8.1 Bash pipeline örneği

```bash
set -e
cd /home/ol_ta/projects/java_reports
export PATH="/home/ol_ta/tools/apache-maven-3.9.9/bin:$PATH"
export PATH="$PATH:/home/ol_ta/tools/allure-2.33.0/bin"
export DRY_RUN=true
export JIRA_DRY_RUN=true

mvn -B -pl test-core test
allure generate --clean test-core/target/allure-results -o test-core/target/allure-report
python3 -m pytest fastapi-server/tests/ -v
```

### 8.2 Jenkins örneği

```groovy
pipeline {
  agent any

  environment {
    JAVA_HOME = tool 'JDK21'
    MAVEN_HOME = '/home/ol_ta/tools/apache-maven-3.9.9'
    ALLURE_HOME = '/home/ol_ta/tools/allure-2.33.0'
    PATH = "${MAVEN_HOME}/bin:${ALLURE_HOME}/bin:${JAVA_HOME}/bin:${PATH}"
    DRY_RUN = 'true'
    JIRA_DRY_RUN = 'true'
  }

  stages {
    stage('Install Python dependencies') {
      steps {
        sh 'python3 -m pip install --upgrade pip'
        sh 'pip install -r fastapi-server/requirements.txt'
      }
    }

    stage('Run Cucumber tests') {
      steps {
        sh 'mvn -B -pl test-core test -Dcucumber.filter.tags="@sample-fail"'
      }
    }

    stage('Generate Allure report') {
      steps {
        sh 'allure generate --clean test-core/target/allure-results -o test-core/target/allure-report'
      }
    }

    stage('FastAPI tests') {
      steps {
        sh 'python3 -m pytest fastapi-server/tests/ -v'
      }
    }
  }

  post {
    always {
      archiveArtifacts artifacts: 'test-core/target/allure-report/**,manifests/*.json', allowEmptyArchive: true
    }
  }
}
```

Gerçek Jira ortamında tokenı Jenkins credential olarak verin. Pipeline dosyasına PAT yazmayın.

### 8.3 GitHub Actions örneği

```yaml
name: test-reporting

on:
  push:
  pull_request:
  workflow_dispatch:

jobs:
  test:
    runs-on: ubuntu-latest
    env:
      DRY_RUN: 'true'
      JIRA_DRY_RUN: 'true'
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install Python dependencies
        run: |
          python3 -m pip install --upgrade pip
          pip install -r fastapi-server/requirements.txt

      - name: Run Cucumber tests
        run: mvn -B -pl test-core test

      - name: Generate Allure report
        run: allure generate --clean test-core/target/allure-results -o test-core/target/allure-report

      - name: Run FastAPI tests
        run: python3 -m pytest fastapi-server/tests/ -v

      - uses: actions/upload-artifact@v4
        with:
          name: test-report-assets
          path: |
            test-core/target/allure-report
            manifests/*.json
```

Gerçek Jira için secret kullanın:

```yaml
env:
  JIRA_URL: ${{ secrets.JIRA_URL }}
  JIRA_PAT: ${{ secrets.JIRA_PAT }}
  JIRA_PROJECT_KEY: ${{ secrets.JIRA_PROJECT_KEY }}
```

## 9. Troubleshooting

### 9.1 Allure sonuçları oluşmuyor

Kontrol edin:

```text
src/test/resources/cucumber.properties
src/test/resources/allure.properties
```

Gerekli plugin:

```properties
cucumber.plugin=io.qameta.allure.cucumber7jvm.AllureCucumber7Jvm,json:target/cucumber-report.json,pretty
```

Sonuç dizini:

```bash
ls test-core/target/allure-results
```

Tek modül için:

```bash
ls target/allure-results
```

### 9.2 Cucumber hook çalışmıyor

`cucumber.glue` içinde hook paketi yoktur veya yanlış yazılmıştır.

```properties
cucumber.glue=com.testreports.allure,com.company.project.steps
```

Runner içindeki `GLUE_PROPERTY_NAME` ile properties dosyasındaki glue değeri çakışıyorsa tek kaynak seçin.

### 9.3 Screenshot eklenmiyor

Olası nedenler:

1. `WebDriverHolder.setDriver(driver)` çağrılmamış olabilir.
2. Driver `TakesScreenshot` desteklemiyor olabilir.
3. Senaryo başarısız olmamıştır. Hook sadece fail durumunda ek üretir.

### 9.4 Video eklenmiyor

Kontrol:

```bash
ffmpeg -version
```

Linux veya WSL ajanında display değeri uygun olmalıdır. CI ortamında sanal ekran yoksa `x11grab` çalışmayabilir. Video zorunlu değilse hook başarısız olduğunda test akışı devam eder.

### 9.5 DOORS numarası manifestte boş

Tag biçimini kontrol edin:

```gherkin
@DOORS-12345
Scenario: Ödeme başarısız olur
```

Parser sadece `@DOORS-` sonrası rakamları alır. `@DOORS-ABC` beklenen format değildir.

### 9.6 FastAPI run listesi boş

Manifest dizinini kontrol edin:

```bash
export MANIFESTS_DIR="/path/to/your/project/manifests"
ls "$MANIFESTS_DIR"
```

FastAPI yalnızca `*.json` dosyalarını okur. Dosya şeması `RunManifest` modeliyle uyumlu değilse API hata döndürür.

### 9.7 401 Unauthorized

Yeni token alın:

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

Header biçimi:

```text
Authorization: Bearer TOKEN_DEGERI
```

### 9.8 Jira issue açılmıyor

Önce dry run ile deneyin:

```bash
export DRY_RUN=true
export JIRA_DRY_RUN=true
```

Gerçek Jira için şu değerleri kontrol edin:

1. `JIRA_URL` veya `JIRA_BASE_URL`
2. `JIRA_PAT`
3. `JIRA_PROJECT_KEY` veya `JIRA_PROJECT`
4. `JIRA_ISSUE_TYPE`
5. Ağ ve proxy erişimi

### 9.9 Allure report komutu bulunmuyor

Bu depodaki Allure CLI yolu:

```bash
export PATH="$PATH:/home/ol_ta/tools/allure-2.33.0/bin"
allure --version
```

### 9.10 Maven bulunmuyor

Bu depodaki Maven yolu:

```bash
export PATH="/home/ol_ta/tools/apache-maven-3.9.9/bin:$PATH"
mvn -version
```

## 10. Entegrasyon kontrol listesi

1. Maven bağımlılıkları eklendi.
2. `cucumber.properties` Allure plugin ve glue değerlerini içeriyor.
3. `allure.properties` `target/allure-results` yazıyor.
4. Runner `features` classpath dizinini seçiyor.
5. Hook paketi Cucumber glue içinde.
6. Driver oluşturulunca `WebDriverHolder.setDriver(driver)` çağrılıyor.
7. Senaryolarda `@DOORS-NNNNN` etiketi var.
8. Test sonrası Allure sonuçları üretiliyor.
9. Manifest dosyaları `MANIFESTS_DIR` altına yazılıyor.
10. FastAPI `/api/v1/runs` endpointi run listesini döndürüyor.
11. Jira önce dry run modunda deneniyor.
12. CI Allure raporunu ve manifestleri artifact olarak saklıyor.
