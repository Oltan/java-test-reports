# Test Raporlama Sistemi Entegrasyon Rehberi

Bu rehber, bu depodaki raporlama altyapısını herhangi bir Java, Selenium ve Cucumber projesine adım adım eklemek için hazırlandı. Örnekler mevcut proje köküne göre verilmiştir:

```text
/mnt/c/Users/ol_ta/desktop/java_reports
```

Mevcut sistem şu ana parçalardan oluşur:

```text
test-core              Cucumber koşucusu, step sınıfları, Selenium sürücü kurulumu
allure-integration    Allure ekran görüntüsü ve video hook sınıfları
report-model          run manifest modeli, Jackson okuma ve yazma sınıfları
fastapi-server        Dashboard, API, triage sayfası ve bug eşleştirme servisi
jira-service          Jira REST API v2 istemcisi
doors-service         IBM DOORS batch DXL çalıştırıcısı
orchestrator          Servisleri bir araya getiren boru hattı katmanı
```

## 1. Genel Bakış

Bu sistem, otomasyon testlerinin ham çıktılarını okunabilir bir raporlama akışına dönüştürür. Cucumber senaryoları Selenium ile çalışır, Allure sonuçları üretir, hata anında ekran görüntüsü ve video ekler, run manifest dosyalarını dashboard üzerinde gösterir, başarısız senaryolar için triage ekranı açar, Jira ve DOORS bağlantılarını aynı akışa bağlar.

Kullanım amacı şudur:

* Test sonucunu tek ekranda görmek.
* Başarısız senaryolarda ekran görüntüsü, video ve hata mesajını birlikte saklamak.
* Her run için makine tarafından okunabilir manifest üretmek.
* Hata kartlarını triage ekranında incelemek.
* Aynı DOORS gereksinimi için tekrar tekrar Jira açılmasını engellemek.
* CI/CD içinde Java testleri, Python API testleri ve Allure rapor üretimini birlikte çalıştırmak.

Bu depoda FastAPI dashboard varsayılan olarak şu adreste çalışır:

```text
http://localhost:8000
```

Varsayılan giriş bilgileri:

```text
Kullanıcı adı: admin
Şifre: admin123
```

## 2. Gereksinimler

Hedef projede şu araçlar bulunmalıdır:

* Java 17 veya üzeri. Bu depodaki ana `pom.xml` Java 21 ile ayarlanmıştır.
* Maven 3.9 veya üzeri.
* Python 3.12 veya üzeri.
* Allure CLI.
* ffmpeg.
* Chrome ve ChromeDriver. Bu depodaki örnek WSL içinde şu yolları kullanır:

```text
/tmp/chrome-linux64/chrome
/tmp/chromedriver-linux64/chromedriver
```

Hızlı kontrol komutları:

```bash
java -version
mvn -version
python3 --version
allure --version
ffmpeg -version
```

Bu depoda Maven yolu bazı komutlarda açık yazılmıştır:

```bash
export PATH="/home/ol_ta/tools/apache-maven-3.9.9/bin:$PATH"
```

Kurumsal projede JDK 17 kullanılıyorsa `maven.compiler.source` ve `maven.compiler.target` değerlerini 17 yapabilirsiniz. Bu depodaki hazır değer 21'dir.

## 3. Maven Entegrasyonu

### 3.1 Ana sürüm yönetimi

Hedef projenizde tek modüllü yapı varsa aşağıdaki sürüm değerlerini doğrudan ana `pom.xml` içine ekleyin. Çok modüllü yapı varsa bu değerleri parent POM içinde tutun.

Bu depodaki ana dosya:

```text
/mnt/c/Users/ol_ta/desktop/java_reports/pom.xml
```

Kullanılan sürümler:

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

### 3.2 Gerekli dependency tanımları

Hedef projenizde Cucumber, Selenium, Allure ve Jackson için şu bağımlılıkları ekleyin:

```xml
<dependencies>
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
    <dependency>
        <groupId>org.seleniumhq.selenium</groupId>
        <artifactId>selenium-java</artifactId>
        <version>${selenium.version}</version>
    </dependency>
    <dependency>
        <groupId>io.qameta.allure</groupId>
        <artifactId>allure-cucumber7-jvm</artifactId>
        <version>${allure.version}</version>
        <exclusions>
            <exclusion>
                <groupId>io.cucumber</groupId>
                <artifactId>gherkin</artifactId>
            </exclusion>
        </exclusions>
    </dependency>
    <dependency>
        <groupId>io.qameta.allure</groupId>
        <artifactId>allure-junit-platform</artifactId>
        <version>${allure.version}</version>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
        <version>${jackson.version}</version>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.datatype</groupId>
        <artifactId>jackson-datatype-jsr310</artifactId>
        <version>${jackson.version}</version>
    </dependency>
</dependencies>
```

