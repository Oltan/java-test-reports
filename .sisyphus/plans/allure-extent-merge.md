# Allure + ExtentReports Birleştirme Planı

## TL;DR

> **Quick Summary**: surefirePlugin'ün retry, @id/@dep bağımlılık, tag-bazlı koşum özelliklerini mevcut Allure tabanlı sisteme taşı. Windows-native çalışacak şekilde düzenle. Hybrid raporlama (Allure ana + ExtentReports opsiyonel).
>
> **Deliverables**:
> - Retry mekanizması (file-based state, konfigure edilebilir retry count)
> - @id/@dep senaryo bağımlılık yönetimi
> - Tag bazlı koşum script'i (Windows .bat + PowerShell)
> - Failure location capture (feature:line)
> - Windows-native kurulum (WSL gerekmez)
> - Kapsamlı geçiş rehberi
>
> **Estimated Effort**: Medium (~3 gün)
> **Parallel Execution**: YES — 3 waves, 4-5 task/wave

---

## 1. Vizyon

İki sistemin en iyi özelliklerini birleştirip Windows'ta tek komutla çalışan entegre bir sistem:

```
Cucumber Feature Dosyaları
    │
    ├── @id:Login @dep:Setup  (senaryo bağımlılığı)
    │
    ▼
CucumberRetryRunner (retry + dependency graph)
    │
    ├── Attempt 1 → FAIL
    ├── Attempt 2 → FAIL  
    ├── Attempt 3 → PASS ✅
    │
    ▼
Allure Results (JSON) + ExtentReports (HTML, opsiyonel)
    │
    ▼
FastAPI Dashboard → Jira Bug → DOORS DXL → Email
```

## 2. Teknik Kararlar

| Karar | Seçim | Gerekçe |
|-------|-------|---------|
| **Retry** | 🔴 **#1 ÖNCELİK** — surefirePlugin Core | Senaryo bazlı, file-based state, example-row level. Maven'in `rerunFailingTestsCount`'u YETERSİZ (class-level, state yok) |
| **Bağımlılık** | 🔴 **#2 ÖNCELİK** — @id/@dep | En çok kullanılan özellik. Toposort + SKIP mekanizması |
| **Tag Runner** | 🔴 **#3 ÖNCELİK** — run-by-tag | Çalıştırma altyapısı. Tag bazlı paralel koşum |
| **Ana rapor** | Allure (üst katman) | Modern UI, ama retry/dependency çalıştığı sürece. Çakışırsa ExtentReports kalır |
| **ExtentReports** | Opsiyonel değil — **birlikte çalışacak** | Hybrid: retry+dependency ExtentReports'ta, görselleştirme Allure'da |
| **Video** | Opsiyonel (ffmpeg varsa) | Disk tasarrufu, graceful skip |
| **Windows** | Python embeddable + .bat | WSL gerekmez, tek tıkla |
| **Build** | Maven (değişmedi) | Mevcut altyapı |

### ⚠️ Kritik: Allure Retry ile Çakışırsa

Allure CucumberJVM adapter her test run'ında yeni sonuç JSON'u oluşturur. Retry sırasında:
- Attempt 1 fail → Allure JSON (status: failed)
- Attempt 2 retry → Allure JSON (status: passed) ← aynı senaryo için 2. JSON

**Çözüm**: Retry runner, Allure results'ları attempt bazında gruplandırır. Dashboard "Attempt 2/3 → PASS" gösterir. Eğer bu çalışmazsa → **Allure'dan vazgeç, ExtentReports + custom plugin devam.**

## 3. İş Paketleri

### 🎯 Öncelik Sıralaması (Değişti!)

| # | Özellik | Eğer Allure ile çakışırsa |
|---|---------|--------------------------|
| 1 | **Retry** | Allure gider, ExtentReports kalır |
| 2 | **@id/@dep** | Allure gider, ExtentReports kalır |
| 3 | **Tag runner** | Bağımsız çalışır (Maven CLI) |
| 4 | Allure görselleştirme | Nice-to-have, ama yukarıdakiler çalışıyorsa |

