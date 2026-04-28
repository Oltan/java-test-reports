# surefirePlugin-master → java-test-reports Geçiş Rehberi

Bu rehber, `surefirePlugin-master` ile çalışan ayrı bir projeyi `java-test-reports` raporlama sistemine taşımak için gereken adımları kapsar.

---

## 1. Neden Değişiyor?

`surefirePlugin-master` şu anda tek başına çalışır ve `ExtentReports` HTML raporu üretir. Bu rapor FastAPI dashboard'a bağlı değildir. `java-test-reports` sistemi ise Allure, JSON manifest, FastAPI dashboard, Jira entegrasyonu, DOORS eşleştirme ve email bildirimini tek bir zincirde birleştirir.

---

## 2. Test Koşum Akışı — Eski vs Yeni

### Eski akış (surefirePlugin-master)

```
mvn test
  └─ ExtentCucumberPlugin → target/extent-report/index.html
                            (tek HTML, FastAPI görmüyor)
```

### Yeni akış (java-test-reports)

```
1. Ayrı projenizde: mvn test
     ├─ AllureCucumber7Jvm  → target/allure-results/*.json
     ├─ VideoHook (ffmpeg)  → target/videos/*.mp4   (sadece fail)
     └─ ScreenshotHook      → allure-results içine embed

2. java-test-reports'ta: java -jar orchestrator/target/orchestrator.jar
     ├─ AllureGenerateStage  → allure-results'ı okur
     ├─ ManifestWriteStage   → manifests/<runId>.json üretir
     ├─ EmailSendStage        → (isteğe bağlı)
     └─ WebDeployStage        → (isteğe bağlı)

3. FastAPI dashboard: manifests/*.json'ı okur → http://localhost:8000
```

> **Kritik nokta:** `mvn test` bittikten sonra orchestrator çalıştırılmazsa FastAPI hiçbir şey görmez. Bu iki adım birbirine bağlıdır.

---

## 3. Ayrı Projenizde Yapılacak Değişiklikler

### 3.1 `pom.xml` — Bağımlılıkları Güncelle

**Kaldırılacaklar:**

```xml
<dependency>
    <groupId>com.aventstack</groupId>
    <artifactId>extentreports</artifactId>
</dependency>
<dependency>
    <groupId>tech.grasshopper</groupId>
    <artifactId>extentreports-cucumber7-adapter</artifactId>
</dependency>
<!-- local jar varsa -->
<dependency>
    <groupId>com.example</groupId>
    <artifactId>scenario-video-logger</artifactId>
</dependency>
```

**Eklenecekler:**

```xml
<dependency>
    <groupId>io.qameta.allure</groupId>
    <artifactId>allure-cucumber7-jvm</artifactId>
    <version>2.25.0</version>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>io.qameta.allure</groupId>
    <artifactId>allure-junit-platform</artifactId>
    <version>2.25.0</version>
    <scope>test</scope>
</dependency>
```

Surefire plugin konfigürasyonu değişmez, olduğu gibi kalır.

---

### 3.2 Java Dosyaları — Silinecekler ve Kopyalanacaklar

**Ayrı projenizden silin:**

```
src/test/java/hooks/ExtentCucumberPlugin.java
src/test/java/hooks/FailureCapturePlugin.java
src/test/java/hooks/DiscoveryPlugin.java
src/test/java/Utils/CaptureScreen.java
src/test/java/CucumberRetryRunnerTest.java
```

**`java-test-reports`'tan kopyalayın → ayrı projenizin `src/test/java/hooks/` altına:**

```
java-test-reports/allure-integration/src/main/java/com/testreports/allure/VideoHook.java
java-test-reports/allure-integration/src/main/java/com/testreports/allure/ScreenshotHook.java
java-test-reports/allure-integration/src/main/java/com/testreports/allure/WebDriverHolder.java
java-test-reports/allure-integration/src/main/java/com/testreports/allure/FailureLocationCapture.java
```

**`java-test-reports`'tan kopyalayın → ayrı projenizin `src/test/java/` altına:**

```
java-test-reports/test-core/src/test/java/com/testreports/runner/RetryTestRunner.java
```

`RetryTestRunner.java` içindeki package ve glue satırlarını kendi proje yapınıza göre güncelleyin:

```java
// Kopyaladıktan sonra bu satırı kendi paketinize göre değiştirin:
private static final String DEFAULT_GLUE = "hooks,stepDefinitions";
```

> Kendi `stepDefinitions/` paketinize dokunmayın. Sadece raporlama katmanı değişiyor.

---

### 3.3 `junit-platform.properties` — Plugin Kaydını Güncelle

**Eskisi:**

```properties
cucumber.plugin=hooks.ExtentCucumberPlugin
cucumber.glue=stepDefinitions,hooks
```

**Yenisi:**

```properties
cucumber.plugin=io.qameta.allure.cucumber7jvm.AllureCucumber7Jvm,\
  hooks.FailureLocationCapture,\
  pretty
cucumber.glue=hooks,stepDefinitions
```

---

### 3.4 `allure.properties` — Oluştur (yoksa)

`src/test/resources/allure.properties` dosyası yoksa oluşturun:

```properties
allure.results.directory=target/allure-results
```

---

### 3.5 WebDriver — Önemli Zorunluluk