Bu depodaki `test-core/pom.xml` içinde `allure-integration` modülü ayrıca bağlıdır:

```xml
<dependency>
    <groupId>com.testreports</groupId>
    <artifactId>allure-integration</artifactId>
    <version>1.0.0-SNAPSHOT</version>
</dependency>
```

Başka bir projeye taşırken iki yol vardır:

1. `allure-integration` modülünü aynı çok modüllü projeye ekleyin ve yukarıdaki bağımlılığı kullanın.
2. `ScreenshotHook`, `VideoHook` ve `WebDriverHolder` sınıflarını hedef projenin test kaynaklarına kopyalayın.

### 3.3 Surefire ve Allure Maven eklentileri

Ana `pom.xml` içinde şu eklenti ayarlarını kullanın:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <source>21</source>
                    <target>21</target>
                    <encoding>UTF-8</encoding>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
                <configuration>
                    <failIfNoTests>false</failIfNoTests>
                    <includes>
                        <include>**/CucumberTestRunner.java</include>
                    </includes>
                </configuration>
            </plugin>
            <plugin>
                <groupId>io.qameta.allure</groupId>
                <artifactId>allure-maven</artifactId>
                <version>2.12.0</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

Derleme kontrolü:

```bash
mvn validate
mvn test
mvn allure:generate --clean
```

## 4. Cucumber Konfigürasyonu

### 4.1 Dosya konumu

Bu depodaki Cucumber ayarı şu dosyadadır:

```text
/mnt/c/Users/ol_ta/desktop/java_reports/test-core/src/test/resources/cucumber.properties
```

Mevcut içerik:

```properties
cucumber.publish.quiet=true
cucumber.plugin=io.qameta.allure.cucumber7jvm.AllureCucumber7Jvm,json:target/cucumber-report.json,pretty
cucumber.glue=com.testreports.allure,com.testreports.steps
```

Hedef projeye uyarlarken `com.testreports.steps` yerine kendi step paketinizin adını yazın. Hook sınıflarını aynı pakette bırakıyorsanız `com.testreports.allure` değerini koruyabilirsiniz. Kopyalayıp kendi paketiniz altına aldıysanız glue değerini de değiştirin.

Örnek hedef proje ayarı:

```properties
cucumber.publish.quiet=true
cucumber.plugin=io.qameta.allure.cucumber7jvm.AllureCucumber7Jvm,json:target/cucumber-report.json,pretty
cucumber.glue=com.sirket.proje.allure,com.sirket.proje.steps
```

### 4.2 Cucumber koşucusu

Bu depodaki koşucu:

```text
/mnt/c/Users/ol_ta/desktop/java_reports/test-core/src/test/java/com/testreports/runner/CucumberTestRunner.java
```

Mevcut yapı:

```java
package com.testreports.runner;

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
@ConfigurationParameter(key = GLUE_PROPERTY_NAME, value = "com.testreports.allure,com.testreports.steps")
public class CucumberTestRunner {
}
```

Hedef projede feature dosyaları `src/test/resources/features` altında olmalıdır. Farklı klasör kullanıyorsanız `@SelectClasspathResource` değerini değiştirin.

## 5. Allure Entegrasyonu

### 5.1 Allure sonuç dizini

Bu depodaki Allure ayarı:

```text
/mnt/c/Users/ol_ta/desktop/java_reports/test-core/src/test/resources/allure.properties
```

İçerik:

```properties
allure.results.directory=target/allure-results
```

Bu değer Cucumber koşusu bittiğinde sonuçların `target/allure-results` altında toplanmasını sağlar.

### 5.2 WebDriverHolder

`ScreenshotHook` çalışırken aktif WebDriver nesnesine erişmelidir. Bu depoda bunun için ThreadLocal tabanlı holder kullanılır:

```text
/mnt/c/Users/ol_ta/desktop/java_reports/allure-integration/src/main/java/com/testreports/allure/WebDriverHolder.java
```

Kod:

```java
package com.testreports.allure;

import org.openqa.selenium.WebDriver;

public final class WebDriverHolder {
    private static final ThreadLocal<WebDriver> driver = new ThreadLocal<>();

    private WebDriverHolder() {
    }

    public static void setDriver(WebDriver webDriver) {
        driver.set(webDriver);
    }

    public static WebDriver getDriver() {
        return driver.get();
    }

    public static void removeDriver() {
        driver.remove();
    }
}
```