### Tag Kullanımı

Evet, tag kullanmaya devam edeceğiz. surefirePlugin'teki sistem aynen korunur:

```gherkin
@Deneme @Smoke @Regression
@id:Login @dep:Setup,DatabaseCheck
Scenario: Kullanıcı girişi
```

- `@Deneme`, `@Smoke` → tag runner ile filtrelenir
- `@id:Login` → dependency graph'te benzersiz kimlik
- `@dep:Setup,DatabaseCheck` → bunlar PASS olmadan bu senaryo koşulmaz
- **Tüm tag'ler Allure'a da label olarak eklenir** (çakışma yok)

### Wave 1: Retry + Bağımlılık (Java, paralel 3 task)

#### Task 1.1: RetryRunner — test-core'a taşı

surefirePlugin'teki `CucumberRetryRunnerTest.java`'i al, `test-core/` modülüne `RetryTestRunner.java` olarak taşı.

- [x] `com.testreports.runner.RetryTestRunner.java`
- [x] Retry mekanizması: `--retry-count N` parametresi
- [x] File-based state: `target/retry-state/` altında senaryo durumu
- [x] RetryDemoSteps benzeri test adımları
- [x] pytest: retry logic testleri

**Süre**: 3 saat  
**Bağımlılık**: Yok

#### Task 1.2: DependencyGraph — @id/@dep sistemi

surefirePlugin'teki dependency graph + toposort'u `test-core/` modülüne taşı.

