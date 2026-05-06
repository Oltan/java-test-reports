# allure-integration Modül Analizi

## Nedir?

Cucumber + Selenium + Allure entegrasyonu için 4 adet hook/plugin sınıfı:

| Sınıf | Satır | Görevi |
|-------|-------|--------|
| `ScreenshotHook.java` | 39 | `@After` — test fail olduğunda WebDriver'dan screenshot alıp Allure'a ekler |
| `VideoHook.java` | 135 | `@Before`/`@After` — ffmpeg ile video kaydı başlatır, fail'de Allure'a ekler, pass'te siler |
| `WebDriverHolder.java` | 28 | `ThreadLocal<WebDriver>` — hook'lar ile step definition'lar arasında driver paylaşımı |
| `FailureLocationCapture.java` | 42 | Cucumber plugin — fail olan testin feature:satır konumunu Allure label olarak ekler |

**Hiçbiri test-core'daki sınıfları import etmez.** Tamamen bağımsız, generic hook'lardır.

## test-core ile Bağlantısı

İki noktada bağlanır:

```java
// 1. LoginSteps.java line 25 — WebDriver'ı hook'lara bildirir
WebDriverHolder.setDriver(driver);

// 2. CucumberTestRunner.java line 17 — Cucumber'ın hook'ları bulması için
@Suite
@IncludeEngines("cucumber")
@ConfigurationParameter(key = GLUE_PROPERTY_NAME, value = "com.testreports.allure, com.testreports.steps")
```

Cucumber, glue path'teki `com.testreports.allure` package'ını classpath tarar ve `@Before`/`@After` annotation'lı sınıfları otomatik keşfeder. Bu standart Cucumber mekanizmasıdır — özel bir coupling yoktur.

## Diğer Projeye Aktarılabilir mi?

**Evet, iki yolu var:**

### Yol 1: Maven dependency (teorik)
```xml
<dependency>
    <groupId>com.testreports</groupId>
    <artifactId>allure-integration</artifactId>
    <version>1.0.0-SNAPSHOT</version>
</dependency>
```
**Ama çalışmaz.** Çünkü `allure-integration` hiçbir Maven repository'ye deploy edilmiyor. Parent POM'da `distributionManagement`, `maven-deploy-plugin` veya `maven-install-plugin` konfigürasyonu **yok**. Sadece local `mvn install` ile `~/.m2`'ye düşer — başka bir makinede çözülmez.

### Yol 2: Kaynak dosyaları kopyala (pratikte tek çalışan yol)
```
kaynak: allure-integration/src/main/java/com/testreports/allure/
  ├── ScreenshotHook.java      → hedef/src/test/java/com/testreports/allure/
  ├── VideoHook.java           → hedef/src/test/java/com/testreports/allure/
  ├── WebDriverHolder.java     → hedef/src/test/java/com/testreports/allure/
  └── FailureLocationCapture.java → hedef/src/test/java/com/testreports/allure/
```

GECIS_REHBERI.md, test_calistirma_rehberi.md ve ENTEGRASYON_REHBERI.md bu kopyalama yolunu dokümante ediyor.

## Karar: Merge mi, Ayrı Modül mü?

| Kriter | Ayrı Modül | test-core'a Merge |
|--------|-----------|-------------------|
| **Yayınlanabilir mi?** | ❌ Maven repo yok, dağıtılamaz | ✅ Zaten test-core'dayken çalışıyor |
| **Başka proje kullanabilir mi?** | ❌ Yayınlanmadığı için Maven'den çekilemez | ✅ Kaynak dosyaları kopyalanabilir (şu anki tek yol zaten bu) |
| **Proje yapısı** | 2 Maven modülü | 1 Maven modülü (daha sade) |
| **Build süresi** | 2 ayrı JAR derlenir | Tek JAR, daha hızlı |
| **Kod organizasyonu** | Hook'lar ayrı package | `test-core/src/test/java/com/testreports/allure/` altında |

### Öneri: **Merge et.**

**Neden:**
1. Ayrı modül olmanın tek avantajı (Maven'dan dependency olarak çekilebilme) şu anda çalışmıyor
2. Diğer projelere aktarımın tek gerçek yolu **kaynak dosya kopyalama** — merge olsa da olmasa da aynı
3. Proje zaten 7 dosya test-core + 7 dosya allure-integration = gereksiz bölünmüş

### Merge sonrası yapı:
```
test-core/src/test/java/com/testreports/
├── allure/                    ← buraya taşınacak
│   ├── ScreenshotHook.java
│   ├── VideoHook.java
│   ├── WebDriverHolder.java
│   └── FailureLocationCapture.java
├── runner/
│   ├── CucumberTestRunner.java
│   ├── RetryTestRunner.java
│   └── DependencyResolver.java
├── steps/
│   ├── LoginSteps.java
│   └── RetryDemoSteps.java
└── config/
    └── WebDriverFactory.java
```

Değişecek tek şey: `test-core/pom.xml`'deki `allure-integration` dependency'si kalkacak (sınıflar zaten aynı modülde). `pom.xml` parent'tan `allure-integration` modülü kalkacak.

## Sonuç

`allure-integration` işlevsel olarak **her zaman test-core'un bir parçasıydı**. Ayrı Maven modülü olması kağıt üzerinde "reusable library" niyeti taşısa da, Maven publishing altyapısı kurulmadığı için bu niyet gerçekleşmemiş. Diğer projelere aktarım **zaten kaynak dosya kopyalamayla** yapılıyor — merge bu akışı hiç değiştirmez.