Step veya driver factory içinde driver oluşturduktan sonra holder'a yazın:

```java
driver = com.testreports.config.WebDriverFactory.createDriver();
com.testreports.allure.WebDriverHolder.setDriver(driver);
```

Test bitince driver kapatın:

```java
@After(order = 1001)
public void cleanup() {
    if (driver != null) {
        driver.quit();
        com.testreports.allure.WebDriverHolder.removeDriver();
    }
}
```

### 5.3 ScreenshotHook

Bu depodaki sınıf:

```text
/mnt/c/Users/ol_ta/desktop/java_reports/allure-integration/src/main/java/com/testreports/allure/ScreenshotHook.java
```

Hata anında ekran görüntüsü ekler:

```java
@After(order = 100)
public void captureScreenshot(Scenario scenario) {
    if (!scenario.isFailed()) {
        return;
    }

    WebDriver driver = WebDriverHolder.getDriver();
    if (driver == null) {
        System.err.println("ScreenshotHook: WebDriver is null, cannot capture screenshot");
        return;
    }

    if (!(driver instanceof TakesScreenshot)) {
        System.err.println("ScreenshotHook: WebDriver does not support screenshots");
        return;
    }

    try {
        byte[] screenshot = ((TakesScreenshot) driver).getScreenshotAs(OutputType.BYTES);
        Allure.addAttachment("Screenshot", "image/png", new ByteArrayInputStream(screenshot), "png");
    } catch (WebDriverException e) {
        System.err.println("ScreenshotHook: Failed to capture screenshot: " + e.getMessage());
    }
}
```

Bu hook, senaryo başarısız değilse ek dosya üretmez. Böylece başarılı koşularda rapor gereksiz büyümez.

### 5.4 VideoHook

Bu depodaki sınıf:

```text
/mnt/c/Users/ol_ta/desktop/java_reports/allure-integration/src/main/java/com/testreports/allure/VideoHook.java
```

Video dosyaları şu dizine yazılır:

```text
target/videos
```

Kullanılan ffmpeg komutu Java içinden şu argümanlarla oluşturulur:

```java
ProcessBuilder pb = new ProcessBuilder(
        "ffmpeg",
        "-f", "x11grab",
        "-framerate", "15",
        "-video_size", "1920x1080",
        "-i", ":0.0",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
        "-y",
        videoPath.toString()
);
```

Davranış:

* Her senaryo başında kayıt başlar.
* Senaryo başarısızsa video Allure ekine eklenir.
* Senaryo başarılıysa video silinir.
* ffmpeg bulunamazsa test akışı durmaz, sadece video kaydı kapanır.

Başsız tarayıcı ile gerçek ekran kaydı gerekiyorsa CI ortamında sanal ekran hazırlayın. WSL veya Linux ajanında genelde `:0.0` yerine ajan ekranınıza uygun display değeri gerekir.

### 5.5 Allure rapor üretimi

Testten sonra rapor üretin:

```bash
allure generate --clean test-core/target/allure-results -o allure-report
```

Tek modüllü projede komut genelde şöyle olur:

```bash
allure generate --clean target/allure-results -o allure-report
```

## 6. FastAPI Sunucu Kurulumu

### 6.1 Dosyaları hedef projeye ekleme

Bu dizini hedef projeye kopyalayın:

```text
/mnt/c/Users/ol_ta/desktop/java_reports/fastapi-server
```

Manifest dosyaları varsayılan olarak proje kökündeki şu dizinden okunur:

```text
/mnt/c/Users/ol_ta/desktop/java_reports/manifests
```

Sunucu kodundaki ayar:

```python
MANIFESTS_DIR = Path(os.getenv("MANIFESTS_DIR", str(Path(__file__).parent.parent / "manifests")))
```

Başka bir dizin kullanmak için ortam değişkeni verin:

```bash
export MANIFESTS_DIR="/path/to/your/project/manifests"
```

### 6.2 Python bağımlılıkları

Bu depodaki dosya:

```text
/mnt/c/Users/ol_ta/desktop/java_reports/fastapi-server/requirements.txt
```

İçerik:

```text
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
pydantic>=2.7.0
python-dotenv>=1.0.1
PyJWT>=2.8.0
jinja2>=3.1.0
```

Kurulum:

```bash
cd /mnt/c/Users/ol_ta/desktop/java_reports
python3 -m pip install --upgrade pip
pip install -r fastapi-server/requirements.txt
```

### 6.3 Sunucuyu başlatma

WSL veya Linux terminalinde:

