# surefirePlugin-master — Cucumber + ExtentReports Plugin

Ayrı bir Maven projesi. Parent POM'da module listesinde YOK. Kendi başına `mvn test` ile çalışır.

## OVERVIEW

Cucumber 7 + JUnit 5 + ExtentReports 5.1.2 tabanlı test raporlama eklentisi. Retry mekanizması, `@id`/`@dep` senaryo bağımlılık yönetimi, ExtentReports merge tool, ffmpeg video kaydı içerir.

## STRUCTURE

```
surefirePlugin-master/
├── pom.xml                          # Maven (Cucumber 7.14, Selenium 4.35, ExtentReports 5.1.2)
├── run-by-tag.sh / run-by-tags.ps1  # Tag bazlı test koşum scriptleri
├── features.txt                     # Koşulacak tag listesi
├── ExtentMergeTool.jar              # Rapor birleştirme aracı
├── libs/scenario-video-logger.jar   # Video kayıt kütüphanesi
└── src/test/
    ├── java/
    │   ├── CucumberRetryRunnerTest.java   # Ana runner: retry, dependency graph, toposort
    │   ├── ExtentReportMerger.java         # JSoup ile 2 ExtentReports HTML'i birleştirir
    │   ├── hooks/
    │   │   ├── ExtentCucumberPlugin.java   # Core plugin: WebDriver, screenshot, video, retry
    │   │   ├── FailureCapturePlugin.java   # Fail olan testlerin feature:line konumlarını yakalar
    │   │   └── DiscoveryPlugin.java        # --dry-run ile senaryo keşfi
    │   ├── stepDefinitions/
    │   │   ├── StepDefinitions.java        # Login adımları
    │   │   └── RetryDemoSteps.java        # Retry-aware flaky test adımları
    │   └── Utils/CaptureScreen.java        # Selenium screenshot (BASE64 + file)
    └── resources/
        ├── features/sample.feature         # @Deneme, @id:, @dep:, Scenario Outline
        ├── features/anotherSample.feature  # @İmamBayıldı tag
        ├── junit-platform.properties       # cucumber.plugin=hooks.ExtentCucumberPlugin
        └── extent.properties               # extent.reporter.spark.start=true
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Test koşma | `CucumberRetryRunnerTest.java` | JUnit Suite runner, `--retry-count` parametresi |
| Rapor hook'u | `hooks/ExtentCucumberPlugin.java` | 546 satır, WebDriver yönetimi, screenshot, video embed |
| Fail yakalama | `hooks/FailureCapturePlugin.java` | Scenario Outline example-level retry için |
| Senaryo keşfi | `hooks/DiscoveryPlugin.java` | `--dry-run` + tag filter ile |
| Rapor birleştirme | `ExtentReportMerger.java` | Swing GUI, main+rerun HTML'leri JSoup ile birleştirir |
| Screenshot | `Utils/CaptureScreen.java` | BASE64 (ExtentReports embed) veya file |
| Flaky test | `RetryDemoSteps.java` | `target/flaky-state/` dosya tabanlı state |

## KEY PATTERNS

### Senaryo Bağımlılık Yönetimi

```gherkin
@id:Login @dep:OneTimeFlake
Scenario Outline: Login with different users
```

- `@id:UniqueId` — her senaryoya benzersiz kimlik
- `@dep:IdA,IdB` — virgülle ayrılmış bağımlılık ID'leri
- Runner toposort ile bağımlılık sıralaması yapar
- Bağımlılık PASS değilse senaryo SKIP

### Retry Mekanizması

- `--retry-count N` ile maks deneme sayısı
- Fail olan senaryolar tekrar koşulur
- Rerun raporu ayrı HTML olarak çıkar
- `ExtentReportMerger` ile main+rerun birleştirilir

### Tag Bazlı Koşum

```bash
./run-by-tag.sh --retry-count 2 --continue-on-fail
# features.txt içindeki her tag için ayrı ayrı test koşar
# --dry-run: sadece keşif, koşma
# --single-file: her tag için ayrı rapor dosyası
```

## COMMANDS

```bash
# Tek tag ile koş
mvn test -Dcucumber.filter.tags="@Deneme"

# Retry ile koş
mvn test -Dcucumber.filter.tags="@Deneme" -Dretry.count=2

# Tüm tag'leri koş
./run-by-tag.sh

# Rapor birleştir (GUI)
java -cp target/classes:target/dependency/* ExtentReportMerger
```

## NOTES

- WebDriver: ChromeDriver, WebDriverManager ile otomatik indirme
- Video: `libs/scenario-video-logger.jar` kullanır, `video.output.dir` system property ile configure
- Background_ prefix'li senaryolar rapora EKLENMEZ
- Surefire plugin `forkedProcessExitTimeoutInSeconds=5` — zombie process koruması
