# TEST MİMARİSİ — Onarım Ajanının Mimari Çapası

Bu doküman her `/api/repair` isteğinde LLM'e **olduğu gibi** gönderilir; ajanın
projenin özel sınıf yapısını anlamasının birincil kaynağıdır. **Sınıf yapısı
değiştiğinde bu dosya da güncellenmelidir** (aksi halde ajan eski mimariye göre
yama önerir).

## Modüller

- `test-core/` — Maven test modülü (Java 21, JUnit 5 + Cucumber + Selenium + Allure)
- Koşum komutu: `mvn -pl test-core test -Dcucumber.filter.tags=...`
  (sunucu bunu `/api/tests/start` üzerinden per-run izole dizinlerle çağırır)

## Sınıf yapısı (test-core/src/test/java/com/testreports)

### `config/` — sürücü fabrikası
- **`WebDriverFactory`** — TEK WebDriver üretim noktası. System property'lerden
  okur: `browser` (chrome|firefox|edge), `browser.headless` (default true),
  `browser.binary`, `webdriver.chrome.driver`. Driver çözümü Selenium Manager'a
  bırakılır; **koda yol/binary hardcode edilmez** (proje anti-pattern'i).
  Selenium hatalarında ilk bakılacak yer burasıdır.

### `allure/` — hook'lar ve rapor entegrasyonu
- **`WebDriverHolder`** — statik driver taşıyıcı; step'ler driver'ı buraya koyar
  (`setDriver`), hook'lar buradan alır (`getDriver`). Driver'ı hook'lara taşımanın
  tek yolu budur.
- **`ScreenshotHook`** — `@After(order=100)`: senaryo FAILED ise Holder'daki
  driver'dan ekran görüntüsü alıp Allure'a ekler; driver null ise sessiz geçer.
- **`VideoHook`** — ffmpeg x11grab ile video; `-Dvideo.dir`, `-Dvideo.display`,
  `-Dvideo.size` property'leri. Linux dışında/ffmpeg yoksa graceful skip.
- **`FailureLocationCapture`** — failure'ın feature dosyası/satırını Allure'a yazar.

### `runner/` — koşum ve bağımlılık motoru
- **`CucumberTestRunner`** — JUnit Platform suite girişi; feature'lar
  `src/test/resources/features/` altından koşar.
- **`DependencyResolver`** — `@id:X` / `@dep:X,Y` tag'lerinden topolojik sıra
  üretir; bağımlılığı düşen senaryoyu atlatır. Döngü = hata.
- **`RetryTestRunner`** — düşen senaryoları yeniden koşar; deduplication
  DependencyResolver'a delegedir. Retry durumu `-Dretry.state.dir` altında
  dosyayla taşınır (senaryo adı slug'ı .txt).

### `steps/` — step definition'lar
- Cucumber anotasyonlu sınıflar (`io.cucumber.java.en.*`). Desen:
  - Selenium step'leri driver'ı `WebDriverFactory.createDriver()` ile alır ve
    `WebDriverHolder.setDriver(...)` ile hook'lara kaydeder (bkz. `LoginSteps`).
  - Tarayıcısız birim step'leri düz Java assert'leriyle çalışır (bkz. `UnitDemoSteps`).
  - Senaryo durumu step sınıfı alanlarında taşınır (Cucumber her senaryoda yeni instance üretir).

## Feature/tag sözleşmesi (lint ile zorlanır)

- Her senaryoda tam 1 `@DOORS-nnnnn` (repo genelinde tekil)
- `@id:`/`@dep:` bağımlılık grameri; `@sample-fail` = bilerek düşen demo
- Tarayıcısız feature'lar `@UnitDemo` gibi grup tag'i taşır
- Ayrıntı: `docs/OTOMASYON_KURALLARI.md` §1

## pom.xml notları (bağlamda salt-okunur gönderilir)

- Kök `pom.xml`: parent; `test-core/pom.xml`: surefire `systemPropertyVariables`
  ile `allure.results.directory`, `video.dir`, `retry.state.dir` per-run geçer.
- **pom değişikliği onarım ajanının yetkisinde DEĞİLDİR** — bağımlılık/plugin
  sorunu tespit edilirse ajan `needs_human` yanıtı verir, insana devreder.

## Onarım ajanı için yol haritası

1. Hata `org.openqa.selenium.*` (SessionNotCreated, NoSuchElement, Timeout…) ise:
   stack trace'teki proje sınıfına bak (çoğunlukla `WebDriverFactory` veya ilgili
   step sınıfı); locator/bekleme sorunlarında step dosyasını düzelt.
2. Hata `AssertionFailedError` ise: beklenen değer test-verisi hatası olmadıkça
   assertion'ı DEĞİŞTİRME — bug akışına bırak.
3. Hata derleme/bağımlılık kaynaklıysa (pom, sürüm çakışması): `needs_human`.
4. Yama yalnız `test-core/src/test/**` altına yazılabilir (kod seviyesinde zorlanır).