```bash
cd /mnt/c/Users/ol_ta/desktop/java_reports/fastapi-server
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
```

Proje kökünden hazır script ile:

```bash
cd /mnt/c/Users/ol_ta/desktop/java_reports
bash start.sh
```

Windows tarafından WSL üstünde başlatmak için hazır batch dosyası:

```text
/mnt/c/Users/ol_ta/desktop/java_reports/scripts/start-server.bat
```

İçindeki komut:

```bat
wsl -d Ubuntu -e bash -c "cd /mnt/c/Users/ol_ta/desktop/java_reports/fastapi-server && python3 -m uvicorn server:app --host 0.0.0.0 --port 8000"
```

### 6.4 Kimlik doğrulama

Varsayılan kullanıcı bilgileri `server.py` içinde ortam değişkenlerinden okunur:

```python
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))
```

Üretim benzeri ortamda `.env` dosyasına şunları yazın:

```text
ADMIN_USERNAME=admin
ADMIN_PASSWORD=guclu_sifre_yazin
JWT_SECRET=uzun_rastgele_bir_deger_yazin
JWT_EXPIRATION_HOURS=24
MANIFESTS_DIR=/mnt/c/Users/ol_ta/desktop/java_reports/manifests
```

Token alma isteği:

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

Token ile run listesi alma:

```bash
curl http://localhost:8000/api/v1/runs \
  -H "Authorization: Bearer TOKEN_DEGERI"
```

## 7. Web Dashboard

### 7.1 Dashboard dosyaları

Bu depoda dashboard şablonu ve statik dosyalar şuradadır:

```text
/mnt/c/Users/ol_ta/desktop/java_reports/fastapi-server/templates/dashboard.html
/mnt/c/Users/ol_ta/desktop/java_reports/fastapi-server/templates/triage.html
/mnt/c/Users/ol_ta/desktop/java_reports/fastapi-server/static/dashboard.css
/mnt/c/Users/ol_ta/desktop/java_reports/fastapi-server/static/chart.min.js
```

Dashboard içinde Chart.js yerel dosyadan çağrılır:

```html
<script src="/static/chart.min.js"></script>
```

Bu sayede dış adreslere bağımlı kalmadan grafik çizilir.

### 7.2 Statik dosya mount ayarı

`server.py` sonunda şu mount tanımları vardır:

```python
app.mount("/reports", StaticFiles(directory=str(MANIFESTS_DIR)), name="reports")
app.mount("/static", StaticFiles(directory="static"), name="static")
```

Sunucuyu `fastapi-server` dizini içinden başlatın. Çünkü `/static` için göreli `static` dizini kullanılır. Başka dizinden başlatmak istiyorsanız mount değerini mutlak yola çevirin:

```python
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
```

### 7.3 Dashboard akışı

Ana sayfa:

```text
http://localhost:8000/
```

Dashboard şunları gösterir:

* Başarı oranı.
* Toplam run sayısı.
* Ortalama süre.
* Trend.
* Pass, fail ve skipped dağılımı.
* Son run tablosu.
* Triage bağlantısı.

Run verileri şu endpoint üzerinden gelir:

```text
GET /api/v1/runs
```

Triage ekranı:

```text
http://localhost:8000/reports/live-demo-001/triage
```

Genel format:

```text
/reports/{runId}/triage
```

## 8. CI/CD Pipeline

### 8.1 Jenkins örneği

Bu depodaki dosya:

```text
/mnt/c/Users/ol_ta/desktop/java_reports/Jenkinsfile
```

Temel akış:

```groovy
pipeline {
  agent any

  environment {
    JAVA_HOME = tool 'JDK21'
    PATH = "${JAVA_HOME}/bin:${PATH}"
  }

  stages {
    stage('Setup Python') {
      steps {
        sh 'python3 --version'
      }
    }

    stage('Install Python Dependencies') {
      steps {
        sh 'pip install -r fastapi-server/requirements.txt'
      }
    }

    stage('Run Java Tests') {
      steps {
        sh '/home/ol_ta/tools/apache-maven-3.9.9/bin/mvn -B test -pl test-core,jira-service,email-service,doors-service,report-model,allure-integration,javalin-server,orchestrator'
      }
    }

    stage('Run Python Tests') {
      steps {
        sh 'cd fastapi-server && python3 -m pytest tests/ -v'
      }
    }

    stage('Generate Allure Report') {
      steps {
        sh 'allure generate --clean test-core/target/allure-results -o allure-report'
      }
    }
  }

  post {
    always {
      allure includeProperties: false, results: [[path: 'test-core/target/allure-results']]
    }
  }
}
```