`ScreenshotHook` fail anında ekran görüntüsü almak için `WebDriverHolder`'dan driver'ı okur. Bunun çalışması için ayrı projenizde driver oluşturulduğu anda `WebDriverHolder.setDriver(driver)` çağrılmalı, driver kapatıldığında ise `WebDriverHolder.removeDriver()` çağrılmalıdır.

Step definition'larınızdaki driver kurulum bloğuna ekleyin:

```java
// Driver oluştururken:
WebDriver driver = new ChromeDriver();
WebDriverHolder.setDriver(driver);

// @After hook içinde driver kapatırken:
driver.quit();
WebDriverHolder.removeDriver();
```

Şu an `surefirePlugin-master`'da driver `ExtentCucumberPlugin` içinde statik olarak tutuluyordu. Yeni yapıda bu sorumluluğu step definition'larınız üstlenir.

---

## 4. java-test-reports'ta Yapılacak Değişiklik

### 4.1 `scripts/run-by-tags.sh` — Eksik, Oluşturulacak

`scripts/` klasöründe `.bat` ve `.ps1` versiyonları mevcut, ancak Linux bash versiyonu (`run-by-tags.sh`) yok. Bu dosya `surefirePlugin-master/run-by-tag.sh`'den uyarlanarak oluşturulacak ve test koşumundan sonra orchestrator çağrısı eklenecek.

Script şu iki işi yapmalı:

```bash
# 1. Testleri koş (ayrı projede)
mvn test -Dcucumber.filter.tags="$tag" -Dretry.count=$RETRY_COUNT

# 2. Orchestrator ile manifesti üret
java -jar /path/to/orchestrator/target/orchestrator.jar --run-id="$slug-$timestamp"
```

Mevcut `.bat` ve `.ps1` dosyaları da orchestrator çağrısı içermiyor — bu ikisi de güncellenecek.

---

## 5. Orchestrator Komutunu Çalıştırma

Testler bittikten sonra orchestrator'ı elle de çalıştırabilirsiniz.

**Önce bir kez build edin (java-test-reports dizininde):**

```bash
cd java-test-reports
mvn package -pl orchestrator -am -DskipTests
# Çıktı: orchestrator/target/orchestrator.jar
```

**Her test koşumu sonrası:**

```bash
java -jar java-test-reports/orchestrator/target/orchestrator.jar --run-id="benim-kosum-001"
```

Orchestrator varsayılan olarak `target/allure-results` klasörünü okur. Ayrı projenizin çıktısı farklı bir yerdeyse ortam değişkeniyle belirtin:

```bash
export ORCHESTRATOR_ALLURE_RESULTS_DIR=/ayrı-proje/target/allure-results
export ORCHESTRATOR_MANIFEST_DIR=/java-test-reports/manifests
java -jar orchestrator/target/orchestrator.jar --run-id="kosum-001"
```

---

## 6. Günlük Kullanım Sırası

```bash
# 1. FastAPI'yi başlat (java-test-reports dizininde, tek seferlik)
cd java-test-reports/fastapi-server
uvicorn server:app --host 0.0.0.0 --port 8000

# 2. Ayrı projenizde testleri koş
cd ayrı-proje
mvn test -Dcucumber.filter.tags="@smoke" -Dretry.count=2

# 3. Orchestrator ile manifesti üret
java -jar java-test-reports/orchestrator/target/orchestrator.jar --run-id="smoke-$(date +%Y%m%d_%H%M%S)"

# 4. Dashboard'da görüntüle
# http://localhost:8000
```

---

## 7. Kontrol Listesi

| Adım | Değişiklik | Durum |
|------|-----------|-------|
| Ayrı proje `pom.xml` | Extent bağımlılıkları kaldırıldı | ☐ |
| Ayrı proje `pom.xml` | Allure bağımlılıkları eklendi | ☐ |
| Ayrı proje `src/test/java` | Extent hook dosyaları silindi | ☐ |
| Ayrı proje `src/test/java` | VideoHook, ScreenshotHook, WebDriverHolder, FailureLocationCapture kopyalandı | ☐ |
| Ayrı proje `src/test/java` | RetryTestRunner kopyalandı, glue paketi güncellendi | ☐ |
| Ayrı proje `junit-platform.properties` | Allure plugin kaydedildi | ☐ |
| Ayrı proje `allure.properties` | Oluşturuldu | ☐ |
| Ayrı proje step definitions | `WebDriverHolder.setDriver()` ve `removeDriver()` eklendi | ☐ |
| java-test-reports `scripts/` | `run-by-tags.sh` oluşturuldu | ☐ |
| java-test-reports `scripts/` | `.bat` ve `.ps1` orchestrator çağrısıyla güncellendi | ☐ |
| java-test-reports `orchestrator` | `mvn package` ile `orchestrator.jar` build edildi | ☐ |
| Doğrulama | `mvn test` → allure-results oluştu | ☐ |
| Doğrulama | Orchestrator → `manifests/*.json` oluştu | ☐ |
| Doğrulama | FastAPI dashboard'da run görünüyor | ☐ |
| Doğrulama | Fail senaryoda screenshot var | ☐ |
| Doğrulama | Fail senaryoda video var | ☐ |
| Doğrulama | Retry ve `@id/@dep` davranışı korundu | ☐ |