- [x] `com.testreports.runner.DependencyResolver.java`
- [x] `@id:` ve `@dep:` tag parser
- [x] Topolojik sıralama (Kahn's algorithm)
- [x] Bağımlılık PASS değilse SKIP
- [x] Test feature dosyasında örnek `@id:` / `@dep:` kullanımı

**Süre**: 3 saat  
**Bağımlılık**: Yok

#### Task 1.3: FailureCapture — feature:line konum yakalama

surefirePlugin'teki `FailureCapturePlugin.java`'i `allure-integration/` modülüne taşı.

- [x] `com.testreports.allure.FailureLocationCapture.java`
- [x] Fail olan her senaryo için `feature:line` kaydı
- [x] Allure JSON'a label olarak ekleme
- [x] Dashboard'da "Kaynak: login.feature:42" şeklinde gösterim

**Süre**: 2 saat  
**Bağımlılık**: Yok

---

### Wave 2: Script + Dashboard (paralel 3 task)

#### Task 2.1: Tag Runner Script (Windows)

surefirePlugin'teki `run-by-tag.sh`'i Windows'a uyarla.

- [x] `scripts/run-by-tag.bat` (Windows batch)
- [x] `scripts/run-by-tag.ps1` (PowerShell)
- [x] `features.txt` formatı aynı
- [x] `--retry-count`, `--continue-on-fail`, `--dry-run` flag'leri
- [x] Her tag için ayrı timing + özet

**Süre**: 2 saat  
**Bağımlılık**: Task 1.1

#### Task 2.2: Dashboard — retry + dependency gösterimi

FastAPI dashboard'una retry ve dependency bilgilerini ekle.

- [x] `templates/scenario-detail.html`: retry count, attempt history
- [x] `templates/dashboard.html`: dependency graph görselleştirme (opsiyonel)
- [x] API: `GET /api/v1/runs/{id}/dependencies` endpoint
- [x] Test: pytest ile yeni endpoint'ler

**Süre**: 3 saat  
**Bağımlılık**: Task 1.1, 1.2

#### Task 2.3: Windows Native Kurulum

WSL gerekmeden Windows'ta çalışacak paket.

- [x] Python embeddable package (`.zip`, portable)
- [x] `start-server.bat` güncelleme (Windows path'ler)
- [x] `.env.example` Windows path formatı
- [x] Allure CLI Windows path
- [x] Maven wrapper (`mvnw.bat`) ekleme
- [x] Tek tıkla kurulum: `setup.bat`

**Süre**: 3 saat  
**Bağımlılık**: Yok

---

### Wave 3: Geçiş Rehberi + Final (paralel 2 task)

#### Task 3.1: Geçiş Rehberi

ExtentReports'tan Allure'a geçiş için kapsamlı rehber.

- [x] `GECIS_REHBERI.md`:
  - Neden Allure? (karşılaştırma tablosu)
  - Mevcut ExtentReports projesine Allure ekleme (adım adım)
  - surefirePlugin özelliklerini taşıma
  - ExtentReports'u tamamen kaldırma (opsiyonel)
  - Hybrid kullanım (ikisi birden)
  - Sık sorulan sorular
  - Önce/sonra ekran görüntüleri

**Süre**: 2 saat  
**Bağımlılık**: Yok

#### Task 3.2: Final QA + Test

Tüm sistemin Windows'ta uçtan uca testi.

- [x] `mvn clean test` (tüm modüller)
- [x] `pytest fastapi-server/tests/ -v`
- [x] `scripts/run-by-tag.bat` test
- [x] Dashboard screenshot (Playwright)
- [x] Performance: dashboard yüklenme < 1s
- [x] Allure report + ExtentReports report karşılaştırma

**Süre**: 2 saat  
**Bağımlılık**: Tüm Wave 1 + 2

---

## 4. Bağımlılık Grafiği

```
Wave 1 (Paralel):
  Task 1.1 (Retry) ──────────────┐
  Task 1.2 (Dependency) ─────────┤
  Task 1.3 (FailureCapture) ─────┤
                                  │
Wave 2 (Paralel):                 │
  Task 2.1 (Tag Runner) ◄────────┘ (Task 1.1)
  Task 2.2 (Dashboard)  ◄────────┘ (Task 1.1 + 1.2)
  Task 2.3 (Windows) ──────────── (bağımsız)
                                  │
Wave 3 (Paralel):                 │
  Task 3.1 (Rehber) ───────────── (bağımsız)
  Task 3.2 (QA)      ◄───────────┘ (tüm Wave 1 + 2)
```

## 5. Windows Mimarisi

```
C:\test-reports\
├── setup.bat              # Tek tıkla kurulum
├── start-server.bat       # Sunucu başlat
├── run-tests.bat          # Testleri koş
├── python\                # Python embeddable (portable)
├── mvnw.bat               # Maven wrapper
├── java\                  # Java (sistemde varsa gerekmez)
└── ... (proje dosyaları)
```

## 6. Commit Planı

```
feat(retry): port retry runner + file-based state from surefirePlugin
feat(dependency): @id/@dep dependency graph + toposort resolver
feat(failure): FailureCapturePlugin → Allure label integration
feat(scripts): Windows tag-based test runner (.bat + .ps1)
feat(dashboard): retry history + dependency info in scenario detail
feat(windows): portable Python, mvnw, one-click setup.bat
docs: ExtentReports→Allure geçiş rehberi
test(qa): full Windows end-to-end verification
```

## 7. Kabul Kriterleri

- [x] Retry: `mvn test -Dretry.count=3` ile 3 deneme yapar
- [x] Dependency: `@id:A @dep:B` ile B PASS değilse A SKIP
- [x] Failure: Allure JSON'da `feature:line` label'ı var
- [x] Tag runner: `run-by-tag.bat` Windows'ta çalışır
- [x] Dashboard: scenario detail'de "Attempt 2/3" gösterir
- [x] Windows: `setup.bat` ile tek tıkla kurulum
- [x] Geçiş rehberi: adım adım takip edilebilir
- [x] Tüm mevcut testler bozulmaz