Hedef projede modül adlarını kendi projenize göre değiştirin. Tek modüllü projede Java test adımı şu hale gelebilir:

```groovy
sh 'mvn -B test'
```

Allure sonuç dizini de tek modüllü yapı için genelde şöyledir:

```groovy
sh 'allure generate --clean target/allure-results -o allure-report'
```

Jenkins credential içinde Jira PAT saklayacaksanız bu depodaki örnek gibi credential kimliği kullanabilirsiniz:

```groovy
withCredentials([string(credentialsId: 'jira-pat-id', variable: 'JIRA_PAT')]) {
    sh 'mvn -B test'
}
```

### 8.2 GitHub Actions örneği

Bu depodaki dosya:

```text
/mnt/c/Users/ol_ta/desktop/java_reports/.github/workflows/test-report.yml
```

Temel akış:

```yaml
name: Test Report Pipeline

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]
  workflow_dispatch:

env:
  JAVA_VERSION: '21'
  PYTHON_VERSION: '3.12'

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up JDK 21
        uses: actions/setup-java@v4
        with:
          java-version: ${{ env.JAVA_VERSION }}
          distribution: 'temurin'

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Install Python dependencies
        run: |
          python3 -m pip install --upgrade pip
          pip install -r fastapi-server/requirements.txt

      - name: Run Java tests
        run: |
          mvn -B test -pl test-core,jira-service,email-service,doors-service,report-model,allure-integration,javalin-server,orchestrator

      - name: Run Python tests
        run: |
          cd fastapi-server && python3 -m pytest tests/ -v

      - name: Generate Allure report
        run: |
          allure generate --clean test-core/target/allure-results -o allure-report

      - name: Upload Allure report artifact
        uses: actions/upload-artifact@v4
        with:
          name: allure-report
          path: allure-report
          retention-days: 30
```

GitHub Actions içinde Jira değerlerini secret olarak saklayın:

```yaml
env:
  JIRA_URL: ${{ secrets.JIRA_URL }}
  JIRA_PAT: ${{ secrets.JIRA_PAT }}
  JIRA_PROJECT_KEY: ${{ secrets.JIRA_PROJECT_KEY }}
```

## 9. Jira Entegrasyonu

### 9.1 Ortam değişkenleri

Bu depodaki örnek dosya:

```text
/mnt/c/Users/ol_ta/desktop/java_reports/.env.example
```

Jira için gerekli alanlar:

```text
JIRA_URL=JIRA_SUNUCU_ADRESI
JIRA_PAT=JIRA_PERSONAL_ACCESS_TOKEN_DEGERI
JIRA_PROJECT_KEY=TEST
```

Orchestrator kullanıyorsanız şu karşılıkları da doldurun:

```text
ORCHESTRATOR_JIRA_URL=JIRA_SUNUCU_ADRESI
ORCHESTRATOR_JIRA_PAT=JIRA_PERSONAL_ACCESS_TOKEN_DEGERI
ORCHESTRATOR_JIRA_PROJECT_KEY=TEST
```

PAT değerini asla repoya yazmayın. Jenkins credential, GitHub secret veya yerel `.env` kullanın.

### 9.2 Java Jira istemcisi

Bu depodaki istemci:

```text
/mnt/c/Users/ol_ta/desktop/java_reports/jira-service/src/main/java/com/testreports/jira/JiraClient.java
```

Öne çıkan davranışlar:

* REST API v2 endpoint yapısını kullanır.
* PAT ile Basic Authentication yapar.
* 429 ve 5xx cevaplarda tekrar dener.
* Aynı dedup anahtarı için aynı oturumda ikinci kez issue açmaz.
* Dosya eki gönderebilir.
* `jira.dry-run` sistem özelliği ile gerçek istek atmadan denenebilir.

Örnek kullanım:

```java
JiraClient client = new JiraClient(System.getenv("JIRA_URL"), System.getenv("JIRA_PAT"));
JiraIssueRequest request = new JiraIssueRequest(
        System.getenv("JIRA_PROJECT_KEY"),
        "Bug",
        "Otomasyon hatası: Login",
        "Cucumber senaryosu başarısız oldu. Allure eklerini kontrol edin."
);
JiraIssueResponse response = client.createIssue(request);
```

Kuru koşu için:

```bash
mvn test -Djira.dry-run=true
```

### 9.3 bug-tracker.json

Bu dosya DOORS numarası ile Jira anahtarını eşler:

```text
/mnt/c/Users/ol_ta/desktop/java_reports/bug-tracker.json
```

Başlangıç içeriği:

