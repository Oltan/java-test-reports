# Entegrasyon Rehberi

Bu rehber, mevcut veya yeni bir Java/Cucumber/Selenium projesini bu raporlama platformuna bağlamak ve dış sistemleri (Jira, DOORS, email, CI/CD) yapılandırmak için gereken adımları içerir.

## İçindekiler

1. [Sistemin çalışma mantığı](#1-sistemin-çalışma-mantığı)
2. [Ön gereksinimler](#2-ön-gereksinimler)
3. [pom.xml yapılandırması](#3-pomxml-yapılandırması)
4. [Zorunlu Java dosyaları (hook'lar)](#4-zorunlu-java-dosyaları-hooklar)
5. [Properties dosyaları](#5-properties-dosyaları)
6. [Feature yazım kuralları: DOORS ve bağımlılık etiketleri](#6-feature-yazım-kuralları-doors-ve-bağımlılık-etiketleri)
7. [Step sınıflarında WebDriver bağlantısı](#7-step-sınıflarında-webdriver-bağlantısı)
8. [Retry ile çalıştırma](#8-retry-ile-çalıştırma)
9. [Sonuçların FastAPI'ye akışı](#9-sonuçların-fastapiye-akışı)
10. [Başka bir Java projesini bağlama](#10-başka-bir-java-projesini-bağlama)
11. [Jira entegrasyonu](#11-jira-entegrasyonu)
12. [Sürüm ve ortam bilgisi](#12-sürüm-ve-ortam-bilgisi)
13. [Pipeline ve DOORS/email aşamaları](#13-pipeline-ve-doorsemail-aşamaları)
14. [CI/CD örnekleri](#14-cicd-örnekleri)
15. [Sık yapılan hatalar](#15-sık-yapılan-hatalar)

---

## 1. Sistemin çalışma mantığı

```
Java Testleri (Cucumber + Selenium)
        │  @After hook → Allure'a screenshot/video ekler
        ▼
test-core/target/allure-results/   ← Allure JSON sonuçları
        │  FastAPI, koşu bitince bu dizini parse eder
        ▼
DuckDB (reports.duckdb) + manifests/{run_id}.json
        │
        ▼
FastAPI Dashboard (http://localhost:8000)
        ├── Run listesi, pass/fail/skip sayıları
        ├── Senaryo detayları, hata mesajları
        ├── DOORS numarasına göre Jira auto-match
        └── Triage: Jira aç / mevcut Jira bağla / pass-skip override
```

FastAPI, Java koduna bağımlı değildir: Java sadece Allure sonuçları üretir, sunucu bu sonuçları okur. Testler dashboard'dan (veya `POST /api/tests/start` ile) başlatıldığında sunucu Maven'i kendisi çalıştırır ve sonuçları otomatik işler.

## 2. Ön gereksinimler

Java 21, Maven 3.9+, Python 3.11+, Allure CLI ve (opsiyonel) ffmpeg kurulumu için [KURULUM.md](KURULUM.md).

## 3. pom.xml yapılandırması

### 3.1 Sürümler (parent veya tek modül POM)

Bu depodaki parent `pom.xml` ile birebir uyumlu değerler:

```xml
<properties>
    <java.version>21</java.version>
    <maven.compiler.source>21</maven.compiler.source>
    <maven.compiler.target>21</maven.compiler.target>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <cucumber.version>7.18.0</cucumber.version>
    <selenium.version>4.21.0</selenium.version>
    <junit.version>5.10.2</junit.version>
    <allure.version>2.25.0</allure.version>
</properties>
```

### 3.2 Test modülü bağımlılıkları

Tam ve çalışan örnek: bu depodaki [`pom.xml`](../pom.xml) (dependencyManagement) ve [`test-core/pom.xml`](../test-core/pom.xml). Hedef projeye eklenecek temel bağımlılıklar:

- `io.cucumber:cucumber-java`, `cucumber-junit-platform-engine`, `cucumber-core`
- `org.seleniumhq.selenium:selenium-java`
- `org.junit.jupiter:junit-jupiter-api`, `junit-jupiter-engine`
- `org.junit.platform:junit-platform-launcher`, `junit-platform-suite`
- `io.qameta.allure:allure-cucumber7-jvm` (içindeki `gherkin` exclusion'ı ile — Cucumber'ın kendi gherkin'i ile çakışmasın)

### 3.3 Surefire ayarı

Sadece Cucumber runner'ın koşması için:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <includes>
            <include>**/CucumberTestRunner.java</include>
        </includes>
    </configuration>
</plugin>
```

> Bu depoda ayrıca `retry-runner` adında bir Maven profili vardır: `-Dretry.count=N` verildiğinde Surefire `RetryTestRunner`'ı çalıştırır (bkz. [Bölüm 8](#8-retry-ile-çalıştırma)).

## 4. Zorunlu Java dosyaları (hook'lar)

Aşağıdaki 4 hook sınıfını `test-core/src/test/java/com/testreports/allure/` dizininden kendi projenize kopyalayın (paket adını değiştirebilirsiniz):

| Sınıf | Görevi |
|---|---|
| `WebDriverHolder.java` | `ThreadLocal<WebDriver>` — hook'lar ile step'ler arasında driver paylaşımı |
| `ScreenshotHook.java` | `@After(order=100)` — senaryo fail olursa Allure'a PNG ekler |
| `VideoHook.java` | `@Before(order=1)` / `@After(order=200)` — ffmpeg ile kayıt; fail'de Allure'a ekler, pass'te siler; ffmpeg yoksa sessizce atlar |
| `FailureLocationCapture.java` | Cucumber plugin — fail eden senaryonun `feature:satır` konumunu Allure label olarak yazar |

Runner örneği (bu depodaki `test-core/src/test/java/com/testreports/runner/CucumberTestRunner.java`):

```java
@Suite
@IncludeEngines("cucumber")
@SelectClasspathResource("features")   // src/test/resources/features
@ConfigurationParameter(key = PLUGIN_PROPERTY_NAME,
    value = "io.qameta.allure.cucumber7jvm.AllureCucumber7Jvm,"
          + "com.sirket.proje.allure.FailureLocationCapture,"
          + "json:target/cucumber-report.json,pretty")
@ConfigurationParameter(key = GLUE_PROPERTY_NAME,
    value = "com.sirket.proje.allure,com.sirket.proje.steps")
public class CucumberTestRunner {}
```

`GLUE_PROPERTY_NAME` içinde **iki paket zorunludur**: hook paketi (`...allure`) ve kendi step paketiniz.

## 5. Properties dosyaları

`src/test/resources/cucumber.properties`:

```properties
cucumber.publish.quiet=true
cucumber.plugin=io.qameta.allure.cucumber7jvm.AllureCucumber7Jvm,\
  com.sirket.proje.allure.FailureLocationCapture,\
  json:target/cucumber-report.json,\
  pretty
cucumber.glue=com.sirket.proje.allure,com.sirket.proje.steps
```

`src/test/resources/allure.properties`:

```properties
allure.results.directory=target/allure-results
allure.report.directory=target/allure-report
```

> `cucumber.plugin` hem runner'da hem properties dosyasında tanımlıysa Cucumber ikisini birleştirir ve Allure plugin iki kez çalışabilir. Tek kaynak seçin.

## 6. Feature yazım kuralları: DOORS ve bağımlılık etiketleri

### 6.1 DOORS etiketi

Sunucu, Cucumber tag'lerinden gereksinim numarasını şu desenle okur (büyük/küçük harf duyarsız): `@DOORS-<rakam>` veya `@ABS-<rakam>`.

```gherkin
@smoke @DOORS-30001
Scenario: Hatalı giriş
  Given user is on the login page
  ...
```

Kurallar:

- Doğru: `@DOORS-12345`, `@doors-12345`, `@ABS-4711`
- Yanlış (eşleşmez): `@DOORS-ABC` (rakam değil), `@DOORS12345` (tire yok), `@DOORS_12345` (alt çizgi)
- Feature düzeyindeki etiket tüm senaryolara miras kalır; senaryoya özel numara senaryo düzeyine yazılır.
- Eşleşen değer manifest'te `doorsAbsNumber` alanına `DOORS-12345` biçiminde (tam ad, `@` işaretsiz) yazılır. Triage ve `bug-tracker.json` aynı değeri kullanır.

### 6.2 Senaryo bağımlılıkları (`@id:` / `@dep:`)

```gherkin
@id:Setup @DOORS-10001
Scenario: Database setup

@id:Login @dep:Setup @DOORS-10002
Scenario: User login

@id:Dashboard @dep:Login,Setup @DOORS-10003
Scenario: Dashboard loads
```

`@dep:` içindeki senaryo fail olursa ona bağlı senaryolar retry koşusunda otomatik skip edilir (topolojik sıralama `RetryTestRunner` + `DependencyResolver` ile yapılır). Çalışan örnek: `test-core/src/test/resources/features/dependency-demo.feature`.

## 7. Step sınıflarında WebDriver bağlantısı

Driver oluşturur oluşturmaz holder'a kaydetmek **zorunludur**; aksi hâlde screenshot hook driver'ı bulamaz:

```java
WebDriver driver = new ChromeDriver(opts);
WebDriverHolder.setDriver(driver);    // ← zorunlu

// Test sonunda:
driver.quit();
WebDriverHolder.removeDriver();       // ← temizlik zorunlu
```

Hook çalışma sırası (Cucumber, `@After`'ları order değerine göre küçükten büyüğe koşturur):

| Hook | Order | Ne yapar |
|---|---|---|
| `VideoHook @Before` | 1 | Kaydı başlatır |
| `ScreenshotHook @After` | 100 | Screenshot çeker |
| `VideoHook @After` | 200 | Kaydı durdurur |
| Step sınıfı `@After` | 1001 | Driver'ı kapatır (**en son** — screenshot driver kapanmadan alınmalı) |

Merkezi driver yönetimi örneği: `test-core/src/test/java/com/testreports/config/WebDriverFactory.java`.

## 8. Retry ile çalıştırma

```bash
mvn -pl test-core test -Dretry.count=2
```

`retry.count` verildiğinde `retry-runner` Maven profili aktifleşir: normal runner yerine `RetryTestRunner` koşar, başarısız senaryoları N kez yeniden dener ve `@dep:` bağımlılıklarına göre topolojik sıralama yapar. `retry.count=0` ile retry runner devre dışıdır. Kaynak: `test-core/src/test/java/com/testreports/runner/RetryTestRunner.java`.

Sunucu, aynı senaryonun retry denemelerini `historyId` üzerinden gruplar ve manifest'te `attempts` listesi + `is_flaky` bayrağı olarak gösterir.

## 9. Sonuçların FastAPI'ye akışı

### 9.1 Sunucuyu başlatma

```bash
cd fastapi-server
pip install -r requirements.txt -r requirements-dev.txt
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
```

### 9.2 Veri akışı — iki yol

**Yol A — Testi sunucu başlatsın (önerilen):** Admin panelinden veya `POST /api/tests/start` ile koşu başlatın. Sunucu `mvn -pl test-core test -Dcucumber.filter.tags=...` komutunu çalıştırır, koşu bitince `ALLURE_RESULTS_DIR` dizinini parse eder, DuckDB'ye yazar ve `<repo>/manifests/{run_id}.json` manifest'ini üretir.

**Yol B — Hazır manifest okutmak:** Dashboard run listesi `MANIFESTS_DIR` (varsayılan `<repo>/manifests`) altındaki `*.json` dosyalarından beslenir. Şemaya uygun manifest'i bu dizine koyan her sistem listede görünür:

```bash
export MANIFESTS_DIR="/path/to/your/project/manifests"
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
```

Manifest şeması (`fastapi-server/models.py` → `RunManifest`):

```json
{
  "runId": "20260503-120000-a1b2c3",
  "timestamp": "2026-05-03T12:00:00Z",
  "totalScenarios": 1,
  "passed": 0, "failed": 1, "skipped": 0,
  "duration": "12.0s",
  "version": "v1.2.3",
  "environment": "staging",
  "scenarios": [
    {
      "id": "scenario-001",
      "name": "Hatalı giriş",
      "status": "failed",
      "duration": "12.0s",
      "doorsAbsNumber": "DOORS-12345",
      "tags": ["@DOORS-12345", "@smoke"],
      "steps": [], "attachments": []
    }
  ]
}
```

`status` alanı `passed|failed|skipped|broken` değerlerinden biri olmalıdır.

### 9.3 İlgili ortam değişkenleri

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `MANIFESTS_DIR` | `<repo>/manifests` | Dashboard'ın okuduğu manifest dizini |
| `ALLURE_RESULTS_DIR` | `<repo>/test-core/target/allure-results` | Koşu sonrası parse edilen Allure sonuç dizini |
| `MAVEN_CMD` | PATH'teki `mvn` | Maven çalıştırılabilir dosyasının tam yolu (PATH'te yoksa) |
| `REPORTS_DUCKDB_PATH` | `reports.duckdb` | DuckDB dosya yolu |

### 9.4 Doğrulama

`http://localhost:8000` → run listesinde koşu görünmeli; pass/fail sayıları doğru olmalı; fail senaryolarda DOORS numarası etiketi görünmeli. API ile:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')

curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/runs
```

## 10. Başka bir Java projesini bağlama

Hedef projenin koşusunu bu sunucudan yönetmenin desteklenen yolu, projeyi **bu deponun Maven modülü** olarak eklemektir:

1. Test projenizi depo köküne bir modül olarak yerleştirin (örn. `myproject/`).
2. Parent `pom.xml` içindeki `<modules>` bloğuna ekleyin (dosyada hazır yorum satırı vardır):
   ```xml
   <modules>
       <module>test-core</module>
       <module>myproject</module>
   </modules>
   ```
3. Pipeline koşularının sizin modülünüzü kullanması için `.env` dosyasına:
   ```env
   MAVEN_MODULE=myproject
   ALLURE_RESULTS_DIR=/path/to/repo/myproject/target/allure-results
   ```
   `MAVEN_MODULE` pipeline'ın Maven aşamasında `mvn -pl <MAVEN_MODULE> test` olarak kullanılır; `ALLURE_RESULTS_DIR` sonuçların nereden okunacağını belirler.

> Not: Admin panelindeki "test başlat" akışı (`/api/tests/start`) şu an `-pl test-core` ile sabittir; farklı modül adı yalnızca pipeline (`/api/pipeline/run`, `PIPELINE_MAVEN_COMMAND`/`MAVEN_MODULE`) tarafından desteklenir. Tamamen ayrı bir depodaki projeyi ise [Bölüm 9.2 Yol B](#92-veri-akışı--iki-yol) ile (manifest paylaşımı) bağlayabilirsiniz.

Projenizde olması gerekenler: bölüm 3-7'deki bağımlılıklar, hook sınıfları, properties dosyaları ve `@DOORS-NNNNN` etiketleri.

## 11. Jira entegrasyonu

### 11.1 Mimari

Bağlantı `fastapi-server/jira_client.py` üzerinden, `atlassian-python-api` kütüphanesiyle ve **PAT (Personal Access Token)** ile yapılır. Açıklamalar Jira Server/DC wiki formatında (`h2.`, `*bold*`) gönderilir.

### 11.2 Ortam değişkenleri

```env
# Zorunlu
JIRA_URL=https://jira.sirket.local      # alternatif ad: JIRA_BASE_URL
JIRA_PAT=personal_access_token
JIRA_PROJECT_KEY=PROJ                   # alternatif ad: JIRA_PROJECT

# Opsiyonel
JIRA_ISSUE_TYPE=Bug                     # varsayılan: Bug
JIRA_RETRY_COUNT=3                      # API hatasında deneme sayısı (exponential backoff)
JIRA_VERIFY_SSL=true                    # self-signed sertifika için false
JIRA_DRY_RUN=false                      # true → gerçek Jira'ya yazmadan simüle eder
```

PAT yetkileri: Create Issues, Add Comments, Add Attachments, Browse Projects.

### 11.3 Dry-run modu (Jira yokken)

```bash
export DRY_RUN=true          # tüm dış sistemler (Jira/DOORS/email) için genel dry-run
# veya sadece Jira için:
export JIRA_DRY_RUN=true
export JIRA_DRY_RUN_RESULT=failure   # hata senaryosu simülasyonu (opsiyonel)
```

Dry-run'da issue key `DRY-{hash}` biçiminde üretilir, URL `https://dry-run.local/browse/...` olur. Sahte issue'lar `fastapi-server/mock_jira.json` dosyasından okunur:

```json
{
  "BUG-001": {"key": "BUG-001", "status": "Open", "doors_number": "DOORS-12345"}
}
```

### 11.4 `DOORS Number` custom field ve auto-match

`search_by_doors_number()` Jira'da şu JQL'i çalıştırır (`jira_client.py`):

```
project = <PROJECT_KEY> AND "DOORS Number" ~ "<doors_number>"
```

Jira'nızda `DOORS Number` adında custom field tanımlı olmalıdır; alan adınız farklıysa `jira_client.py` içindeki JQL'i güncelleyin.

Triage sayfasındaki auto-match (`POST /api/triage/{run_id}/auto-match-jira`):

1. Run'daki FAILED/BROKEN senaryoları tarar,
2. Her senaryonun DOORS numarasıyla Jira'da arama yapar,
3. **Aktif** issue'ları senaryoya bağlar; pasif statüler hariç tutulur (`server.py`):
   `done, closed, resolved, cancelled, wont fix, won't fix, duplicate, rejected`
4. Manuel triage kararı verilmiş senaryolar atlanır.

### 11.5 Endpoint'ler

| Endpoint | Metod | Açıklama |
|---|---|---|
| `/api/triage/{run_id}` | GET | Run'ın triage durumu |
| `/api/triage/{run_id}/auto-match-jira` | POST | DOORS numarasıyla otomatik eşleştir |
| `/api/triage/{run_id}/scenarios/{id}/jira` | POST | Yeni Jira bug oluştur |
| `/api/triage/{run_id}/scenarios/{id}/link-jira` | POST | Mevcut Jira'yı bağla (`{"jira_key":"PROJ-123"}`) |
| `/api/triage/{run_id}/scenarios/{id}/override` | POST | Pass/skip kararı (`{"decision":"accepted_pass","reason":"..."}`) |
| `/api/v1/runs/{run_id}/scenarios/{id}/jira` | POST | Eski API — triage kararı oluşturmaz, yenisini tercih edin |
| `/api/v1/bugs`, `/api/v1/bugs/{doors_number}` | GET | Bug eşleşmeleri (`bug-tracker.json`) |
| `/api/v1/bugs/{doors_number}/create` | POST | Sahte bug kaydı — **yalnızca `DRY_RUN=true` iken** çalışır |
| `/api/v1/runs/{run_id}/bug-status` | GET | Run'daki senaryoların Jira/bug durumları |

DOORS ↔ Jira eşleşmeleri kökteki `bug-tracker.json` dosyasında saklanır (`{"version":"1.0","mappings":{...}}`; anahtar `DOORS-NNNNN`). Dosya bozulursa bu iskeletle sıfırlayın.

### 11.6 Hata kodları

| Durum | HTTP | Açıklama |
|---|---|---|
| Jira yapılandırılmamış | 503 | `JIRA_URL`/`JIRA_PAT` eksik — dry-run ile test edin |
| Jira API hatası | 502 | Ağ, proxy veya PAT yetki sorunu |
| Senaryo bulunamadı | 404 | run_id/scenario_id kontrol edin |
| Aynı senaryoda mevcut Jira | 200 | Yeni issue açılmaz, mevcut key döner |

## 12. Sürüm ve ortam bilgisi

Dashboard'daki "sürüm" ve "ortam" alanları iki kaynaktan dolar:

**Yöntem 1 — Koşu başlatırken göndermek (önerilen):** `POST /api/tests/start` gövdesindeki `version` ve `environment` alanları (admin panelindeki form da bunları gönderir):

```json
{"tags": "@smoke", "version": "v1.4.2", "environment": "staging", "visibility": "internal"}
```

`environment` yalnızca `staging|prod|dev` değerlerini kabul eder.

**Yöntem 2 — `environment.properties` fallback:** `version` boş gelirse sunucu `ALLURE_RESULTS_DIR` içindeki `environment.properties` dosyasından `VERSION=` anahtarını okur:

```properties
VERSION=1.4.2
```

Bu dosyayı test projeniz üretmelidir (örn. bir `@BeforeAll` içinde `target/allure-results/environment.properties` dosyasına `VERSION=` satırını yazan küçük bir yardımcı ile). Sunucu yalnızca `VERSION` anahtarını kullanır; diğer anahtarlar sadece Allure raporunda görünür.

**allure-results temizliği:** Allure sonuç dizini Maven tarafından otomatik temizlenmez. Sunucu koşu zaman penceresine göre eski dosyaları filtreler, ama kesin sonuç için:

```bash
mvn clean test            # veya
rm -rf test-core/target/allure-results && mvn test
```

## 13. Pipeline ve DOORS/email aşamaları

`POST /api/pipeline/run` şu aşamaları sırayla yürütür: `maven_test → manifest → allure → jira → doors → email`. Her aşama ortam değişkeniyle yapılandırılır; tanımsız aşamalar **skipped** sayılır:

| Değişken | Aşama | Açıklama |
|---|---|---|
| `PIPELINE_MAVEN_COMMAND` | maven_test | Tam komut override; yoksa `mvn -pl $MAVEN_MODULE test` |
| `MAVEN_CMD`, `MAVEN_MODULE` | maven_test | Maven yolu ve modül adı (varsayılan `test-core`) |
| `PIPELINE_MANIFEST_COMMAND` | manifest | Manifest üretim komutu (opsiyonel) |
| `PIPELINE_ALLURE_COMMAND` veya `ALLURE_BIN`/`ALLURE_RESULTS_DIR`/`ALLURE_REPORT_DIR` | allure | Rapor üretimi; varsayılan `allure generate --clean <results> -o <report>` |
| `PIPELINE_JIRA_COMMAND` | jira | Jira aşaması komutu |
| `PIPELINE_DOORS_COMMAND` | doors | DOORS DXL komutu (IBM DOORS genellikle Windows ajan ister) |
| `PIPELINE_EMAIL_COMMAND` | email | Email aşaması komutu |
| `PIPELINE_VERSION`, `PIPELINE_ENVIRONMENT` | — | Run kaydına yazılan sürüm/ortam |

Email gönderimi `fastapi-server/email_service.py` ile yapılır: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` (DRY_RUN aktifken gerçek gönderim yapılmaz). Durum sorgusu: `GET /api/pipeline/status/{run_id}`.

## 14. CI/CD örnekleri

### 14.1 GitHub Actions

```yaml
name: test-reporting
on: [push, pull_request, workflow_dispatch]

jobs:
  test:
    runs-on: ubuntu-latest
    env:
      DRY_RUN: 'true'
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with: {distribution: temurin, java-version: '21'}
      - uses: actions/setup-python@v5
        with: {python-version: '3.12'}

      - name: Allure CLI kur
        run: |
          curl -LO https://github.com/allure-framework/allure2/releases/download/2.33.0/allure-2.33.0.tgz
          tar -xzf allure-2.33.0.tgz -C $HOME
          echo "$HOME/allure-2.33.0/bin" >> $GITHUB_PATH

      - name: Python bağımlılıkları
        run: pip install -r fastapi-server/requirements.txt -r fastapi-server/requirements-dev.txt

      - name: Cucumber testleri
        run: mvn -B -pl test-core test

      - name: Allure raporu
        if: always()
        run: allure generate --clean test-core/target/allure-results -o test-core/target/allure-report

      - name: Python testleri
        run: cd fastapi-server && python3 -m pytest tests/ -v

      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: test-report-assets
          path: |
            test-core/target/allure-report
            manifests/*.json
```

Gerçek Jira için secret kullanın (`JIRA_URL`, `JIRA_PAT`, `JIRA_PROJECT_KEY`); PAT'i asla dosyaya yazmayın.

### 14.2 Jenkins

Bu depodaki [`Jenkinsfile`](../Jenkinsfile) çalışan örnektir. Özet:

```groovy
pipeline {
  agent any
  environment {
    JAVA_HOME = tool 'JDK21'
    PATH = "${JAVA_HOME}/bin:${PATH}"
    DRY_RUN = 'true'
  }
  stages {
    stage('Python deps')  { steps { sh 'pip install -r fastapi-server/requirements.txt' } }
    stage('Java tests')   { steps { sh 'mvn -B test -pl test-core' } }
    stage('Python tests') { steps { sh 'cd fastapi-server && python3 -m pytest tests/ -v' } }
    stage('Allure')       { steps { sh 'allure generate --clean test-core/target/allure-results -o allure-report' } }
  }
}
```

Maven/Allure ajan PATH'inde olmalı; değilse `MAVEN_HOME`/`ALLURE_BIN` ortam değişkenleriyle yol verin. Jira PAT'ini Jenkins credential olarak tanımlayın.

## 15. Sık yapılan hatalar

**`target/allure-results` boş** — `allure-cucumber7-jvm` bağımlılığı eksik veya `cucumber.plugin` satırında Allure plugin yok. Hem runner'da hem properties'te tanımlıysa birini silin.

**Screenshot eklenmiyor** — `WebDriverHolder.setDriver(driver)` çağrılmamış, driver `TakesScreenshot` desteklemiyor veya senaryo fail olmamış (hook sadece fail'de ek üretir).

**Video eklenmiyor** — `ffmpeg -version` kontrol edin. CI'da sanal ekran yoksa `x11grab` çalışmaz; Xvfb kurun veya video kaydından vazgeçin.

**DOORS numarası triage'da boş** — Etiket biçimi `@DOORS-12345` olmalı (rakam + tire). Bölüm 6.1'e bakın.

**Step bulunamıyor (`UndefinedStepException`)** — `cucumber.glue` değerinde step paketiniz eksik.

**Maven "No tests were executed"** — Surefire `<includes>` bloğunda runner sınıfınız yok veya runner `src/test/java` altında değil.

**Auto-match `matched: 0`** — Jira'daki `DOORS Number` alanı etiketle eşleşmiyor, tüm issue'lar kapalı statüde veya (dry-run'da) `mock_jira.json` içeriği uymuyor.

**FastAPI run listesi boş** — `MANIFESTS_DIR` doğru mu? Sunucu yalnızca `RunManifest` şemasına uyan `*.json` dosyalarını okur.

**401 Unauthorized** — Token süresi dolmuş (varsayılan 24 saat, `JWT_EXPIRATION_HOURS`). Yeniden login olun.

**`mvn`/`allure` bulunamıyor** — PATH'e ekleyin veya `MAVEN_CMD` / `ALLURE_BIN` ile tam yol verin.
