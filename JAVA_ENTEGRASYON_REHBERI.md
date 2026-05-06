# Java → FastAPI Entegrasyon Rehberi

Bu rehber, mevcut veya yeni bir Java/Cucumber/Selenium projesini bu raporlama platformuna bağlamak için gereken **her adımı** içerir. Sistemi hiç bilmeden sıfırdan başlayıp çalışır hale getirebilirsiniz.

---

## İçindekiler

1. [Sistemin çalışma mantığı](#1-sistemin-çalışma-mantığı)
2. [Ön gereksinimler](#2-ön-gereksinimler)
3. [pom.xml yapılandırması](#3-pomxml-yapılandırması)
4. [Zorunlu Java dosyaları](#4-zorunlu-java-dosyaları)
5. [Properties dosyaları](#5-properties-dosyaları)
6. [Feature dosyası yazım kuralları](#6-feature-dosyası-yazım-kuralları)
7. [Step sınıflarında WebDriver bağlantısı](#7-step-sınıflarında-webdriver-bağlantısı)
8. [Senaryo bağımlılıkları ve retry](#8-senaryo-bağımlılıkları-ve-retry)
9. [Testleri çalıştırma](#9-testleri-çalıştırma)
10. [Allure sonuçlarını FastAPI'ye gönderme](#10-allure-sonuçlarını-fastapiye-gönderme)
11. [CI/CD entegrasyonu](#11-cicd-entegrasyonu)
12. [Sık yapılan hatalar](#12-sık-yapılan-hatalar)

---

## 1. Sistemin çalışma mantığı

```
Java Testleri (Cucumber + Selenium)
        │
        │  @After hook → Allure'a screenshot/video ekle
        ▼
target/allure-results/   ← Allure JSON dosyaları burada üretilir
        │
        │  FastAPI sunucu başlangıcında veya ingest endpoint'iyle okur
        ▼
FastAPI Dashboard (http://localhost:8000)
        │
        ├── Run listesi, pass/fail/skip sayıları
        ├── Senaryo detayları, hata mesajları
        ├── DOORS numarasına göre Jira auto-match
        └── Triage: hata kararları (Jira aç, pass işaretle, skip işaretle)
```

FastAPI, Java tarafında **hiçbir değişiklik gerektirmez**. Java sadece Allure sonuçlarını üretir. FastAPI bu sonuçları okur.

---

## 2. Ön gereksinimler

| Araç | Minimum Sürüm | Kontrol |
|---|---|---|
| Java JDK | 17 veya 21 | `java -version` |
| Apache Maven | 3.8+ | `mvn -version` |
| Google Chrome | Güncel | `google-chrome --version` |
| ChromeDriver | Chrome ile eşleşmeli | `chromedriver --version` |
| Allure CLI | 2.25+ | `allure --version` |
| Python | 3.10+ | `python3 --version` |

Allure CLI kurulumu (Linux):
```bash
curl -LO https://github.com/allure-framework/allure2/releases/download/2.33.0/allure-2.33.0.tgz
tar -xzf allure-2.33.0.tgz -C ~/tools/
export PATH="$PATH:$HOME/tools/allure-2.33.0/bin"
```

---

## 3. pom.xml yapılandırması

### 3.1 Tek modüllü proje (en yaygın durum)

`pom.xml` dosyanıza aşağıdaki bloğu ekleyin. Zaten Spring Boot veya başka bir parent'ınız varsa `<parent>` bloğunu kaldırın, sadece `<properties>` ve `<dependencies>` kısımlarını alın.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           http://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.sirket.proje</groupId>
  <artifactId>test-automation</artifactId>
  <version>1.0.0-SNAPSHOT</version>
  <packaging>jar</packaging>

  <properties>
    <java.version>21</java.version>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <maven.compiler.source>21</maven.compiler.source>
    <maven.compiler.target>21</maven.compiler.target>

    <cucumber.version>7.18.0</cucumber.version>
    <selenium.version>4.21.0</selenium.version>
    <junit.version>5.10.2</junit.version>
    <junit.platform.version>1.10.2</junit.platform.version>
    <allure.version>2.25.0</allure.version>
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
    <dependency>
      <groupId>io.cucumber</groupId>
      <artifactId>cucumber-core</artifactId>
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
      <artifactId>junit-jupiter-api</artifactId>
      <version>${junit.version}</version>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter-engine</artifactId>
      <version>${junit.version}</version>
    </dependency>
    <dependency>
      <groupId>org.junit.platform</groupId>
      <artifactId>junit-platform-launcher</artifactId>
      <version>${junit.platform.version}</version>
    </dependency>
    <dependency>
      <groupId>org.junit.platform</groupId>
      <artifactId>junit-platform-suite</artifactId>
      <version>${junit.platform.version}</version>
    </dependency>

    <!-- Allure + Cucumber entegrasyonu -->
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

  </dependencies>

  <build>
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
        <version>3.5.2</version>
        <configuration>
          <failIfNoTests>false</failIfNoTests>
          <!-- Sadece runner'ı çalıştır, diğer *Test.java dosyaları dahil olmasın -->
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
  </build>

</project>
```

### 3.2 Çok modüllü proje

Parent `pom.xml`'e `<dependencyManagement>` bloğunu ekleyin (sürümleri tek yerden yönetin), test modülünün `pom.xml`'ine ise sadece `<dependencies>` bloğunu (sürümsüz) koyun. Bu depodaki `pom.xml` ve `test-core/pom.xml` tam bir örnek olarak kullanılabilir.

---

## 4. Zorunlu Java dosyaları

Aşağıdaki **5 Java dosyasını** kendi projenizin test kaynak dizinine kopyalayın. Paket adını kendi paket yapınıza göre değiştirin.

```
src/test/java/
└── com/sirket/proje/
    ├── allure/
    │   ├── WebDriverHolder.java        ← ThreadLocal driver tutucusu
    │   ├── ScreenshotHook.java         ← Başarısızlıkta ekran görüntüsü
    │   ├── VideoHook.java              ← Başarısızlıkta video kaydı
    │   └── FailureLocationCapture.java ← Hata lokasyonu Allure'a yazar
    └── runner/
        └── CucumberTestRunner.java     ← Cucumber suite tanımı
```

### 4.1 WebDriverHolder.java

Driver'ı thread-safe tutan yardımcı sınıf. Her step sınıfı driver oluştururken buraya kaydetmek **zorunludur**, aksi hâlde screenshot çekilemez.

```java
package com.sirket.proje.allure;

import org.openqa.selenium.WebDriver;

public final class WebDriverHolder {

    private static final ThreadLocal<WebDriver> driver = new ThreadLocal<>();

    private WebDriverHolder() {}

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

### 4.2 ScreenshotHook.java

Senaryo başarısız olduğunda Allure'a PNG ekran görüntüsü ekler.

```java
package com.sirket.proje.allure;

import io.cucumber.java.After;
import io.cucumber.java.Scenario;
import io.qameta.allure.Allure;
import org.openqa.selenium.OutputType;
import org.openqa.selenium.TakesScreenshot;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.WebDriverException;
import java.io.ByteArrayInputStream;

public class ScreenshotHook {

    @After(order = 100)
    public void captureScreenshot(Scenario scenario) {
        if (!scenario.isFailed()) return;

        WebDriver driver = WebDriverHolder.getDriver();
        if (driver == null || !(driver instanceof TakesScreenshot)) return;

        try {
            byte[] shot = ((TakesScreenshot) driver).getScreenshotAs(OutputType.BYTES);
            Allure.addAttachment("Screenshot", "image/png",
                new ByteArrayInputStream(shot), "png");
        } catch (WebDriverException e) {
            System.err.println("ScreenshotHook: " + e.getMessage());
        }
    }
}
```

### 4.3 VideoHook.java

`ffmpeg` ile ekran kaydı yapar. Senaryo başarılı olursa videoyu siler, başarısız olursa Allure'a ekler. `ffmpeg` kurulu değilse sessizce atlar.

```java
package com.sirket.proje.allure;

import io.cucumber.java.After;
import io.cucumber.java.Before;
import io.cucumber.java.Scenario;
import io.qameta.allure.Allure;
import java.io.*;
import java.nio.file.*;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.concurrent.atomic.AtomicReference;
import java.util.logging.*;

public class VideoHook {

    private static final Logger LOG = Logger.getLogger(VideoHook.class.getName());
    private static final Path VIDEO_DIR = Paths.get("target/videos");
    private static final DateTimeFormatter FMT = DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss");

    private final AtomicReference<Process> proc = new AtomicReference<>();
    private final AtomicReference<Path> videoPath = new AtomicReference<>();

    @Before(order = 1)
    public void startVideo(Scenario scenario) {
        try { Files.createDirectories(VIDEO_DIR); } catch (IOException ignored) {}

        String name = scenario.getName().replaceAll("[^a-zA-Z0-9_-]", "_");
        Path out = VIDEO_DIR.resolve(name + "_" + LocalDateTime.now().format(FMT) + ".mp4");

        try {
            ProcessBuilder pb = new ProcessBuilder(
                "ffmpeg", "-f", "x11grab", "-framerate", "15",
                "-video_size", "1920x1080", "-i", ":0.0",
                "-c:v", "libx264", "-preset", "ultrafast",
                "-pix_fmt", "yuv420p", "-y", out.toString()
            );
            pb.redirectErrorStream(true);
            Process p = pb.start();
            if (p.isAlive()) { proc.set(p); videoPath.set(out); }
        } catch (IOException e) {
            // ffmpeg kurulu değilse devam et
        }
    }

    @After(order = 200)
    public void stopVideo(Scenario scenario) {
        Process p = proc.getAndSet(null);
        if (p != null && p.isAlive()) {
            p.destroy();
            try { p.waitFor(); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
        }

        Path vp = videoPath.getAndSet(null);
        if (vp == null) return;

        if (scenario.isFailed()) {
            attachVideo(vp);
        } else {
            try { Files.deleteIfExists(vp); } catch (IOException ignored) {}
        }
    }

    private void attachVideo(Path vp) {
        try {
            if (Files.exists(vp)) {
                Allure.addAttachment("Video", "video/mp4",
                    new ByteArrayInputStream(Files.readAllBytes(vp)), "mp4");
            }
        } catch (IOException e) {
            LOG.warning("VideoHook attach failed: " + e.getMessage());
        }
    }
}
```

> **Not:** CI ortamında sanal ekran yoksa `x11grab` çalışmaz. Headless CI için `Xvfb` kurun veya VideoHook'u devre dışı bırakın. MacOS'ta `-f avfoundation` kullanın.

### 4.4 FailureLocationCapture.java

Başarısız senaryonun feature dosyası satırını Allure label olarak kaydeder. Triage ekranında hata lokasyonu gösterilir.

```java
package com.sirket.proje.allure;

import io.cucumber.plugin.ConcurrentEventListener;
import io.cucumber.plugin.event.*;
import io.qameta.allure.Allure;
import java.net.URI;

public class FailureLocationCapture implements ConcurrentEventListener {

    private static final Object LOCK = new Object();

    @Override
    public void setEventPublisher(EventPublisher publisher) {
        publisher.registerHandlerFor(TestCaseFinished.class, this::onFinished);
    }

    private void onFinished(TestCaseFinished event) {
        if (event.getResult().getStatus() != Status.FAILED) return;
        TestCase tc = event.getTestCase();
        String loc = tc.getUri() + ":" + tc.getLocation().getLine();
        synchronized (LOCK) {
            Allure.label("failure_location", loc);
            Allure.description("Failed at: " + loc);
        }
    }
}
```

### 4.5 CucumberTestRunner.java

Cucumber suite'ini tanımlar. `GLUE_PROPERTY_NAME` değerindeki **iki paket zorunludur**:
- `com.sirket.proje.allure` — hook sınıfları (ScreenshotHook, VideoHook, vb.)
- `com.sirket.proje.steps` — kendi step tanımlarınız

```java
package com.sirket.proje.runner;

import org.junit.platform.suite.api.*;
import static io.cucumber.junit.platform.engine.Constants.*;

@Suite
@IncludeEngines("cucumber")
@SelectClasspathResource("features")   // src/test/resources/features dizini
@ConfigurationParameter(
    key   = PLUGIN_PROPERTY_NAME,
    value = "io.qameta.allure.cucumber7jvm.AllureCucumber7Jvm,"
          + "com.sirket.proje.allure.FailureLocationCapture,"
          + "json:target/cucumber-report.json,pretty"
)
@ConfigurationParameter(
    key   = GLUE_PROPERTY_NAME,
    value = "com.sirket.proje.allure,com.sirket.proje.steps"
)
public class CucumberTestRunner {}
```

**Kontrol:** Paket adları `cucumber.properties` dosyasındaki `cucumber.glue` değeriyle **aynı** olmalıdır (bir sonraki bölümde).

---

## 5. Properties dosyaları

### 5.1 src/test/resources/cucumber.properties

```properties
cucumber.publish.quiet=true
cucumber.plugin=io.qameta.allure.cucumber7jvm.AllureCucumber7Jvm,\
  com.sirket.proje.allure.FailureLocationCapture,\
  json:target/cucumber-report.json,\
  pretty
cucumber.glue=com.sirket.proje.allure,com.sirket.proje.steps
```

> `cucumber.plugin` ve runner'daki `PLUGIN_PROPERTY_NAME` değerleri aynı anda tanımlıysa Cucumber ikisini birleştirir ve Allure plugin iki kez çalışabilir. Sadece birini kullanın: ya `cucumber.properties`'e yazın, ya da runner'a `@ConfigurationParameter` ile. Bu depoda runner'a yazılmış, `cucumber.properties` yedek olarak var.

### 5.2 src/test/resources/allure.properties

```properties
allure.results.directory=target/allure-results
allure.report.directory=target/allure-report
```

Bu iki satır yeterli. Allure sonuçları `target/allure-results` dizinine yazılır. FastAPI bu dizini okur.

---

## 6. Feature dosyası yazım kuralları

### 6.1 DOORS numarası etiketi

```gherkin
@DOORS-12345
Feature: Ödeme Modülü

  @smoke @DOORS-12346
  Scenario: Başarılı ödeme
    Given kullanıcı ödeme sayfasındadır
    When geçerli kart bilgisi girilir
    Then ödeme onaylanır

  @smoke @DOORS-12347
  Scenario: Geçersiz kart
    Given kullanıcı ödeme sayfasındadır
    When geçersiz kart girilir
    Then hata mesajı gösterilir
```

**Kurallar:**
- Etiket `@DOORS-` ile başlamalı, arkasından rakam gelmeli: `@DOORS-12345`
- Büyük/küçük harf fark etmez: `@doors-12345` de çalışır
- Feature düzeyinde etiket tüm senaryolara uygulanır — bir feature'daki tüm senaryolar aynı DOORS numarasına bağlanacaksa feature düzeyine koyun
- Her senaryonun kendi DOORS numarası varsa senaryo düzeyine koyun

**Hatalı format** (auto-match çalışmaz):
```gherkin
@DOORS-ABC      ← Rakam olmalı
@doors12345     ← Tire olmalı
@DOORS_12345    ← Alt çizgi değil, tire olmalı
```

### 6.2 Senaryo ID ve bağımlılık etiketleri (opsiyonel)

Senaryolar arasında çalışma sırası bağımlılığı varsa:

```gherkin
@id:Kurulum @DOORS-10001
Scenario: Veritabanı kurulumu
  Given veritabanı hazırlanır

@id:Giris @dep:Kurulum @DOORS-10002
Scenario: Kullanıcı girişi
  Given kurulum tamamdır
  When kullanıcı giriş yapar

@id:Sepet @dep:Giris,Kurulum @DOORS-10003
Scenario: Sepete ürün ekleme
  Given kullanıcı giriş yapmıştır
  When ürün sepete eklenir
```

`@dep:` etiketindeki senaryo başarısız olursa, ona bağlı senaryolar **otomatik skip** edilir.

---

## 7. Step sınıflarında WebDriver bağlantısı

Her step sınıfında driver oluştururken `WebDriverHolder.setDriver(driver)` çağırmak **zorunludur**. Aksi hâlde screenshot hook driver'ı bulamaz.

### 7.1 Basit step sınıfı örneği

```java
package com.sirket.proje.steps;

import com.sirket.proje.allure.WebDriverHolder;
import io.cucumber.java.After;
import io.cucumber.java.en.Given;
import io.cucumber.java.en.Then;
import io.cucumber.java.en.When;
import org.openqa.selenium.By;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.chrome.ChromeDriver;
import org.openqa.selenium.chrome.ChromeOptions;
import org.openqa.selenium.support.ui.WebDriverWait;
import java.time.Duration;

public class OdemeStepler {

    private WebDriver driver;

    @Given("kullanıcı ödeme sayfasındadır")
    public void kullanici_odeme_sayfasinda() {
        ChromeOptions opts = new ChromeOptions();
        opts.addArguments("--headless=new", "--no-sandbox", "--disable-dev-shm-usage");
        driver = new ChromeDriver(opts);

        // ─── ZORUNLU: hook'ların driver'ı bulabilmesi için ───
        WebDriverHolder.setDriver(driver);

        driver.get("https://uygulamaniz.local/odeme");
    }

    @When("geçerli kart bilgisi girilir")
    public void gecerli_kart_gir() {
        driver.findElement(By.id("kart-no")).sendKeys("4111111111111111");
        driver.findElement(By.id("son-tarih")).sendKeys("12/26");
        driver.findElement(By.id("cvv")).sendKeys("123");
        driver.findElement(By.id("odeme-btn")).click();
    }

    @Then("ödeme onaylanır")
    public void odeme_onaylandi() {
        WebDriverWait wait = new WebDriverWait(driver, Duration.ofSeconds(10));
        wait.until(d -> d.findElement(By.cssSelector(".onay-mesaji")).isDisplayed());
    }

    @After(order = 1001)          // Screenshot hook'tan (100) sonra çalışır
    public void kapat() {
        if (driver != null) {
            driver.quit();
            WebDriverHolder.removeDriver();  // ← Temizlik zorunlu
        }
    }
}
```

### 7.2 WebDriverFactory (merkezi driver yönetimi)

Birden fazla step sınıfı aynı driver'ı kullanacaksa factory + holder birlikte kullanın:

```java
package com.sirket.proje.config;

import com.sirket.proje.allure.WebDriverHolder;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.chrome.ChromeDriver;
import org.openqa.selenium.chrome.ChromeOptions;

public class WebDriverFactory {

    public static WebDriver createAndRegister() {
        ChromeOptions opts = new ChromeOptions();
        opts.addArguments("--headless=new", "--no-sandbox", "--disable-dev-shm-usage");
        // İstediğiniz ChromeDriver yolunu belirtin
        // System.setProperty("webdriver.chrome.driver", "/usr/bin/chromedriver");
        WebDriver driver = new ChromeDriver(opts);
        WebDriverHolder.setDriver(driver);   // ← Her zaman kaydet
        return driver;
    }

    public static void quit(WebDriver driver) {
        if (driver != null) {
            driver.quit();
            WebDriverHolder.removeDriver();
        }
    }
}
```

Step sınıfında kullanımı:

```java
@Given("kullanıcı giriş sayfasındadır")
public void giris_sayfasi() {
    driver = WebDriverFactory.createAndRegister();
    driver.get("https://uygulamaniz.local/giris");
}

@After(order = 1001)
public void kapat() {
    WebDriverFactory.quit(driver);
}
```

### 7.3 Hook çalışma sırası (order)

| Hook | Order | Ne yapar |
|---|---|---|
| `VideoHook @Before` | 1 | Kayıt başlatır (en erken) |
| `VideoHook @After` | 200 | Kaydı durdurur |
| `ScreenshotHook @After` | 100 | Screenshot çeker |
| Step sınıfı `@After` | 1001 | Driver'ı kapatır (en geç) |

**Kritik:** Driver kapanmadan önce screenshot alınmalıdır. Bu yüzden step `@After(order = 1001)` ile screenshot hook `@After(order = 100)`'dan **büyük** order değeri kullanır. Cucumber order'ı küçükten büyüğe çalıştırır (100 önce, 1001 sonra).

---

## 8. Senaryo bağımlılıkları ve retry

### 8.1 Retry ile çalıştırma

Başarısız senaryoları N kez yeniden deneyen `RetryTestRunner` şu komutu kullanır:

```bash
mvn test -Dretry.count=3
```

Bu komut:
1. Normal `CucumberTestRunner`'ı devre dışı bırakır
2. `RetryTestRunner`'ı aktif eder
3. Başarısız senaryoları 3 kez daha çalıştırır
4. Bağımlı senaryolar için topolojik sıralama yapar

**`RetryTestRunner.java`** bu depodaki `test-core/src/test/java/com/testreports/runner/RetryTestRunner.java` dosyasıdır. Paket adını kendi projenize göre değiştirerek kopyalayın.

### 8.2 Bağımlılık kuralları

```gherkin
@id:A @DOORS-001
Scenario: A - Bağımsız

@id:B @dep:A @DOORS-002
Scenario: B - A'ya bağımlı

@id:C @dep:A,B @DOORS-003
Scenario: C - Hem A hem B'ye bağımlı
```

- A başarısız → B ve C skip
- A başarılı, B başarısız → C skip
- A ve B başarılı → C çalışır

---

## 9. Testleri çalıştırma

### 9.1 Tüm testler

```bash
mvn test
```

### 9.2 Tag filtresiyle

```bash
# Sadece smoke testleri
mvn test -Dcucumber.filter.tags="@smoke"

# Birden fazla tag (AND)
mvn test -Dcucumber.filter.tags="@smoke and @DOORS-12345"

# Birden fazla tag (OR)
mvn test -Dcucumber.filter.tags="@smoke or @regression"

# Tag hariç
mvn test -Dcucumber.filter.tags="not @wip"
```

### 9.3 Retry ile

```bash
mvn test -Dretry.count=2
```

### 9.4 Allure raporu üretme

```bash
allure generate --clean target/allure-results -o target/allure-report
allure open target/allure-report   # tarayıcıda açar
```

### 9.5 Sonuçların nerede olduğunu kontrol etme

```bash
ls target/allure-results/
# *-result.json dosyaları burada olmalı
# Boşsa test hiç çalışmamış veya Allure plugin aktif değil
```

---

## 10. Allure sonuçlarını FastAPI'ye gönderme

### 10.1 FastAPI'yi başlatma

```bash
cd /path/to/fastapi-server

# .env dosyasını ayarla (ilk kurulumda)
cat > .env << 'EOF'
ADMIN_USERNAME=admin
ADMIN_PASSWORD=şifreniz
JWT_SECRET=uzun_rastgele_string
MANIFESTS_DIR=/path/to/java-project/manifests
JIRA_DRY_RUN=true
JIRA_PROJECT_KEY=PROJ
EOF

pip install -r requirements.txt
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
```

### 10.2 MANIFESTS_DIR nedir?

FastAPI manifest JSON dosyalarını okur. Bu dosyalar Allure sonuçlarından üretilir.

**Seçenek A: FastAPI otomatik üretsin (önerilen)**

FastAPI admin panelinden "Yeni Koşu Başlat" butonuyla testleri çalıştırırsanız sonuçlar otomatik işlenir.

**Seçenek B: Manuel ingest**

Testleri dışarıda çalıştırdıktan sonra Allure sonuçlarını FastAPI'ye gönderin:

```bash
# Token al
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"şifreniz"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')

# Allure sonuçlarını sıkıştır ve gönder
cd target
zip -r allure-results.zip allure-results/
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@allure-results.zip"
```

**Seçenek C: Paylaşılan dizin**

`MANIFESTS_DIR` ortam değişkenini Java projenizin manifest çıktı dizinine ayarlayın. Java'nın ürettiği manifest'ler FastAPI tarafından otomatik okunur:

```bash
# Java projesinin manifest çıktısı: /home/kullanici/java-proje/manifests/
export MANIFESTS_DIR=/home/kullanici/java-proje/manifests
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
```

### 10.3 Doğrulama

Dashboard'u açın: `http://localhost:8000`

Beklentiler:
- Run listesinde son koşu görünür
- Passed/Failed/Skipped sayıları doğru
- Başarısız senaryolarda DOORS numarası etiket olarak görünür
- Triage sayfasında auto-match çalışıyorsa Jira issue'ları otomatik bağlanır

---

## 11. CI/CD entegrasyonu

### 11.1 GitHub Actions — tam örnek

```yaml
name: Test Otomasyon

on:
  push:
    branches: [main, develop]
  pull_request:
  workflow_dispatch:
    inputs:
      tags:
        description: 'Cucumber tag filtresi (örn: @smoke)'
        default: '@smoke'

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Java kur
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - name: Python kur
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Allure CLI kur
        run: |
          curl -LO https://github.com/allure-framework/allure2/releases/download/2.33.0/allure-2.33.0.tgz
          tar -xzf allure-2.33.0.tgz -C $HOME
          echo "$HOME/allure-2.33.0/bin" >> $GITHUB_PATH

      - name: FastAPI bağımlılıkları kur
        run: pip install -r fastapi-server/requirements.txt

      - name: Testleri çalıştır
        run: |
          TAG="${{ github.event.inputs.tags || '@smoke' }}"
          mvn -B test -Dcucumber.filter.tags="$TAG"

      - name: Allure raporu üret
        if: always()
        run: allure generate --clean target/allure-results -o target/allure-report

      - name: FastAPI sunucusunu başlat
        if: always()
        env:
          ADMIN_PASSWORD: ${{ secrets.REPORT_ADMIN_PASSWORD }}
          JWT_SECRET:     ${{ secrets.REPORT_JWT_SECRET }}
          JIRA_URL:       ${{ secrets.JIRA_URL }}
          JIRA_PAT:       ${{ secrets.JIRA_PAT }}
          JIRA_PROJECT_KEY: ${{ secrets.JIRA_PROJECT_KEY }}
        run: |
          cd fastapi-server
          python3 -m uvicorn server:app --host 0.0.0.0 --port 8000 &
          sleep 4

      - name: Sonuçları gönder
        if: always()
        run: |
          TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
            -H 'Content-Type: application/json' \
            -d "{\"username\":\"admin\",\"password\":\"$REPORT_ADMIN_PASSWORD\"}" \
            | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')
          zip -r results.zip target/allure-results/
          curl -X POST http://localhost:8000/api/v1/ingest \
            -H "Authorization: Bearer $TOKEN" \
            -F "file=@results.zip"
        env:
          REPORT_ADMIN_PASSWORD: ${{ secrets.REPORT_ADMIN_PASSWORD }}

      - name: Artefaktları sakla
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-raporu-${{ github.run_number }}
          path: |
            target/allure-report/
            target/allure-results/
            target/cucumber-report.json
```

### 11.2 Jenkins — tam Pipeline örneği

```groovy
pipeline {
    agent any

    parameters {
        string(name: 'TAGS', defaultValue: '@smoke', description: 'Cucumber tag filtresi')
        string(name: 'RETRY_COUNT', defaultValue: '0', description: 'Başarısız test retry sayısı')
    }

    environment {
        JAVA_HOME    = tool 'JDK21'
        ALLURE_HOME  = '/opt/allure-2.33.0'
        PATH         = "${JAVA_HOME}/bin:${ALLURE_HOME}/bin:${PATH}"
        JIRA_URL     = credentials('jira-url')
        JIRA_PAT     = credentials('jira-pat')
        ADMIN_PASS   = credentials('report-admin-password')
        JWT_SECRET   = credentials('report-jwt-secret')
    }

    stages {
        stage('Python kurulum') {
            steps {
                sh 'pip install -r fastapi-server/requirements.txt'
            }
        }

        stage('Testleri çalıştır') {
            steps {
                script {
                    def cmd = "mvn -B test -Dcucumber.filter.tags='${params.TAGS}'"
                    if (params.RETRY_COUNT.toInteger() > 0) {
                        cmd += " -Dretry.count=${params.RETRY_COUNT}"
                    }
                    sh cmd
                }
            }
            post {
                always {
                    sh 'allure generate --clean target/allure-results -o target/allure-report || true'
                }
            }
        }

        stage('FastAPI başlat ve ingest') {
            steps {
                sh '''
                    cd fastapi-server
                    ADMIN_PASSWORD=$ADMIN_PASS JWT_SECRET=$JWT_SECRET \
                    JIRA_URL=$JIRA_URL JIRA_PAT=$JIRA_PAT \
                    python3 -m uvicorn server:app --host 0.0.0.0 --port 8000 &
                    sleep 5

                    TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
                      -H 'Content-Type: application/json' \
                      -d "{\"username\":\"admin\",\"password\":\"$ADMIN_PASS\"}" \
                      | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')

                    zip -r results.zip ../target/allure-results/
                    curl -X POST http://localhost:8000/api/v1/ingest \
                      -H "Authorization: Bearer $TOKEN" \
                      -F "file=@results.zip"
                '''
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'target/allure-report/**,target/cucumber-report.json',
                             allowEmptyArchive: true
            allure includeProperties: false, jdk: '', results: [[path: 'target/allure-results']]
        }
    }
}
```

---

## 12. Sık yapılan hatalar

### "No allure-results dizini" — Allure plugin aktif değil

**Belirti:** `target/allure-results/` dizini boş veya yok.

**Neden:** `allure-cucumber7-jvm` bağımlılığı eksik ya da `cucumber.plugin` satırında Allure plugin tanımlı değil.

**Çözüm:**
1. `pom.xml`'de `allure-cucumber7-jvm` bağımlılığını kontrol edin.
2. `cucumber.properties`'te şu satırın olduğunu doğrulayın:
   ```
   cucumber.plugin=io.qameta.allure.cucumber7jvm.AllureCucumber7Jvm,...
   ```
3. Hem runner'da hem properties'te tanımlıysa birini silin.

---

### Screenshot eklenmiyor

**Belirti:** Başarısız senaryo Allure'da var ama screenshot eki yok.

**Neden:** `WebDriverHolder.setDriver(driver)` çağrılmamış.

**Çözüm:** Her `@Given` veya `@Before` içinde driver oluştururken hemen ardından:
```java
WebDriverHolder.setDriver(driver);
```

---

### Triage'da DOORS numarası boş

**Belirti:** Senaryo dashboard'da görünüyor ama DOORS etiketi yok.

**Neden:** Etiket formatı yanlış.

**Kontrol:**
```gherkin
@DOORS-12345   ← doğru
@DOORS-ABC     ← yanlış (rakam olmalı)
@doors12345    ← yanlış (tire eksik)
```

---

### "cucumber.glue" hatası — step bulunamıyor

**Belirti:** `io.cucumber.java.UndefinedStepException` veya step tanımsız uyarısı.

**Neden:** `cucumber.glue` değerinde step paketiniz eksik.

**Çözüm:** `cucumber.properties` ve runner `@ConfigurationParameter` içindeki `GLUE_PROPERTY_NAME` değerinde kendi step paketinizin adı olduğunu kontrol edin:
```
cucumber.glue=com.sirket.proje.allure,com.sirket.proje.steps
```

---

### Auto-match 0 döndürüyor

**Belirti:** Triage'da `matched: 0`, senaryoların DOORS numarası var ama Jira bağlanmıyor.

**Neden seçenekleri:**
1. `mock_jira.json`'daki `doors_number` değeri etiketle eşleşmiyor
2. Tüm Jira issue'ları kapalı statüde (`Closed`, `Done`, vs.)
3. Gerçek Jira'da `DOORS Number` custom field tanımlı değil

**Çözüm:**
```bash
# dry-run modunda mock_jira.json'ı kontrol et
cat fastapi-server/mock_jira.json

# Gerçek Jira'da JQL ile test et
# project = PROJ AND "DOORS Number" ~ "12345"
```

---

### Maven "No tests were executed"

**Belirti:** `mvn test` çalışıyor ama senaryo koşulmuyor.

**Neden:** Surefire `CucumberTestRunner.java`'yı bulamıyor.

**Çözüm:**
```xml
<!-- pom.xml içinde -->
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

Runner dosyasının `src/test/java/` altında olduğunu ve derlenebildiğini kontrol edin.

---

### 401 Unauthorized — FastAPI API'si

**Belirti:** `curl` komutları 401 döndürüyor.

**Çözüm:**
```bash
# Token yenile
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"şifreniz"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')

# Sonra isteği tekrar at
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/runs
```