```json
{"version": "1.0", "mappings": {}}
```

FastAPI tarafında kullanılan sınıf:

```text
/mnt/c/Users/ol_ta/desktop/java_reports/fastapi-server/bug_tracker.py
```

Yeni eşleşme şu alanları yazar:

```json
{
  "jiraKey": "PROJ-1234",
  "status": "OPEN",
  "firstSeen": "2026-04-26T10:30:00+00:00",
  "lastSeen": "2026-04-26T10:30:00+00:00",
  "scenarioName": "Order Submission",
  "runIds": ["run-2026-04-26-001"],
  "resolution": null
}
```

### 9.4 Web triage akışı

Triage ekranı başarısız senaryoları listeler ve DOORS numarasına göre bug durumunu kontrol eder.

Kullanılan endpoint'ler:

```text
GET  /api/v1/bugs
GET  /api/v1/bugs/{doors_number}
POST /api/v1/bugs/{doors_number}/create
POST /api/v1/runs/{run_id}/scenarios/{scenario_id}/jira
```

Mevcut `server.py` içinde `/api/v1/runs/{run_id}/scenarios/{scenario_id}/jira` endpoint'i örnek olarak `PROJ-123` döndürür. Gerçek Jira bağlantısı için bu noktada `jira-service` istemcisini çağıran bir katman ekleyin.

## 10. DOORS Entegrasyonu

### 10.1 Gereksinim

IBM DOORS batch DXL çalıştırması Windows gerektirir. Bu depodaki Java istemcisi Linux üzerinde gerçek `doors.exe` bulunmazsa çalışmayı atlar. Test double çalıştırılacaksa Linux üzerinde yürütülebilir bir sahte dosya kullanılabilir.

Ortam değişkeni örneği:

```text
DOORS_PATH=C:/Program Files/IBM/DOORS/bin/dxl.exe
```

### 10.2 Java istemcisi

Bu depodaki sınıf:

```text
/mnt/c/Users/ol_ta/desktop/java_reports/doors-service/src/main/java/com/testreports/doors/DoorsClient.java
```

Davranış:

* `RunManifest` içindeki senaryoları okur.
* `doorsAbsNumber` dolu olanları DXL payload içine koyar.
* Geçici JSON dosyası üretir.
* DXL script dosyasını classpath üzerinden geçici dosyaya kopyalar.
* `doors.exe` komutunu batch modda çalıştırır.
* 120 saniye içinde bitmezse timeout hatası verir.

Üretilen payload yapısı:

```json
{
  "runId": "run-123",
  "results": [
    { "absNumber": "DOORS-12345", "status": "failed" }
  ]
}
```

Çalıştırılan komut biçimi:

```text
doors.exe -b DoorsDxlScript.dxl -paramFile <temp-json> -W
```

### 10.3 DXL script

Bu depodaki script:

```text
/mnt/c/Users/ol_ta/desktop/java_reports/doors-service/src/main/resources/DoorsDxlScript.dxl
```

Mevcut script bir şablondur. Kurumsal DOORS alan adlarınıza göre değiştirmeniz gerekir.

Şablonda hedeflenen alanlar:

```dxl
requirement."Last Test Run" = runId
requirement."Automated Test Status" = status
requirement."Automated Test Updated" = today()
save(requirement)
```

Dry run için:

```bash
mvn test -Ddoors.dry.run=true
```

## 11. Sorun Giderme

### 11.1 Allure sonuçları oluşmuyor

Kontrol edin:

```text
test-core/src/test/resources/allure.properties
test-core/src/test/resources/cucumber.properties
```

`cucumber.plugin` içinde Allure adaptörü olmalıdır:

```properties
cucumber.plugin=io.qameta.allure.cucumber7jvm.AllureCucumber7Jvm,json:target/cucumber-report.json,pretty
```

Testten sonra dizini kontrol edin:

```bash
ls test-core/target/allure-results
```

Tek modüllü projede:

```bash
ls target/allure-results
```

### 11.2 Screenshot eklenmiyor

Olası nedenler:

* `WebDriverHolder.setDriver(driver)` çağrılmamış olabilir.
* Driver `TakesScreenshot` desteklemiyor olabilir.
* Hook paketi Cucumber glue içine eklenmemiş olabilir.

Doğru glue örneği:

```properties
cucumber.glue=com.testreports.allure,com.testreports.steps
```

Driver oluşturduktan sonra:

```java
com.testreports.allure.WebDriverHolder.setDriver(driver);
```

### 11.3 Video eklenmiyor

Kontrol edin:

```bash
ffmpeg -version
```

