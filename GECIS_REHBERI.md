# java-test-reports Kullanım Rehberi

Bu rehber, `java-test-reports` raporlama sisteminin nasıl kullanılacağını kapsar.

---

## 1. Sistem Genel Bakış

`java-test-reports` sistemi: Allure, JSON manifest, FastAPI dashboard, Jira entegrasyonu, DOORS eşleştirme ve email bildirimini tek bir zincirde birleştirir.

---

## 2. Test Koşum Akışı

```
1. Test koşumu: mvn test
     ├─ AllureCucumber7Jvm  → target/allure-results/*.json
     ├─ VideoHook (ffmpeg)  → target/videos/*.mp4   (sadece fail)
     └─ ScreenshotHook      → allure-results içine embed

2. FastAPI dashboard: manifests/*.json'ı okur → http://localhost:8000
```

---

## 3. Test Projenizde Yapılacak Değişiklikler

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

---

### 3.2 Java Dosyaları — Hook Dosyaları

**Silinecekler:**

```
src/test/java/hooks/ExtentCucumberPlugin.java
src/test/java/hooks/FailureCapturePlugin.java
src/test/java/hooks/DiscoveryPlugin.java
src/test/java/Utils/CaptureScreen.java
src/test/java/CucumberRetryRunnerTest.java
```

**Ekleneckler:**

```
java-test-reports/allure-integration/src/main/java/com/testreports/allure/VideoHook.java
java-test-reports/allure-integration/src/main/java/com/testreports/allure/ScreenshotHook.java
java-test-reports/allure-integration/src/main/java/com/testreports/allure/WebDriverHolder.java
java-test-reports/allure-integration/src/main/java/com/testreports/allure/FailureLocationCapture.java
```

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

`ScreenshotHook` fail anında ekran görüntüsü almak için `WebDriverHolder`'dan driver'ı okur. Step definition'larınızdaki driver kurulum bloğuna ekleyin:

```java
// Driver oluştururken:
WebDriver driver = new ChromeDriver();
WebDriverHolder.setDriver(driver);

// @After hook içinde driver kapatırken:
driver.quit();
WebDriverHolder.removeDriver();
```

---

## 4. Günlük Kullanım Sırası

```bash
# 1. FastAPI'yi başlat
cd fastapi-server
uvicorn server:app --host 0.0.0.0 --port 8000

# 2. Testleri koş
cd ayrı-proje
mvn test -Dcucumber.filter.tags="@smoke"

# 3. Dashboard'da görüntüle
# http://localhost:8000
```

---

## 5. Kontrol Listesi

| Adım | Değişiklik | Durum |
|------|-----------|-------|
| Test projesi `pom.xml` | Extent bağımlılıkları kaldırıldı | ☐ |
| Test projesi `pom.xml` | Allure bağımlılıkları eklendi | ☐ |
| Test projesi `src/test/java` | Extent hook dosyaları silindi | ☐ |
| Test projesi `src/test/java` | VideoHook, ScreenshotHook, WebDriverHolder, FailureLocationCapture eklendi | ☐ |
| Test projesi `junit-platform.properties` | Allure plugin kaydedildi | ☐ |
| Test projesi `allure.properties` | Oluşturuldu | ☐ |
| Test projesi step definitions | `WebDriverHolder.setDriver()` ve `removeDriver()` eklendi | ☐ |
| Doğrulama | `mvn test` → allure-results oluştu | ☐ |
| Doğrulama | FastAPI dashboard'da run görünüyor | ☐ |
| Doğrulama | Fail senaryoda screenshot var | ☐ |
| Doğrulama | Fail senaryoda video var | ☐ |