Linux veya WSL ortamında display değeri doğru olmalıdır. Bu depoda varsayılan değer:

```text
:0.0
```

CI ortamında sanal ekran yoksa `x11grab` çalışmayabilir. Böyle bir durumda önce sanal ekran başlatın veya video hook'u sadece uygun ajanlarda açın.

### 11.4 FastAPI sunucusu açılmıyor

Sunucuyu doğru dizinden başlatın:

```bash
cd /mnt/c/Users/ol_ta/desktop/java_reports/fastapi-server
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
```

Port doluysa farklı port kullanın:

```bash
python3 -m uvicorn server:app --host 0.0.0.0 --port 8001
```

Windows tarayıcısından şu adresi deneyin:

```text
http://localhost:8000
```

WSL IP gerektiğinde:

```bash
wsl hostname -I
```

### 11.5 401 Unauthorized

Token yoktur, süresi bitmiştir veya yanlış gönderilmiştir.

Yeni token alın:

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

Header biçimi şu olmalıdır:

```text
Authorization: Bearer TOKEN_DEGERI
```

### 11.6 404 Run bulunamadı

Önce run listesini alın:

```bash
curl http://localhost:8000/api/v1/runs \
  -H "Authorization: Bearer TOKEN_DEGERI"
```

Manifest dizinini kontrol edin:

```text
/mnt/c/Users/ol_ta/desktop/java_reports/manifests
```

`MANIFESTS_DIR` farklı bir yeri gösteriyorsa o dizinde JSON dosyası olmalıdır.

### 11.7 Dashboard CSS veya grafikler yüklenmiyor

`/static` mount ayarını ve çalışma dizinini kontrol edin:

```python
app.mount("/static", StaticFiles(directory="static"), name="static")
```

Sunucuyu `fastapi-server` dizininden başlatmıyorsanız statik dizini mutlak yola alın.

### 11.8 Jira bug açılmıyor

Kontrol listesi:

* `JIRA_URL` doğru mu?
* `JIRA_PAT` geçerli mi?
* `JIRA_PROJECT_KEY` doğru mu?
* Projede Bug issue type var mı?
* Ağ veya proxy Jira erişimini engelliyor mu?

Kuru koşu ile test edin:

```bash
mvn test -Djira.dry-run=true
```

### 11.9 DOORS güncellemesi çalışmıyor

Kontrol listesi:

* Windows ajan kullanılıyor mu?
* `DOORS_PATH` gerçek `doors.exe` veya `dxl.exe` dosyasını gösteriyor mu?
* DXL script kurumunuzdaki alan adlarıyla uyumlu mu?
* `doorsAbsNumber` manifest içinde dolu mu?

Linux üzerinde gerçek DOORS beklenmemelidir. Bu depodaki istemci Linux üzerinde `doors.exe` yoksa atlar.

### 11.10 ChromeDriver başlamıyor

Bu depodaki örnek yollar:

```java
private static final String CHROME_PATH = "/tmp/chrome-linux64/chrome";
private static final String CHROMEDRIVER_PATH = "/tmp/chromedriver-linux64/chromedriver";
```

Hedef projede kendi ajanınıza göre değiştirin. Örnek ChromeOptions:

```java
ChromeOptions options = new ChromeOptions();
options.setBinary(CHROME_PATH);
options.addArguments("--headless=new");
options.addArguments("--disable-gpu");
options.addArguments("--no-sandbox");
options.addArguments("--disable-dev-shm-usage");
System.setProperty("webdriver.chrome.driver", CHROMEDRIVER_PATH);
return new ChromeDriver(options);
```

## 12. Örnek Proje Yapısı

Çok modüllü kurulum için önerilen yapı:

```text
java_reports/
├── pom.xml
├── .env.example
├── bug-tracker.json
├── Jenkinsfile
├── start.sh
├── scripts/
│   └── start-server.bat
├── test-core/
│   ├── pom.xml
│   └── src/test/
│       ├── java/com/testreports/
│       │   ├── config/WebDriverFactory.java
│       │   ├── runner/CucumberTestRunner.java
│       │   └── steps/LoginSteps.java
│       └── resources/
│           ├── allure.properties
│           ├── cucumber.properties
│           └── features/login.feature
├── allure-integration/
│   ├── pom.xml
│   └── src/main/java/com/testreports/allure/
│       ├── ScreenshotHook.java
│       ├── VideoHook.java
│       └── WebDriverHolder.java
├── report-model/
│   ├── pom.xml
│   └── src/main/java/com/testreports/model/
├── jira-service/
│   ├── pom.xml
│   └── src/main/java/com/testreports/jira/
├── doors-service/
│   ├── pom.xml
│   └── src/main/resources/DoorsDxlScript.dxl
├── orchestrator/
│   └── pom.xml
├── fastapi-server/
│   ├── requirements.txt
│   ├── server.py
│   ├── bug_tracker.py
│   ├── models.py
│   ├── static/
│   │   ├── chart.min.js
│   │   └── dashboard.css
│   └── templates/
│       ├── dashboard.html
│       └── triage.html
└── manifests/
    └── sample-run-001.json
```

Tek modüllü hedef projede sade yapı:

```text
my-selenium-project/
├── pom.xml
├── bug-tracker.json
├── manifests/
├── fastapi-server/
├── src/test/java/com/sirket/proje/
│   ├── allure/
│   │   ├── ScreenshotHook.java
│   │   ├── VideoHook.java
│   │   └── WebDriverHolder.java
│   ├── config/WebDriverFactory.java
│   ├── runner/CucumberTestRunner.java
│   └── steps/
└── src/test/resources/
    ├── allure.properties
    ├── cucumber.properties
    └── features/
```

Manifest dosyası örneği:

```json
{
  "runId": "run-2026-04-26-001",
  "timestamp": "2026-04-26T10:30:00Z",
  "totalScenarios": 2,
  "passed": 1,
  "failed": 1,
  "skipped": 0,
  "duration": "PT58.125S",
  "scenarios": [
    {
      "id": "scenario-002",
      "name": "Order Submission",
      "status": "failed",
      "duration": "PT42.891S",
      "doorsAbsNumber": "ABS-12346",
      "tags": ["checkout", "regression"],
      "steps": [
        { "name": "Navigate to checkout", "status": "passed", "errorMessage": null },
        { "name": "Submit order", "status": "failed", "errorMessage": "Payment processing failed: card declined" }
      ],
      "attachments": [
        { "name": "order-failure.png", "type": "image/png", "path": "screenshots/order-failure.png" }
      ]
    }
  ]
}
```

FastAPI Pydantic modeli şu alanları bekler:

```python
class ScenarioResult(BaseModel):
    id: str
    name: str
    status: str
    duration: str
    doorsAbsNumber: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    steps: List[StepResult] = Field(default_factory=list)
    attachments: List[Attachment] = Field(default_factory=list)

class RunManifest(BaseModel):
    runId: str
    timestamp: datetime
    totalScenarios: int
    passed: int
    failed: int
    skipped: int
    duration: str
    scenarios: List[ScenarioResult]
```

## 13. Hızlı Başlangıç

Beş dakikalık yerel kurulum için şu sırayı izleyin.

### Adım 1, bağımlılıkları kontrol edin

```bash
java -version
mvn -version
python3 --version
allure --version
ffmpeg -version
```

### Adım 2, Python paketlerini kurun

```bash
cd /mnt/c/Users/ol_ta/desktop/java_reports
pip install -r fastapi-server/requirements.txt
```

### Adım 3, Java testlerini çalıştırın

```bash
cd /mnt/c/Users/ol_ta/desktop/java_reports
export PATH="/home/ol_ta/tools/apache-maven-3.9.9/bin:$PATH"
mvn -pl test-core test
```

### Adım 4, Allure raporu üretin

```bash
allure generate --clean test-core/target/allure-results -o allure-report
```

### Adım 5, FastAPI dashboard başlatın

```bash
cd /mnt/c/Users/ol_ta/desktop/java_reports/fastapi-server
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
```

### Adım 6, tarayıcıdan açın

```text
http://localhost:8000
```

Giriş yaptıktan sonra dashboard run listesini gösterir. Hata kartları için bir run satırındaki triage bağlantısına tıklayın veya şu formatı kullanın:

```text
http://localhost:8000/reports/{runId}/triage
```

### Adım 7, CI içine alın

Jenkins için `Jenkinsfile` örneğini, GitHub Actions için `.github/workflows/test-report.yml` örneğini kendi proje adlarınıza göre düzenleyin. En küçük pipeline sırası şu olmalıdır:

1. Java kur.
2. Python kur.
3. `pip install -r fastapi-server/requirements.txt` çalıştır.
4. `mvn -B test` çalıştır.
5. Python testleri varsa çalıştır.
6. `allure generate --clean ...` çalıştır.
7. Allure raporunu artifact olarak sakla.

Bu adımlar tamamlandığında hedef Java Selenium Cucumber projesi, Allure ekleri, FastAPI dashboard, triage ekranı, Jira eşleştirme ve DOORS batch güncelleme akışına hazır hale gelir.
